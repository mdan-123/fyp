"""
Tasks routes: create, list, update, delete, duration estimation,
schedule preview, schedule commit.
"""
import uuid
import datetime as dt
from datetime import timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from firebase_admin import firestore as fs

import dependencies as deps
from dependencies import verify_firebase_token, parse_iso, get_user_timezone

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SubTask(BaseModel):
    id: str
    title: str
    is_completed: bool = False


class TaskRequest(BaseModel):
    id: Optional[str] = None
    user_id: str
    title: str
    description: Optional[str] = ""
    sub_tasks: List[SubTask] = []
    estimated_duration: Optional[int] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    status: str = "pending"
    priority: int = 3
    energy_level: Optional[str] = "medium"
    tags: List[str] = []
    linked_event_id: Optional[str] = None
    linked_reminder_ids: List[str] = []
    is_locked: bool = False
    created_at: Optional[str] = None
    snooze_count: int = 0
    completed_at: Optional[str] = None
    debt_applied: bool = False
    is_perishable: bool = False


class TaskUpdate(BaseModel):
    id: str
    user_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    sub_tasks: Optional[List[Dict[str, Any]]] = None
    estimated_duration: Optional[int] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    energy_level: Optional[str] = None
    tags: Optional[List[str]] = None
    linked_event_ids: Optional[List[str]] = None
    snooze_count: Optional[int] = None
    completed_at: Optional[str] = None
    debt_applied: Optional[bool] = None
    is_perishable: Optional[bool] = None


class DeleteTaskRequest(BaseModel):
    user_id: str
    task_id: str


class TaskScheduleRequest(BaseModel):
    user_id: str
    target_date: str
    task_ids: List[str] = []


class TaskScheduleCommitRequest(BaseModel):
    user_id: str
    events: List[Dict[str, Any]]


class EstimateRequest(BaseModel):
    title: str
    description: Optional[str] = ""


# ---------------------------------------------------------------------------
# Risk scoring helper (heuristic-based, not the ML model)
# ---------------------------------------------------------------------------

def _calculate_risk_score(task_data: dict, global_time_debt: int) -> int:
    if task_data.get("status") not in ["pending", "scheduled"]:
        return 0
    priority = task_data.get("priority", 3)
    base_risk = {1: 40, 2: 30, 3: 20, 4: 10, 5: 5}.get(priority, 20)
    snooze_penalty = task_data.get("snooze_count", 0) * 15
    debt_penalty = (max(0, global_time_debt) // 60) * 5
    duration_penalty = 10 if (task_data.get("estimated_duration") or 60) > 60 else 0
    return max(0, min(100, base_risk + snooze_penalty + debt_penalty + duration_penalty))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/tasks/create")
async def create_task(
    task: TaskRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        task_id = f"task_{uuid.uuid4().hex[:10]}"
        task_data = task.model_dump()
        task_data["id"] = task_id
        task_data["created_at"] = (
            dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        for sub in task_data.get("sub_tasks", []):
            if not sub.get("id"):
                sub["id"] = f"sub_{uuid.uuid4().hex[:8]}"

        deps.db.collection("users").document(task.user_id).collection(
            "raw_tasks"
        ).document(task_id).set(task_data)

        return {"status": "success", "task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tasks/list/{user_id}")
async def list_tasks(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        user_doc = deps.db.collection("users").document(user_id).get()
        global_debt = 0
        if user_doc.exists:
            global_debt = user_doc.to_dict().get("total_time_debt", 0)

        tasks_ref = (
            deps.db.collection("users").document(user_id).collection("raw_tasks")
        )
        tasks = []
        for doc in tasks_ref.stream():
            t_data = doc.to_dict()
            t_data["risk_score"] = _calculate_risk_score(t_data, global_debt)
            tasks.append(t_data)

        tasks.sort(
            key=lambda x: (-x.get("risk_score", 0), x.get("due_date") or "9999")
        )
        return {"status": "success", "tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/tasks/update")
async def update_task(
    task: TaskUpdate,
    _token=Depends(verify_firebase_token),
):
    try:
        task_ref = (
            deps.db.collection("users")
            .document(task.user_id)
            .collection("raw_tasks")
            .document(task.id)
        )
        existing_task_doc = task_ref.get()
        if not existing_task_doc.exists:
            raise HTTPException(status_code=404, detail="Task not found")

        existing_data = existing_task_doc.to_dict()
        old_status = existing_data.get("status")
        update_data = task.dict(exclude={"id", "user_id"}, exclude_none=True)

        old_due = parse_iso(existing_data.get("due_date"))
        new_due = parse_iso(task.due_date if task.due_date is not None else existing_data.get("due_date"))
        snooze_increment = 1 if (old_due and new_due and new_due > old_due) else 0
        update_data["snooze_count"] = (
            existing_data.get("snooze_count", 0) + snooze_increment
        )

        debt_applied = existing_data.get("debt_applied", False)
        is_perish = existing_data.get("is_perishable", False)

        if old_status == "missed" and snooze_increment > 0:
            if task.status not in ["completed", "missed"]:
                update_data["status"] = "pending"

            if debt_applied and not is_perish:
                refund_mins = 0
                est_dur = existing_data.get("estimated_duration")
                if est_dur:
                    refund_mins = est_dur
                else:
                    linked_evs = existing_data.get("linked_event_ids", [])
                    if linked_evs:
                        ev_ref = (
                            deps.db.collection("users")
                            .document(task.user_id)
                            .collection("raw_events")
                        )
                        for eid in linked_evs:
                            edoc = ev_ref.document(eid).get()
                            if edoc.exists:
                                edata = edoc.to_dict()
                                if edata.get("completion_status") == "missed":
                                    es = parse_iso(edata.get("start"))
                                    ee = parse_iso(edata.get("end"))
                                    if es and ee:
                                        refund_mins += int(
                                            (ee - es).total_seconds() / 60
                                        )
                if refund_mins > 0:
                    deps.db.collection("users").document(task.user_id).update(
                        {"total_time_debt": fs.Increment(-refund_mins)}
                    )
                    print(f"💰 Refunded {refund_mins} minutes of Task Time Debt")

            update_data["debt_applied"] = False

        new_status = update_data.get("status", old_status)
        if new_status == "completed" and old_status != "completed":
            update_data["completed_at"] = (
                dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        elif new_status != "completed":
            update_data["completed_at"] = None

        if new_status == "completed" and old_status != "completed":
            linked_event_ids = existing_data.get("linked_event_ids", [])
            if linked_event_ids:
                events_ref = (
                    deps.db.collection("users")
                    .document(task.user_id)
                    .collection("raw_events")
                )
                now = dt.datetime.now(timezone.utc)
                batch = deps.db.batch()
                events_deleted = 0
                events_to_keep = []

                for event_id in linked_event_ids:
                    event_doc = events_ref.document(event_id).get()
                    if event_doc.exists:
                        event_data = event_doc.to_dict()
                        event_start_str = event_data.get("start")
                        if event_start_str:
                            start_dt = dt.datetime.fromisoformat(
                                event_start_str.replace("Z", "+00:00")
                            )
                            if start_dt > now:
                                batch.delete(events_ref.document(event_id))
                                events_deleted += 1
                            else:
                                events_to_keep.append(event_id)
                        else:
                            events_to_keep.append(event_id)

                if events_deleted > 0:
                    batch.commit()
                    update_data["linked_event_ids"] = events_to_keep

        task_ref.update(update_data)
        return {"status": "success", "message": "Task updated successfully"}

    except Exception as e:
        print(f"Error updating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/tasks/delete")
async def delete_task(
    request: DeleteTaskRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        deps.db.collection("users").document(request.user_id).collection(
            "raw_tasks"
        ).document(request.task_id).delete()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/tasks/estimate-duration")
async def estimate_duration(
    req: EstimateRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        minutes = deps.estimator.estimate(req.title, req.description)
        return {"status": "success", "estimated_minutes": minutes}
    except Exception as e:
        return {"status": "error", "estimated_minutes": 60, "detail": str(e)}


@router.post("/api/tasks/schedule/preview")
async def preview_task_scheduling(
    request: TaskScheduleRequest,
    _token=Depends(verify_firebase_token),
):
    from datetime import timedelta
    from task import TaskScheduler

    user_id = request.user_id
    try:
        clean_date_str = request.target_date[:10]
        target_date = dt.datetime.fromisoformat(clean_date_str).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format.")

    try:
        user_tz = get_user_timezone(user_id)
        prefs_ref = (
            deps.db.collection("users").document(user_id).collection("preferences")
        )
        preferences = [doc.to_dict() for doc in prefs_ref.stream()]

        events_ref = (
            deps.db.collection("users").document(user_id).collection("raw_events")
        )
        existing_events = []
        for doc in events_ref.stream():
            event_data = doc.to_dict()
            event_data["id"] = doc.id
            existing_events.append(event_data)

        tasks_ref = (
            deps.db.collection("users").document(user_id).collection("raw_tasks")
        )
        tasks_stream = tasks_ref.where("status", "in", ["pending"]).stream()
        if request.task_ids:
            pending_tasks = [
                doc.to_dict()
                for doc in tasks_stream
                if doc.id in request.task_ids
            ]
        else:
            pending_tasks = [doc.to_dict() for doc in tasks_stream]

        task_scheduler = TaskScheduler(
            existing_events, preferences, user_tz_string=str(user_tz)
        )
        horizon_end = target_date + timedelta(days=14)
        task_ghosts = task_scheduler.schedule_tasks(
            target_date, horizon_end, pending_tasks
        )

        return {
            "status": "success",
            "original_events": existing_events,
            "preview_events": existing_events + task_ghosts,
        }
    except Exception as e:
        print(f"Error during task scheduling preview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/tasks/schedule/commit")
async def commit_task_schedule(
    request: TaskScheduleCommitRequest,
    _token=Depends(verify_firebase_token),
):
    user_id = request.user_id
    events = request.events

    try:
        task_ghosts = [
            e
            for e in events
            if e.get("is_ghost") and e.get("provider") == "tasks"
        ]
        if not task_ghosts:
            return {"status": "success", "message": "No new tasks to schedule."}

        task_event_map: dict = {}
        batch = deps.db.batch()

        events_ref = (
            deps.db.collection("users").document(user_id).collection("raw_events")
        )

        for ghost in task_ghosts:
            task_id = ghost.get("linked_task_id")
            if not task_id:
                continue
            event_data = dict(ghost)
            event_data.pop("is_ghost", None)
            event_data.pop("id", None)
            event_data["linked_task_id"] = task_id

            new_event_ref = events_ref.document()
            new_event_id = new_event_ref.id
            batch.set(new_event_ref, event_data)

            if task_id not in task_event_map:
                task_event_map[task_id] = []
            task_event_map[task_id].append(new_event_id)

        tasks_ref = (
            deps.db.collection("users").document(user_id).collection("raw_tasks")
        )
        for task_id, event_ids in task_event_map.items():
            batch.update(
                tasks_ref.document(task_id),
                {
                    "linked_event_ids": fs.ArrayUnion(event_ids),
                    "status": "scheduled",
                },
            )

        batch.commit()
        return {
            "status": "success",
            "message": (
                f"Successfully scheduled {len(task_ghosts)} events "
                f"for {len(task_event_map)} tasks."
            ),
        }
    except Exception as e:
        print(f"Error committing task schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))
