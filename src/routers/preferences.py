"""
Preferences routes: parse (NLU), list, delete.
"""
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

import dependencies as deps
from dependencies import verify_firebase_token

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
    try:
        result = await deps.nlu_engine.process(req.raw_text, req.user_id, req.user_timezone)
        intent = result.get("intent")
        entities = result.get("entities", {})
        raw_preferences = entities.get("preferences", [])

        if intent != "SET_PREFERENCES" or not raw_preferences:
            return {
                "status": "no_preference",
                "message": "No preferences detected in input.",
            }

        prefs_ref = (
            deps.db.collection("users").document(req.user_id).collection("preferences")
        )
        saved = []
        for pref in raw_preferences:
            new_ref = prefs_ref.document()
            new_ref.set(pref)
            saved.append({"id": new_ref.id, **pref})

        return {"status": "success", "saved_preferences": saved}
    except Exception as e:
        print(f"Error parsing preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
