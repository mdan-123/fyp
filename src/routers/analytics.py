"""
Analytics routes: predict_risk, dashboard, sweep, telemetry.
"""
import datetime as dt
from datetime import timezone
from collections import defaultdict
from typing import Union

import pandas as pd
import numpy as np
import shap
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from firebase_admin import firestore as fs
from firebase_admin import auth as fb_auth

import dependencies as deps
from dependencies import verify_firebase_token, parse_iso, safe_parse_dt, get_user_timezone

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TaskRiskRequest(BaseModel):
    snooze_count: int
    priority: int
    energy_level: Union[int, str]
    estimated_duration: int
    global_time_debt: float
    tasks_due_same_day: int
    days_since_created: int
    hour_of_due_time: int
    day_of_week: int


class TelemetryRecordRequest(BaseModel):
    user_id: str
    task_id: str
    outcome: str
    category: str
    priority: int
    energy_level: int
    estimated_duration: int
    hour_of_day: int
    day_of_week: int
    lead_time_days: int
    snooze_count: int
    active_time_debt_mins: int
    daily_task_load: int
    category_success_rate: float


# ---------------------------------------------------------------------------
# ML helpers
# ---------------------------------------------------------------------------

def _encode_task_for_inference(task: dict) -> dict:
    task = dict(task)
    hour = task.pop("hour_of_due_time")
    day = task.pop("day_of_week")
    task["hour_sin"] = float(np.sin(2 * np.pi * hour / 24))
    task["hour_cos"] = float(np.cos(2 * np.pi * hour / 24))
    task["day_sin"] = float(np.sin(2 * np.pi * day / 7))
    task["day_cos"] = float(np.cos(2 * np.pi * day / 7))
    days = max(int(task.get("days_since_created", 1)), 1)
    task["snooze_rate"] = task.get("snooze_count", 0) / days
    return task


def _explain_prediction(explainer, encoded_task: dict, column_order: list, original_task: dict = None) -> list:
    row = pd.DataFrame([[encoded_task[col] for col in column_order]], columns=column_order)
    shap_values = explainer.shap_values(row)

    if isinstance(shap_values, list):
        sv = shap_values[1][0]
    elif shap_values.ndim == 3:
        sv = shap_values[0, :, 1]
    else:
        sv = shap_values[0]

    ENERGY_LABELS = {1: "Low", 2: "Medium", 3: "High"}

    def feature_label(feat, val, original):
        if feat in ("hour_sin", "hour_cos"):
            h = original.get("hour_of_due_time", "?") if original else "?"
            return f"Due time: {h}:00"
        if feat in ("day_sin", "day_cos"):
            d = original.get("day_of_week", -1) if original else -1
            day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d] if 0 <= d <= 6 else "?"
            return f"Day: {day_name}"
        label_map = {
            "snooze_count": f"Snoozed {int(val)} time(s)",
            "priority": f"Priority {int(val)}",
            "energy_level": f"Energy: {ENERGY_LABELS.get(int(val), str(val))}",
            "estimated_duration": f"Duration: {int(val)} mins",
            "global_time_debt": f"Time debt: {int(val)} mins",
            "tasks_due_same_day": f"{int(val)} other tasks today",
            "days_since_created": f"Task age: {int(val)} days",
            "snooze_rate": f"Snooze rate: {val:.2f}/day",
        }
        return label_map.get(feat, feat)

    hour_shap, day_shap, other = 0.0, 0.0, []
    for feat, val, sv_val in zip(column_order, row.iloc[0], sv):
        if feat in ("hour_sin", "hour_cos"):
            hour_shap += float(sv_val)
        elif feat in ("day_sin", "day_cos"):
            day_shap += float(sv_val)
        else:
            other.append({
                "feature": feat,
                "value": float(val),
                "shap": round(float(sv_val), 4),
                "direction": "increases_risk" if sv_val > 0 else "decreases_risk",
                "label": feature_label(feat, val, original_task),
            })

    h = original_task.get("hour_of_due_time", "?") if original_task else "?"
    d = original_task.get("day_of_week", -1) if original_task else -1
    day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d] if 0 <= d <= 6 else "?"

    other.append({"feature": "hour_of_due_time", "value": h, "shap": round(hour_shap, 4),
                  "direction": "increases_risk" if hour_shap > 0 else "decreases_risk", "label": f"Due time: {h}:00"})
    other.append({"feature": "day_of_week", "value": d, "shap": round(day_shap, 4),
                  "direction": "increases_risk" if day_shap > 0 else "decreases_risk", "label": f"Day: {day_name}"})
    other.sort(key=lambda x: abs(x["shap"]), reverse=True)
    for item in other:
        sign = "+" if item["shap"] > 0 else "-"
        pct = abs(round(item["shap"] * 100, 1))
        item["explanation"] = f"{item['label']} ({sign}{pct}% risk)"
    return other


def _predict_risk(task: dict) -> dict:
    model, explainer, meta = deps.ai_model, deps.ai_explainer, deps.ai_meta
    column_order = meta["feature_columns"]
    threshold = meta["optimal_threshold"]
    encoded = _encode_task_for_inference(task)
    row = pd.DataFrame([[encoded[col] for col in column_order]], columns=column_order)
    prob = float(model.predict_proba(row)[0][1])
    prediction = int(prob >= threshold)
    if prob < 0.35:
        label = "LOW"
    elif prob < 0.65:
        label = "MEDIUM"
    else:
        label = "HIGH"
    explanations = _explain_prediction(explainer, encoded, column_order, original_task=task)
    return {
        "risk_score": round(prob, 4),
        "risk_label": label,
        "prediction": prediction,
        "threshold": round(threshold, 4),
        "explanations": explanations[:4],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/analytics/predict_risk")
async def get_task_risk(
    task: TaskRiskRequest,
    _token=Depends(verify_firebase_token),
):
    if not deps.ai_model or not deps.ai_explainer or not deps.ai_meta:
        raise HTTPException(status_code=503, detail="AI Model is not loaded on the server.")
    try:
        task_dict = task.dict()
        raw_energy = task_dict.get("energy_level")
        if isinstance(raw_energy, str):
            task_dict["energy_level"] = {"low": 1, "medium": 2, "high": 3}.get(raw_energy.lower(), 2)
        return _predict_risk(task_dict)
    except Exception as e:
        print(f"[AI Inference Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/analytics/dashboard/{user_id}")
async def get_master_dashboard_data(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    if not deps.ai_model or not deps.ai_explainer or not deps.ai_meta:
        raise HTTPException(status_code=503, detail="AI Model is not loaded on the server.")

    try:
        now_dt = dt.datetime.now(timezone.utc)
        user_tz = get_user_timezone(user_id)
        now_local = now_dt.astimezone(user_tz)

        user_doc = deps.db.collection("users").document(user_id).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        global_debt = user_data.get("total_time_debt") or 0
        sunk_debt = user_data.get("sunk_time_debt") or 0
        time_refunded_offset = user_data.get("time_refunded_offset") or 0

        tasks_ref = deps.db.collection("users").document(user_id).collection("raw_tasks")
        events_ref = deps.db.collection("users").document(user_id).collection("raw_events")

        all_tasks = [doc.to_dict() for doc in tasks_ref.stream()]
        all_events = [doc.to_dict() for doc in events_ref.stream()]

        tasks_per_day: dict = defaultdict(int)
        for t in all_tasks:
            due_dt = parse_iso(t.get("due_date"))
            if due_dt:
                local_due = due_dt.astimezone(user_tz)
                tasks_per_day[local_due.strftime("%Y-%m-%d")] += 1

        pending_tasks, completed_tasks, missed_tasks = [], [], []
        completed_events_count = missed_events_count = 0
        completed_routines = missed_routines = 0
        time_refunded = weekly_snoozes = 0
        energy_counts = {"high": 0, "medium": 0, "low": 0}
        priority_completions = {"high": 0, "medium": 0, "low": 0}
        hour_distribution = {h: 0 for h in range(24)}
        friction_hours_list = []
        category_stats: dict = defaultdict(lambda: {"scheduled": 0, "completed": 0})
        last_7_days = [(now_local - dt.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        trend_data_dict = {day: {"tasks": 0, "events": 0} for day in last_7_days}

        for event in all_events:
            status = event.get("completion_status", "pending")
            category = event.get("category", "MEETING")
            category_stats[category]["scheduled"] += 1
            if event.get("is_reclaimed_debt") and status != "missed":
                start_dt = parse_iso(event.get("start"))
                end_dt = parse_iso(event.get("end"))
                if start_dt and end_dt:
                    time_refunded += max(0, int((end_dt - start_dt).total_seconds() / 60))
            if event.get("is_perishable"):
                if status == "completed":
                    completed_routines += 1
                elif status == "missed":
                    missed_routines += 1
            if status == "completed":
                completed_events_count += 1
                category_stats[category]["completed"] += 1
                comp_dt = parse_iso(event.get("completed_at"))
                if comp_dt:
                    local_comp = comp_dt.astimezone(user_tz)
                    comp_str = local_comp.strftime("%Y-%m-%d")
                    if comp_str in trend_data_dict:
                        trend_data_dict[comp_str]["events"] += 1
            elif status == "missed":
                missed_events_count += 1
            event_start = parse_iso(event.get("start"))
            if event_start:
                local_start = event_start.astimezone(user_tz)
                if (now_local - dt.timedelta(days=7)).date() <= local_start.date() <= (now_local + dt.timedelta(days=7)).date():
                    weekly_snoozes += int(event.get("snooze_count") or 0)

        for task in all_tasks:
            status = task.get("status")
            raw_energy = task.get("energy_level")
            clean_energy = {"low": 1, "medium": 2, "high": 3}.get(str(raw_energy).lower(), 2) if isinstance(raw_energy, str) else (int(raw_energy) if isinstance(raw_energy, (int, float)) else 2)
            due_dt = parse_iso(task.get("due_date"))
            if due_dt:
                local_due = due_dt.astimezone(user_tz)
                if (now_local - dt.timedelta(days=7)).date() <= local_due.date() <= (now_local + dt.timedelta(days=7)).date():
                    weekly_snoozes += int(task.get("snooze_count") or 0)
            if status == "completed":
                completed_tasks.append(task)
                if clean_energy == 3:
                    energy_counts["high"] += 1
                elif clean_energy == 1:
                    energy_counts["low"] += 1
                else:
                    energy_counts["medium"] += 1
                comp_dt = parse_iso(task.get("completed_at"))
                create_dt = parse_iso(task.get("created_at"))
                if comp_dt:
                    local_comp = comp_dt.astimezone(user_tz)
                    comp_str = local_comp.strftime("%Y-%m-%d")
                    if comp_str in trend_data_dict:
                        trend_data_dict[comp_str]["tasks"] += 1
                    hour_distribution[local_comp.hour] += 1
                    if create_dt:
                        friction_hours_list.append(max(0, (comp_dt - create_dt).total_seconds() / 3600))
                p = int(task.get("priority") or 3)
                if p <= 2:
                    priority_completions["high"] += 1
                elif p == 3:
                    priority_completions["medium"] += 1
                else:
                    priority_completions["low"] += 1
            elif status == "missed":
                missed_tasks.append(task)
            elif status in ["pending", "scheduled"]:
                task["clean_energy"] = clean_energy
                pending_tasks.append(task)

        scored_pending_tasks = []
        total_risk = 0
        for task in pending_tasks:
            due_dt = parse_iso(task.get("due_date")) or now_dt
            created_dt = parse_iso(task.get("created_at")) or now_dt
            local_due_dt = due_dt.astimezone(user_tz)
            ai_payload = {
                "snooze_count": int(task.get("snooze_count") or 0),
                "priority": int(task.get("priority") or 3),
                "energy_level": task.get("clean_energy", 2),
                "estimated_duration": int(task.get("estimated_duration") or 60),
                "global_time_debt": float(global_debt),
                "tasks_due_same_day": int(tasks_per_day.get(local_due_dt.strftime("%Y-%m-%d"), 1)),
                "days_since_created": int(max((now_dt - created_dt).days, 1)),
                "hour_of_due_time": int(local_due_dt.hour),
                "day_of_week": int(local_due_dt.weekday()),
            }
            try:
                ai_result = _predict_risk(ai_payload)
                task["risk_score"] = int(ai_result["risk_score"] * 100)
                task["risk_label"] = ai_result["risk_label"]
                task["ai_explanations"] = ai_result["explanations"]
                total_risk += task["risk_score"]
                scored_pending_tasks.append(task)
            except Exception:
                pass

        avg_friction = (sum(friction_hours_list) / len(friction_hours_list)) if friction_hours_list else 0
        peak_hour = max(hour_distribution, key=hour_distribution.get) if completed_tasks else 9

        # Cold-start detection: account ≤ 7 days old AND no historical data yet
        is_cold_start = False
        try:
            user_record = fb_auth.get_user(user_id)
            creation_ms = user_record.user_metadata.creation_timestamp  # milliseconds since epoch
            account_age_days = (now_dt - dt.datetime.fromtimestamp(creation_ms / 1000, tz=timezone.utc)).days
            no_history = len(completed_tasks) == 0 and completed_events_count == 0
            is_cold_start = account_age_days <= 7 and no_history
        except Exception:
            pass
        most_avoided = sorted([t for t in pending_tasks if (t.get("snooze_count") or 0) > 0], key=lambda x: x.get("snooze_count") or 0, reverse=True)[:5]
        scored_pending_tasks.sort(key=lambda x: x.get("risk_score") or 0, reverse=True)
        danger_zone = [t for t in scored_pending_tasks if (t.get("risk_score") or 0) >= 65][:3]
        avg_risk = (total_risk / len(scored_pending_tasks)) if scored_pending_tasks else 0
        total_tasks_ever = len(completed_tasks) + len(missed_tasks)
        task_completion_rate = (len(completed_tasks) / total_tasks_ever * 100) if total_tasks_ever > 0 else 0
        total_events_ever = completed_events_count + missed_events_count
        event_completion_rate = (completed_events_count / total_events_ever * 100) if total_events_ever > 0 else 0
        total_routines = completed_routines + missed_routines
        routine_adherence = (completed_routines / total_routines * 100) if total_routines > 0 else 0
        formatted_trend_data = [{"date": day, "tasks": data["tasks"], "events": data["events"]} for day, data in trend_data_dict.items()]
        # Apply reset offset so the counter shows time refunded since last reset
        time_refunded = max(0, time_refunded - time_refunded_offset)

        return {
            "status": "success",
            "is_cold_start": is_cold_start,
            "core_ledgers": {
                "active_debt_mins": global_debt,
                "sunk_debt_mins": sunk_debt,
                "time_refunded_mins": time_refunded,
            },
            "procrastination_profile": most_avoided,
            "weekly_snoozes": weekly_snoozes,
            "risk_forecast": {"average_risk_score": int(avg_risk), "danger_zone": danger_zone},
            "energy_analytics": energy_counts,
            "completion_funnel": {
                "task_completion_rate": task_completion_rate,
                "event_completion_rate": event_completion_rate,
                "routine_adherence": routine_adherence,
                "trend_data": formatted_trend_data,
            },
            "advanced_metrics": {
                "priority_alignment": priority_completions,
                "peak_action_window": {"peak_hour": peak_hour, "distribution": list(hour_distribution.values())},
                "task_friction_hours": int(avg_friction),
                "category_stats": dict(category_stats),
            },
        }
    except Exception as e:
        print(f"[Master Dashboard Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/analytics/sweep/{user_id}")
async def run_time_debt_sweeper(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        from firebase_admin import firestore as _fs
        now_dt = dt.datetime.now(dt.timezone.utc)
        batch = deps.db.batch()
        active_reschedulable_debt = 0
        active_sunk_debt = 0
        items_swept = 0

        events_ref = deps.db.collection("users").document(user_id).collection("raw_events")
        tasks_ref = deps.db.collection("users").document(user_id).collection("raw_tasks")

        for doc in events_ref.where("completion_status", "==", "pending").stream():
            event = doc.to_dict()
            end_dt = safe_parse_dt(event.get("end"))
            if end_dt and end_dt < now_dt:
                start_dt = safe_parse_dt(event.get("start"))
                duration = int((end_dt - start_dt).total_seconds() / 60) if start_dt and end_dt else 60
                capped_duration = min(max(0, duration), 120)
                if event.get("is_perishable"):
                    active_sunk_debt += capped_duration
                else:
                    active_reschedulable_debt += capped_duration
                batch.update(doc.reference, {"completion_status": "missed", "debt_applied": True})
                items_swept += 1

        for status in ["pending", "scheduled"]:
            for doc in tasks_ref.where("status", "==", status).stream():
                task = doc.to_dict()
                due_dt = safe_parse_dt(task.get("due_date"))
                if due_dt and due_dt < now_dt:
                    base_duration = task.get("estimated_duration") or 60
                    scheduled_mins = 0
                    for eid in task.get("linked_event_ids", []):
                        edoc = events_ref.document(eid).get()
                        if edoc.exists:
                            edata = edoc.to_dict()
                            es = safe_parse_dt(edata.get("start"))
                            ee = safe_parse_dt(edata.get("end"))
                            if es and ee:
                                scheduled_mins += int((ee - es).total_seconds() / 60)
                    unscheduled_debt = max(0, base_duration - scheduled_mins)
                    capped_duration = min(unscheduled_debt, 120)
                    if capped_duration > 0:
                        if task.get("is_perishable"):
                            active_sunk_debt += capped_duration
                        else:
                            active_reschedulable_debt += capped_duration
                    batch.update(doc.reference, {"status": "missed", "debt_applied": True})
                    items_swept += 1

        if items_swept > 0:
            user_ref = deps.db.collection("users").document(user_id)
            updates = {}
            if active_reschedulable_debt > 0:
                updates["total_time_debt"] = _fs.Increment(active_reschedulable_debt)
            if active_sunk_debt > 0:
                updates["sunk_time_debt"] = _fs.Increment(active_sunk_debt)
            if updates:
                batch.update(user_ref, updates)
            batch.commit()

        return {
            "status": "success",
            "items_swept": items_swept,
            "debt_added": active_reschedulable_debt,
            "sunk_added": active_sunk_debt,
        }
    except Exception as e:
        print(f"[Sweeper Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/analytics/telemetry/record")
async def record_training_telemetry(
    req: TelemetryRecordRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        from firebase_admin import firestore as _fs
        if req.outcome not in ["completed", "missed"]:
            raise ValueError("Outcome must be either 'completed' or 'missed'")

        telemetry_ref = deps.db.collection("training_telemetry").document()
        telemetry_data = {
            "user_id": req.user_id,
            "task_id": req.task_id,
            "target_label": req.outcome,
            "features_intrinsic": {
                "category": req.category,
                "priority": req.priority,
                "energy_level": req.energy_level,
                "estimated_duration": req.estimated_duration,
            },
            "features_temporal": {
                "hour_of_day": req.hour_of_day,
                "day_of_week": req.day_of_week,
                "lead_time_days": req.lead_time_days,
            },
            "features_behavioural": {
                "snooze_count": req.snooze_count,
                "active_time_debt_mins": req.active_time_debt_mins,
                "daily_task_load": req.daily_task_load,
                "category_success_rate": req.category_success_rate,
            },
            "recorded_at": _fs.SERVER_TIMESTAMP,
        }
        telemetry_ref.set(telemetry_data)
        return {"status": "success", "message": "Telemetry recorded for future model training."}
    except Exception as e:
        print(f"[Telemetry Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Snooze ledger
# ---------------------------------------------------------------------------

class ClearSnoozeRequest(BaseModel):
    user_id: str
    item_id: str
    item_type: str  # "task" or "event"


@router.get("/api/analytics/snoozed/{user_id}")
async def get_snoozed_items(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        tasks_ref = deps.db.collection("users").document(user_id).collection("raw_tasks")
        events_ref = deps.db.collection("users").document(user_id).collection("raw_events")

        snoozed_tasks = []
        for doc in tasks_ref.stream():
            t = doc.to_dict()
            if (t.get("snooze_count") or 0) > 0:
                snoozed_tasks.append({
                    "id": t.get("id") or doc.id,
                    "type": "task",
                    "title": t.get("title", "Untitled"),
                    "description": t.get("description") or "",
                    "snooze_count": t.get("snooze_count", 0),
                    "due_date": t.get("due_date"),
                    "start_date": t.get("start_date"),
                    "estimated_duration": t.get("estimated_duration"),
                    "category": t.get("category"),
                    "tags": t.get("tags") or [],
                    "priority": t.get("priority"),
                    "energy_level": t.get("energy_level"),
                    "status": t.get("status"),
                })

        snoozed_events = []
        for doc in events_ref.stream():
            e = doc.to_dict()
            if (e.get("snooze_count") or 0) > 0:
                start_str = e.get("start")
                end_str = e.get("end")
                duration_mins = None
                if start_str and end_str:
                    try:
                        s_dt = parse_iso(start_str)
                        e_dt = parse_iso(end_str)
                        if s_dt and e_dt:
                            duration_mins = int((e_dt - s_dt).total_seconds() / 60)
                    except Exception:
                        pass
                snoozed_events.append({
                    "id": e.get("id") or doc.id,
                    "type": "event",
                    "title": e.get("title", "Untitled"),
                    "description": e.get("description") or "",
                    "snooze_count": e.get("snooze_count", 0),
                    "start": start_str,
                    "end": end_str,
                    "duration_mins": duration_mins,
                    "category": e.get("category"),
                    "location": e.get("location") or "",
                    "completion_status": e.get("completion_status"),
                })

        return {"status": "success", "tasks": snoozed_tasks, "events": snoozed_events}
    except Exception as e:
        print(f"[Snoozed Items Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/analytics/clear-snooze")
async def clear_snooze(
    req: ClearSnoozeRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        if req.item_type == "task":
            ref = (
                deps.db.collection("users")
                .document(req.user_id)
                .collection("raw_tasks")
                .document(req.item_id)
            )
        elif req.item_type == "event":
            ref = (
                deps.db.collection("users")
                .document(req.user_id)
                .collection("raw_events")
                .document(req.item_id)
            )
        else:
            raise HTTPException(status_code=400, detail="item_type must be 'task' or 'event'")

        if not ref.get().exists:
            raise HTTPException(status_code=404, detail="Item not found")

        ref.update({"snooze_count": 0})
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Clear Snooze Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/analytics/capacity/{user_id}")
async def get_capacity_status(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    """
    Lightweight capacity check used when the user opens the 'Add Task' modal.
    Scores all pending tasks and returns an aggregate risk status plus the
    context values needed for the frontend to score the new task in real-time.
    """
    if not deps.ai_model or not deps.ai_explainer or not deps.ai_meta:
        raise HTTPException(status_code=503, detail="AI Model is not loaded on the server.")
    try:
        now_dt = dt.datetime.now(timezone.utc)
        user_tz = get_user_timezone(user_id)
        now_local = now_dt.astimezone(user_tz)

        user_doc = deps.db.collection("users").document(user_id).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        global_debt = float(user_data.get("total_time_debt") or 0)

        tasks_ref = deps.db.collection("users").document(user_id).collection("raw_tasks")
        all_tasks = [doc.to_dict() for doc in tasks_ref.stream()]

        # Build per-day task count for tasks_due_same_day feature
        tasks_per_day: dict = defaultdict(int)
        for t in all_tasks:
            due_dt = parse_iso(t.get("due_date"))
            if due_dt:
                local_due = due_dt.astimezone(user_tz)
                tasks_per_day[local_due.strftime("%Y-%m-%d")] += 1

        today_str = now_local.strftime("%Y-%m-%d")
        tasks_due_today = int(tasks_per_day.get(today_str, 0))

        pending_tasks = [t for t in all_tasks if t.get("status") in ["pending", "scheduled"]]

        if not pending_tasks:
            return {
                "status": "OK",
                "danger_count": 0,
                "avg_risk_score": 0,
                "total_pending": 0,
                "time_debt_mins": int(global_debt),
                "tasks_due_today": tasks_due_today,
                "top_risk_tasks": [],
            }

        danger_count = 0
        total_risk = 0
        scored_tasks = []

        for task in pending_tasks:
            due_dt = parse_iso(task.get("due_date")) or now_dt
            created_dt = parse_iso(task.get("created_at")) or now_dt
            local_due_dt = due_dt.astimezone(user_tz)
            raw_energy = task.get("energy_level")
            clean_energy = (
                {"low": 1, "medium": 2, "high": 3}.get(str(raw_energy).lower(), 2)
                if isinstance(raw_energy, str)
                else (int(raw_energy) if isinstance(raw_energy, (int, float)) else 2)
            )
            ai_payload = {
                "snooze_count": int(task.get("snooze_count") or 0),
                "priority": int(task.get("priority") or 3),
                "energy_level": clean_energy,
                "estimated_duration": int(task.get("estimated_duration") or 60),
                "global_time_debt": global_debt,
                "tasks_due_same_day": int(tasks_per_day.get(local_due_dt.strftime("%Y-%m-%d"), 1)),
                "days_since_created": int(max((now_dt - created_dt).days, 1)),
                "hour_of_due_time": int(local_due_dt.hour),
                "day_of_week": int(local_due_dt.weekday()),
            }
            try:
                result = _predict_risk(ai_payload)
                score = int(result["risk_score"] * 100)
                total_risk += score
                if score >= 65:
                    danger_count += 1
                scored_tasks.append({
                    "title": task.get("title", "Untitled"),
                    "risk_score": score,
                    "risk_label": result["risk_label"],
                })
            except Exception:
                pass

        scored_tasks.sort(key=lambda x: x["risk_score"], reverse=True)
        avg_risk = int(total_risk / len(scored_tasks)) if scored_tasks else 0

        if danger_count >= 3 or avg_risk >= 65:
            capacity_status = "OVERLOADED"
        elif danger_count >= 1 or avg_risk >= 40:
            capacity_status = "MODERATE"
        else:
            capacity_status = "OK"

        return {
            "status": capacity_status,
            "danger_count": danger_count,
            "avg_risk_score": avg_risk,
            "total_pending": len(pending_tasks),
            "time_debt_mins": int(global_debt),
            "tasks_due_today": tasks_due_today,
            "top_risk_tasks": scored_tasks[:3],
        }
    except Exception as e:
        print(f"[Capacity Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/analytics/reset-refunded/{user_id}")
async def reset_refunded_counter(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    """Store the current calculated time_refunded total as an offset so the
    displayed counter resets to zero from this point forward."""
    try:
        events_ref = deps.db.collection("users").document(user_id).collection("raw_events")
        current_total = 0
        for doc in events_ref.stream():
            e = doc.to_dict()
            if e.get("is_reclaimed_debt") and e.get("completion_status") != "missed":
                s = parse_iso(e.get("start"))
                end = parse_iso(e.get("end"))
                if s and end:
                    current_total += max(0, int((end - s).total_seconds() / 60))

        deps.db.collection("users").document(user_id).update(
            {"time_refunded_offset": current_total}
        )
        return {"status": "success", "offset_set": current_total}
    except Exception as e:
        print(f"[Reset Refunded Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))
