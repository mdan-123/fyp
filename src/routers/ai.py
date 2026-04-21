"""
AI routes: parse, feedback, history, daily-digest.
"""
import json
import re
import datetime as dt
from datetime import timezone
from typing import Optional

import pytz
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from firebase_admin import firestore

import dependencies as deps
from dependencies import (
    verify_firebase_token,
    get_user_timezone,
    _load_aliases,
    _expand_aliases,
    _detect_teach_phrase,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AIParseRequest(BaseModel):
    text: str
    user_id: str
    timezone: str = "UTC"
    intent_override: Optional[str] = None
    entity_overrides: Optional[dict] = None


class FeedbackRequest(BaseModel):
    interaction_id: str
    prompt: str
    response: str
    rating: str
    source: str = ""
    intents: list = []
    entities: dict = {}


class DigestRequest(BaseModel):
    user_id: str
    local_date: str
    timezone: str = "Europe/London"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _save_chat_message(user_id: str, role: str, content: str, source: str = "unknown"):
    try:
        deps.db.collection("users").document(user_id).collection("chat_history").add({
            "role": role,
            "text": content,
            "source": source,
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        print(f"[ChatHistory] Failed to save message: {e}")


def _get_chat_history_string(user_id: str, limit: int = 12) -> str:
    try:
        docs = (
            deps.db.collection("users").document(user_id).collection("chat_history")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        lines = []
        for doc in docs:
            d = doc.to_dict()
            role = d.get("role", "unknown").capitalize()
            content = d.get("text") or d.get("content") or ""
            lines.append(f"[{role}]: {content}")
        lines.reverse()
        return "\n".join(lines)
    except Exception as e:
        print(f"[ChatHistory] Failed to fetch: {e}")
        return ""


def _build_assistant_message(results: list, original_text: str) -> str:
    for r in results:
        status = r.get("status")
        if status == "success":
            msg = r.get("result", {})
            if isinstance(msg, dict):
                return msg.get("message", "Done.")
            return str(msg)
        if status == "chat_response":
            return str(r.get("result", ""))
        if status == "clarification_needed":
            return r.get("message", "I need a bit more information.")
        if status == "error":
            return r.get("error", "Something went wrong.")
    return "Request processed."


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/ai/parse")
async def parse_event_with_ai(
    req: AIParseRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        now_iso = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        user_tz = get_user_timezone(req.user_id)

        events_ref = deps.db.collection("users").document(req.user_id).collection("raw_events")
        tasks_ref = deps.db.collection("users").document(req.user_id).collection("raw_tasks")

        chat_history_str = _get_chat_history_string(req.user_id)
        aliases = _load_aliases(req.user_id)
        teach = _detect_teach_phrase(req.text)

        if teach:
            alias, full_form = teach
            vocab_ref = (
                deps.db.collection("users")
                .document(req.user_id)
                .collection("vocabulary")
                .document("aliases")
            )
            vocab_ref.set({"aliases": {alias: full_form}}, merge=True)
            reply = f"Got it — I'll treat '{alias}' as '{full_form}' from now on."
            _save_chat_message(req.user_id, role="assistant", content=reply, source="vocabulary")
            return {"status": "success", "type": "chat", "message": reply}

        expanded_text = _expand_aliases(req.text, aliases)
        if expanded_text != req.text:
            print(f"[AliasExpander] Expanded: '{req.text}' → '{expanded_text}'")

        _save_chat_message(req.user_id, role="user", content=expanded_text, source="user_input")

        _WEEKDAY_MAP = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        _from_day_match = re.search(
            r'\b(?:move|reschedule|shift|cancel)\b.*?\bfrom\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow)\b',
            expanded_text.lower()
        )

        context_string = "--- UPCOMING EVENTS ---\n"
        event_count = 0

        if _from_day_match:
            _day_str = _from_day_match.group(1)
            _now_local = dt.datetime.now(user_tz)
            if _day_str == "today":
                _local_midnight = _now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            elif _day_str == "tomorrow":
                _local_midnight = (_now_local + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                _target_wday = _WEEKDAY_MAP[_day_str]
                _days_until = (_target_wday - _now_local.weekday()) % 7
                if _days_until == 0:
                    _days_until = 7
                _local_midnight = (_now_local + dt.timedelta(days=_days_until)).replace(hour=0, minute=0, second=0, microsecond=0)
            _utc_window_start = _local_midnight.astimezone(dt.timezone.utc)
            _utc_window_end = _utc_window_start + dt.timedelta(hours=24)
            _w_start_iso = _utc_window_start.isoformat().replace("+00:00", "Z")
            _w_end_iso = _utc_window_end.isoformat().replace("+00:00", "Z")
            _day_docs = events_ref.where("start", ">=", _w_start_iso).stream()
            for doc in _day_docs:
                data = doc.to_dict()
                if data.get("start", "") < _w_end_iso:
                    context_string += f"- {data.get('title', 'Untitled')} (Starts: {data.get('start', '')}, Ends: {data.get('end', '?')})\n"
                    event_count += 1
        else:
            for doc in events_ref.where("end", ">=", now_iso).limit(30).stream():
                data = doc.to_dict()
                context_string += f"- {data.get('title', 'Untitled')} (Starts: {data.get('start', '?')}, Ends: {data.get('end', '?')})\n"
                event_count += 1

        if event_count == 0:
            context_string += "User has no upcoming events.\n"

        context_string += "\n--- PENDING TASKS ---\n"
        task_count = 0
        for doc in tasks_ref.where("status", "==", "pending").limit(30).stream():
            data = doc.to_dict()
            context_string += f"- {data.get('title', 'Untitled')} (Due: {data.get('due_date', 'No due date')})\n"
            task_count += 1
        if task_count == 0:
            context_string += "User has no pending tasks.\n"

        if req.intent_override and req.entity_overrides is not None:
            routing_result = {
                "source": "user_confirmed",
                "intents": [req.intent_override],
                "entities": req.entity_overrides,
                "text": expanded_text,
                "chat_response": "",
            }
        else:
            routing_result = deps.routing_engine.evaluate(
                expanded_text,
                user_context=context_string,
                chat_history=chat_history_str,
                user_timezone=str(user_tz),
            )

        if routing_result.get("chat_response"):
            reply = routing_result["chat_response"]
            _save_chat_message(req.user_id, role="assistant", content=reply, source="LLM_chat")
            return {"status": "success", "type": "chat", "message": reply}

        if routing_result.get("intents"):
            dispatch_results = deps.routing_engine.dispatch(
                nlu_result=routing_result,
                user_id=req.user_id,
                intent_handlers=deps.db_engine.get_intent_map(),
            )
            clarification_items = [r for r in dispatch_results if r.get("status") == "clarification_needed"]
            if clarification_items:
                cl = clarification_items[0]
                cl_type = cl.get("clarification_type")
                if cl_type == "ambiguous_match":
                    clarification_msg = cl.get("message", "I found multiple matches. Which did you mean?")
                elif cl_type == "slot_conflict":
                    clarification_msg = cl.get("message", "That time slot is already booked.")
                else:
                    clarification_msg = cl.get("message", "I need more information.")
                _save_chat_message(req.user_id, role="assistant", content=clarification_msg, source="clarification")
                return {
                    "status": "clarification_needed",
                    "type": "clarification",
                    "clarification_type": cl_type,
                    "message": clarification_msg,
                    "candidates": [
                        {
                            "id": c.get("id", ""),
                            "title": c.get("title", ""),
                            "start": c.get("start", ""),
                            "end": c.get("end", ""),
                            "location": c.get("location", ""),
                            "description": c.get("description", ""),
                            "due_date": c.get("due_date", ""),
                            "status": c.get("status", ""),
                        }
                        for c in cl.get("candidates", [])
                    ],
                    "query": cl.get("query", ""),
                    "entity_key": cl.get("entity_key", "events"),
                    "requested_start": cl.get("requested_start"),
                    "requested_end": cl.get("requested_end"),
                    "suggested_start": cl.get("suggested_start"),
                    "suggested_end": cl.get("suggested_end"),
                    "title": cl.get("title"),
                    "original_intent": cl.get("intent"),
                    "original_entities": routing_result.get("entities", {}),
                    "original_text": expanded_text,
                }
            assistant_msg = _build_assistant_message(dispatch_results, expanded_text)
            _save_chat_message(req.user_id, role="assistant", content=assistant_msg, source=routing_result.get("source", "unknown"))
            return {
                "status": "success",
                "type": "action",
                "results": dispatch_results,
                "original_text": expanded_text,
            }

        fallback_msg = "I couldn't quite grasp that scheduling request. Could you rephrase it?"
        _save_chat_message(req.user_id, role="assistant", content=fallback_msg, source="fallback")
        return {"status": "error", "message": fallback_msg}

    except Exception as e:
        print(f"API Engine error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/ai/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        analysis = {"actionable": True, "failure_type": "unknown", "component": "unknown", "confidence": "low", "summary": ""}

        if deps.nlu_engine.gemini_client:
            prompt = f"""
            You are an AI quality analyst for a scheduling assistant.
            A user gave a {'THUMBS DOWN (negative)' if req.rating == 'negative' else 'THUMBS UP (positive)'} rating.

            USER'S ORIGINAL MESSAGE:
            "{req.prompt}"

            ASSISTANT'S RESPONSE:
            "{req.response}"

            ROUTING METADATA:
            - Source: {req.source}
            - Intents detected: {req.intents}
            - Entities extracted: {json.dumps(req.entities, indent=2)}

            Your task:
            1. Determine if this feedback is ACTIONABLE.
            2. If negative and actionable, identify the most likely failure component.
            3. Classify the failure_type.
            4. Rate your confidence: "high" | "medium" | "low"
            5. Write a one-sentence summary.

            Return ONLY valid JSON:
            {{
                "actionable":    true,
                "failure_type":  "temporal_extraction",
                "component":     "NER",
                "confidence":    "high",
                "summary":       "NER failed to extract the start and end times."
            }}
            """
            try:
                from google.genai import types as gtypes
                response = deps.nlu_engine.gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=gtypes.GenerateContentConfig(response_mime_type="application/json"),
                )
                analysis = json.loads(response.text)
            except Exception as e:
                print(f"[Feedback] Gemini analysis failed: {e}")

        feedback_data = {
            "prompt": req.prompt,
            "response": req.response,
            "rating": req.rating,
            "source": req.source,
            "intents": req.intents,
            "entities": req.entities,
            "analysis": analysis,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "reviewed": False,
        }
        deps.db.collection("feedback").add(feedback_data)
        uid = req.interaction_id.split("_")[0] if "_" in req.interaction_id else "unknown"
        deps.db.collection("users").document(uid).collection("feedback").add(feedback_data)

        return {"status": "success", "message": "Thanks for the feedback.", "analysis": analysis}
    except Exception as e:
        print(f"[Feedback] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/ai/history/{user_id}")
async def get_chat_history(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        chat_ref = deps.db.collection("users").document(user_id).collection("chat_history")
        docs = chat_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(50).stream()
        history = []
        for doc in docs:
            data = doc.to_dict()
            raw_ts = data.get("timestamp")
            iso_ts = dt.datetime.now(timezone.utc).isoformat()
            if raw_ts:
                if hasattr(raw_ts, "isoformat"):
                    iso_ts = raw_ts.isoformat()
                elif isinstance(raw_ts, str):
                    iso_ts = raw_ts
                elif isinstance(raw_ts, dt.datetime):
                    iso_ts = raw_ts.isoformat()
            history.append({
                "id": doc.id,
                "role": data.get("role"),
                "content": data.get("text") or data.get("content") or "",
                "timestamp": iso_ts,
                "source": data.get("source", "unknown"),
                "isResolved": True,
            })
        return {"status": "success", "history": history[::-1]}
    except Exception as e:
        print(f"Error fetching history for {user_id}: {e}")
        return {"status": "error", "history": [], "detail": str(e)}


@router.post("/api/ai/daily-digest")
async def generate_daily_digest(
    req: DigestRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        from datetime import datetime as _dt
        user_ref = deps.db.collection("users").document(req.user_id)
        user_tz = pytz.timezone(req.timezone)

        tasks_ref = user_ref.collection("raw_tasks")
        tasks_query = tasks_ref.where("due_date", "==", req.local_date).where("status", "in", ["pending", "scheduled"]).stream()

        today_tasks = []
        high_risk_tasks = []
        for doc in tasks_query:
            t = doc.to_dict()
            t["id"] = doc.id
            today_tasks.append(t)
            if t.get("priority") in [1, 2, "high", "1", "2"] or t.get("energy_level") == "high":
                high_risk_tasks.append(t)
        high_risk_tasks.sort(key=lambda x: str(x.get("priority", "5")))

        events_ref = user_ref.collection("raw_events")
        today_events = []
        for doc in events_ref.where("status", "==", "synced").stream():
            e = doc.to_dict()
            e["id"] = doc.id
            start_str = e.get("start", "")
            if req.local_date in start_str:
                try:
                    utc_dt = _dt.fromisoformat(start_str.replace("Z", "+00:00"))
                    local_dt = utc_dt.astimezone(user_tz)
                    e["formatted_time"] = local_dt.strftime("%H:%M")
                except Exception:
                    e["formatted_time"] = "TBC"
                today_events.append(e)
        today_events.sort(key=lambda x: x.get("start", ""))

        lines = ["Good morning. Here is your comprehensive briefing for today.", ""]
        lines.append("Calendar Schedule:")
        if not today_events:
            lines.append("• Your calendar is entirely clear today.")
        elif len(today_events) <= 4:
            for ev in today_events:
                lines.append(f"• {ev['formatted_time']} : {ev['title']}")
        else:
            lines.append(f"• You have a busy schedule with {len(today_events)} events.")
            lines.append(f"• Your first meeting is '{today_events[0]['title']}' at {today_events[0]['formatted_time']}.")
            lines.append(f"• Your final meeting is '{today_events[-1]['title']}' at {today_events[-1]['formatted_time']}.")
        lines.append("")
        lines.append("Task Priorities:")
        if not today_tasks:
            lines.append("• You have no pending tasks scheduled for today.")
        else:
            lines.append(f"• You have {len(today_tasks)} total tasks on your agenda.")
            if high_risk_tasks:
                lines.append("• High Priority items requiring your attention:")
                for task in high_risk_tasks[:3]:
                    energy_note = " (Requires High Energy)" if task.get("energy_level") == "high" else ""
                    lines.append(f"  - {task['title']}{energy_note}")
                if len(high_risk_tasks) > 3:
                    lines.append(f"  - Plus {len(high_risk_tasks) - 3} additional high-priority items.")
            else:
                lines.append("• There are no high-risk items, allowing for a flexible workflow today.")

        return {
            "status": "success",
            "data": {
                "digest_text": "\n".join(lines),
                "events": today_events,
                "high_priority_tasks": high_risk_tasks,
                "total_tasks_count": len(today_tasks),
            },
        }
    except Exception as e:
        print(f"[Daily Digest Error] {e}")
        raise HTTPException(status_code=500, detail="Failed to generate morning digest")
