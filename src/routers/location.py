"""
Location routes: travel-time (Google Routes API).
"""
import math

import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import dependencies as deps
from dependencies import verify_firebase_token

router = APIRouter()


class TravelTimeRequest(BaseModel):
    origin: str
    destination: str
    mode: str = "driving"


@router.post("/api/location/travel-time")
async def calculate_travel_time(
    req: TravelTimeRequest,
    _token=Depends(verify_firebase_token),
):
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    mode_map = {"driving": "DRIVE", "walking": "WALK", "cycling": "BICYCLE", "transit": "TRANSIT"}
    google_mode = mode_map.get(req.mode.lower(), "DRIVE")

    payload = {
        "origin": {"address": req.origin},
        "destination": {"address": req.destination},
        "travelMode": google_mode,
    }
    if google_mode == "DRIVE":
        payload["routingPreference"] = "TRAFFIC_AWARE"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": deps.GOOGLE_API_KEY,
        "X-Goog-FieldMask": "routes.duration",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            data = response.json()
            if "routes" not in data or len(data["routes"]) == 0:
                raise HTTPException(status_code=400, detail="Could not find a route for this mode of transport")
            duration_string = data["routes"][0].get("duration", "0s")
            seconds = int(duration_string.replace("s", ""))
            return {"status": "success", "minutes": math.ceil(seconds / 60)}
        except httpx.RequestError as e:
            print(f"Error calling Google Routes API: {e}")
            raise HTTPException(status_code=500, detail="Failed to calculate travel time")
