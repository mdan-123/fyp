"""
Calendar routes: create, update, sync, list, delete, resolve conflicts,
optimise, snapshot/undo, and debt rescheduling.
"""
import uuid
import json
import hashlib
import datetime as dt
from datetime import timezone
from typing import Optional, List, Dict, Any, Literal

import requests as http_requests
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
import msal

import dependencies as deps
from dependencies import (
    verify_firebase_token,
    parse_iso,
    ensure_strict_iso_string,
    safe_parse_dt,
    get_user_timezone,
    sync_task_with_events,
    create_calendar_snapshot,
)
from categorise import categorise_event

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SyncRequest(BaseModel):
    user_id: str


class EventPayload(BaseModel):
    event_id: Optional[str] = None
    user_id: str
    title: str
    start: str
    end: str
    location: Optional[str] = ""
    meeting_link: Optional[str] = ""
    is_locked: bool = True
    description: Optional[str] = ""
    recurrence: Optional[str] = "none"
    recurrence_days: Optional[List[str]] = []
    travel_time: Optional[int] = 0
    travel_origin: Optional[str] = ""
    travel_mode: Optional[str] = "driving"
    provider: str
    email: str
    attachments: List[str] = []
    category: Optional[str] = "None"
    update_mode: Optional[str] = "all"
    instance_date: Optional[str] = None
    completion_status: Optional[str] = "pending"
    snooze_count: Optional[int] = 0
    completed_at: Optional[str] = None
    debt_applied: Optional[bool] = False
    is_perishable: Optional[bool] = False


class DisconnectRequest(BaseModel):
    user_id: str
    email: str
    provider: str


class ResolveConflictRequest(BaseModel):
    user_id: str
    event_id: str
    resolution: Literal["external", "proposed", "revert"]


class OptimiseRequest(BaseModel):
    user_id: str
    target_date: str


class UndoRequest(BaseModel):
    user_id: str


class CommitOptimisationRequest(BaseModel):
    user_id: str
    events: list[dict[str, Any]]


class ReschedulePreviewRequest(BaseModel):
    user_id: str


class RescheduleCommitRequest(BaseModel):
    user_id: str
    events: list


class DeleteEventRequest(BaseModel):
    event_id: str
    user_id: str


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_google_calendar_events(refresh_token: str, email: str, sync_id: str):
    now = dt.datetime.now(timezone.utc)
    time_min = (now - dt.timedelta(days=30)).isoformat()
    time_max = (now + dt.timedelta(days=30)).isoformat()

    try:
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=deps.GOOGLE_CLIENT_ID,
            client_secret=deps.GOOGLE_CLIENT_SECRET,
        )
        service = build("calendar", "v3", credentials=creds)
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        return [
            {
                "id": ev.get("id"),
                "title": ev.get("summary", "Untitled Event"),
                "start": ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date"),
                "end": ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date"),
                "provider": "google",
                "email": email,
                "sync_id": sync_id,
            }
            for ev in events_result.get("items", [])
        ]

    except RefreshError as e:
        print(f"🚨 Refresh token dead for {email}: {e}")
        return []
    except Exception as e:
        print(f"Error fetching for {email}: {e}")
        return []


def _get_outlook_calendar_events(refresh_token: str, email: str, sync_id: str):
    client = msal.ConfidentialClientApplication(
        deps.OUTLOOK_CLIENT_ID,
        client_credential=deps.OUTLOOK_CLIENT_SECRET,
        authority=deps.OUTLOOK_AUTHORITY,
    )
    token_result = client.acquire_token_by_refresh_token(
        refresh_token, scopes=deps.OUTLOOK_SCOPES
    )

    if "access_token" not in token_result:
        print(f"Error refreshing Outlook token for {email}")
        return []

    access_token = token_result["access_token"]
    now = dt.datetime.now(timezone.utc)
    start_date = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    end_date = (now + dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")

    endpoint = (
        f"https://graph.microsoft.com/v1.0/me/calendarView"
        f"?startDateTime={start_date}&endDateTime={end_date}&$top=100"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Prefer": 'outlook.timezone="UTC"',
    }
    response = http_requests.get(endpoint, headers=headers)
    if response.status_code != 200:
        print(f"Microsoft Graph Error: {response.text}")
        return []

    return [
        {
            "id": ev.get("id"),
            "title": ev.get("subject", "Untitled Event"),
            "start": ev.get("start", {}).get("dateTime"),
            "end": ev.get("end", {}).get("dateTime"),
            "provider": "outlook",
            "email": email,
            "sync_id": sync_id,
        }
        for ev in response.json().get("value", [])
    ]


def _hash_event_list(events: List[Dict[str, Any]]) -> str:
    simplified = sorted(
        [
            {
                "id": e.get("id"),
                "start": e.get("proposed_start") or e.get("start"),
                "end": e.get("proposed_end") or e.get("end"),
            }
            for e in events
        ],
        key=lambda x: (x["start"], x["id"] or ""),
    )
    return hashlib.md5(
        json.dumps(simplified, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _create_calendar_snapshot(user_id: str):
    return create_calendar_snapshot(user_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/calendar/new")
async def create_event(
    payload: EventPayload,
    _token=Depends(verify_firebase_token),
):
    try:
        from firebase_admin import firestore as fs

        user_ref = deps.db.collection("users").document(payload.user_id)
        events_ref = user_ref.collection("raw_events")
        doc_id = f"custom_{uuid.uuid4().hex[:8]}"

        event_data = payload.dict(exclude_none=True)
        event_data["id"] = doc_id

        assigned_category = categorise_event(
            title=payload.title or "Untitled",
            description=payload.description or "",
        )
        event_data["category"] = assigned_category
        event_data["sync_status"] = "synced"
        event_data["requires_review"] = False
        event_data["has_drifted"] = False
        event_data["original_start"] = payload.start
        event_data["original_end"] = payload.end
        event_data["sync_action_required"] = "push_to_provider"
        event_data["completion_status"] = "pending"
        event_data["snooze_count"] = 0
        event_data["completed_at"] = None
        event_data["debt_applied"] = False

        perishable_categories = ["Health & Fitness", "Routine", "Meals", "Personal Care"]
        if payload.recurrence != "none" or assigned_category in perishable_categories:
            event_data["is_perishable"] = True
        else:
            event_data["is_perishable"] = payload.is_perishable

        events_ref.document(doc_id).set(event_data)
        return {"status": "success", "event_id": doc_id, "category": assigned_category}
    except Exception as e:
        print(f"Error creating event: {e}")
        raise HTTPException(status_code=500, detail="Failed to create event")


@router.post("/api/calendar/update")
async def update_event(
    payload: EventPayload,
    _token=Depends(verify_firebase_token),
):
    from firebase_admin import firestore as fs

    if not payload.event_id:
        raise HTTPException(status_code=400, detail="Missing event_id for update")

    try:
        events_ref = (
            deps.db.collection("users")
            .document(payload.user_id)
            .collection("raw_events")
        )
        existing_doc = events_ref.document(payload.event_id).get()
        if not existing_doc.exists:
            raise HTTPException(status_code=404, detail="Event not found")

        existing_data = existing_doc.to_dict()

        category_changed = (
            payload.category is not None
            and payload.category != existing_data.get("category")
        )
        new_title = payload.title if payload.title is not None else existing_data.get("title", "")
        new_desc = (
            payload.description
            if payload.description is not None
            else existing_data.get("description", "")
        )
        title_changed = payload.title is not None and payload.title != existing_data.get("title")
        desc_changed = (
            payload.description is not None
            and payload.description != existing_data.get("description")
        )

        if category_changed:
            updated_category = payload.category
        elif title_changed or desc_changed or not existing_data.get("category"):
            updated_category = categorise_event(title=new_title, description=new_desc)
        else:
            updated_category = existing_data.get("category")

        ui_comp_status = (
            payload.completion_status
            if payload.completion_status is not None
            else existing_data.get("completion_status", "pending")
        )
        ui_is_perishable = (
            payload.is_perishable
            if payload.is_perishable is not None
            else existing_data.get("is_perishable", False)
        )

        old_start = parse_iso(existing_data.get("start"))
        new_start = parse_iso(payload.start) if payload.start else old_start

        snooze_increment = 0
        if old_start and new_start and new_start > old_start:
            snooze_increment = 1

        new_snooze_count = existing_data.get("snooze_count", 0) + snooze_increment

        comp_status = ui_comp_status
        is_perish = ui_is_perishable
        debt_applied = existing_data.get("debt_applied", False)
        completed_at = existing_data.get("completed_at")

        if existing_data.get("completion_status") == "missed" and snooze_increment > 0:
            if payload.completion_status not in ["completed", "missed"]:
                comp_status = "pending"
            if debt_applied and not is_perish:
                old_end = parse_iso(existing_data.get("end"))
                if old_start and old_end:
                    duration_mins = int((old_end - old_start).total_seconds() / 60)
                    if duration_mins > 0:
                        deps.db.collection("users").document(payload.user_id).update(
                            {"total_time_debt": fs.Increment(-duration_mins)}
                        )
            debt_applied = False

        # Retroactive completion: marking a missed event as completed without rescheduling
        if (
            comp_status == "completed"
            and existing_data.get("completion_status") == "missed"
            and snooze_increment == 0
        ):
            if existing_data.get("debt_applied"):
                retro_start = parse_iso(existing_data.get("start"))
                retro_end = parse_iso(existing_data.get("end"))
                if retro_start and retro_end:
                    retro_mins = int((retro_end - retro_start).total_seconds() / 60)
                    if retro_mins > 0:
                        debt_field = "sunk_time_debt" if is_perish else "total_time_debt"
                        deps.db.collection("users").document(payload.user_id).update(
                            {debt_field: fs.Increment(-retro_mins)}
                        )
                        print(f"💰 Refunded {retro_mins} mins via retroactive completion")
            debt_applied = False

        if comp_status == "completed" and existing_data.get("completion_status") != "completed":
            completed_at = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        elif comp_status != "completed":
            completed_at = None

        if payload.update_mode == "single" and payload.instance_date:
            events_ref.document(payload.event_id).update(
                {
                    "exception_dates": fs.ArrayUnion([payload.instance_date]),
                    "sync_action_required": "push_to_provider",
                }
            )
            new_doc_id = f"custom_{uuid.uuid4().hex[:8]}"
            new_event_data = payload.dict(
                exclude={"event_id", "user_id", "update_mode", "instance_date"},
                exclude_none=True,
            )
            new_event_data["id"] = new_doc_id
            new_event_data["recurrence"] = "none"
            new_event_data["parent_event_id"] = payload.event_id
            new_event_data["sync_status"] = "synced"
            new_event_data["requires_review"] = False
            new_event_data["has_drifted"] = False
            new_event_data["proposed_start"] = payload.start
            new_event_data["proposed_end"] = payload.end
            new_event_data["sync_action_required"] = "push_to_provider"
            new_event_data["category"] = updated_category
            new_event_data["completion_status"] = comp_status
            new_event_data["snooze_count"] = 0
            new_event_data["debt_applied"] = False
            new_event_data["is_perishable"] = is_perish
            new_event_data["completed_at"] = completed_at
            events_ref.document(new_doc_id).set(new_event_data)

        elif payload.update_mode == "exception_delete" and payload.instance_date:
            events_ref.document(payload.event_id).update(
                {
                    "exception_dates": fs.ArrayUnion([payload.instance_date]),
                    "sync_action_required": "push_to_provider",
                }
            )

        else:
            update_data = payload.dict(
                exclude={"event_id", "user_id", "update_mode", "instance_date"},
                exclude_none=True,
            )
            update_data["proposed_start"] = payload.start
            update_data["proposed_end"] = payload.end
            update_data["requires_review"] = False
            update_data["has_drifted"] = False
            update_data["status"] = "resolved"
            update_data["sync_action_required"] = "push_to_provider"
            update_data["category"] = updated_category
            update_data["completion_status"] = comp_status
            update_data["snooze_count"] = new_snooze_count
            update_data["debt_applied"] = debt_applied
            update_data["is_perishable"] = is_perish
            update_data["completed_at"] = completed_at
            events_ref.document(payload.event_id).update(update_data)

        linked_task_id = existing_data.get("linked_task_id")
        if linked_task_id:
            sync_task_with_events(payload.user_id, linked_task_id)

        return {"status": "success"}
    except Exception as e:
        print(f"Error updating event: {e}")
        raise HTTPException(status_code=500, detail="Failed to update event")


@router.post("/api/calendar/sync")
async def sync_calendar(
    request: SyncRequest,
    _token=Depends(verify_firebase_token),
):
    from firebase_admin import firestore as fs

    user_id = request.user_id
    user_ref = deps.db.collection("users").document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        return {"status": "success", "events": [], "linked_accounts": []}

    linked_accounts = user_doc.to_dict().get("linked_accounts", [])
    events_ref = user_ref.collection("raw_events")

    sync_id = str(uuid.uuid4())
    current_time_iso = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    existing_events = {doc.id: doc.to_dict() for doc in events_ref.stream()}

    all_events = []
    safe_accounts = []
    batch = deps.db.batch()
    global_processed_ids = set()
    active_sync_emails = set()

    for account in linked_accounts:
        provider = account.get("provider")
        email = account.get("email")
        safe_accounts.append({"provider": provider, "email": email})

        provider_events = []
        try:
            if provider == "google":
                provider_events = _get_google_calendar_events(
                    account["refresh_token"], email, sync_id
                )
            elif provider == "outlook":
                provider_events = _get_outlook_calendar_events(
                    account["refresh_token"], email, sync_id
                )
            active_sync_emails.add(email)
        except Exception as e:
            print(f"Fetch failed for {email}: {e}")
            continue

        for event in provider_events:
            raw_id = str(event.get("id", "")).strip()
            doc_id = f"{provider}_{raw_id}"
            global_processed_ids.add(doc_id)
            is_new = doc_id not in existing_events

            new_start = ensure_strict_iso_string(event.get("start"))
            new_end = ensure_strict_iso_string(event.get("end"))
            event_title = event.get("title", "Untitled")
            event_desc = event.get("description", "")
            attendees_count = len(event.get("attendees", []))
            has_video = bool(event.get("hangoutLink") or event.get("onlineMeeting"))

            if is_new:
                assigned_category = categorise_event(
                    event_title, event_desc, attendees_count, has_video
                )
                event["category"] = assigned_category
                event["is_locked"] = True
                event["requires_review"] = True
                event["has_drifted"] = False
                event["original_start"] = new_start
                event["original_end"] = new_end
                event["previous_start"] = None
                event["previous_end"] = None
                event["proposed_start"] = None
                event["proposed_end"] = None
                event["status"] = "synced"
                event["completion_status"] = "pending"
                event["snooze_count"] = 0
                event["completed_at"] = None
                event["debt_applied"] = False
                perishable_categories = [
                    "Health & Fitness", "Routine", "Meals", "Personal Care"
                ]
                event["is_perishable"] = assigned_category in perishable_categories
            else:
                old_data = existing_events[doc_id]
                if old_data.get("sync_action_required") == "push_to_provider":
                    continue

                existing_category = old_data.get("category")
                event["category"] = (
                    existing_category
                    if existing_category
                    else categorise_event(event_title, event_desc, attendees_count, has_video)
                )

                old_start_parsed = parse_iso(old_data.get("original_start"))
                new_start_parsed = parse_iso(new_start)
                old_end_parsed = parse_iso(old_data.get("original_end"))
                new_end_parsed = parse_iso(new_end)
                time_changed = (old_start_parsed != new_start_parsed) or (
                    old_end_parsed != new_end_parsed
                )

                event["is_locked"] = old_data.get("is_locked", True)
                if time_changed:
                    event["has_drifted"] = True
                    event["requires_review"] = True
                    event["previous_start"] = old_data.get("original_start")
                    event["previous_end"] = old_data.get("original_end")
                    event["status"] = (
                        "conflict" if old_data.get("proposed_start") else "drifted"
                    )
                else:
                    event["has_drifted"] = old_data.get("has_drifted", False)
                    event["requires_review"] = old_data.get("requires_review", False)
                    event["previous_start"] = old_data.get("previous_start")
                    event["previous_end"] = old_data.get("previous_end")
                    event["status"] = old_data.get("status", "synced")

                event["original_start"] = new_start
                event["original_end"] = new_end
                event["proposed_start"] = old_data.get("proposed_start")
                event["proposed_end"] = old_data.get("proposed_end")
                event["completion_status"] = old_data.get("completion_status", "pending")
                event["snooze_count"] = old_data.get("snooze_count", 0)
                event["completed_at"] = old_data.get("completed_at")
                event["debt_applied"] = old_data.get("debt_applied", False)
                event["is_perishable"] = old_data.get("is_perishable", False)

            event["start"] = new_start
            event["end"] = new_end
            event["last_synced_from_provider"] = current_time_iso
            event["sync_id"] = sync_id
            event["email"] = email

            all_events.append(event)
            batch.set(events_ref.document(doc_id), event, merge=True)

    for old_doc_id, old_doc_data in existing_events.items():
        old_email = old_doc_data.get("email")
        old_provider = old_doc_data.get("provider")
        sync_action = old_doc_data.get("sync_action_required")

        if old_provider in ["google", "outlook"] and old_email in active_sync_emails:
            if old_doc_id not in global_processed_ids:
                if sync_action != "push_to_provider":
                    batch.delete(events_ref.document(old_doc_id))

    batch.commit()
    return {
        "status": "success",
        "events": all_events,
        "linked_accounts": safe_accounts,
        "sync_id": sync_id,
    }


@router.get("/api/calendar/events/{user_id}")
async def list_events(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        events_ref = (
            deps.db.collection("users").document(user_id).collection("raw_events")
        )
        events = []
        for doc in events_ref.stream():
            data = doc.to_dict()
            data["id"] = doc.id
            events.append(data)
        return {"status": "success", "events": events}
    except Exception as e:
        print(f"Error listing events for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch events")


@router.post("/api/calendar/disconnect")
async def disconnect_calendar(
    req: DisconnectRequest,
    _token=Depends(verify_firebase_token),
):
    from firebase_admin import firestore as fs

    try:
        user_ref = deps.db.collection("users").document(req.user_id)
        user_doc = user_ref.get()
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")

        accounts = user_doc.to_dict().get("linked_accounts", [])
        account_to_remove = next(
            (
                acc
                for acc in accounts
                if acc["email"] == req.email and acc["provider"] == req.provider
            ),
            None,
        )

        if account_to_remove:
            user_ref.update({"linked_accounts": fs.ArrayRemove([account_to_remove])})
            events_ref = user_ref.collection("raw_events")
            stale_events = (
                events_ref.where("email", "==", req.email)
                .where("provider", "==", req.provider)
                .stream()
            )
            batch = deps.db.batch()
            for event in stale_events:
                batch.delete(event.reference)
            batch.commit()
            return {
                "status": "success",
                "message": f"Disconnected {req.email} and purged events",
            }

        return {"status": "error", "message": "Account not found"}
    except Exception as e:
        print(f"Disconnect error: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect account")


@router.post("/api/calendar/resolve")
async def resolve_calendar_conflict(
    req: ResolveConflictRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        event_ref = (
            deps.db.collection("users")
            .document(req.user_id)
            .collection("raw_events")
            .document(req.event_id)
        )
        event_doc = event_ref.get()
        if not event_doc.exists:
            raise HTTPException(status_code=404, detail="Event not found")

        event_data = event_doc.to_dict()
        updates = {
            "has_drifted": False,
            "requires_review": False,
            "previous_start": None,
            "previous_end": None,
            "status": "resolved",
        }

        if req.resolution == "external":
            updates["proposed_start"] = None
            updates["proposed_end"] = None
            updates["sync_action_required"] = "none"
        elif req.resolution == "proposed":
            updates["sync_action_required"] = "push_to_provider"
        elif req.resolution == "revert":
            previous_start = event_data.get("previous_start")
            previous_end = event_data.get("previous_end")
            if previous_start:
                updates["proposed_start"] = previous_start
                updates["proposed_end"] = previous_end
                updates["sync_action_required"] = "push_to_provider"

        event_ref.update(updates)
        return {
            "status": "success",
            "resolved_id": req.event_id,
            "action_taken": req.resolution,
        }
    except Exception as e:
        print(f"Error resolving conflict: {e}")
        raise HTTPException(status_code=500, detail="Failed to resolve calendar conflict")


@router.post("/api/calendar/optimise/preview")
async def preview_optimisation(
    request: OptimiseRequest,
    _token=Depends(verify_firebase_token),
):
    from optimiser import Optimiser

    user_id = request.user_id
    target_date_str = request.target_date

    user_doc_sched = deps.db.collection("users").document(user_id).get()
    user_settings_sched = user_doc_sched.to_dict() if user_doc_sched.exists else {}
    sched_window_days = int(user_settings_sched.get("optimisation_window_days", 7))
    optimise_weekends = bool(user_settings_sched.get("optimise_weekends", False))
    routines_on_weekends = bool(user_settings_sched.get("routines_on_weekends", False))
    sched_start_hour = int(user_settings_sched.get("scheduling_start_hour", 8))
    sched_end_hour = int(user_settings_sched.get("scheduling_end_hour", 22))

    try:
        clean_date_str = target_date_str[:10]
        target_date = dt.datetime.fromisoformat(clean_date_str).date()
        start_of_window = target_date
        end_of_window = start_of_window + dt.timedelta(days=sched_window_days - 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    try:
        user_tz = get_user_timezone(user_id)
        prefs_ref = deps.db.collection("users").document(user_id).collection("preferences")
        preferences = [doc.to_dict() for doc in prefs_ref.stream()]

        events_ref = deps.db.collection("users").document(user_id).collection("raw_events")
        existing_events = []
        for doc in events_ref.stream():
            event_data = doc.to_dict()
            event_data["id"] = doc.id
            existing_events.append(event_data)

        original_hash = _hash_event_list([e for e in existing_events if not e.get("is_ghost")])
        calendar_optimiser = Optimiser(
            existing_events, preferences, user_tz_string=str(user_tz),
            skip_weekends=not optimise_weekends,
            routines_on_weekends=routines_on_weekends,
            scheduling_start_hour=sched_start_hour,
            scheduling_end_hour=sched_end_hour,
        )
        ghost_events = calendar_optimiser.inject_routines(start_of_window, end_of_window)
        preview_events = []

        for event in existing_events:
            if event.get("is_ghost"):
                continue
            if event.get("is_locked", True):
                preview_events.append(event)
                continue

            event_start_str = event.get("start", "")
            if not event_start_str:
                preview_events.append(event)
                continue

            parsed_start = safe_parse_dt(event_start_str)
            if not parsed_start:
                preview_events.append(event)
                continue

            event_start_date = parsed_start.astimezone(calendar_optimiser.user_tz).date()
            if not (start_of_window <= event_start_date <= end_of_window):
                preview_events.append(event)
                continue

            start_dt = safe_parse_dt(event["start"])
            end_dt = safe_parse_dt(event["end"])
            if not start_dt or not end_dt:
                preview_events.append(event)
                continue

            duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
            category = event.get("category", "MEETING")
            calendar_optimiser.existing_events = [
                e
                for e in calendar_optimiser.existing_events
                if e.get("id") != event.get("id")
            ]

            best_slot = calendar_optimiser.find_best_slot(
                event_start_date,
                duration_minutes,
                category,
                original_start_dt=start_dt,
            )

            if best_slot:
                event["proposed_start"] = best_slot.start.astimezone(
                    dt.timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                event["proposed_end"] = best_slot.end.astimezone(
                    dt.timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                event["requires_review"] = True
                dummy_locked = dict(event)
                dummy_locked["start"] = event["proposed_start"]
                dummy_locked["end"] = event["proposed_end"]
                dummy_locked["is_locked"] = True
                calendar_optimiser.existing_events.append(dummy_locked)
            else:
                # No slot found — re-add event at its original time so later
                # events still respect this slot and don't overlap with it.
                original_locked = dict(event)
                original_locked["is_locked"] = True
                calendar_optimiser.existing_events.append(original_locked)

            preview_events.append(event)

        preview_events.extend(ghost_events)
        new_hash = _hash_event_list(preview_events)

        if original_hash == new_hash:
            return {
                "status": "already_optimised",
                "message": "Your calendar is already mathematically perfectly aligned with your preferences.",
                "preview_events": preview_events,
            }

        return {"status": "success", "preview_events": preview_events}

    except Exception as e:
        print(f"\n❌ [FATAL OPTIMISER ERROR] {e}\n")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate calendar optimisation preview",
        )


@router.post("/api/calendar/optimise/commit")
async def commit_optimisation(
    request: CommitOptimisationRequest,
    _token=Depends(verify_firebase_token),
):
    user_id = request.user_id
    proposed_events = request.events

    try:
        _create_calendar_snapshot(user_id)
        events_ref = (
            deps.db.collection("users").document(user_id).collection("raw_events")
        )
        batch = deps.db.batch()

        # Delete any stale ghost events left from previous uncommitted previews
        for ghost_doc in events_ref.where("is_ghost", "==", True).stream():
            batch.delete(ghost_doc.reference)

        for event in proposed_events:
            doc_id = event.pop("_id", None) or event.get("id")
            if not doc_id:
                continue
            if event.get("proposed_start") and event.get("proposed_end"):
                event["previous_start"] = event.get("start")
                event["previous_end"] = event.get("end")
                event["start"] = event["proposed_start"]
                event["end"] = event["proposed_end"]
                event["proposed_start"] = None
                event["proposed_end"] = None
            if event.get("is_ghost"):
                event["is_ghost"] = False
            event["sync_action_required"] = "push_to_provider"
            event["requires_review"] = False
            batch.set(events_ref.document(doc_id), event, merge=True)

        batch.commit()
        return {"status": "success", "message": "Optimisation committed and snapshot created."}
    except Exception as e:
        print(f"Error committing optimisation: {e}")
        raise HTTPException(status_code=500, detail="Failed to commit calendar changes")


@router.post("/api/calendar/snapshot/undo")
async def undo_last_change(
    request: UndoRequest,
    _token=Depends(verify_firebase_token),
):
    from google.cloud import firestore as gc_fs

    user_id = request.user_id
    try:
        snapshots_ref = (
            deps.db.collection("users")
            .document(user_id)
            .collection("calendar_snapshots")
        )
        latest_snapshots = (
            snapshots_ref.order_by(
                "created_at", direction=gc_fs.Query.DESCENDING
            )
            .limit(1)
            .get()
        )

        if not latest_snapshots:
            raise HTTPException(status_code=404, detail="No snapshot found to undo")

        latest_snapshot_doc = latest_snapshots[0]
        historical_events = latest_snapshot_doc.to_dict().get("events", [])

        events_ref = (
            deps.db.collection("users").document(user_id).collection("raw_events")
        )
        batch = deps.db.batch()
        for doc in events_ref.stream():
            batch.delete(doc.reference)

        for event in historical_events:
            doc_id = event.pop("_id", None) or event.get(
                "id", f"custom_{uuid.uuid4().hex[:8]}"
            )
            event["sync_action_required"] = "push_to_provider"
            batch.set(events_ref.document(doc_id), event)

        batch.delete(latest_snapshot_doc.reference)
        batch.commit()

        return {
            "status": "success",
            "message": f"Restored {len(historical_events)} events and removed snapshot from history.",
        }
    except Exception as e:
        print(f"Error during undo: {e}")
        raise HTTPException(status_code=500, detail="Failed to undo calendar changes")


@router.delete("/api/calendar/delete-event")
async def delete_event_endpoint(
    req: DeleteEventRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        doc_ref = (
            deps.db.collection("users")
            .document(req.user_id)
            .collection("raw_events")
            .document(req.event_id)
        )
        doc_snap = doc_ref.get()
        if not doc_snap.exists:
            raise HTTPException(status_code=404, detail="Event not found")

        event_data = doc_snap.to_dict()
        linked_task_id = event_data.get("linked_task_id")

        # Refund debt if this missed event had debt applied
        if event_data.get("completion_status") == "missed" and event_data.get("debt_applied"):
            ev_start = safe_parse_dt(event_data.get("start"))
            ev_end = safe_parse_dt(event_data.get("end"))
            if ev_start and ev_end:
                duration = int((ev_end - ev_start).total_seconds() / 60)
                capped = min(max(0, duration), 120)
                if capped > 0:
                    debt_field = "sunk_time_debt" if event_data.get("is_perishable") else "total_time_debt"
                    deps.db.collection("users").document(req.user_id).update(
                        {debt_field: fs.Increment(-capped)}
                    )
                    print(f"💰 Refunded {capped} mins on event deletion")

        doc_ref.delete()

        if linked_task_id:
            sync_task_with_events(req.user_id, linked_task_id)

        return {"status": "success", "message": "Event deleted successfully"}
    except Exception as e:
        print(f"Delete Endpoint Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/calendar/reschedule_debt/preview")
async def preview_reschedule_debt(
    req: ReschedulePreviewRequest,
    _token=Depends(verify_firebase_token),
):
    from task import DebtRescheduler

    user_id = req.user_id
    try:
        user_tz = get_user_timezone(user_id)
        now_local = dt.datetime.now(user_tz)
        target_date = now_local.date()

        events_ref = deps.db.collection("users").document(user_id).collection("raw_events")
        tasks_ref = deps.db.collection("users").document(user_id).collection("raw_tasks")
        prefs_ref = deps.db.collection("users").document(user_id).collection("preferences")

        preferences = [doc.to_dict() for doc in prefs_ref.stream()]
        existing_events = []
        for doc in events_ref.stream():
            e = doc.to_dict()
            e["id"] = doc.id
            existing_events.append(e)

        reschedule_queue = []

        for doc in events_ref.where("completion_status", "==", "missed").stream():
            event = doc.to_dict()
            if event.get("is_perishable") is True:
                continue
            if event.get("debt_applied") is False:
                continue
            if not event.get("parent_task_id"):
                es = parse_iso(event.get("start"))
                ee = parse_iso(event.get("end"))
                duration = max(0, int((ee - es).total_seconds() / 60) if es and ee else 60)
                reschedule_queue.append(
                    {
                        "id": doc.id,
                        "title": event.get("title", "Missed Event"),
                        "duration": duration,
                        "priority": 1,
                        "energy_level": "medium",
                        "original_type": "event",
                    }
                )

        for doc in tasks_ref.where("status", "==", "missed").stream():
            task = doc.to_dict()
            if task.get("is_perishable") is True:
                continue
            if task.get("debt_applied") is False:
                continue
            base_dur = task.get("estimated_duration") or 60
            allocated_mins = 0
            for eid in task.get("linked_event_ids", []):
                edoc = events_ref.document(eid).get()
                if edoc.exists:
                    edata = edoc.to_dict()
                    es = parse_iso(edata.get("start"))
                    ee = parse_iso(edata.get("end"))
                    if es and ee:
                        allocated_mins += int((ee - es).total_seconds() / 60)
            rem_dur = max(0, base_dur - allocated_mins)
            if rem_dur > 0:
                reschedule_queue.append(
                    {
                        "id": doc.id,
                        "title": task.get("title", "Missed Task"),
                        "duration": rem_dur,
                        "priority": task.get("priority", 3),
                        "energy_level": task.get("energy_level", "medium"),
                        "original_type": "task",
                    }
                )

        if not reschedule_queue:
            user_doc = deps.db.collection("users").document(user_id).get()
            global_debt = (
                user_doc.to_dict().get("total_time_debt", 0) if user_doc.exists else 0
            )
            if global_debt > 0:
                chunks = global_debt // 60
                remainder = global_debt % 60
                for i in range(int(chunks)):
                    reschedule_queue.append(
                        {
                            "id": f"orphan_{i}",
                            "title": "Reclaimed Focus Time",
                            "duration": 60,
                            "priority": 2,
                            "energy_level": "medium",
                            "original_type": "task",
                        }
                    )
                if remainder > 0:
                    reschedule_queue.append(
                        {
                            "id": "orphan_rem",
                            "title": "Reclaimed Focus Time",
                            "duration": remainder,
                            "priority": 2,
                            "energy_level": "medium",
                            "original_type": "task",
                        }
                    )
            else:
                return {
                    "status": "success",
                    "message": "No debt to reschedule.",
                    "preview_events": existing_events,
                    "original_events": existing_events,
                }

        user_doc_sched = deps.db.collection("users").document(user_id).get()
        user_settings_sched = user_doc_sched.to_dict() if user_doc_sched.exists else {}
        sched_window_days = int(user_settings_sched.get("optimisation_window_days", 7))
        schedule_on_weekends = bool(user_settings_sched.get("schedule_on_weekends", False))
        sched_start_hour = int(user_settings_sched.get("scheduling_start_hour", 8))
        sched_end_hour = int(user_settings_sched.get("scheduling_end_hour", 22))

        scheduler = DebtRescheduler(
            existing_events, preferences, user_tz_string=str(user_tz),
            skip_weekends=not schedule_on_weekends,
            scheduling_start_hour=sched_start_hour,
            scheduling_end_hour=sched_end_hour,
        )
        horizon_end = target_date + dt.timedelta(days=sched_window_days)
        ghosts = scheduler.schedule_debt(target_date, horizon_end, reschedule_queue)

        return {
            "status": "success",
            "original_events": existing_events,
            "preview_events": existing_events + ghosts,
        }
    except Exception as e:
        print(f"❌ [Preview Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/calendar/reschedule_debt/commit")
async def commit_reschedule_debt(
    req: RescheduleCommitRequest,
    _token=Depends(verify_firebase_token),
):
    from firebase_admin import firestore as fs

    user_id = req.user_id
    events = req.events

    try:
        debt_ghosts = [
            e
            for e in events
            if e.get("is_ghost") and e.get("id", "").startswith("ghost_debt_")
        ]
        if not debt_ghosts:
            return {"status": "success", "refunded_mins": 0}

        create_calendar_snapshot(user_id)

        batch = deps.db.batch()
        events_ref = (
            deps.db.collection("users").document(user_id).collection("raw_events")
        )
        tasks_ref = (
            deps.db.collection("users").document(user_id).collection("raw_tasks")
        )
        user_ref = deps.db.collection("users").document(user_id)

        total_refund = 0
        task_updates: dict = {}

        for ghost in debt_ghosts:
            ghost_dur = ghost.pop("debt_duration", 0)
            orig_task_id = ghost.get("linked_task_id")
            orig_event_id = ghost.get("linked_event_id")

            ghost.pop("is_ghost", None)
            ghost.pop("id", None)
            ghost["is_reclaimed_debt"] = True

            new_event_ref = events_ref.document()
            batch.set(new_event_ref, ghost)

            if orig_task_id and not orig_task_id.startswith("orphan_"):
                if orig_task_id not in task_updates:
                    task_updates[orig_task_id] = []
                task_updates[orig_task_id].append(new_event_ref.id)
                total_refund += ghost_dur
            elif orig_event_id and not orig_event_id.startswith("orphan_"):
                batch.update(
                    events_ref.document(orig_event_id),
                    {"debt_applied": False, "snooze_count": fs.Increment(1)},
                )
                total_refund += ghost_dur
            else:
                total_refund += ghost_dur

        for task_id, new_event_ids in task_updates.items():
            batch.update(
                tasks_ref.document(task_id),
                {
                    "linked_event_ids": fs.ArrayUnion(new_event_ids),
                    "status": "scheduled",
                    "debt_applied": False,
                    "snooze_count": fs.Increment(1),
                },
            )

        if total_refund > 0:
            user_doc_snap = user_ref.get()
            if user_doc_snap.exists:
                current_debt = user_doc_snap.to_dict().get("total_time_debt", 0)
                new_debt = max(0, current_debt - total_refund)
                batch.update(user_ref, {"total_time_debt": new_debt})

        batch.commit()
        return {"status": "success", "refunded_mins": total_refund}
    except Exception as e:
        print(f"❌ [Commit Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))
