"""
Shared dependencies, helpers, and mutable global state for all routers.
Initialised once at startup by main.py and imported by each router.
"""
import os
import re
import json
import datetime as dt
from datetime import timezone
import zoneinfo

import firebase_admin
from firebase_admin import credentials, auth, firestore
from fastapi import HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends

# ---------------------------------------------------------------------------
# Firebase / Firestore client (set during app startup in main.py)
# ---------------------------------------------------------------------------
db: firestore.Client = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Security helper
# ---------------------------------------------------------------------------
_security = HTTPBearer()


def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    """Dependency that validates a Firebase ID token from the Authorization header."""
    token = credentials.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
        )


# ---------------------------------------------------------------------------
# Mutable AI engine globals (populated in main.py lifespan)
# ---------------------------------------------------------------------------
nlu_engine = None
routing_engine = None
db_engine = None

ai_model = None
ai_explainer = None
ai_meta = None

estimator = None  # DurationEstimator instance


# ---------------------------------------------------------------------------
# Environment / API keys
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

OUTLOOK_CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
OUTLOOK_CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
OUTLOOK_AUTHORITY = "https://login.microsoftonline.com/common"
OUTLOOK_SCOPES = ["Calendars.ReadWrite", "email", "User.Read"]

GOOGLE_REDIRECT_URI = "https://danishs-macbook-pro.tail79ab0c.ts.net/api/auth/google/callback"
OUTLOOK_REDIRECT_URI = "https://danishs-macbook-pro.tail79ab0c.ts.net/api/auth/outlook/callback"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

CLIENT_CONFIG = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    }
}

RP_ID = "localhost"
RP_NAME = "Scheduler App"
MOBILE_ORIGIN = "capacitor://localhost"
DESKTOP_ORIGIN = "http://localhost:3000"
TRUSTED_ORIGINS = [MOBILE_ORIGIN, DESKTOP_ORIGIN]

# ---------------------------------------------------------------------------
# Shared helper functions
# ---------------------------------------------------------------------------

def parse_iso(time_str):
    if not time_str:
        return None
    if isinstance(time_str, dt.datetime):
        if time_str.tzinfo is None:
            return time_str.replace(tzinfo=timezone.utc)
        return time_str

    time_str = str(time_str).strip()
    if len(time_str) == 10:
        time_str += "T00:00:00Z"

    try:
        parsed = dt.datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def ensure_strict_iso_string(time_val):
    if not time_val:
        return None
    if isinstance(time_val, dt.datetime):
        return time_val.isoformat().replace("+00:00", "") + "Z"

    time_str = str(time_val).strip()
    if len(time_str) == 10:
        return f"{time_str}T00:00:00Z"

    if not time_str.endswith("Z") and "+" not in time_str:
        return f"{time_str}Z"

    return time_str


def safe_parse_dt(iso_str: str) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        s = str(iso_str).strip()
        s = s.replace("+00:00Z", "+00:00")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        s = s.replace("+00:00+00:00", "+00:00")

        parsed = dt.datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception as e:
        print(f"[Parse Error] Failed to parse {iso_str}: {e}")
        return None


def get_user_timezone(user_id: str) -> zoneinfo.ZoneInfo:
    """Fetches dynamic timezone from user profile, defaults to UTC."""
    try:
        user_doc = db.collection("users").document(user_id).get()
        if user_doc.exists:
            tz_string = user_doc.to_dict().get("timezone", "UTC")
            return zoneinfo.ZoneInfo(tz_string)
    except Exception as e:
        print(f"[Timezone] Error fetching timezone for {user_id}: {e}")

    return zoneinfo.ZoneInfo("UTC")


def sync_task_with_events(user_id: str, task_id: str):
    """
    Evaluates all events linked to a task and auto-updates the task's status.
    """
    try:
        events_ref = db.collection("users").document(user_id).collection("raw_events")
        task_ref = (
            db.collection("users")
            .document(user_id)
            .collection("raw_tasks")
            .document(task_id)
        )

        task_doc = task_ref.get()
        if not task_doc.exists:
            return

        task_data = task_doc.to_dict()
        if task_data.get("status") == "missed":
            return

        linked_events = list(
            events_ref.where("linked_task_id", "==", task_id).stream()
        )

        if len(linked_events) == 0:
            task_ref.update({"status": "pending", "linked_event_ids": []})
            print(f"🔄 Task {task_id} reverted to 'pending' (0 events remaining).")
            return

        all_completed = True
        active_event_ids = []

        for doc in linked_events:
            ev = doc.to_dict()
            active_event_ids.append(doc.id)
            if ev.get("completion_status") != "completed":
                all_completed = False

        update_payload = {"linked_event_ids": active_event_ids}

        if all_completed:
            update_payload["status"] = "completed"
            update_payload["completed_at"] = dt.datetime.now(
                dt.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(
                f"✅ Task {task_id} auto-completed "
                f"(All {len(active_event_ids)} events cleared)."
            )
        else:
            update_payload["status"] = "scheduled"

        task_ref.update(update_payload)

    except Exception as e:
        print(f"⚠️ Failed to sync task {task_id} with its events: {e}")


# ---------------------------------------------------------------------------
# Alias / vocabulary helpers (shared by ai and vocabulary routers)
# ---------------------------------------------------------------------------

_TEACH_PATTERN = re.compile(
    r"(?:when i say|if i say|by|use)\s+['\"]?(\w+)['\"]?\s+"
    r"(?:i mean|it means|that means|refers to|stands for|to mean)\s+(.+)",
    re.IGNORECASE,
)

_TEACH_PATTERN_2 = re.compile(
    r"['\"]?(\w+)['\"]?\s+(?:stands for|means|is short for|is an acronym for)\s+(.+)",
    re.IGNORECASE,
)


def _detect_teach_phrase(text: str):
    for pattern in [_TEACH_PATTERN, _TEACH_PATTERN_2]:
        match = pattern.search(text)
        if match:
            alias = match.group(1).lower().strip()
            full_form = match.group(2).strip().rstrip(".")
            return alias, full_form
    return None


def _load_aliases(user_id: str) -> dict:
    try:
        doc = (
            db.collection("users")
            .document(user_id)
            .collection("vocabulary")
            .document("aliases")
            .get()
        )
        return doc.to_dict().get("aliases", {}) if doc.exists else {}
    except Exception as e:
        print(f"[Vocabulary] Failed to load aliases: {e}")
        return {}


def _expand_aliases(text: str, aliases: dict) -> str:
    expanded = text
    for alias, full_form in aliases.items():
        pattern = rf"\b{re.escape(alias)}\b"
        replaced = re.sub(pattern, full_form, expanded, flags=re.IGNORECASE)
        if replaced != expanded:
            print(f"[AliasExpander] '{alias}' → '{full_form}'")
            expanded = replaced
    return expanded
