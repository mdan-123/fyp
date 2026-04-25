"""
Preferences routes: parse (NLU, async-queued), list, delete, job status.

POST /api/preferences/parse   → enqueues a job, returns job_id immediately.
GET  /api/preferences/job/{job_id} → poll for job completion / result.
"""
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

import dependencies as deps
from dependencies import verify_firebase_token
from routers import pref_queue

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ParsePreferencesRequest(BaseModel):
    user_id: str
    raw_text: str
    user_timezone: Optional[str] = "UTC"


class DeletePreferenceRequest(BaseModel):
    user_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/preferences/parse")
async def parse_preferences(
    req: ParsePreferencesRequest,
    _token=Depends(verify_firebase_token),
):
    """
    Enqueue a preference-parsing job and return a job_id immediately.
    The heavy Gemini call happens in the background worker, which retries
    automatically on resource-exhausted (429) errors.
    """
    job_id = pref_queue.enqueue_job(req.raw_text, req.user_id, req.user_timezone or "UTC")
    return {"status": "queued", "job_id": job_id}


@router.get("/api/preferences/job/{job_id}")
async def get_preference_job(
    job_id: str,
    _token=Depends(verify_firebase_token),
):
    """
    Poll for the result of a queued preference-parsing job.

    Possible `status` values:
    - "queued"      – waiting in the queue
    - "processing"  – currently being handled by the worker
    - "done"        – completed; `result` contains the saved preferences
    - "failed"      – all retries exhausted; `error` describes the cause
    """
    job = pref_queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": job["status"],
        "result": job.get("result"),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }


@router.get("/api/preferences/list")
async def list_preferences(
    userId: str = Query(..., alias="userId"),
    _token=Depends(verify_firebase_token),
):
    try:
        prefs_ref = (
            deps.db.collection("users").document(userId).collection("preferences")
        )
        preferences = []
        for doc in prefs_ref.stream():
            data = doc.to_dict()
            data["id"] = doc.id
            preferences.append(data)
        return {"status": "success", "preferences": preferences}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/preferences/{pref_id}")
async def delete_preference(
    pref_id: str,
    userId: str = Query(..., alias="userId"),
    _token=Depends(verify_firebase_token),
):
    try:
        (
            deps.db.collection("users")
            .document(userId)
            .collection("preferences")
            .document(pref_id)
            .delete()
        )
        return {"status": "success", "message": "Preference deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
