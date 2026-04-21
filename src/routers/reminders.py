"""
Reminders routes: create, list, update, delete.
"""
import datetime as dt
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from firebase_admin import firestore as fs

import dependencies as deps
from dependencies import verify_firebase_token

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class LocationData(BaseModel):
    lat: float
    lng: float
    radius: float
    trigger_on: str


class ReminderCreate(BaseModel):
    user_id: str
    title: str
    body: Optional[str] = None
    type: str
    reference_id: Optional[str] = None
    trigger_type: str
    trigger_time: Optional[str] = None
    location_data: Optional[LocationData] = None
    priority: str = "standard"
    repeat: str = "none"
    custom_repeat_days: Optional[List[str]] = None


class ReminderUpdate(BaseModel):
    id: str
    user_id: str
    title: Optional[str] = None
    body: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_time: Optional[str] = None
    location_data: Optional[LocationData] = None
    priority: Optional[str] = None
    repeat: Optional[str] = None
    status: Optional[str] = None
    custom_repeat_days: Optional[List[str]] = None


class ReminderDelete(BaseModel):
    user_id: str
    reminder_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/reminders/create")
async def create_reminder(
    req: ReminderCreate,
    _token=Depends(verify_firebase_token),
):
    try:
        batch = deps.db.batch()

        reminders_ref = (
            deps.db.collection("users").document(req.user_id).collection("reminders")
        )
        new_reminder_ref = reminders_ref.document()

        reminder_data = req.dict(exclude_none=True)
        reminder_data["status"] = "pending"
        reminder_data["created_at"] = (
            dt.datetime.now(dt.timezone.utc).isoformat() + "Z"
        )
        batch.set(new_reminder_ref, reminder_data)

        if req.reference_id and req.type in ["task", "event"]:
            collection_name = "raw_tasks" if req.type == "task" else "raw_events"
            parent_ref = (
                deps.db.collection("users")
                .document(req.user_id)
                .collection(collection_name)
                .document(req.reference_id)
            )
            batch.update(
                parent_ref,
                {"linked_reminder_ids": fs.ArrayUnion([new_reminder_ref.id])},
            )

        batch.commit()
        return {
            "status": "success",
            "message": "Reminder created and linked successfully",
            "reminder_id": new_reminder_ref.id,
        }
    except Exception as e:
        print(f"Error creating reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/reminders/list/{user_id}")
async def list_reminders(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        reminders_ref = (
            deps.db.collection("users").document(user_id).collection("reminders")
        )
        reminders = []
        for doc in reminders_ref.stream():
            data = doc.to_dict()
            data["id"] = doc.id
            reminders.append(data)

        reminders.sort(key=lambda x: x.get("trigger_time") or "9999-12-31")
        return {"status": "success", "reminders": reminders}
    except Exception as e:
        print(f"Error fetching reminders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/reminders/update")
async def update_reminder(
    req: ReminderUpdate,
    _token=Depends(verify_firebase_token),
):
    try:
        reminder_ref = (
            deps.db.collection("users")
            .document(req.user_id)
            .collection("reminders")
            .document(req.id)
        )
        if not reminder_ref.get().exists:
            raise HTTPException(status_code=404, detail="Reminder not found")

        update_data = req.dict(exclude={"id", "user_id"}, exclude_none=True)
        update_data["updated_at"] = (
            dt.datetime.now(dt.timezone.utc).isoformat() + "Z"
        )
        reminder_ref.update(update_data)
        return {"status": "success", "message": "Reminder updated successfully"}
    except Exception as e:
        print(f"Error updating reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/reminders/delete")
async def delete_reminder(
    req: ReminderDelete,
    _token=Depends(verify_firebase_token),
):
    try:
        reminder_ref = (
            deps.db.collection("users")
            .document(req.user_id)
            .collection("reminders")
            .document(req.reminder_id)
        )
        reminder_doc = reminder_ref.get()
        if not reminder_doc.exists:
            return {"status": "success", "message": "Reminder already deleted"}

        reminder_data = reminder_doc.to_dict()
        batch = deps.db.batch()
        batch.delete(reminder_ref)

        ref_id = reminder_data.get("reference_id")
        ref_type = reminder_data.get("type")
        if ref_id and ref_type in ["task", "event"]:
            collection_name = "raw_tasks" if ref_type == "task" else "raw_events"
            parent_ref = (
                deps.db.collection("users")
                .document(req.user_id)
                .collection(collection_name)
                .document(ref_id)
            )
            if parent_ref.get().exists:
                batch.update(
                    parent_ref,
                    {
                        "linked_reminder_ids": fs.ArrayRemove([req.reminder_id])
                    },
                )

        batch.commit()
        return {
            "status": "success",
            "message": "Reminder deleted and unlinked successfully",
        }
    except Exception as e:
        print(f"Error deleting reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))
