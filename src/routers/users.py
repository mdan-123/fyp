"""
Users routes: timezone, profile, linked-accounts, show-weekends.
"""
import zoneinfo

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import dependencies as deps
from dependencies import verify_firebase_token

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TimezoneUpdateRequest(BaseModel):
    user_id: str
    timezone: str


class ShowWeekendsRequest(BaseModel):
    user_id: str
    show_weekends: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/users/timezone")
async def update_user_timezone(
    req: TimezoneUpdateRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        try:
            zoneinfo.ZoneInfo(req.timezone)
        except zoneinfo.ZoneInfoNotFoundError:
            raise HTTPException(status_code=400, detail="Invalid IANA timezone string.")

        deps.db.collection("users").document(req.user_id).set({"timezone": req.timezone}, merge=True)
        return {"status": "success", "message": "Timezone updated successfully.", "timezone": req.timezone}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Timezone Update Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/users/profile/{user_id}")
async def get_user_profile(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        user_doc = deps.db.collection("users").document(user_id).get()
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        data = user_doc.to_dict()
        return {
            "status": "success",
            "linked_accounts": [
                {"provider": acc.get("provider"), "email": acc.get("email")}
                for acc in data.get("linked_accounts", [])
            ],
            "preferences": data.get("preferences", []),
            "timezone": data.get("timezone", "UTC"),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching profile for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user profile")


@router.get("/api/users/linked-accounts/{user_id}")
async def get_linked_accounts(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        user_doc = deps.db.collection("users").document(user_id).get()
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        accounts = user_doc.to_dict().get("linked_accounts", [])
        return {
            "status": "success",
            "linked_accounts": [
                {"provider": acc.get("provider"), "email": acc.get("email")}
                for acc in accounts
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching linked accounts for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch linked accounts")


@router.post("/api/users/show-weekends")
async def set_show_weekends(
    req: ShowWeekendsRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        deps.db.collection("users").document(req.user_id).set(
            {"show_weekends": req.show_weekends}, merge=True
        )
        return {"status": "success", "show_weekends": req.show_weekends}
    except Exception as e:
        print(f"[ShowWeekends] Error for {req.user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/users/show-weekends/{user_id}")
async def get_show_weekends(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        user_doc = deps.db.collection("users").document(user_id).get()
        if not user_doc.exists:
            return {"status": "success", "show_weekends": True}
        return {"status": "success", "show_weekends": user_doc.to_dict().get("show_weekends", True)}
    except Exception as e:
        print(f"[ShowWeekends] Error fetching for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
