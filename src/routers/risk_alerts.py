"""
Background risk-alert scanner + dismiss endpoint.

The worker runs every 30 minutes, scores every user's pending/scheduled tasks
against the ML risk model, and writes a Firestore document to
  users/{uid}/risk_alerts
for any task that crosses the HIGH threshold.

Deduplication: a task will not produce a new alert if one already exists for it
in the last 24 hours (regardless of status), preventing notification spam.

The frontend's NotificationProvider listens to this collection in real-time and
fires a toast / iOS local notification when a new document appears.
"""

import asyncio
import datetime as dt
from collections import defaultdict
from datetime import timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import dependencies as deps
from dependencies import parse_iso, get_user_timezone, verify_firebase_token

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AlertStatusUpdate(BaseModel):
    user_id: str
    alert_id: str
    status: str  # "delivered" | "dismissed"


# ---------------------------------------------------------------------------
# Dismiss / deliver endpoint
# ---------------------------------------------------------------------------

@router.put("/api/risk-alerts/update")
async def update_risk_alert(
    req: AlertStatusUpdate,
    _token=Depends(verify_firebase_token),
):
    if req.status not in ("delivered", "dismissed"):
        raise HTTPException(status_code=400, detail="status must be 'delivered' or 'dismissed'")
    try:
        alert_ref = (
            deps.db.collection("users")
            .document(req.user_id)
            .collection("risk_alerts")
            .document(req.alert_id)
        )
        if not alert_ref.get().exists:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert_ref.update({"status": req.status})
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RiskAlert Update Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

async def risk_alert_worker():
    """Async background task: scan all users every 30 minutes for HIGH-risk tasks."""
    # Small initial delay so the app finishes booting before the first scan
    await asyncio.sleep(60)
    while True:
        try:
            await _scan_all_users()
        except Exception as e:
            print(f"[RiskAlertWorker] Unhandled error during scan: {e}")
        await asyncio.sleep(30 * 60)  # 30-minute cadence


async def _scan_all_users():
    from routers.analytics import _predict_risk  # local import to avoid circular deps

    if not deps.ai_model or not deps.ai_explainer or not deps.ai_meta:
        print("[RiskAlertWorker] AI model not loaded, skipping scan.")
        return

    now_dt = dt.datetime.now(timezone.utc)
    print(f"[RiskAlertWorker] Starting scan at {now_dt.isoformat()}")
    scanned = alerted = 0

    try:
        users_stream = list(deps.db.collection("users").stream())
    except Exception as e:
        print(f"[RiskAlertWorker] Failed to stream users: {e}")
        return

    for user_doc in users_stream:
        user_id = user_doc.id
        try:
            n = await _scan_user(user_id, user_doc.to_dict(), now_dt)
            scanned += 1
            alerted += n
        except Exception as e:
            print(f"[RiskAlertWorker] Error scanning user {user_id}: {e}")

    print(f"[RiskAlertWorker] Scan complete. Users={scanned}, Alerts written={alerted}")


async def _scan_user(user_id: str, user_data: dict, now_dt: dt.datetime) -> int:
    """Score a single user's tasks. Returns number of new alerts written."""
    from routers.analytics import _predict_risk

    user_tz = get_user_timezone(user_id)
    global_debt = float(user_data.get("total_time_debt") or 0)

    tasks_ref = deps.db.collection("users").document(user_id).collection("raw_tasks")
    alerts_ref = deps.db.collection("users").document(user_id).collection("risk_alerts")

    # Fetch pending / scheduled tasks
    all_tasks = []
    for doc in tasks_ref.where("status", "in", ["pending", "scheduled"]).stream():
        t = doc.to_dict()
        t["_doc_id"] = doc.id
        all_tasks.append(t)

    if not all_tasks:
        return 0

    # Count tasks per local due-date (needed for same-day load feature)
    tasks_per_day: dict = defaultdict(int)
    for t in all_tasks:
        due_dt = parse_iso(t.get("due_date"))
        if due_dt:
            tasks_per_day[due_dt.astimezone(user_tz).strftime("%Y-%m-%d")] += 1

    # Build deduplication set: task IDs alerted in the last 24 hours
    cutoff_24h = now_dt - dt.timedelta(hours=24)
    alerted_task_ids: set = set()
    for doc in alerts_ref.stream():
        a = doc.to_dict()
        created = parse_iso(a.get("created_at"))
        if created and created > cutoff_24h and a.get("task_id"):
            alerted_task_ids.add(a["task_id"])

    new_alerts = 0
    for task in all_tasks:
        task_id = task.get("id") or task.get("_doc_id")
        if not task_id or task_id in alerted_task_ids:
            continue

        due_dt = parse_iso(task.get("due_date")) or now_dt
        created_dt = parse_iso(task.get("created_at")) or now_dt
        local_due_dt = due_dt.astimezone(user_tz)

        raw_energy = task.get("energy_level")
        if isinstance(raw_energy, str):
            clean_energy = {"low": 1, "medium": 2, "high": 3}.get(raw_energy.lower(), 2)
        else:
            clean_energy = int(raw_energy) if isinstance(raw_energy, (int, float)) else 2

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
        except Exception as e:
            print(f"[RiskAlertWorker] Inference error for task {task_id}: {e}")
            continue

        if result["risk_label"] != "HIGH":
            continue

        alert_doc = {
            "task_id": task_id,
            "task_title": task.get("title", "Untitled Task"),
            "task_due_date": task.get("due_date"),
            "risk_score": int(result["risk_score"] * 100),
            "risk_label": "HIGH",
            "explanations": result["explanations"][:3],
            "status": "pending",
            "created_at": now_dt.isoformat() + "Z",
        }
        alerts_ref.document().set(alert_doc)
        alerted_task_ids.add(task_id)  # prevent double-alerting same task in same scan
        new_alerts += 1
        print(f"[RiskAlertWorker] HIGH alert → user={user_id}, task={task_id}")

    return new_alerts
