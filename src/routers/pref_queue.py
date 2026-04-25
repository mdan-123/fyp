"""
Asynchronous preference-parsing queue.

Handles Gemini "resource exhausted" (429) errors by queuing jobs and
retrying with exponential backoff so every request eventually succeeds.

Usage
-----
1. Call `enqueue_job(raw_text, user_id, user_timezone)` → returns a job_id.
2. Call `get_job(job_id)` to poll status / result.
3. Start `worker()` as a background asyncio task at app startup.
"""

import asyncio
import uuid
import time
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------
# { job_id: { "status": "queued|processing|done|failed", "result": ...,
#             "error": ..., "created_at": ..., "updated_at": ... } }
_jobs: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# The queue itself  (each item is a job_id string)
# ---------------------------------------------------------------------------
_queue: asyncio.Queue = asyncio.Queue()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_RETRIES = 6          # max attempts before marking a job failed
BASE_BACKOFF = 2.0       # seconds; doubles each retry  (2, 4, 8, 16, 32, 64)
MAX_BACKOFF = 64.0       # cap on backoff seconds


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def enqueue_job(raw_text: str, user_id: str, user_timezone: str = "UTC") -> str:
    """Create a new pending job and add it to the queue. Returns the job_id."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "queued",
        "user_id": user_id,
        "raw_text": raw_text,
        "user_timezone": user_timezone,
        "result": None,
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _queue.put_nowait(job_id)
    print(f"[PrefQueue] Enqueued job {job_id} for user {user_id}")
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    """Return the job record or None if it doesn't exist."""
    return _jobs.get(job_id)


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

async def worker():
    """
    Processes jobs from the queue one at a time.

    On a Gemini "resource exhausted" (429) error, the job is retried
    with exponential backoff. All other exceptions mark the job failed.
    """
    import dependencies as deps  # imported here to avoid circular imports

    print("[PrefQueue] Worker started.")
    loop = asyncio.get_event_loop()

    while True:
        job_id = await _queue.get()
        job = _jobs.get(job_id)

        if job is None:
            _queue.task_done()
            continue

        job["status"] = "processing"
        job["updated_at"] = _now()

        attempt = 0
        success = False

        while attempt < MAX_RETRIES:
            try:
                print(f"[PrefQueue] Processing job {job_id} (attempt {attempt + 1})")

                # nlu_engine.process() is synchronous & CPU-bound – run in
                # thread pool so we don't block the event loop.
                result = await loop.run_in_executor(
                    None,
                    lambda: deps.nlu_engine.process(
                        job["raw_text"],
                        job["user_id"],
                        "",
                        job["user_timezone"],
                    ),
                )

                intent = result.get("intent") if result else None
                entities = (result.get("entities", {}) if result else {})
                raw_preferences = entities.get("preferences", [])

                if intent != "SET_PREFERENCES" or not raw_preferences:
                    # Valid response, just nothing to save
                    job["status"] = "done"
                    job["result"] = {
                        "status": "no_preference",
                        "message": "No preferences detected in input.",
                        "saved_preferences": [],
                    }
                else:
                    # Persist to Firestore
                    prefs_ref = (
                        deps.db.collection("users")
                        .document(job["user_id"])
                        .collection("preferences")
                    )
                    saved = []
                    for pref in raw_preferences:
                        new_ref = prefs_ref.document()
                        new_ref.set(pref)
                        saved.append({"id": new_ref.id, **pref})

                    job["status"] = "done"
                    job["result"] = {
                        "status": "success",
                        "saved_preferences": saved,
                    }

                job["updated_at"] = _now()
                success = True
                print(f"[PrefQueue] Job {job_id} completed successfully.")
                break

            except Exception as exc:
                err_str = str(exc).lower()

                if "resource_exhausted" in err_str or "429" in err_str or "quota" in err_str:
                    backoff = min(BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                    attempt += 1
                    print(
                        f"[PrefQueue] Job {job_id} hit resource exhausted "
                        f"(attempt {attempt}/{MAX_RETRIES}). "
                        f"Retrying in {backoff:.0f}s…"
                    )
                    await asyncio.sleep(backoff)
                else:
                    # Non-retryable error
                    print(f"[PrefQueue] Job {job_id} failed with non-retryable error: {exc}")
                    job["status"] = "failed"
                    job["error"] = str(exc)
                    job["updated_at"] = _now()
                    break

        if not success and job["status"] != "failed":
            print(f"[PrefQueue] Job {job_id} exhausted all retries.")
            job["status"] = "failed"
            job["error"] = "Gemini API resource exhausted after maximum retries."
            job["updated_at"] = _now()

        _queue.task_done()
