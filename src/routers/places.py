"""
Places routes: autocomplete, details (Google Maps).
Public endpoints — no auth token required (called before user context).
"""
import requests

from fastapi import APIRouter, HTTPException

import dependencies as deps

router = APIRouter()


@router.get("/api/places/autocomplete")
async def autocomplete_places(query: str):
    if not query:
        return {"predictions": []}
    url = (
        f"https://maps.googleapis.com/maps/api/place/autocomplete/json"
        f"?input={query}&key={deps.GOOGLE_MAPS_API_KEY}"
    )
    try:
        response = requests.get(url)
        data = response.json()
        return {"predictions": data.get("predictions", [])}
    except Exception as e:
        print(f"Places API error: {e}")
        return {"predictions": []}


@router.get("/api/places/details")
async def get_place_details(place_id: str):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {"place_id": place_id, "fields": "geometry", "key": deps.GOOGLE_MAPS_API_KEY}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "OK":
            raise HTTPException(status_code=400, detail=f"Google Maps API error: {data.get('status')}")
        location = data.get("result", {}).get("geometry", {}).get("location")
        if not location:
            raise HTTPException(status_code=404, detail="Location details not found")
        return {"status": "success", "location": location}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching place details: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch location details")
