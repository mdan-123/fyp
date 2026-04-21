"""
Search route: unified global search across events, tasks, reminders.
"""
from typing import Literal

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import dependencies as deps
from dependencies import verify_firebase_token

router = APIRouter()


class GlobalSearchRequest(BaseModel):
    user_id: str
    query: str
    search_type: Literal["events", "tasks", "reminders", "all"]


@router.post("/api/search")
async def global_search(
    req: GlobalSearchRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        q_lower = req.query.lower().strip()
        if not q_lower:
            return {"status": "success", "results": []}

        results = []
        collections_to_search = []
        if req.search_type in ["events", "all"]:
            collections_to_search.append(("raw_events", "event"))
        if req.search_type in ["tasks", "all"]:
            collections_to_search.append(("raw_tasks", "task"))
        if req.search_type in ["reminders", "all"]:
            collections_to_search.append(("reminders", "reminder"))

        for coll_name, item_type in collections_to_search:
            docs = deps.db.collection("users").document(req.user_id).collection(coll_name).stream()
            for doc in docs:
                data = doc.to_dict()
                search_string = f"{data.get('title', '')} {data.get('description', '')} {data.get('body', '')}".lower()
                if q_lower in search_string:
                    result_item = {
                        "id": doc.id,
                        "type": item_type,
                        "title": data.get("title", ""),
                        "status": data.get("status") or data.get("completion_status", "pending"),
                        "created_at": data.get("created_at", ""),
                    }
                    if item_type == "event":
                        result_item["start"] = data.get("start")
                        result_item["end"] = data.get("end")
                        result_item["location"] = data.get("location")
                        result_item["category"] = data.get("category")
                    elif item_type == "task":
                        result_item["due_date"] = data.get("due_date")
                        result_item["priority"] = data.get("priority")
                        result_item["estimated_duration"] = data.get("estimated_duration")
                        result_item["energy_level"] = data.get("energy_level")
                    elif item_type == "reminder":
                        result_item["trigger_time"] = data.get("trigger_time")
                        result_item["trigger_type"] = data.get("trigger_type")
                        result_item["priority"] = data.get("priority")
                        result_item["repeat"] = data.get("repeat")
                    results.append(result_item)

        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"status": "success", "results": results[:15]}
    except Exception as e:
        print(f"[GlobalSearch] Error: {e}")
        raise HTTPException(status_code=500, detail="Search failed")
