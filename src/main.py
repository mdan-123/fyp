import os
from pydantic import BaseModel
from fastapi import HTTPException
from scheduler_engine import SchedulerNLU 
import json
import hashlib
from IntentEngine import IntentExecutionEngine
from router import MultiSignalRouter
from optimiser import Optimiser
from llm_parser import ConstraintParser
from fastapi.responses import HTMLResponse
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import requests
from task import TaskScheduler, DebtRescheduler
from google.cloud import firestore
from fastapi.responses import RedirectResponse
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import msal
from google.auth.exceptions import RefreshError 
from pydantic import BaseModel
import re
import zoneinfo
import firebase_admin
from firebase_admin import credentials, auth, firestore
from typing import Dict, List, Any
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json
)
from fastapi import Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from webauthn.helpers.structs import (
    RegistrationCredential, 
    AuthenticationCredential,
    UserVerificationRequirement
)
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import timedelta, timezone, date
import datetime as dt
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from google_auth_oauthlib.flow import Flow
from fastapi import Request
from dotenv import load_dotenv
load_dotenv("./.env.local")

# Initialise Firebase Admin SDK using your service account key
# You must download this JSON file from the Firebase Console (Project Settings -> Service Accounts)
cred = credentials.Certificate("./firebase-service-account.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")


from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# -------------------------------------------------------------------
# 1. FIREBASE INITIALISATION (Adjust import based on your setup)
# -------------------------------------------------------------------
# from your_firebase_file import db
# For example, if using firebase_admin:
# import firebase_admin
# from firebase_admin import credentials, firestore
# cred = credentials.Certificate("path/to/serviceAccountKey.json")
# firebase_admin.initialize_app(cred)
# db = firestore.client()

# -------------------------------------------------------------------
# 2. GLOBAL AI VARIABLES & LIFESPAN MANAGER
# -------------------------------------------------------------------
ai_model = None
ai_explainer = None
ai_meta = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ai_model, ai_explainer, ai_meta
    print("Loading AI Risk Prediction Model...")
    try:
        with open("risk_prediction_model.pkl", "rb") as f:
            ai_model = pickle.load(f)
        with open("risk_prediction_model_shap_explainer.pkl", "rb") as f:
            ai_explainer = pickle.load(f)
        with open("risk_prediction_model_meta.json", "r") as f:
            ai_meta = json.load(f)
        print("AI Model Loaded Successfully.")
    except Exception as e:
        print(f"Warning: Could not load AI model files. Error: {e}")
    
    yield
    print("Shutting down AI Model...")

# -------------------------------------------------------------------
# 3. FASTAPI APP & CORS SETUP
# -------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)


def parse_iso(time_str):
    if not time_str: return None
    if isinstance(time_str, dt.datetime):
        if time_str.tzinfo is None: return time_str.replace(tzinfo=timezone.utc)
        return time_str
    
    time_str = str(time_str).strip()
    if len(time_str) == 10: time_str += "T00:00:00Z"
    
    try:
        parsed = dt.datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "capacitor://localhost",
        "http://192.168.1.50:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
OUTLOOK_REDIRECT_URI = "http://localhost:8000/api/auth/outlook/callback" 
OUTLOOK_CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
OUTLOOK_CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
OUTLOOK_AUTHORITY = "https://login.microsoftonline.com/common"
GOOGLE_REDIRECT_URI = "https://danishs-macbook-pro.tail79ab0c.ts.net/api/auth/google/callback"
OUTLOOK_REDIRECT_URI = "https://danishs-macbook-pro.tail79ab0c.ts.net/api/auth/outlook/callback"
OUTLOOK_SCOPES = ["Calendars.ReadWrite", "email", "User.Read"]# Your Next.js frontend URL
RP_ID = "localhost" 
RP_NAME = "Scheduler App"
MOBILE_ORIGIN = "capacitor://localhost"
DESKTOP_ORIGIN = "http://localhost:3000"
TRUSTED_ORIGINS = [MOBILE_ORIGIN, DESKTOP_ORIGIN]

CLIENT_CONFIG = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    }
}

# --- Pydantic Models for incoming JSON ---
class RegisterStartRequest(BaseModel):
    user_id: str
    email: str

class VerifyRequest(BaseModel):
    user_id: str
    credential: dict

class LoginStartRequest(BaseModel):
    user_id: str

class LoginStartAuthRequest(BaseModel):
    email: str

class VerifyLoginRequest(BaseModel):
    email: str
    credential: dict
class MobileBiometricLoginRequest(BaseModel):
    email: str

class MobileBiometricRegisterRequest(BaseModel):
    user_id: str
    has_mobile_biometrics: bool

security = HTTPBearer()

import uuid





def get_outlook_calendar_events(refresh_token: str, email: str, sync_id: str):
    client = msal.ConfidentialClientApplication(
        OUTLOOK_CLIENT_ID, 
        client_credential=OUTLOOK_CLIENT_SECRET, 
        authority=OUTLOOK_AUTHORITY
    )
    
    token_result = client.acquire_token_by_refresh_token(
        refresh_token, 
        scopes=OUTLOOK_SCOPES
    )
    
    if "access_token" not in token_result:
        print(f"Error refreshing Outlook token for {email}")
        return []

    access_token = token_result["access_token"]
    now = dt.datetime.now(timezone.utc)
    start_date = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    end_date = (now + dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")

    endpoint = f"https://graph.microsoft.com/v1.0/me/calendarView?startDateTime={start_date}&endDateTime={end_date}&$top=100"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Prefer": 'outlook.timezone="UTC"'
    }
    
    response = requests.get(endpoint, headers=headers)
    
    if response.status_code != 200:
        print(f"Microsoft Graph Error: {response.text}")
        return []

    items = response.json().get("value", [])
    formatted_events = []

    for event in items:
        formatted_events.append({
            "id": event.get("id"),
            "title": event.get("subject", "Untitled Event"),
            "start": event.get("start", {}).get("dateTime"),
            "end": event.get("end", {}).get("dateTime"),
            "provider": "outlook",
            "email": email,
            "sync_id": sync_id
        })

    return formatted_events

def get_google_calendar_events(refresh_token: str, email: str, sync_id: str):
    now = dt.datetime.now(timezone.utc)
    time_min = (now - dt.timedelta(days=30)).isoformat()
    time_max = (now + dt.timedelta(days=30)).isoformat()

    try:
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET
        )

        service = build("calendar", "v3", credentials=creds)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        fetched_items = events_result.get("items", [])
        formatted_events = []

        for event in fetched_items:
            formatted_events.append({
                "id": event.get("id"),
                "title": event.get("summary", "Untitled Event"),
                "start": event.get("start").get("dateTime") or event.get("start").get("date"),
                "end": event.get("end").get("dateTime") or event.get("end").get("date"),
                "provider": "google",
                "email": email,
                "sync_id": sync_id
            })

        return formatted_events

    except RefreshError as e:
        # This specifically catches the 'invalid_grant' error
        print(f"🚨 Refresh token dead for {email}: {e}")
        
        # TODO: Update your database here to mark this account as disconnected
        # db.collection('users').document(user_id).update({'google_connected': False})
        
        return []
        
    except Exception as e:
        print(f"Error fetching for {email}: {e}")
        return []

def verify_firebase_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Firebase Admin verifies the cryptographic signature of the JWT
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        raise HTTPException(
            status_code=401, 
            detail="Invalid or expired authentication token"
        )
# --- REGISTRATION ENDPOINTS ---

@app.post("/api/auth/register/start")
async def start_registration(req: RegisterStartRequest):
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=req.user_id.encode('utf-8'),
        user_name=req.email,
    )
    
    # Safely convert the binary options to a dictionary
    options_dict = json.loads(options_to_json(options))
    
    db.collection("webauthn_challenges").document(req.user_id).set({
        "challenge": options_dict["challenge"]
    })
    
    return options_dict

@app.post("/api/auth/register/verify")
async def verify_registration(req: VerifyRequest):
    doc = db.collection("webauthn_challenges").document(req.user_id).get()
    if not doc.exists:
        raise HTTPException(status_code=400, detail="Challenge not found")
    
    expected_challenge_bytes = base64url_to_bytes(doc.to_dict()["challenge"])
    
    # Check which origin to use (Desktop vs Mobile)
    # If it's not mobile, default to desktop
    current_origin = MOBILE_ORIGIN if req.user_id.startswith("mobile_") else DESKTOP_ORIGIN
    
    try:
        verification = verify_registration_response(
            credential=req.credential,
            expected_challenge=expected_challenge_bytes,
            expected_origin=TRUSTED_ORIGINS, # The library can accept a list here
            expected_rp_id=RP_ID,
            require_user_verification=True
        )
        
        db.collection("users").document(req.user_id).collection("passkeys").add({
            "credential_id": bytes_to_base64url(verification.credential_id),
            "public_key": bytes_to_base64url(verification.credential_public_key),
            "sign_count": verification.sign_count,
            "transports": req.credential.get("response", {}).get("transports", [])
        })
        
        return {"status": "success", "message": "Passkey registered"}
        
    except Exception as e:
        print(f"Verification Error: {e}") # This will show you exactly why it failed in your terminal
        raise HTTPException(status_code=400, detail=str(e))
# --- LOGIN ENDPOINTS ---

@app.post("/api/auth/login/start")
async def start_login(req: LoginStartAuthRequest):
    try:
        # Ask Firebase to find the user by their email address
        user_record = auth.get_user_by_email(req.email)
        user_id = user_record.uid
    except Exception:
        raise HTTPException(status_code=400, detail="User not found")

    options = generate_authentication_options(
        rp_id=RP_ID,
        user_verification=UserVerificationRequirement.REQUIRED
    )
    
    options_dict = json.loads(options_to_json(options))
    
    db.collection("webauthn_challenges").document(user_id).set({
        "challenge": options_dict["challenge"]
    })
    
    return options_dict

@app.post("/api/auth/login/verify")
async def verify_login(req: VerifyLoginRequest):
    try:
        # Ask Firebase to find the user by their email address again
        user_record = auth.get_user_by_email(req.email)
        user_id = user_record.uid
    except Exception:
        raise HTTPException(status_code=400, detail="User not found")

    doc = db.collection("webauthn_challenges").document(user_id).get()
    if not doc.exists:
        raise HTTPException(status_code=400, detail="Challenge not found")
        
    expected_challenge_bytes = base64url_to_bytes(doc.to_dict()["challenge"])
    
    passkeys = db.collection("users").document(user_id).collection("passkeys").limit(1).get()
    if not passkeys:
        raise HTTPException(status_code=400, detail="No biometrics registered for this user")
        
    saved_key_data = passkeys[0].to_dict()
    
    try:
        verification = verify_authentication_response(
            credential=req.credential,
            expected_challenge=expected_challenge_bytes,
            expected_origin=TRUSTED_ORIGINS, # Allow both desktop and mobile
            expected_rp_id=RP_ID,
            credential_public_key=base64url_to_bytes(saved_key_data["public_key"]),
            credential_current_sign_count=saved_key_data["sign_count"]
        )
        
        custom_token = auth.create_custom_token(user_id)
        
        return {"status": "success", "token": custom_token.decode('utf-8')}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

@app.get("/api/secure-test")
async def secure_test_endpoint(user_data: dict = Depends(verify_firebase_token)):
    # If the code reaches this line, the token is 100% valid
    # user_data contains their decoded Firebase profile, including their unique uid
    user_id = user_data.get("uid")
    email = user_data.get("email")
    
    return {
        "status": "success", 
        "message": "You have successfully breached the mainframe.",
        "authorised_user": user_id,
        "email": email
    }


# --- NATIVE MOBILE BIOMETRIC ENDPOINTS ---

@app.post("/api/auth/register/mobile-biometrics")
async def register_mobile_biometrics(req: MobileBiometricRegisterRequest):
    try:
        # Save a flag in the user's main document to mark them as Biometric-enabled
        db.collection("users").document(req.user_id).set({
            "has_mobile_biometrics": req.has_mobile_biometrics
        }, merge=True)
        return {"status": "success", "message": "Mobile biometrics flagged in database"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/mobile-biometric-login")
async def mobile_biometric_login(req: MobileBiometricLoginRequest):
    try:
        # 1. Ask Firebase for the user's UID based on email
        user_record = auth.get_user_by_email(req.email)
        user_id = user_record.uid
        
        # 2. Check Firestore for the 'has_mobile_biometrics' flag
        user_doc = db.collection("users").document(user_id).get()
        
        if not user_doc.exists or not user_doc.to_dict().get("has_mobile_biometrics"):
            raise HTTPException(
                status_code=403, 
                detail="Biometrics not enabled for this account. Please use password login."
            )

        # 3. Generate the Firebase Custom Token
        # This token allows the iPhone to sign into Firebase without a password
        custom_token = auth.create_custom_token(user_id)
        
        return {
            "status": "success", 
            "token": custom_token.decode("utf-8")
        }
        
    except auth.UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/api/auth/google/login")
async def google_login(user_id: str):
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES
    )
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    
    # Adding 'select_account' ensures the user can choose a second, different email
    authorization_url, _ = flow.authorization_url(
        access_type='offline',
        state=user_id,
        prompt='select_account consent' 
    )
    return {"url": authorization_url}

from fastapi.responses import RedirectResponse

@app.get("/api/auth/google/callback")
async def google_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state") 

    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    flow.fetch_token(code=code)
    
    credentials = flow.credentials

    # Decode the ID token to extract the email address
    id_info = id_token.verify_oauth2_token(
        credentials.id_token, google_requests.Request(), GOOGLE_CLIENT_ID
    )
    user_email = id_info.get("email")

    # Create a dictionary for this specific account
    new_account = {
        "provider": "google",
        "email": user_email,
        "refresh_token": credentials.refresh_token,
    }

    # Use ArrayUnion to append this account without overwriting others like Outlook
    # Save to the linked_accounts array...
    db.collection("users").document(state).set({
        "linked_accounts": firestore.ArrayUnion([new_account])
    }, merge=True)

    # The smart callback response
    html_content = """
    <html>
        <head>
            <script>
                // 1. Try to redirect back to the mobile app
                window.location.href = "schedulerai://callback";
                
                // 2. If this is a desktop popup, close it automatically
                setTimeout(() => { 
                    window.close(); 
                }, 1000);
            </script>
        </head>
        <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f9fafb;">
            <h2>Authentication complete! You can close this window.</h2>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)



@app.get("/api/auth/outlook/login")
async def outlook_login(user_id: str):
    client = msal.ConfidentialClientApplication(
        OUTLOOK_CLIENT_ID, 
        client_credential=OUTLOOK_CLIENT_SECRET, 
        authority=OUTLOOK_AUTHORITY
    )
    
    auth_url = client.get_authorization_request_url(
        OUTLOOK_SCOPES, 
        redirect_uri=OUTLOOK_REDIRECT_URI,
        state=user_id,
        prompt="select_account" # Forces the account chooser for multiple accounts
    )
    return {"url": auth_url}

@app.get("/api/auth/outlook/callback")
async def outlook_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state") # This is your Firebase user_id
    
    client = msal.ConfidentialClientApplication(
        OUTLOOK_CLIENT_ID, 
        client_credential=OUTLOOK_CLIENT_SECRET, 
        authority=OUTLOOK_AUTHORITY
    )
    
    result = client.acquire_token_by_authorization_code(
        code, 
        scopes=OUTLOOK_SCOPES, 
        redirect_uri=OUTLOOK_REDIRECT_URI
    )
    
    if "error" in result:
        print(f"Outlook Auth Error: {result.get('error_description')}")
        return {"error": "Failed to authenticate with Microsoft"}

    # Extract email and refresh token
    id_claims = result.get("id_token_claims", {})
    email = id_claims.get("preferred_username") or id_claims.get("email")
    refresh_token = result.get("refresh_token")

    # Save to the linked_accounts array using ArrayUnion to support multiples
    new_account = {
        "provider": "outlook",
        "email": email,
        "refresh_token": refresh_token,
    }

    # Save to the linked_accounts array...
    db.collection("users").document(state).set({
        "linked_accounts": firestore.ArrayUnion([new_account])
    }, merge=True)

    # The smart callback response
    html_content = """
    <html>
        <head>
            <script>
                // 1. Try to redirect back to the mobile app
                window.location.href = "schedulerai://callback";
                
                // 2. If this is a desktop popup, close it automatically
                setTimeout(() => { 
                    window.close(); 
                }, 1000);
            </script>
        </head>
        <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f9fafb;">
            <h2>Authentication complete! You can close this window.</h2>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

import uuid

from fastapi import APIRouter, HTTPException
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pydantic import BaseModel
from typing import Any, Optional, List


class SyncRequest(BaseModel):
    user_id: str

class EventPayload(BaseModel):
    event_id: Optional[str] = None
    user_id: str
    title: str
    start: str
    end: str
    location: Optional[str] = ""
    meeting_link: Optional[str] = ""
    is_locked: bool = True
    description: Optional[str] = ""
    recurrence: Optional[str] = "none"
    recurrence_days: Optional[List[str]] = []
    travel_time: Optional[int] = 0
    travel_origin: Optional[str] = ""
    travel_mode: Optional[str] = "driving"
    provider: str
    email: str
    attachments: List[str] = []
    category: Optional[str] = "None"    
    # Exception Fields
    update_mode: Optional[str] = "all"
    instance_date: Optional[str] = None
    # --- NEW TELEMETRY FIELDS ---
    completion_status: Optional[str] = "pending"
    snooze_count: Optional[int] = 0
    completed_at: Optional[str] = None
    debt_applied: Optional[bool] = False
    is_perishable: Optional[bool] = False

import uuid
import os
from datetime import datetime, timezone
import datetime as dt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google.cloud import firestore
from categorise import categorise_event


def ensure_strict_iso_string(time_val):
    if not time_val:
        return None
    # FIXED: explicitly using dt.datetime
    if isinstance(time_val, dt.datetime):
        return time_val.isoformat().replace("+00:00", "") + "Z"
    
    time_str = str(time_val).strip()
    if len(time_str) == 10: 
        return f"{time_str}T00:00:00Z"
    
    if not time_str.endswith("Z") and "+" not in time_str:
        return f"{time_str}Z"
        
    return time_str

import datetime as dt

def sync_task_with_events(user_id: str, task_id: str):
    """
    Evaluates all events linked to a task and auto-updates the task's status.
    - 0 events = 'pending'
    - All events 'completed' = 'completed'
    - Otherwise = 'scheduled'
    """
    try:
        events_ref = db.collection("users").document(user_id).collection("raw_events")
        task_ref = db.collection("users").document(user_id).collection("raw_tasks").document(task_id)
        
        # 1. Check if the task actually exists
        task_doc = task_ref.get()
        if not task_doc.exists:
            return
            
        task_data = task_doc.to_dict()
        if task_data.get("status") == "missed":
            return # Don't auto-resurrect missed tasks unless done explicitly

        # 2. Grab all remaining events linked to this task
        linked_events = list(events_ref.where("linked_task_id", "==", task_id).stream())
        
        # SCENARIO A: All events were deleted
        if len(linked_events) == 0:
            task_ref.update({
                "status": "pending",
                "linked_event_ids": []
            })
            print(f"🔄 Task {task_id} reverted to 'pending' (0 events remaining).")
            return
            
        # SCENARIO B & C: Check completion status
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
            update_payload["completed_at"] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            print(f"✅ Task {task_id} auto-completed (All {len(active_event_ids)} events cleared).")
        else:
            update_payload["status"] = "scheduled"
            
        task_ref.update(update_payload)

    except Exception as e:
        print(f"⚠️ Failed to sync task {task_id} with its events: {e}")


@app.post("/api/calendar/new")
async def create_event(payload: EventPayload):
    try:
        user_ref = db.collection("users").document(payload.user_id)
        events_ref = user_ref.collection("raw_events")
        
        doc_id = f"custom_{uuid.uuid4().hex[:8]}"
        
        event_data = payload.dict(exclude_none=True)
        event_data["id"] = doc_id
        
        assigned_category = categorise_event(
            title=payload.title or "Untitled", 
            description=payload.description or ""
        )
        event_data["category"] = assigned_category
        
        # Original Sync fields
        event_data["sync_status"] = "synced"
        event_data["requires_review"] = False
        event_data["has_drifted"] = False
        event_data["original_start"] = payload.start
        event_data["original_end"] = payload.end
        event_data["sync_action_required"] = "push_to_provider"

        # --- TELEMETRY INITIALIZATION ---
        event_data["completion_status"] = "pending"
        event_data["snooze_count"] = 0
        event_data["completed_at"] = None
        event_data["debt_applied"] = False
        
        # Auto-flag perishability for habits/routines
        perishable_categories = ["Health & Fitness", "Routine", "Meals", "Personal Care"]
        if payload.recurrence != "none" or assigned_category in perishable_categories:
            event_data["is_perishable"] = True
        else:
            event_data["is_perishable"] = payload.is_perishable
        
        events_ref.document(doc_id).set(event_data)
        
        return {"status": "success", "event_id": doc_id, "category": assigned_category}
    except Exception as e:
        print(f"Error creating event: {e}")
        raise HTTPException(status_code=500, detail="Failed to create event")
    


@app.post("/api/calendar/update")
async def update_event(payload: EventPayload):
    if not payload.event_id:
        raise HTTPException(status_code=400, detail="Missing event_id for update")
        
    try:
        events_ref = db.collection("users").document(payload.user_id).collection("raw_events")
        
        existing_doc = events_ref.document(payload.event_id).get()
        if not existing_doc.exists:
            raise HTTPException(status_code=404, detail="Event not found")
            
        existing_data = existing_doc.to_dict()
        
        # --- 1. Category Resolution ---
        category_changed = payload.category is not None and payload.category != existing_data.get("category")
        new_title = payload.title if payload.title is not None else existing_data.get("title", "")
        new_desc = payload.description if payload.description is not None else existing_data.get("description", "")
        title_changed = payload.title is not None and payload.title != existing_data.get("title")
        desc_changed = payload.description is not None and payload.description != existing_data.get("description")
        
        if category_changed:
            updated_category = payload.category
        elif title_changed or desc_changed or not existing_data.get("category"):
            updated_category = categorise_event(title=new_title, description=new_desc)
        else:
            updated_category = existing_data.get("category")

        # --- 2. Read UI Overrides First (THE FIX) ---
        ui_comp_status = payload.completion_status if payload.completion_status is not None else existing_data.get("completion_status", "pending")
        ui_is_perishable = payload.is_perishable if payload.is_perishable is not None else existing_data.get("is_perishable", False)

        old_start = parse_iso(existing_data.get("start"))
        new_start = parse_iso(payload.start) if payload.start else old_start
        
        # --- 3. Telemetry Hooks ---
        # Snooze Hook
        snooze_increment = 0
        if old_start and new_start and new_start > old_start:
            snooze_increment = 1
            
        new_snooze_count = existing_data.get("snooze_count", 0) + snooze_increment
        
        comp_status = ui_comp_status
        is_perish = ui_is_perishable
        debt_applied = existing_data.get("debt_applied", False)
        completed_at = existing_data.get("completed_at")
        
        # Debt Relief Hook (If it was missed, and the user just pushed the time to the future)
        if existing_data.get("completion_status") == "missed" and snooze_increment > 0:
            # Resurrect it to pending (unless they explicitly clicked 'Completed' in the UI just now)
            if payload.completion_status not in ["completed", "missed"]:
                comp_status = "pending"
            
            if debt_applied and not is_perish:
                old_end = parse_iso(existing_data.get("end"))
                if old_start and old_end:
                    duration_mins = int((old_end - old_start).total_seconds() / 60)
                    if duration_mins > 0:
                        db.collection("users").document(payload.user_id).update({
                            "total_time_debt": firestore.Increment(-duration_mins)
                        })
            debt_applied = False # Reset the flag

        # Completion Timestamp Hook
        if comp_status == "completed" and existing_data.get("completion_status") != "completed":
            completed_at = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        elif comp_status != "completed":
            completed_at = None

        # --- 4. Applying Updates to Firestore ---
        if payload.update_mode == "single" and payload.instance_date:
            events_ref.document(payload.event_id).update({
                "exception_dates": firestore.ArrayUnion([payload.instance_date]),
                "sync_action_required": "push_to_provider" 
            })
            
            new_doc_id = f"custom_{uuid.uuid4().hex[:8]}"
            new_event_data = payload.dict(exclude={"event_id", "user_id", "update_mode", "instance_date"}, exclude_none=True)
            new_event_data["id"] = new_doc_id
            new_event_data["recurrence"] = "none" 
            new_event_data["parent_event_id"] = payload.event_id 
            new_event_data["sync_status"] = "synced"
            new_event_data["requires_review"] = False
            new_event_data["has_drifted"] = False
            new_event_data["proposed_start"] = payload.start
            new_event_data["proposed_end"] = payload.end
            new_event_data["sync_action_required"] = "push_to_provider"
            new_event_data["category"] = updated_category
            
            # Inject new telemetry for the exception instance
            new_event_data["completion_status"] = comp_status
            new_event_data["snooze_count"] = 0
            new_event_data["debt_applied"] = False
            new_event_data["is_perishable"] = is_perish
            new_event_data["completed_at"] = completed_at
            
            events_ref.document(new_doc_id).set(new_event_data)
            
        elif payload.update_mode == "exception_delete" and payload.instance_date:
            events_ref.document(payload.event_id).update({
                "exception_dates": firestore.ArrayUnion([payload.instance_date]),
                "sync_action_required": "push_to_provider" 
            })
            
        else:
            update_data = payload.dict(exclude={"event_id", "user_id", "update_mode", "instance_date"}, exclude_none=True)
            update_data["proposed_start"] = payload.start
            update_data["proposed_end"] = payload.end
            update_data["requires_review"] = False
            update_data["has_drifted"] = False
            update_data["status"] = "resolved" 
            update_data["sync_action_required"] = "push_to_provider"
            update_data["category"] = updated_category
            
            # Explicitly overwrite with our mathematically calculated telemetry
            update_data["completion_status"] = comp_status
            update_data["snooze_count"] = new_snooze_count
            update_data["debt_applied"] = debt_applied
            update_data["is_perishable"] = is_perish
            update_data["completed_at"] = completed_at
            
            events_ref.document(payload.event_id).update(update_data)

        linked_task_id = existing_data.get("linked_task_id")
        if linked_task_id:
            sync_task_with_events(payload.user_id, linked_task_id)

        return {"status": "success"}
    except Exception as e:
        print(f"Error updating event: {e}")
        raise HTTPException(status_code=500, detail="Failed to update event") 


@app.post("/api/calendar/sync")
async def sync_calendar(request: SyncRequest):
    user_id = request.user_id
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return {"status": "success", "events": [], "linked_accounts": []}

    linked_accounts = user_doc.to_dict().get("linked_accounts", [])
    events_ref = user_ref.collection("raw_events")
    
    sync_id = str(uuid.uuid4())
    current_time_iso = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")    
    existing_events_stream = events_ref.stream()
    existing_events = {doc.id: doc.to_dict() for doc in existing_events_stream}
    
    all_events = []
    safe_accounts = []
    batch = db.batch()
    
    global_processed_ids = set()
    active_sync_emails = set()

    for account in linked_accounts:
        provider = account.get("provider")
        email = account.get("email")
        
        safe_accounts.append({"provider": provider, "email": email})
        
        provider_events = []
        try:
            if provider == "google":
                provider_events = get_google_calendar_events(account["refresh_token"], email, sync_id)
            elif provider == "outlook":
                provider_events = get_outlook_calendar_events(account["refresh_token"], email, sync_id)
            active_sync_emails.add(email)
        except Exception as e:
            print(f"Fetch failed for {email}: {e}")
            continue
            
        for event in provider_events:
            raw_id = str(event.get('id', '')).strip()
            doc_id = f"{provider}_{raw_id}"
            
            global_processed_ids.add(doc_id) 
            is_new = doc_id not in existing_events
            
            new_start = ensure_strict_iso_string(event.get("start"))
            new_end = ensure_strict_iso_string(event.get("end"))
            
            event_title = event.get("title", "Untitled")
            event_desc = event.get("description", "")
            attendees_count = len(event.get("attendees", []))
            has_video = bool(event.get("hangoutLink") or event.get("onlineMeeting"))
            
            if is_new:
                assigned_category = categorise_event(event_title, event_desc, attendees_count, has_video)
                event["category"] = assigned_category
                event["is_locked"] = True
                event["requires_review"] = True 
                event["has_drifted"] = False
                event["original_start"] = new_start
                event["original_end"] = new_end
                event["previous_start"] = None
                event["previous_end"] = None
                event["proposed_start"] = None
                event["proposed_end"] = None
                event["status"] = "synced"
                
                # Telemetry Initialization
                event["completion_status"] = "pending"
                event["snooze_count"] = 0
                event["completed_at"] = None
                event["debt_applied"] = False
                
                perishable_categories = ["Health & Fitness", "Routine", "Meals", "Personal Care"]
                event["is_perishable"] = assigned_category in perishable_categories
            else:
                old_data = existing_events[doc_id]
                
                if old_data.get("sync_action_required") == "push_to_provider":
                    continue
                    
                existing_category = old_data.get("category")
                if not existing_category:
                    event["category"] = categorise_event(event_title, event_desc, attendees_count, has_video)
                else:
                    event["category"] = existing_category
                    
                old_start = old_data.get("original_start")
                old_end = old_data.get("original_end")
                
                old_start_parsed = parse_iso(old_start)
                new_start_parsed = parse_iso(new_start)
                old_end_parsed = parse_iso(old_end)
                new_end_parsed = parse_iso(new_end)
                
                time_changed = (old_start_parsed != new_start_parsed) or (old_end_parsed != new_end_parsed)
                event["is_locked"] = old_data.get("is_locked", True)
                
                if time_changed:
                    event["has_drifted"] = True
                    event["requires_review"] = True
                    event["previous_start"] = old_start
                    event["previous_end"] = old_end
                    event["status"] = "conflict" if old_data.get("proposed_start") else "drifted"
                else:
                    event["has_drifted"] = old_data.get("has_drifted", False)
                    event["requires_review"] = old_data.get("requires_review", False)
                    event["previous_start"] = old_data.get("previous_start")
                    event["previous_end"] = old_data.get("previous_end")
                    event["status"] = old_data.get("status", "synced")
                
                event["original_start"] = new_start
                event["original_end"] = new_end
                event["proposed_start"] = old_data.get("proposed_start")
                event["proposed_end"] = old_data.get("proposed_end")
                
                # Carry over telemetry
                event["completion_status"] = old_data.get("completion_status", "pending")
                event["snooze_count"] = old_data.get("snooze_count", 0)
                event["completed_at"] = old_data.get("completed_at")
                event["debt_applied"] = old_data.get("debt_applied", False)
                event["is_perishable"] = old_data.get("is_perishable", False)
            
            event["start"] = new_start
            event["end"] = new_end
            event["last_synced_from_provider"] = current_time_iso
            event["sync_id"] = sync_id
            event["email"] = email 
            
            all_events.append(event)
            event_doc = events_ref.document(doc_id)
            batch.set(event_doc, event, merge=True)
            
    for old_doc_id, old_doc_data in existing_events.items():
        old_email = old_doc_data.get("email")
        old_provider = old_doc_data.get("provider")
        sync_action = old_doc_data.get("sync_action_required")
        
        if old_provider in ["google", "outlook"] and old_email in active_sync_emails:
            if old_doc_id not in global_processed_ids:
                if sync_action != "push_to_provider":
                    batch.delete(events_ref.document(old_doc_id))

    batch.commit()

    return {
        "status": "success", 
        "events": all_events, 
        "linked_accounts": safe_accounts,
        "sync_id": sync_id
    }



from pydantic import BaseModel

class DisconnectRequest(BaseModel):
    user_id: str
    email: str
    provider: str

@app.post("/api/calendar/disconnect")
async def disconnect_calendar(req: DisconnectRequest):
    try:
        user_ref = db.collection("users").document(req.user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
            
        accounts = user_doc.to_dict().get("linked_accounts", [])
        
        account_to_remove = next(
            (acc for acc in accounts if acc['email'] == req.email and acc['provider'] == req.provider), 
            None
        )

        if account_to_remove:
            user_ref.update({
                "linked_accounts": firestore.ArrayRemove([account_to_remove])
            })
            
            # Wipe the deleted account's events from the database
            events_ref = user_ref.collection("raw_events")
            stale_events = events_ref.where("email", "==", req.email).where("provider", "==", req.provider).stream()
            
            batch = db.batch()
            for event in stale_events:
                batch.delete(event.reference)
            batch.commit()
            
            return {"status": "success", "message": f"Disconnected {req.email} and purged events"}
        
        return {"status": "error", "message": "Account not found"}
    except Exception as e:
        print(f"Disconnect error: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect account")
    





from pydantic import BaseModel



INTENT_PATH = "./modernbert_intent_model/checkpoint-2160"
NER_PATH = "./modernbert_ner_model/checkpoint-3987"
CENTROIDS_PATH = "./intent_centroids.npy"
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_KEY == "":
    raise ValueError("GEMINI_API_KEY is not set")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
if GOOGLE_API_KEY == "":
    raise ValueError("GOOGLE_API_KEY is not set")       
print("Loading AI models into memory...")

nlu_engine = SchedulerNLU(intent_path=INTENT_PATH, ner_path=NER_PATH, gemini_api_key=GEMINI_KEY)
routing_engine = MultiSignalRouter(nlu_engine, centroids_path=CENTROIDS_PATH)
db_engine = IntentExecutionEngine(db_client=db)







GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

@app.get("/api/places/autocomplete")
async def autocomplete_places(query: str):
    if not query:
        return {"predictions": []}

    url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?input={query}&key={GOOGLE_MAPS_API_KEY}"
    
    try:
        response = requests.get(url)
        data = response.json()
        return {"predictions": data.get("predictions", [])}
    except Exception as e:
        print(f"Places API error: {e}")
        return {"predictions": []}
    

@app.get("/api/places/details")
async def get_place_details(place_id: str):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "geometry",
        "key": GOOGLE_MAPS_API_KEY
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK":
            print(f"Google API Error: {data}")
            raise HTTPException(status_code=400, detail=f"Google Maps API error: {data.get('status')}")

        location = data.get("result", {}).get("geometry", {}).get("location")
        
        if not location:
            raise HTTPException(status_code=404, detail="Location details not found")

        return {"status": "success", "location": location}

    except Exception as e:
        print(f"Error fetching place details: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch location details")
    

from google.cloud.firestore import FieldFilter
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import msal
import requests

class PreferenceRequest(BaseModel):
    user_id: str
    raw_text: str

@app.post("/api/preferences/parse")
async def parse_and_save_preference(req: PreferenceRequest):
    parser = ConstraintParser(API_KEY=GEMINI_KEY)
    result = parser.parse(req.raw_text)
    if result:
            # Normalise the result to always be a list
            if isinstance(result, dict):
                result = [result]
                
            saved_preferences = []
            
            # Loop through and save each constraint as its own document
            for item in result:
                doc_ref = db.collection("users").document(req.user_id).collection("preferences").document()
                doc_ref.set(item)
                saved_preferences.append({"id": doc_ref.id, "data": item})
                
            return {"status": "success", "saved_preferences": saved_preferences}
            
    return {"status": "error", "message": "Failed to parse preference"}

from fastapi import Query

@app.get("/api/preferences/list")
async def list_preferences(userId: str):
    try:
        docs = db.collection("users").document(userId).collection("preferences").stream()
        prefs = [{"id": doc.id, **doc.to_dict()} for doc in docs]
        return {"status": "success", "preferences": prefs}
    except Exception as e:
        print(f"Error fetching preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch preferences")

@app.delete("/api/preferences/{pref_id}")
async def delete_preference(pref_id: str, userId: str = Query(...)):
    try:
        # Verify the user owns this preference before deleting
        doc_ref = db.collection("users").document(userId).collection("preferences").document(pref_id)
        doc_ref.delete()
        return {"status": "success", "deleted_id": pref_id}
    except Exception as e:
        print(f"Error deleting preference: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete preference")




from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from typing import Literal

class ResolveConflictRequest(BaseModel):
    user_id: str
    event_id: str
    resolution: Literal['external', 'proposed', 'revert']

@app.post("/api/calendar/resolve")
async def resolve_calendar_conflict(req: ResolveConflictRequest):
    try:
        event_ref = db.collection("users").document(req.user_id).collection("raw_events").document(req.event_id)
        event_doc = event_ref.get()

        if not event_doc.exists:
            raise HTTPException(status_code=404, detail="Event not found")

        event_data = event_doc.to_dict()
        
        # Base updates to clear the conflict UI
        updates = {
            "has_drifted": False,
            "requires_review": False,
            "previous_start": None,
            "previous_end": None,
            "status": "resolved"
        }

        if req.resolution == 'external':
            # The user accepts the new Google time.
            # We clear the AI's proposal so the calendar falls back to the original_start.
            updates["proposed_start"] = None
            updates["proposed_end"] = None
            updates["sync_action_required"] = "none"
        
        elif req.resolution == 'proposed':
            # The user keeps the AI's plan.
            # We leave proposed_start/end exactly as they are.
            # We flag this so a background job knows to push this change back to Google later.
            updates["sync_action_required"] = "push_to_provider"

        elif req.resolution == 'revert':
            # The user wants to ignore the Google update and go back to the previous baseline.
            # We cannot overwrite original_start (because the next sync would just flag it as a drift again).
            # Instead, we set the proposed time to the previous baseline and flag it to be pushed to Google.
            previous_start = event_data.get("previous_start")
            previous_end = event_data.get("previous_end")
            
            if previous_start:
                updates["proposed_start"] = previous_start
                updates["proposed_end"] = previous_end
                updates["sync_action_required"] = "push_to_provider"

        # Apply the updates to Firestore
        event_ref.update(updates)
        
        return {"status": "success", "resolved_id": req.event_id, "action_taken": req.resolution}

    except Exception as e:
        print(f"Error resolving conflict: {e}")
        raise HTTPException(status_code=500, detail="Failed to resolve calendar conflict")
    

import uuid
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from typing import Optional, List

import uuid
from google.cloud import firestore
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from typing import Optional, List



import httpx
import math
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from typing import Optional

class TravelTimeRequest(BaseModel):
    origin: str
    destination: str
    mode: str = "driving"

@app.post("/api/location/travel-time")
async def calculate_travel_time(req: TravelTimeRequest):
    api_key = GOOGLE_MAPS_API_KEY
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    
    # Map frontend friendly names to Google API strict ENUMs
    mode_map = {
        "driving": "DRIVE",
        "walking": "WALK",
        "cycling": "BICYCLE",
        "transit": "TRANSIT"
    }
    
    google_mode = mode_map.get(req.mode.lower(), "DRIVE")
    
    payload = {
        "origin": {
            "address": req.origin
        },
        "destination": {
            "address": req.destination
        },
        "travelMode": google_mode,
    }
    
    # Traffic awareness is only valid for motorised vehicles in the API
    if google_mode == "DRIVE":
        payload["routingPreference"] = "TRAFFIC_AWARE"
        
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "routes.duration"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            data = response.json()
            
            if "routes" not in data or len(data["routes"]) == 0:
                raise HTTPException(status_code=400, detail="Could not find a route for this mode of transport")
                
            duration_string = data["routes"][0].get("duration", "0s")
            seconds = int(duration_string.replace("s", ""))
            
            minutes = math.ceil(seconds / 60)
            
            return {"status": "success", "minutes": minutes}
            
        except httpx.RequestError as e:
            print(f"Error calling Google Routes API: {e}")
            raise HTTPException(status_code=500, detail="Failed to calculate travel time")
        

import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google.cloud import firestore






from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
    
from pydantic import BaseModel
from typing import Any, Optional



class OptimiseRequest(BaseModel):
    user_id: str
    target_date: str 



class UndoRequest(BaseModel):
    user_id: str

def create_calendar_snapshot(user_id: str):
    """
    Takes a complete backup of the user's current raw_events collection.
    """
    try:
        events_ref = db.collection("users").document(user_id).collection("raw_events")
        existing_events_stream = events_ref.stream()
        
        snapshot_data = []
        for doc in existing_events_stream:
            event_dict = doc.to_dict()
            event_dict["_id"] = doc.id 
            snapshot_data.append(event_dict)
            
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        snapshot_ref = db.collection("users").document(user_id).collection("calendar_snapshots").document(snapshot_id)
        
        snapshot_ref.set({
            "snapshot_id": snapshot_id,
            "created_at": timestamp,
            "event_count": len(snapshot_data),
            "events": snapshot_data
        })
        
        print(f"Snapshot {snapshot_id} created successfully for user {user_id}")
        return snapshot_id

    except Exception as e:
        print(f"Error creating snapshot for {user_id}: {e}")
        return None


def hash_event_list(events: List[Dict[str, Any]]) -> str:
    """Helper function to create a fingerprint of the calendar state."""
    simplified_events = []
    for e in events:
        simplified_events.append({
            "id": e.get("id"),
            "start": e.get("proposed_start") or e.get("start"),
            "end": e.get("proposed_end") or e.get("end"),
        })
    simplified_events.sort(key=lambda x: (x["start"], x["id"] or ""))
    events_json = json.dumps(simplified_events, sort_keys=True)
    return hashlib.md5(events_json.encode('utf-8')).hexdigest()

@app.post("/api/calendar/optimise/preview")
async def preview_optimisation(request: OptimiseRequest):
    user_id = request.user_id
    target_date_str = request.target_date
    
    print(f"\n{'='*60}")
    print(f"🚀 [OPTIMISE PREVIEW] REQUEST INITIATED")
    print(f"👤 User ID: {user_id}")
    print(f"📅 Target Date String: {target_date_str}")
    print(f"{'='*60}\n")
    
    try:
        clean_date_str = target_date_str[:10] 
        target_date = dt.datetime.fromisoformat(clean_date_str).date()
        
        # --- THE FIX: Rolling 7-Day Window ---
        # Instead of finding the previous Monday, we start exactly on the target date
        start_of_window = target_date
        end_of_window = start_of_window + dt.timedelta(days=6)
        
        print(f"📆 Computed 7-Day Window: {start_of_window} to {end_of_window}")
    except ValueError:
        print("❌ [ERROR] Invalid date format received.")
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    try:
        user_tz = get_user_timezone(user_id)
        print(f"🌍 Extracted Timezone: {user_tz}")
        
        prefs_ref = db.collection("users").document(user_id).collection("preferences")
        preferences = [doc.to_dict() for doc in prefs_ref.stream()]
        print(f"📋 Loaded {len(preferences)} preferences.")

        events_ref = db.collection("users").document(user_id).collection("raw_events")
        existing_events = []
        for doc in events_ref.stream():
            event_data = doc.to_dict()
            event_data["id"] = doc.id
            existing_events.append(event_data)
            
        print(f"🗓️ Loaded {len(existing_events)} total events from database.")

        original_hash = hash_event_list(existing_events)

        calendar_optimiser = Optimiser(existing_events, preferences, user_tz_string=str(user_tz))
        
        print("\n[PHASE 1] Injecting Routines...")
        # Feed the rolling window to the routine injector
        ghost_events = calendar_optimiser.inject_routines(start_of_window, end_of_window)
        print(f"  -> Injected {len(ghost_events)} routine blocks.")

        preview_events = []
        
        print(f"\n[PHASE 2] Looping through existing events for {start_of_window} to {end_of_window}...")
        for event in existing_events:
            title = event.get('title', 'Untitled')
            
            if event.get("is_ghost"):
                continue

            if event.get("is_locked", True):
                preview_events.append(event)
                continue

            event_start_str = event.get("start", "")
            if not event_start_str:
                preview_events.append(event)
                continue
                
            parsed_start = safe_parse_dt(event_start_str)
            if not parsed_start:
                print(f"  ⚠️ Warning: Could not parse start date for '{title}'. Skipping reschedule.")
                preview_events.append(event)
                continue
                
            event_start_date = parsed_start.astimezone(calendar_optimiser.user_tz).date()
            
            # Check against the rolling window bounds
            if not (start_of_window <= event_start_date <= end_of_window):
                preview_events.append(event)
                continue

            print(f"\n  🎯 Evaluating Event: '{title}'")
            print(f"     -> Original String: {event_start_str}")
            print(f"     -> Parsed Local Time: {parsed_start.astimezone(calendar_optimiser.user_tz).strftime('%Y-%m-%d %H:%M')}")

            start_dt = safe_parse_dt(event["start"])
            end_dt = safe_parse_dt(event["end"])
            
            if not start_dt or not end_dt:
                print(f"     -> ❌ Critical error: Missing valid start/end times. Skipping.")
                preview_events.append(event)
                continue
                
            duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
            category = event.get("category", "MEETING")

            calendar_optimiser.existing_events = [e for e in calendar_optimiser.existing_events if e.get("id") != event.get("id")]

            print(f"     -> Firing Search Engine (Duration: {duration_minutes}m, Category: {category})")
            best_slot = calendar_optimiser.find_best_slot(event_start_date, duration_minutes, category, original_start_dt=start_dt)

            if best_slot:
                new_start = best_slot.start.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                new_end = best_slot.end.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                
                print(f"     -> ✅ Best Slot Found: {best_slot.start.astimezone(calendar_optimiser.user_tz).strftime('%H:%M')} (Score: {best_slot.score})")
                print(f"     -> Generated Safe String: {new_start}")
                
                event["proposed_start"] = new_start
                event["proposed_end"] = new_end
                event["requires_review"] = True 
                
                dummy_locked = dict(event)
                dummy_locked["start"] = event["proposed_start"]
                dummy_locked["end"] = event["proposed_end"]
                dummy_locked["is_locked"] = True
                calendar_optimiser.existing_events.append(dummy_locked)
            else:
                print(f"     -> ❌ Search Engine failed to find a valid slot.")
            
            preview_events.append(event)

        preview_events.extend(ghost_events)
        
        new_hash = hash_event_list(preview_events)

        if original_hash == new_hash:
            print("\n  -> 🏁 Result: Already Optimised.")
            return {
                "status": "already_optimised",
                "message": "Your calendar is already mathematically perfectly aligned with your preferences.",
                "preview_events": preview_events
            }

        print("\n  -> 🏁 Result: Optimisation Successful.")
        return {
            "status": "success",
            "preview_events": preview_events
        }

    except Exception as e:
        print(f"\n❌ [FATAL OPTIMISER ERROR] {e}\n")
        raise HTTPException(status_code=500, detail="Failed to generate calendar optimisation preview")
    
def safe_parse_dt(iso_str: str) -> dt.datetime | None:
    if not iso_str: return None
    try:
        s = str(iso_str).strip()
        s = s.replace("+00:00Z", "+00:00") 
        if s.endswith('Z'): s = s[:-1] + "+00:00"
        s = s.replace("+00:00+00:00", "+00:00")
        
        parsed = dt.datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception as e:
        print(f"[Parse Error] Failed to parse {iso_str}: {e}")
        return None

@app.post("/api/calendar/snapshot/undo")
async def undo_last_change(request: UndoRequest):
    from google.cloud import firestore
    user_id = request.user_id
    
    try:
        snapshots_ref = db.collection("users").document(user_id).collection("calendar_snapshots")
        latest_snapshots = snapshots_ref.order_by("created_at", direction=firestore.Query.DESCENDING).limit(1).get()
        
        if not latest_snapshots:
            raise HTTPException(status_code=404, detail="No snapshot found to undo")
            
        latest_snapshot_doc = latest_snapshots[0]
        snapshot_data = latest_snapshot_doc.to_dict()
        historical_events = snapshot_data.get("events", [])
        
        events_ref = db.collection("users").document(user_id).collection("raw_events")
        current_events_stream = events_ref.stream()
        
        batch = db.batch()
        
        for doc in current_events_stream:
            batch.delete(doc.reference)
            
        for event in historical_events:
            doc_id = event.pop("_id", None) or event.get("id", f"custom_{uuid.uuid4().hex[:8]}")
            event["sync_action_required"] = "push_to_provider"
            
            new_doc_ref = events_ref.document(doc_id)
            batch.set(new_doc_ref, event)
            
        batch.delete(latest_snapshot_doc.reference)
        batch.commit()
        
        return {
            "status": "success", 
            "message": f"Restored {len(historical_events)} events and removed snapshot from history."
        }

    except Exception as e:
        print(f"Error during undo: {e}")
        raise HTTPException(status_code=500, detail="Failed to undo calendar changes")
    

from pydantic import BaseModel
from typing import Any
from fastapi import HTTPException

class CommitOptimisationRequest(BaseModel):
    user_id: str
    events: list[dict[str, Any]]

@app.post("/api/calendar/optimise/commit")
async def commit_optimisation(request: CommitOptimisationRequest):
    """
    Takes the accepted preview events, creates a rollback snapshot, 
    and saves the new schedule permanently to the database.
    """
    user_id = request.user_id
    proposed_events = request.events
    
    try:
        # Step 1: Create a snapshot of the calendar before we touch anything
        create_calendar_snapshot(user_id)
        
        events_ref = db.collection("users").document(user_id).collection("raw_events")
        batch = db.batch()
        
        for event in proposed_events:
            # Safely grab the document ID
            doc_id = event.pop("_id", None) or event.get("id")
            if not doc_id:
                continue
            
            # Step 2: Swap the proposed times into the official time slots
            if event.get("proposed_start") and event.get("proposed_end"):
                event["previous_start"] = event.get("start")
                event["previous_end"] = event.get("end")
                event["start"] = event["proposed_start"]
                event["end"] = event["proposed_end"]
                
                # Clear the proposed fields since they are now official
                event["proposed_start"] = None
                event["proposed_end"] = None
            
            # Step 3: Turn AI routines from "ghosts" into real events
            if event.get("is_ghost"):
                event["is_ghost"] = False
                
            # Step 4: Flag for external sync and clear the review warnings
            event["sync_action_required"] = "push_to_provider"
            event["requires_review"] = False
            
            # Add to the database batch operation
            new_doc_ref = events_ref.document(doc_id)
            batch.set(new_doc_ref, event, merge=True)
            
        # Step 5: Commit everything to Firestore at exactly the same time
        batch.commit()
        
        return {
            "status": "success", 
            "message": "Optimisation committed and snapshot created."
        }

    except Exception as e:
        print(f"Error committing optimisation: {e}")
        raise HTTPException(status_code=500, detail="Failed to commit calendar changes")
    

############# REMINDERS API GOES HERE ############



# --- Pydantic Models for Reminders ---

class LocationData(BaseModel):
    lat: float
    lng: float
    radius: float
    trigger_on: str  # "entry" or "exit"

class ReminderCreate(BaseModel):
    user_id: str
    title: str
    body: Optional[str] = None
    type: str  # "event", "task", "standalone"
    reference_id: Optional[str] = None
    trigger_type: str  # "time", "location"
    trigger_time: Optional[str] = None
    location_data: Optional[LocationData] = None
    priority: str = "standard"  # "standard", "high"
    repeat: str = "none"  # "none", "daily", "weekly", "monthly", "custom"
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
    status: Optional[str] = None  # "pending", "delivered", "dismissed", "missed"
    custom_repeat_days: Optional[List[str]] = None

class ReminderDelete(BaseModel):
    user_id: str
    reminder_id: str


# --- Reminder API Endpoints ---

@app.post("/api/reminders/create")
async def create_reminder(req: ReminderCreate):
    try:
        batch = db.batch()
        
        # 1. Create the new reminder document
        reminders_ref = db.collection("users").document(req.user_id).collection("reminders")
        new_reminder_ref = reminders_ref.document()
        
        reminder_data = req.dict(exclude_none=True)
        reminder_data["status"] = "pending"
        reminder_data["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"
        
        batch.set(new_reminder_ref, reminder_data)

        # 2. If it links to a Task or Event, update the parent document
        if req.reference_id and req.type in ["task", "event"]:
            collection_name = "raw_tasks" if req.type == "task" else "raw_events"
            parent_ref = db.collection("users").document(req.user_id).collection(collection_name).document(req.reference_id)
            
            # Use ArrayUnion to safely append the new reminder ID without overwriting existing ones
            batch.update(parent_ref, {
                "linked_reminder_ids": firestore.ArrayUnion([new_reminder_ref.id])
            })

        # 3. Commit both writes simultaneously
        batch.commit()

        return {
            "status": "success",
            "message": "Reminder created and linked successfully",
            "reminder_id": new_reminder_ref.id
        }

    except Exception as e:
        print(f"Error creating reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reminders/list/{user_id}")
async def list_reminders(user_id: str):
    try:
        reminders_ref = db.collection("users").document(user_id).collection("reminders")
        docs = reminders_ref.stream()
        
        reminders = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            reminders.append(data)
            
        # Sort so the soonest time-based reminders appear first
        reminders.sort(key=lambda x: x.get("trigger_time") or "9999-12-31")
        
        return {"status": "success", "reminders": reminders}
        
    except Exception as e:
        print(f"Error fetching reminders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/reminders/update")
async def update_reminder(req: ReminderUpdate):
    try:
        reminder_ref = db.collection("users").document(req.user_id).collection("reminders").document(req.id)
        
        if not reminder_ref.get().exists:
            raise HTTPException(status_code=404, detail="Reminder not found")

        update_data = req.dict(exclude={"id", "user_id"}, exclude_none=True)
        update_data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"

        reminder_ref.update(update_data)
        
        return {"status": "success", "message": "Reminder updated successfully"}

    except Exception as e:
        print(f"Error updating reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/reminders/delete")
async def delete_reminder(req: ReminderDelete):
    try:
        reminder_ref = db.collection("users").document(req.user_id).collection("reminders").document(req.reminder_id)
        reminder_doc = reminder_ref.get()
        
        if not reminder_doc.exists:
            return {"status": "success", "message": "Reminder already deleted"}
            
        reminder_data = reminder_doc.to_dict()
        batch = db.batch()
        
        # 1. Queue the reminder for deletion
        batch.delete(reminder_ref)
        
        # 2. Clean up the reference on the parent Event or Task
        ref_id = reminder_data.get("reference_id")
        ref_type = reminder_data.get("type")
        
        if ref_id and ref_type in ["task", "event"]:
            collection_name = "raw_tasks" if ref_type == "task" else "raw_events"
            parent_ref = db.collection("users").document(req.user_id).collection(collection_name).document(ref_id)
            
            # Only update the parent if it still exists
            if parent_ref.get().exists:
                batch.update(parent_ref, {
                    "linked_reminder_ids": firestore.ArrayRemove([req.reminder_id])
                })

        batch.commit()
        
        return {"status": "success", "message": "Reminder deleted and unlinked successfully"}

    except Exception as e:
        print(f"Error deleting reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))









##################################################





from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class SubTask(BaseModel):
    id: str
    title: str
    is_completed: bool = False

class TaskRequest(BaseModel):
    id: Optional[str] = None
    user_id: str
    title: str
    description: Optional[str] = ""
    
    # The Checklist
    sub_tasks: List[SubTask] = []
    
    # Timing
    estimated_duration: Optional[int] = None  # In minutes. Null means flexible/stacked view.
    start_date: Optional[str] = None  # Earliest time to start (ISO string)
    due_date: Optional[str] = None    # Hard deadline (ISO string)
    
    # Categorisation & AI Hooks
    status: str = "pending" # pending, scheduled, in_progress, completed, missed
    priority: int = 3 # 1 (High) to 5 (Low)
    energy_level: Optional[str] = "medium" # high, medium, low
    tags: List[str] = []
    
    # System Linkages
    linked_event_id: Optional[str] = None
    linked_reminder_ids: List[str] = [] # Array of IDs pointing to the Reminders collection
    is_locked: bool = False
    created_at: Optional[str] = None
    
    # --- NEW TELEMETRY FIELDS ---
    snooze_count: int = 0
    completed_at: Optional[str] = None
    debt_applied: bool = False
    is_perishable: bool = False # Tasks are generally reschedulable, but kept for schema parity

@app.post("/api/tasks/create")
async def create_task(task: TaskRequest):
    try:
        task_id = f"task_{uuid.uuid4().hex[:10]}"
        task_data = task.model_dump() 
        
        task_data["id"] = task_id
        task_data["created_at"] = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Ensure sub-tasks have unique IDs if not provided by frontend
        for i, sub in enumerate(task_data.get("sub_tasks", [])):
            if not sub.get("id"):
                sub["id"] = f"sub_{uuid.uuid4().hex[:8]}"
        
        db.collection("users").document(task.user_id).collection("raw_tasks").document(task_id).set(task_data)
        
        return {"status": "success", "task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





def calculate_risk_score(task_data: dict, global_time_debt: int) -> int:
    """
    Calculates a 0-100 risk score representing the probability of failing this task.
    """
    if task_data.get("status") not in ["pending", "scheduled"]:
        return 0

    # 1. Base risk from priority (1 = Highest, 5 = Lowest)
    priority = task_data.get("priority", 3)
    base_risk = {1: 40, 2: 30, 3: 20, 4: 10, 5: 5}.get(priority, 20)

    # 2. Snooze penalty (15 points per snooze, compounding)
    snooze_count = task_data.get("snooze_count", 0)
    snooze_penalty = snooze_count * 15

    # 3. Global Debt Burden (Every 60 mins of global debt adds 5 points of overwhelm risk)
    safe_debt = max(0, global_time_debt)
    debt_penalty = (safe_debt // 60) * 5

    # 4. Duration Friction (Tasks over 60 mins get a 10 point procrastination penalty)
    duration_penalty = 0
    est_duration = task_data.get("estimated_duration") or 60
    if est_duration > 60:
        duration_penalty = 10

    total_risk = base_risk + snooze_penalty + debt_penalty + duration_penalty

    # Cap firmly between 0 and 100
    return max(0, min(100, total_risk))


@app.get("/api/tasks/list/{user_id}")
async def list_tasks(user_id: str):
    try:
        # Fetch global time debt first to feed the algorithm
        user_doc = db.collection("users").document(user_id).get()
        global_debt = 0
        if user_doc.exists:
            global_debt = user_doc.to_dict().get("total_time_debt", 0)

        tasks_ref = db.collection("users").document(user_id).collection("raw_tasks")
        docs = tasks_ref.stream()
        
        tasks = []
        for doc in docs:
            t_data = doc.to_dict()
            
            # Inject dynamic risk score before sending to frontend
            t_data["risk_score"] = calculate_risk_score(t_data, global_debt)
            tasks.append(t_data)
        
        # Sort by risk score (highest first), then by due date
        tasks.sort(key=lambda x: (-x.get("risk_score", 0), x.get("due_date") or "9999"))
        
        return {"status": "success", "tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
import datetime

class TaskUpdate(BaseModel):
    id: str
    user_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    sub_tasks: Optional[List[Dict[str, Any]]] = None
    estimated_duration: Optional[int] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    energy_level: Optional[str] = None
    tags: Optional[List[str]] = None
    linked_event_ids: Optional[List[str]] = None
    
    # --- NEW TELEMETRY UPDATE FIELDS ---
    snooze_count: Optional[int] = None
    completed_at: Optional[str] = None
    debt_applied: Optional[bool] = None
    is_perishable: Optional[bool] = None


@app.put("/api/tasks/update")
async def update_task(task: TaskUpdate):
    try:
        task_ref = db.collection("users").document(task.user_id).collection("raw_tasks").document(task.id)
        existing_task_doc = task_ref.get()
        
        if not existing_task_doc.exists:
            raise HTTPException(status_code=404, detail="Task not found")
            
        existing_data = existing_task_doc.to_dict()
        old_status = existing_data.get("status")
        
        # exclude_none ensures we don't overwrite existing arrays with nulls if the frontend omits them
        update_data = task.dict(exclude={"id", "user_id"}, exclude_none=True)
        
        # --- 1. TELEMETRY HOOKS: The Snooze Tracker ---
        old_due_str = existing_data.get("due_date")
        new_due_str = task.due_date if task.due_date is not None else old_due_str
        
        old_due = parse_iso(old_due_str)
        new_due = parse_iso(new_due_str)
        
        snooze_increment = 0
        if old_due and new_due and new_due > old_due:
            snooze_increment = 1
            
        update_data["snooze_count"] = existing_data.get("snooze_count", 0) + snooze_increment

        # --- 2. TELEMETRY HOOKS: The Debt Relief Hook ---
        debt_applied = existing_data.get("debt_applied", False)
        is_perish = existing_data.get("is_perishable", False)
        
        if old_status == "missed" and snooze_increment > 0:
            # Resurrect the task to pending if the user didn't explicitly send a new terminal status
            if task.status not in ["completed", "missed"]:
                update_data["status"] = "pending"
                
            if debt_applied and not is_perish:
                refund_mins = 0
                est_dur = existing_data.get("estimated_duration")
                
                # If there's an estimated duration, use it directly.
                if est_dur:
                    refund_mins = est_dur
                else:
                    # Otherwise, calculate from linked events, BUT ONLY if they were actually missed
                    linked_evs = existing_data.get("linked_event_ids", [])
                    if linked_evs:
                        ev_ref = db.collection("users").document(task.user_id).collection("raw_events")
                        for eid in linked_evs:
                            edoc = ev_ref.document(eid).get()
                            if edoc.exists:
                                edata = edoc.to_dict()
                                # PERFECT MATH FIX: Only refund time that contributed to the debt
                                if edata.get("completion_status") == "missed":
                                    es = parse_iso(edata.get("start"))
                                    ee = parse_iso(edata.get("end"))
                                    if es and ee:
                                        refund_mins += int((ee - es).total_seconds() / 60)
                                        
                if refund_mins > 0:
                    db.collection("users").document(task.user_id).update({
                        "total_time_debt": firestore.Increment(-refund_mins)
                    })
                    print(f"💰 Refunded {refund_mins} minutes of Task Time Debt")
                    
            update_data["debt_applied"] = False

        # --- 3. TELEMETRY HOOKS: The Completion Timestamp ---
        new_status = update_data.get("status", old_status)
        if new_status == "completed" and old_status != "completed":
            update_data["completed_at"] = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        elif new_status != "completed":
            update_data["completed_at"] = None

        # --- 4. FUTURE EVENT CLEANUP LOGIC ---
        if new_status == "completed" and old_status != "completed":
            linked_event_ids = existing_data.get("linked_event_ids", [])
            
            if linked_event_ids:
                events_ref = db.collection("users").document(task.user_id).collection("raw_events")
                now = dt.datetime.now(timezone.utc)
                
                batch = db.batch()
                events_deleted = 0
                events_to_keep = []
                
                for event_id in linked_event_ids:
                    event_doc = events_ref.document(event_id).get()
                    if event_doc.exists:
                        event_data = event_doc.to_dict()
                        event_start_str = event_data.get("start")
                        
                        if event_start_str:
                            start_dt = dt.datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
                            
                            # If the event is in the future, delete it from the calendar
                            if start_dt > now:
                                batch.delete(events_ref.document(event_id))
                                events_deleted += 1
                            else:
                                events_to_keep.append(event_id)
                        else:
                            events_to_keep.append(event_id)
                            
                if events_deleted > 0:
                    batch.commit()
                    update_data["linked_event_ids"] = events_to_keep
        
        task_ref.update(update_data)
        
        return {"status": "success", "message": "Task updated successfully"}
        
    except Exception as e:
        print(f"Error updating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DeleteTaskRequest(BaseModel):
    user_id: str
    task_id: str

@app.delete("/api/tasks/delete")
async def delete_task(request: DeleteTaskRequest):
    try:
        db.collection("users").document(request.user_id).collection("raw_tasks").document(request.task_id).delete()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
class TaskScheduleRequest(BaseModel):
    user_id: str
    target_date: str
    task_ids: List[str] = [] # If empty, it will schedule all valid pending tasks

from pydantic import BaseModel
from llm_duration import DurationEstimator

class EstimateRequest(BaseModel):
    title: str
    description: Optional[str] = ""

estimator = DurationEstimator()

@app.post("/api/tasks/estimate-duration")
async def estimate_duration(req: EstimateRequest):
    try:
        minutes = estimator.estimate(req.title, req.description)
        return {"status": "success", "estimated_minutes": minutes}
    except Exception as e:
        return {"status": "error", "estimated_minutes": 60, "detail": str(e)}



@app.post("/api/tasks/schedule/preview")
async def preview_task_scheduling(request: TaskScheduleRequest):
    user_id = request.user_id
    target_date_str = request.target_date
    
    try:
        clean_date_str = target_date_str[:10] 
        target_date = dt.datetime.fromisoformat(clean_date_str).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format.")

    try:
        # --- THE FIX: DYNAMIC TIMEZONE ---
        user_tz = get_user_timezone(user_id)
        
        prefs_ref = db.collection("users").document(user_id).collection("preferences")
        preferences = [doc.to_dict() for doc in prefs_ref.stream()]

        events_ref = db.collection("users").document(user_id).collection("raw_events")
        existing_events = []
        for doc in events_ref.stream():
            event_data = doc.to_dict()
            event_data["id"] = doc.id
            existing_events.append(event_data)

        tasks_ref = db.collection("users").document(user_id).collection("raw_tasks")
        tasks_stream = tasks_ref.where("status", "in", ["pending"]).stream()
        
        if request.task_ids:
            pending_tasks = [doc.to_dict() for doc in tasks_stream if doc.id in request.task_ids]
        else:
            pending_tasks = [doc.to_dict() for doc in tasks_stream]

        # Inject the timezone string into the TaskScheduler
        task_scheduler = TaskScheduler(existing_events, preferences, user_tz_string=str(user_tz))
        
        horizon_end = target_date + timedelta(days=14)
        task_ghosts = task_scheduler.schedule_tasks(target_date, horizon_end, pending_tasks)

        return {
            "status": "success",
            "original_events": existing_events,
            "preview_events": existing_events + task_ghosts
        }
    except Exception as e:
        print(f"Error during task scheduling preview: {e}")
        raise HTTPException(status_code=500, detail=str(e))



from pydantic import BaseModel
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException

class TaskScheduleCommitRequest(BaseModel):
    user_id: str
    events: List[Dict[str, Any]]

@app.post("/api/tasks/schedule/commit")
async def commit_task_schedule(request: TaskScheduleCommitRequest):
    user_id = request.user_id
    events = request.events

    try:
        # 1. Filter out ONLY the new ghost events created for tasks
        task_ghosts = [e for e in events if e.get("is_ghost") and e.get("provider") == "tasks"]

        if not task_ghosts:
            return {"status": "success", "message": "No new tasks to schedule."}

        task_event_map = {}
        batch = db.batch() 

        events_ref = db.collection("users").document(user_id).collection("raw_events")

        # 2. Process each ghost event into a real database event
        for ghost in task_ghosts:
            task_id = ghost.get("linked_task_id")
            if not task_id:
                continue

            event_data = dict(ghost)
            event_data.pop("is_ghost", None)
            event_data.pop("id", None) 
            
            new_event_ref = events_ref.document()
            new_event_id = new_event_ref.id
            
            event_data["linked_task_id"] = task_id
            
            batch.set(new_event_ref, event_data)

            if task_id not in task_event_map:
                task_event_map[task_id] = []
            task_event_map[task_id].append(new_event_id)

        # 3. Update the original tasks with their new event IDs and status
        tasks_ref = db.collection("users").document(user_id).collection("raw_tasks")
        
        for task_id, event_ids in task_event_map.items():
            task_ref = tasks_ref.document(task_id)
            
            # ArrayUnion ensures we don't overwrite any existing event IDs if the task was already partially scheduled
            batch.update(task_ref, {
                "linked_event_ids": firestore.ArrayUnion(event_ids),
                "status": "scheduled"
            })

        # 4. Execute the batch transaction
        batch.commit()

        return {
            "status": "success", 
            "message": f"Successfully scheduled {len(task_ghosts)} events for {len(task_event_map)} tasks."
        }

    except Exception as e:
        print(f"Error committing task schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    


 
class AIParseRequest(BaseModel):
    text:             str
    user_id:          str
    timezone:         str           = "UTC"
    intent_override:  Optional[str] = None
    entity_overrides: Optional[dict]= None


class FeedbackRequest(BaseModel):
    interaction_id: str        # the chat_history doc id of the assistant turn
    prompt:         str        # the original user message
    response:       str        # the assistant message they're rating
    rating:         str        # "positive" | "negative"
    source:         str = ""   # routing source if available
    intents:        list = []
    entities:       dict = {}

class VocabularyRequest(BaseModel):
    user_id: str
    alias:   str    # e.g. "fyp"
    full:    str    # e.g. "final year project"


def _expand_aliases(text: str, aliases: dict) -> str:
    """
    Replaces known user aliases with their full forms.
    Matches whole words only so 'ml' doesn't expand inside 'email'.
    Logs any expansions so they're visible in server output.
    """
    expanded = text
    for alias, full_form in aliases.items():
        pattern  = rf'\b{re.escape(alias)}\b'
        replaced = re.sub(pattern, full_form, expanded, flags=re.IGNORECASE)
        if replaced != expanded:
            print(f"[AliasExpander] '{alias}' → '{full_form}'")
            expanded = replaced
    return expanded

def _load_aliases(db, user_id: str) -> dict:
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

_TEACH_PATTERN = re.compile(
    r"(?:when i say|if i say|by|use)\s+['\"]?(\w+)['\"]?\s+"
    r"(?:i mean|it means|that means|refers to|stands for|to mean)\s+(.+)",
    re.IGNORECASE
)

_TEACH_PATTERN_2 = re.compile(
    r"['\"]?(\w+)['\"]?\s+(?:stands for|means|is short for|is an acronym for)\s+(.+)",
    re.IGNORECASE
)

def _detect_teach_phrase(text: str):
    """
    Returns (alias, full_form) if the text is a teach phrase, else None.
    """
    for pattern in [_TEACH_PATTERN, _TEACH_PATTERN_2]:
        match = pattern.search(text)
        if match:
            alias     = match.group(1).lower().strip()
            full_form = match.group(2).strip().rstrip(".")
            return alias, full_form
    return None

@app.post("/api/vocabulary")
async def add_vocabulary(req: VocabularyRequest):
    try:
        vocab_ref = (
            db.collection("users")
              .document(req.user_id)
              .collection("vocabulary")
              .document("aliases")
        )
        vocab_ref.set(
            {"aliases": {req.alias.lower(): req.full.strip()}},
            merge=True
        )
        print(f"[Vocabulary] Saved: '{req.alias}' → '{req.full}' for {req.user_id}")
        return {
            "status":  "success",
            "message": f"Got it — I'll treat '{req.alias}' as '{req.full}' from now on.",
        }
    except Exception as e:
        print(f"[Vocabulary] Save failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/vocabulary/{user_id}")
async def get_vocabulary(user_id: str):
    try:
        aliases = _load_aliases(db, user_id)
        return {"status": "success", "aliases": aliases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/vocabulary/{user_id}/{alias}")
async def delete_vocabulary(user_id: str, alias: str):
    try:
        vocab_ref = (
            db.collection("users")
              .document(user_id)
              .collection("vocabulary")
              .document("aliases")
        )
        vocab_ref.update({f"aliases.{alias.lower()}": firestore.DELETE_FIELD})
        return {"status": "success", "message": f"Removed alias '{alias}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ------------------------------------------------------------------ #
#  POST /api/ai/feedback                                               #
# ------------------------------------------------------------------ #
@app.post("/api/ai/feedback")
async def submit_feedback(req: FeedbackRequest):
    """
    Receives a thumbs up/down from the frontend, sends the prompt +
    response pair to Gemini for structured analysis, then stores the
    result in Firestore under users/{user_id}/feedback.

    Gemini's job is to:
      - Validate the feedback is meaningful (not a mis-tap)
      - Identify which component likely caused a failure
      - Produce a structured failure_type for later analysis
    """
    try:
        # ── 1. Gemini analysis ─────────────────────────────────────────
        analysis = {"actionable": True, "failure_type": "unknown",
                    "component": "unknown", "confidence": "low", "summary": ""}

        if nlu_engine.gemini_client:
            prompt = f"""
            You are an AI quality analyst for a scheduling assistant.
            
            A user gave a {'THUMBS DOWN (negative)' if req.rating == 'negative' else 'THUMBS UP (positive)'} rating.

            USER'S ORIGINAL MESSAGE:
            "{req.prompt}"

            ASSISTANT'S RESPONSE:
            "{req.response}"

            ROUTING METADATA:
            - Source: {req.source}
            - Intents detected: {req.intents}
            - Entities extracted: {json.dumps(req.entities, indent=2)}

            Your task:
            1. Determine if this feedback is ACTIONABLE (a real error vs a mis-tap or 
               user changing their mind).
            2. If negative and actionable, identify the most likely failure component:
               - "intent_classification" — wrong intent was chosen
               - "NER" — right intent but wrong entities extracted (wrong time, title, date)
               - "routing" — should have gone to LLM but went to NLU, or vice versa
               - "handler" — intent and entities were correct but the DB operation failed
               - "response_format" — the action was correct but the reply was confusing
               - "out_of_scope" — user asked for something the system cannot do
            3. Classify the failure_type with one of these labels:
               "temporal_extraction" | "title_extraction" | "intent_mismatch" |
               "routing_error" | "slot_conflict" | "context_loss" | "correct" | "other"
            4. Rate your confidence: "high" | "medium" | "low"
            5. Write a one-sentence summary explaining what went wrong (or right).

            Return ONLY valid JSON:
            {{
                "actionable":    true,
                "failure_type":  "temporal_extraction",
                "component":     "NER",
                "confidence":    "high",
                "summary":       "NER failed to extract the start and end times from the utterance."
            }}
            """

            try:
                from google.genai import types as gtypes
                response = nlu_engine.gemini_client.models.generate_content(
                    model="gemini-3-pro-preview",
                    contents=prompt,
                    config=gtypes.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                analysis = json.loads(response.text)
                print(f"[Feedback] Gemini analysis: {analysis}")
            except Exception as e:
                print(f"[Feedback] Gemini analysis failed: {e}")

        # ── 2. Store in Firestore ──────────────────────────────────────
        feedback_data = {
            "prompt":       req.prompt,
            "response":     req.response,
            "rating":       req.rating,
            "source":       req.source,
            "intents":      req.intents,
            "entities":     req.entities,
            "analysis":     analysis,
            "timestamp":    firestore.SERVER_TIMESTAMP,
            "reviewed":     False,
        }

        # Store globally for your dissertation analysis
        db.collection("feedback").add(feedback_data)

        # Also store under the user for per-user analysis
        db.collection("users").document(req.interaction_id.split("_")[0] if "_" in req.interaction_id else "unknown")\
          .collection("feedback").add(feedback_data)

        print(f"[Feedback] Stored: {req.rating} | {analysis.get('failure_type')} | {analysis.get('component')}")

        return {
            "status":  "success",
            "message": "Thanks for the feedback.",
            "analysis": analysis,
        }

    except Exception as e:
        print(f"[Feedback] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
 
 
# ------------------------------------------------------------------ #
#  HELPER — persist a single chat turn to Firestore                   #
# ------------------------------------------------------------------ #
def _save_chat_message(db, user_id: str, role: str, content: str, source: str = "unknown"):
    """
    Appends one message to the user's persistent chat_history collection.
    Called once for the user turn and once for the assistant turn so the
    LLM escalation path always has up-to-date context on the next request.
    """
    try:
        db.collection("users").document(user_id).collection("chat_history").add({
            "role":      role,
            "text":      content,
            "source":    source,
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        print(f"[ChatHistory] Failed to save message: {e}")
 
 
# ------------------------------------------------------------------ #
#  HELPER — fetch recent chat history as a formatted string           #
# ------------------------------------------------------------------ #
def _get_chat_history_string(db, user_id: str, limit: int = 12) -> str:
    """
    Returns the last `limit` messages as a newline-separated string
    in the format "[User]: ..." / "[Assistant]: ..." so the LLM prompt
    can resolve pronoun references like "it", "that time", "the one you suggested".
    """
    try:
        docs = (
            db.collection("users").document(user_id).collection("chat_history")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        lines = []
        for doc in docs:
            d       = doc.to_dict()
            role    = d.get("role", "unknown").capitalize()
            content = d.get("text") or d.get("content") or ""
            lines.append(f"[{role}]: {content}")
        lines.reverse()   # oldest first so the LLM reads it chronologically
        return "\n".join(lines)
    except Exception as e:
        print(f"[ChatHistory] Failed to fetch: {e}")
        return ""
 
 
# ------------------------------------------------------------------ #
#  HELPER — build a human-readable assistant message from results     #
# ------------------------------------------------------------------ #
def _build_assistant_message(results: list, original_text: str) -> str:
    """
    Extracts the natural language reply from dispatch results so we can
    save it to chat history for future LLM context.
    """
    for r in results:
        status = r.get("status")
        if status == "success":
            msg = r.get("result", {})
            if isinstance(msg, dict):
                return msg.get("message", "Done.")
            return str(msg)
        if status == "chat_response":
            return str(r.get("result", ""))
        if status == "clarification_needed":
            return r.get("message", "I need a bit more information.")
        if status == "error":
            return r.get("error", "Something went wrong.")
    return "Request processed."
 
 
# ------------------------------------------------------------------ #
#  GET /api/ai/history/{user_id}                                       #
# ------------------------------------------------------------------ #
@app.get("/api/ai/history/{user_id}")
async def get_chat_history(user_id: str):
    """
    Fetches the persistent chat history for a specific user.
    Handles multiple timestamp formats safely to prevent attribute errors.
    """
    try:
        chat_ref = db.collection("users").document(user_id).collection("chat_history")
        docs = chat_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(50).stream()
 
        history = []
        for doc in docs:
            data   = doc.to_dict()
            raw_ts = data.get("timestamp")
            iso_ts = dt.datetime.now(timezone.utc).isoformat()
 
            if raw_ts:
                if hasattr(raw_ts, "isoformat"):
                    iso_ts = raw_ts.isoformat()
                elif isinstance(raw_ts, str):
                    iso_ts = raw_ts
                elif isinstance(raw_ts, dt.datetime):
                    iso_ts = raw_ts.isoformat()
 
            history.append({
                "id":         doc.id,
                "role":       data.get("role"),
                "content":    data.get("text") or data.get("content") or "",
                "timestamp":  iso_ts,
                "source":     data.get("source", "unknown"),
                "isResolved": True,
            })
 
        return {"status": "success", "history": history[::-1]}   # chronological
 
    except Exception as e:
        print(f"❌ Error fetching history for {user_id}: {e}")
        return {"status": "error", "history": [], "detail": str(e)}
 
 


@app.post("/api/ai/parse")
async def parse_event_with_ai(req: AIParseRequest):
    try:
        now_iso  = dt.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # --- THE FIX: DYNAMIC TIMEZONE ---
        user_tz = get_user_timezone(req.user_id)
 
        events_ref = db.collection("users").document(req.user_id).collection("raw_events")
        tasks_ref  = db.collection("users").document(req.user_id).collection("raw_tasks")
 
        chat_history_str = _get_chat_history_string(db, req.user_id)
        aliases = _load_aliases(db, req.user_id)
        teach = _detect_teach_phrase(req.text)

        if teach:
            alias, full_form = teach
            vocab_ref = (
                db.collection("users")
                .document(req.user_id)
                .collection("vocabulary")
                .document("aliases")
            )
            vocab_ref.set({"aliases": {alias: full_form}}, merge=True)
            reply = f"Got it — I'll treat '{alias}' as '{full_form}' from now on."
            _save_chat_message(db, req.user_id, role="assistant", content=reply, source="vocabulary")
            return {"status": "success", "type": "chat", "message": reply}
        
        expanded_text = _expand_aliases(req.text, aliases)
        if expanded_text != req.text:
            print(f"[AliasExpander] Expanded user input: '{req.text}' → '{expanded_text}'")

        _save_chat_message(db, req.user_id, role="user", content=expanded_text, source="user_input")

        _WEEKDAY_MAP = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }
 
        _from_day_match = re.search(
            r'\b(?:move|reschedule|shift|cancel)\b.*?\bfrom\s+'
            r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow)\b',
            expanded_text.lower()
        )
 
        context_string = "--- UPCOMING EVENTS ---\n"
        event_count    = 0
 
        if _from_day_match:
            _day_str   = _from_day_match.group(1)
            # Uses the dynamic timezone for local midnight calculations
            _now_local = dt.datetime.now(user_tz)
 
            if _day_str == "today":
                _local_midnight = _now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            elif _day_str == "tomorrow":
                _local_midnight = (_now_local + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                _target_wday  = _WEEKDAY_MAP[_day_str]
                _days_until   = (_target_wday - _now_local.weekday()) % 7
                if _days_until == 0:
                    _days_until = 7
                _local_midnight = (_now_local + dt.timedelta(days=_days_until)).replace(hour=0, minute=0, second=0, microsecond=0)
 
            _utc_window_start = _local_midnight.astimezone(dt.timezone.utc)
            _utc_window_end   = _utc_window_start + dt.timedelta(hours=24)
            _w_start_iso      = _utc_window_start.isoformat().replace("+00:00", "Z")
            _w_end_iso        = _utc_window_end.isoformat().replace("+00:00", "Z")
 
            print(f"[Context] Bulk-move detected for '{_day_str}'. UTC window: {_w_start_iso} → {_w_end_iso}")
 
            _day_docs = events_ref.where("start", ">=", _w_start_iso).stream()
            for doc in _day_docs:
                data        = doc.to_dict()
                event_start = data.get("start", "")
                if event_start < _w_end_iso:
                    context_string += f"- {data.get('title', 'Untitled')} (Starts: {event_start}, Ends: {data.get('end', '?')})\n"
                    event_count += 1
        else:
            upcoming_events = events_ref.where("end", ">=", now_iso).limit(30).stream()
            for doc in upcoming_events:
                data = doc.to_dict()
                context_string += f"- {data.get('title', 'Untitled')} (Starts: {data.get('start', '?')}, Ends: {data.get('end', '?')})\n"
                event_count += 1
 
        if event_count == 0:
            context_string += "User has no upcoming events.\n"
 
        context_string += "\n--- PENDING TASKS ---\n"
        pending_tasks  = tasks_ref.where("status", "==", "pending").limit(30).stream()
        task_count     = 0
        for doc in pending_tasks:
            data = doc.to_dict()
            context_string += f"- {data.get('title', 'Untitled')} (Due: {data.get('due_date', 'No due date')})\n"
            task_count += 1
        if task_count == 0:
            context_string += "User has no pending tasks.\n"
 
        if req.intent_override and req.entity_overrides is not None:
            print(f"[Parse] Using confirmed overrides: intent={req.intent_override}")
            routing_result = {
                "source":       "user_confirmed",
                "intents":      [req.intent_override],
                "entities":     req.entity_overrides,
                "text":         expanded_text,
                "chat_response": "",
            }
        else:
            routing_result = routing_engine.evaluate(
                expanded_text,
                user_context=context_string,
                chat_history=chat_history_str,
                user_timezone=str(user_tz)
            )
 
        print(f"Routing result: {routing_result}")
 
        if routing_result.get("chat_response"):
            reply = routing_result["chat_response"]
            _save_chat_message(db, req.user_id, role="assistant", content=reply, source="LLM_chat")
            return {"status": "success", "type": "chat", "message": reply}
 
        if routing_result.get("intents"):
            dispatch_results = routing_engine.dispatch(
                nlu_result      = routing_result,
                user_id         = req.user_id,
                intent_handlers = db_engine.get_intent_map()
            )
 
            clarification_items = [r for r in dispatch_results if r.get("status") == "clarification_needed"]
            if clarification_items:
                cl = clarification_items[0]
                cl_type = cl.get("clarification_type")
 
                if cl_type == "ambiguous_match":
                    clarification_msg = cl.get("message", "I found multiple matches. Which did you mean?")
                elif cl_type == "slot_conflict":
                    clarification_msg = cl.get("message", "That time slot is already booked.")
                else:
                    clarification_msg = cl.get("message", "I need more information.")
 
                _save_chat_message(db, req.user_id, role="assistant",
                                   content=clarification_msg, source="clarification")
 
                return {
                    "status":             "clarification_needed",
                    "type":               "clarification",
                    "clarification_type": cl_type,
                    "message":            clarification_msg,
                    "candidates": [
                        {
                            "id":          c.get("id", ""),
                            "title":       c.get("title", ""),
                            "start":       c.get("start", ""),
                            "end":         c.get("end", ""),
                            "location":    c.get("location", ""),
                            "description": c.get("description", ""),
                            "due_date":    c.get("due_date", ""),
                            "status":      c.get("status", ""),
                        }
                        for c in cl.get("candidates", [])
                    ],
                    "query":              cl.get("query", ""),
                    "entity_key":         cl.get("entity_key", "events"),
                    "requested_start":    cl.get("requested_start"),
                    "requested_end":      cl.get("requested_end"),
                    "suggested_start":    cl.get("suggested_start"),
                    "suggested_end":      cl.get("suggested_end"),
                    "title":              cl.get("title"),
                    "original_intent":   cl.get("intent"),
                    "original_entities": routing_result.get("entities", {}),
                    "original_text":     expanded_text,
                }
 
            assistant_msg = _build_assistant_message(dispatch_results, expanded_text)
            _save_chat_message(db, req.user_id, role="assistant",
                               content=assistant_msg, source=routing_result.get("source", "unknown"))
 
            return {
                "status":        "success",
                "type":          "action",
                "results":       dispatch_results,
                "original_text": expanded_text,
            }
 
        fallback_msg = "I couldn't quite grasp that scheduling request. Could you rephrase it?"
        _save_chat_message(db, req.user_id, role="assistant", content=fallback_msg, source="fallback")
        return {"status": "error", "message": fallback_msg}
 
    except Exception as e:
        print(f"API Engine error: {e}")
        raise HTTPException(status_code=500, detail=str(e))




class DeleteEventRequest(BaseModel):
    event_id: str
    user_id: str

@app.delete("/api/calendar/delete-event")
async def delete_event_endpoint(req: DeleteEventRequest):
    try:
        print(f"Manual Delete Request for Event: {req.event_id}")
        doc_ref = db.collection("users").document(req.user_id).collection("raw_events").document(req.event_id)
        linked_task_id = doc_ref.get().to_dict().get("linked_task_id")
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Event not found")
            
        doc_ref.delete()
        if linked_task_id:
            sync_task_with_events(req.user_id, linked_task_id)

        return {"status": "success", "message": "Event deleted successfully"}
        
    except Exception as e:
        print(f"Delete Endpoint Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    




from fastapi import APIRouter, HTTPException
import datetime as dt
from datetime import timezone
from google.cloud import firestore

# Ensure you have your parse_iso helper available here


@app.get("/api/analytics/summary/{user_id}")
async def get_analytics_summary(user_id: str):
    """
    Powers the Productivity Dashboard. Returns global debt ledgers 
    and specifically highlights the highest-risk tasks.
    """
    try:
        # 1. Fetch Global Ledgers
        user_doc = db.collection("users").document(user_id).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        total_time_debt = user_data.get("total_time_debt", 0)
        sunk_time_debt = user_data.get("sunk_time_debt", 0)
        
        # 2. Fetch and Score Pending Tasks
        tasks_ref = db.collection("users").document(user_id).collection("raw_tasks")
        
        scored_tasks = []
        for status in ["pending", "scheduled"]:
            for doc in tasks_ref.where("status", "==", status).stream():
                t_data = doc.to_dict()
                t_data["risk_score"] = calculate_risk_score(t_data, total_time_debt)
                scored_tasks.append(t_data)
                
        # Sort by highest risk first
        scored_tasks.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
        
        # Filter for only tasks that are actually in danger (e.g., > 40% risk)
        high_risk_tasks = [t for t in scored_tasks if t.get("risk_score", 0) >= 40]
        
        return {
            "status": "success",
            "metrics": {
                "active_time_debt_mins": total_time_debt,
                "sunk_time_debt_mins": sunk_time_debt,
                "total_pending_tasks": len(scored_tasks)
            },
            "high_risk_tasks": high_risk_tasks[:5] # Only return the top 5 most dangerous tasks
        }
        
    except Exception as e:
        print(f"❌ [Analytics Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

import datetime as dt
from datetime import timezone
from collections import defaultdict
import pickle
import json
import pandas as pd
import numpy as np
import shap




# -------------------------------------------------------------------
# 4. PYDANTIC SCHEMAS
# -------------------------------------------------------------------
class TaskRiskRequest(BaseModel):
    snooze_count: int
    priority: int
    energy_level: int | str
    estimated_duration: int
    global_time_debt: float
    tasks_due_same_day: int
    days_since_created: int
    hour_of_due_time: int
    day_of_week: int

class RescheduleItem(BaseModel):
    id: str
    title: str
    duration: int
    priority: int
    original_type: str
    parent_task_id: str | None = None

# -------------------------------------------------------------------
# 5. HELPER FUNCTIONS
# -------------------------------------------------------------------

def encode_task_for_inference(task: dict) -> dict:
    task = dict(task)
    hour = task.pop("hour_of_due_time")
    day  = task.pop("day_of_week")

    task["hour_sin"] = float(np.sin(2 * np.pi * hour / 24))
    task["hour_cos"] = float(np.cos(2 * np.pi * hour / 24))
    task["day_sin"]  = float(np.sin(2 * np.pi * day / 7))
    task["day_cos"]  = float(np.cos(2 * np.pi * day / 7))

    days = max(int(task.get("days_since_created", 1)), 1)
    task["snooze_rate"] = task.get("snooze_count", 0) / days
    return task

def explain_prediction(explainer, encoded_task: dict, column_order: list, original_task: dict = None) -> list:
    row = pd.DataFrame([[encoded_task[col] for col in column_order]], columns=column_order)
    shap_values = explainer.shap_values(row)
    
    if isinstance(shap_values, list):
        sv = shap_values[1][0]       
    elif shap_values.ndim == 3:
        sv = shap_values[0, :, 1]    
    else:
        sv = shap_values[0]

    ENERGY_LABELS = {1: "Low", 2: "Medium", 3: "High"}

    def feature_label(feat, val, original):
        if feat in ("hour_sin", "hour_cos"):
            h = original.get("hour_of_due_time", "?") if original else "?"
            return f"Due time: {h}:00"
        if feat in ("day_sin", "day_cos"):
            d = original.get("day_of_week", -1) if original else -1
            day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d] if 0 <= d <= 6 else "?"
            return f"Day: {day_name}"
        
        label_map = {
            "snooze_count":       f"Snoozed {int(val)} time(s)",
            "priority":           f"Priority {int(val)}",
            "energy_level":       f"Energy: {ENERGY_LABELS.get(int(val), str(val))}",
            "estimated_duration": f"Duration: {int(val)} mins",
            "global_time_debt":   f"Time debt: {int(val)} mins",
            "tasks_due_same_day": f"{int(val)} other tasks today",
            "days_since_created": f"Task age: {int(val)} days",
            "snooze_rate":        f"Snooze rate: {val:.2f}/day",
        }
        return label_map.get(feat, feat)

    hour_shap, day_shap, other = 0.0, 0.0, []

    for feat, val, sv_val in zip(column_order, row.iloc[0], sv):
        if feat in ("hour_sin", "hour_cos"):
            hour_shap += float(sv_val)
        elif feat in ("day_sin", "day_cos"):
            day_shap += float(sv_val)
        else:
            other.append({
                "feature":   feat,
                "value":     float(val),
                "shap":      round(float(sv_val), 4),
                "direction": "increases_risk" if sv_val > 0 else "decreases_risk",
                "label":     feature_label(feat, val, original_task)
            })

    h = original_task.get("hour_of_due_time", "?") if original_task else "?"
    d = original_task.get("day_of_week", -1) if original_task else -1
    day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d] if 0 <= d <= 6 else "?"

    other.append({
        "feature": "hour_of_due_time", "value": h, "shap": round(hour_shap, 4),
        "direction": "increases_risk" if hour_shap > 0 else "decreases_risk", "label": f"Due time: {h}:00"
    })
    other.append({
        "feature": "day_of_week", "value": d, "shap": round(day_shap, 4),
        "direction": "increases_risk" if day_shap > 0 else "decreases_risk", "label": f"Day: {day_name}"
    })

    other.sort(key=lambda x: abs(x["shap"]), reverse=True)

    for item in other:
        sign = "+" if item["shap"] > 0 else "-"
        pct  = abs(round(item["shap"] * 100, 1))
        item["explanation"] = f"{item['label']} ({sign}{pct}% risk)"

    return other

def predict_risk(model, explainer, task: dict, meta: dict) -> dict:
    column_order = meta["feature_columns"]
    threshold    = meta["optimal_threshold"]

    encoded_task = encode_task_for_inference(task)

    row        = pd.DataFrame([[encoded_task[col] for col in column_order]], columns=column_order)
    prob       = float(model.predict_proba(row)[0][1])
    prediction = int(prob >= threshold)

    if prob < 0.35:   label = "LOW"
    elif prob < 0.65: label = "MEDIUM"
    else:             label = "HIGH"

    explanations = explain_prediction(
        explainer, encoded_task, column_order, original_task=task
    )

    return {
        "risk_score":   round(prob, 4),
        "risk_label":   label,
        "prediction":   prediction,
        "threshold":    round(threshold, 4),
        "explanations": explanations[:4]
    }

# -------------------------------------------------------------------
# 6. ENDPOINTS
# -------------------------------------------------------------------

@app.post("/api/analytics/predict_risk")
async def get_task_risk(task: TaskRiskRequest):
    """
    Live prediction endpoint for a single task.
    """
    if not ai_model or not ai_explainer or not ai_meta:
        raise HTTPException(status_code=503, detail="AI Model is not loaded on the server.")

    try:
        task_dict = task.dict()
        
        raw_energy = task_dict.get("energy_level")
        if isinstance(raw_energy, str):
            energy_map = {"low": 1, "medium": 2, "high": 3}
            task_dict["energy_level"] = energy_map.get(raw_energy.lower(), 2)
            
        return predict_risk(ai_model, ai_explainer, task_dict, ai_meta)
    except Exception as e:
        print(f"[AI Inference Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/dashboard/{user_id}")
async def get_master_dashboard_data(user_id: str):
    if not ai_model or not ai_explainer or not ai_meta:
        raise HTTPException(status_code=503, detail="AI Model is not loaded on the server.")

    try:
        now_dt = dt.datetime.now(timezone.utc)
        
        # --- THE FIX: DYNAMIC TIMEZONE ---
        user_tz = get_user_timezone(user_id)
        now_local = now_dt.astimezone(user_tz)
        
        user_doc = db.collection("users").document(user_id).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        global_debt = user_data.get("total_time_debt") or 0
        sunk_debt = user_data.get("sunk_time_debt") or 0

        tasks_ref = db.collection("users").document(user_id).collection("raw_tasks")
        events_ref = db.collection("users").document(user_id).collection("raw_events")
        
        all_tasks = [doc.to_dict() for doc in tasks_ref.stream()]
        all_events = [doc.to_dict() for doc in events_ref.stream()]

        tasks_per_day = defaultdict(int)
        for t in all_tasks:
            due_dt = parse_iso(t.get("due_date"))
            if due_dt:
                # Group by user's local day
                local_due = due_dt.astimezone(user_tz)
                tasks_per_day[local_due.strftime("%Y-%m-%d")] += 1

        pending_tasks, completed_tasks, missed_tasks = [], [], []
        completed_routines, missed_routines = 0, 0
        time_refunded = 0
        energy_counts = {"high": 0, "medium": 0, "low": 0}
        
        last_7_days = [(now_local - dt.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        trend_data_dict = {day: 0 for day in last_7_days}

        priority_completions = {"high": 0, "medium": 0, "low": 0} 
        hour_distribution = {h: 0 for h in range(24)}
        friction_hours_list = []

        for task in all_tasks:
            status = task.get("status")
            raw_energy = task.get("energy_level")
            clean_energy = {"low": 1, "medium": 2, "high": 3}.get(str(raw_energy).lower(), 2) if isinstance(raw_energy, str) else int(raw_energy) if isinstance(raw_energy, (int, float)) else 2

            if status == "completed":
                completed_tasks.append(task)
                time_refunded += (task.get("estimated_duration") or 60)
                
                if clean_energy == 3: energy_counts["high"] += 1
                elif clean_energy == 1: energy_counts["low"] += 1
                else: energy_counts["medium"] += 1
                
                comp_dt = parse_iso(task.get("completed_at"))
                create_dt = parse_iso(task.get("created_at"))

                if comp_dt:
                    # Convert to local time for accurate chronotype tracking
                    local_comp = comp_dt.astimezone(user_tz)
                    comp_str = local_comp.strftime("%Y-%m-%d")
                    if comp_str in trend_data_dict:
                        trend_data_dict[comp_str] += 1
                    
                    hour_distribution[local_comp.hour] += 1
                    
                    if create_dt:
                        diff_hours = (comp_dt - create_dt).total_seconds() / 3600
                        friction_hours_list.append(max(0, diff_hours))
                
                p = int(task.get("priority") or 3)
                if p <= 2: priority_completions["high"] += 1
                elif p == 3: priority_completions["medium"] += 1
                else: priority_completions["low"] += 1

            elif status == "missed":
                missed_tasks.append(task)
            elif status in ["pending", "scheduled"]:
                task["clean_energy"] = clean_energy
                pending_tasks.append(task)

        for event in all_events:
            if event.get("is_perishable"): 
                if event.get("completion_status") == "completed": completed_routines += 1
                elif event.get("completion_status") == "missed": missed_routines += 1

        scored_pending_tasks = []
        total_risk = 0
        for task in pending_tasks:
            due_dt = parse_iso(task.get("due_date")) or now_dt
            created_dt = parse_iso(task.get("created_at")) or now_dt
            
            # Predict risk based on local timezone equivalents
            local_due_dt = due_dt.astimezone(user_tz)
            
            ai_payload = {
                "snooze_count": int(task.get("snooze_count") or 0),
                "priority": int(task.get("priority") or 3),
                "energy_level": task.get("clean_energy", 2),
                "estimated_duration": int(task.get("estimated_duration") or 60),
                "global_time_debt": float(global_debt),
                "tasks_due_same_day": int(tasks_per_day.get(local_due_dt.strftime("%Y-%m-%d"), 1)),
                "days_since_created": int(max((now_dt - created_dt).days, 1)),
                "hour_of_due_time": int(local_due_dt.hour),
                "day_of_week": int(local_due_dt.weekday())
            }
            
            try:
                ai_result = predict_risk(ai_model, ai_explainer, ai_payload, ai_meta)
                task["risk_score"] = int(ai_result["risk_score"] * 100) 
                task["risk_label"] = ai_result["risk_label"]
                task["ai_explanations"] = ai_result["explanations"]
                total_risk += task["risk_score"]
                scored_pending_tasks.append(task)
            except Exception as e:
                pass

        avg_friction = (sum(friction_hours_list) / len(friction_hours_list)) if friction_hours_list else 0
        peak_hour = max(hour_distribution, key=hour_distribution.get) if completed_tasks else 9

        most_avoided = sorted([t for t in pending_tasks if (t.get("snooze_count") or 0) > 0], key=lambda x: (x.get("snooze_count") or 0), reverse=True)[:5]
        scored_pending_tasks.sort(key=lambda x: (x.get("risk_score") or 0), reverse=True)
        danger_zone = [t for t in scored_pending_tasks if (t.get("risk_score") or 0) >= 65][:3] 
        avg_risk = (total_risk / len(scored_pending_tasks)) if scored_pending_tasks else 0
        total_tasks_ever = len(completed_tasks) + len(missed_tasks)
        task_completion_rate = (len(completed_tasks) / total_tasks_ever * 100) if total_tasks_ever > 0 else 0
        total_routines = completed_routines + missed_routines
        routine_adherence = (completed_routines / total_routines * 100) if total_routines > 0 else 0

        return {
            "status": "success",
            "core_ledgers": {
                "active_debt_mins": global_debt,
                "sunk_debt_mins": sunk_debt,
                "time_refunded_mins": time_refunded
            },
            "procrastination_profile": most_avoided,
            "risk_forecast": {
                "average_risk_score": int(avg_risk),
                "danger_zone": danger_zone
            },
            "energy_analytics": energy_counts,
            "completion_funnel": {
                "task_completion_rate": task_completion_rate,
                "routine_adherence": routine_adherence,
                "trend_data": list(trend_data_dict.values())
            },
            "advanced_metrics": {
                "priority_alignment": priority_completions,
                "peak_action_window": {
                    "peak_hour": peak_hour,
                    "distribution": list(hour_distribution.values())
                },
                "task_friction_hours": int(avg_friction)
            }
        }

    except Exception as e:
        print(f"[Master Dashboard Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))



# @app.post("/api/calendar/reschedule_debt/{user_id}")
# async def fetch_reschedulable_debt(user_id: str):
#     """
#     Scoops up non-perishable missed tasks/events and calculates
#     exact remaining durations for the AI Optimiser.
#     """
#     try:
#         events_ref = db.collection("users").document(user_id).collection("raw_events")
#         tasks_ref = db.collection("users").document(user_id).collection("raw_tasks")
        
#         reschedule_queue = []
#         processed_task_ids = set()
        
#         for doc in events_ref.where("completion_status", "==", "missed").stream():
#             event = doc.to_dict()
#             if event.get("is_perishable") == True:
#                 continue
                
#             parent_id = event.get("parent_task_id")
            
#             if not parent_id:
#                 start_dt = parse_iso(event.get("start"))
#                 end_dt = parse_iso(event.get("end"))
#                 duration = 60
#                 if start_dt and end_dt:
#                     duration = int((end_dt - start_dt).total_seconds() / 60)
                    
#                 reschedule_queue.append({
#                     "id": doc.id,
#                     "title": event.get("title", "Missed Event"),
#                     "duration": duration,
#                     "priority": 1, 
#                     "original_type": "event"
#                 })

#         for doc in tasks_ref.where("status", "==", "missed").stream():
#             task = doc.to_dict()
#             if task.get("is_perishable") == True:
#                 continue
                
#             task_id = doc.id
#             processed_task_ids.add(task_id)
            
#             base_duration = task.get("estimated_duration") or 60
            
#             completed_mins = 0
#             linked_evs = task.get("linked_event_ids", [])
            
#             if linked_evs:
#                 for eid in linked_evs:
#                     edoc = events_ref.document(eid).get()
#                     if edoc.exists:
#                         edata = edoc.to_dict()
#                         if edata.get("completion_status") == "completed":
#                             es = parse_iso(edata.get("start"))
#                             ee = parse_iso(edata.get("end"))
#                             if es and ee:
#                                 completed_mins += int((ee - es).total_seconds() / 60)
                                
#             remaining_duration = max(0, base_duration - completed_mins)
            
#             if remaining_duration > 0:
#                 reschedule_queue.append({
#                     "id": task_id,
#                     "title": task.get("title", "Missed Task"),
#                     "duration": remaining_duration,
#                     "priority": 1,
#                     "original_type": "task"
#                 })
                
#         return {
#             "status": "success",
#             "items_to_schedule": reschedule_queue,
#             "total_items": len(reschedule_queue)
#         }
        
#     except Exception as e:
#         print(f"[Auto-Rescheduler Error] {e}")
#         raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analytics/sweep/{user_id}")
async def run_time_debt_sweeper(user_id: str):
    try:
        now_dt = dt.datetime.now(dt.timezone.utc)
        batch = db.batch()
        active_reschedulable_debt = 0
        active_sunk_debt = 0
        items_swept = 0
        
        events_ref = db.collection("users").document(user_id).collection("raw_events")
        tasks_ref = db.collection("users").document(user_id).collection("raw_tasks")

        # --- SWEEP EVENTS ---
        for doc in events_ref.where("completion_status", "==", "pending").stream():
            event = doc.to_dict()
            end_dt = safe_parse_dt(event.get("end"))
            
            if end_dt and end_dt < now_dt:
                start_dt = safe_parse_dt(event.get("start"))
                duration = 60
                
                es_str = event.get("start")
                ee_str = event.get("end")
                if start_dt and end_dt:
                    duration = int((end_dt - start_dt).total_seconds() / 60)
                
                print(f"[Sweeper Math] Event '{event.get('title')}': Start {es_str} -> End {ee_str} = {duration} mins")
                
                capped_duration = min(max(0, duration), 120) 
                if duration != capped_duration:
                    print(f"   -> WARNING: Duration was {duration}m, capped to {capped_duration}m")
                
                if event.get("is_perishable"): active_sunk_debt += capped_duration
                else: active_reschedulable_debt += capped_duration
                    
                batch.update(doc.reference, {"completion_status": "missed", "debt_applied": True})
                items_swept += 1

        # --- SWEEP TASKS ---
        for status in ["pending", "scheduled"]:
            for doc in tasks_ref.where("status", "==", status).stream():
                task = doc.to_dict()
                due_dt = safe_parse_dt(task.get("due_date"))
                
                if due_dt and due_dt < now_dt:
                    base_duration = task.get("estimated_duration") or 60
                    scheduled_mins = 0
                    linked_evs = task.get("linked_event_ids", [])
                    
                    if linked_evs:
                        for eid in linked_evs:
                            edoc = events_ref.document(eid).get()
                            if edoc.exists:
                                edata = edoc.to_dict()
                                es = safe_parse_dt(edata.get("start"))
                                ee = safe_parse_dt(edata.get("end"))
                                if es and ee: scheduled_mins += int((ee - es).total_seconds() / 60)
                    
                    unscheduled_debt = max(0, base_duration - scheduled_mins)
                    capped_duration = min(unscheduled_debt, 120)

                    print(f"[Sweeper Math] Task '{task.get('title')}': Est {base_duration}m - Sched {scheduled_mins}m = {unscheduled_debt}m (Capped: {capped_duration}m)")

                    if capped_duration > 0:
                        if task.get("is_perishable"): active_sunk_debt += capped_duration
                        else: active_reschedulable_debt += capped_duration
                        
                    batch.update(doc.reference, {"status": "missed", "debt_applied": True})
                    items_swept += 1

        # --- APPLY TO USER PROFILE ---
        if items_swept > 0:
            user_ref = db.collection("users").document(user_id)
            updates = {}
            if active_reschedulable_debt > 0: updates["total_time_debt"] = firestore.Increment(active_reschedulable_debt)
            if active_sunk_debt > 0: updates["sunk_time_debt"] = firestore.Increment(active_sunk_debt)
            if updates: batch.update(user_ref, updates)
            batch.commit()
            
        return {"status": "success", "items_swept": items_swept, "debt_added": active_reschedulable_debt, "sunk_added": active_sunk_debt}

    except Exception as e:
        print(f"❌ [Sweeper Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    


class ReschedulePreviewRequest(BaseModel):
    user_id: str

class RescheduleCommitRequest(BaseModel):
    user_id: str
    events: list

@app.post("/api/calendar/reschedule_debt/preview")
async def preview_reschedule_debt(req: ReschedulePreviewRequest):
    print("\n" + "="*60)
    print(f"🚀 [API] /api/calendar/reschedule_debt/preview CALLED")
    
    user_id = req.user_id
    try:
        # --- THE FIX: DYNAMIC TIMEZONE ---
        user_tz = get_user_timezone(user_id)
        now_local = dt.datetime.now(user_tz)
        target_date = now_local.date()
        
        events_ref = db.collection("users").document(user_id).collection("raw_events")
        tasks_ref = db.collection("users").document(user_id).collection("raw_tasks")
        prefs_ref = db.collection("users").document(user_id).collection("preferences")
        
        preferences = [doc.to_dict() for doc in prefs_ref.stream()]
        
        existing_events = []
        for doc in events_ref.stream():
            e = doc.to_dict()
            e["id"] = doc.id
            existing_events.append(e)

        reschedule_queue = []
        
        print("🔍 Scanning for missed events...")
        for doc in events_ref.where("completion_status", "==", "missed").stream():
            event = doc.to_dict()
            if event.get("is_perishable") == True: continue
            if event.get("debt_applied") == False: continue 
            
            if not event.get("parent_task_id"):
                es = parse_iso(event.get("start"))
                ee = parse_iso(event.get("end"))
                duration = int((ee - es).total_seconds() / 60) if es and ee else 60
                duration = min(max(0, duration), 120) 

                reschedule_queue.append({
                    "id": doc.id,
                    "title": event.get('title', 'Missed Event'),
                    "duration": duration,
                    "priority": 1,
                    "energy_level": "medium",
                    "original_type": "event"
                })

        print("🔍 Scanning for missed tasks...")
        for doc in tasks_ref.where("status", "==", "missed").stream():
            task = doc.to_dict()
            if task.get("is_perishable") == True: continue
            if task.get("debt_applied") == False: continue 
            
            base_dur = task.get("estimated_duration") or 60
            allocated_mins = 0
            
            for eid in task.get("linked_event_ids", []):
                edoc = events_ref.document(eid).get()
                if edoc.exists:
                    edata = edoc.to_dict()
                    es = parse_iso(edata.get("start"))
                    ee = parse_iso(edata.get("end"))
                    if es and ee: allocated_mins += int((ee - es).total_seconds() / 60)
            
            rem_dur = max(0, base_dur - allocated_mins)
            rem_dur = min(rem_dur, 120)

            if rem_dur > 0:
                reschedule_queue.append({
                    "id": doc.id,
                    "title": task.get('title', 'Missed Task'),
                    "duration": rem_dur,
                    "priority": 1,
                    "energy_level": task.get("energy_level", "medium"),
                    "original_type": "task"
                })

        if not reschedule_queue:
            print("⚠️ Queue empty. Checking for ORPHANED DEBT...")
            user_doc = db.collection("users").document(user_id).get()
            global_debt = user_doc.to_dict().get("total_time_debt", 0) if user_doc.exists else 0
            
            if global_debt > 0:
                chunks = global_debt // 60
                remainder = global_debt % 60
                for i in range(int(chunks)):
                    reschedule_queue.append({"id": f"orphan_{i}", "title": "Reclaimed Focus Time", "duration": 60, "priority": 2, "energy_level": "medium", "original_type": "task"})
                if remainder > 0:
                    reschedule_queue.append({"id": f"orphan_rem", "title": "Reclaimed Focus Time", "duration": remainder, "priority": 2, "energy_level": "medium", "original_type": "task"})
            else:
                return {"status": "success", "message": "No debt to reschedule.", "preview_events": existing_events, "original_events": existing_events}

        print(f"🚀 Passing {len(reschedule_queue)} sanitized items to DebtRescheduler...")
        # Inject the timezone string into the DebtRescheduler
        scheduler = DebtRescheduler(existing_events, preferences, user_tz_string=str(user_tz))
        horizon_end = target_date + dt.timedelta(days=14)
        
        ghosts = scheduler.schedule_debt(target_date, horizon_end, reschedule_queue)

        print("="*60 + "\n")
        return {"status": "success", "original_events": existing_events, "preview_events": existing_events + ghosts}

    except Exception as e:
        print(f"❌ [Preview Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    


class RescheduleCommitRequest(BaseModel):
    user_id: str
    events: list

@app.post("/api/calendar/reschedule_debt/commit")
async def commit_reschedule_debt(req: RescheduleCommitRequest):
    print("\n" + "="*60)
    print(f"🚀 [API] /api/calendar/reschedule_debt/commit CALLED")
    
    user_id = req.user_id
    events = req.events

    try:
        # Filter out only the newly generated catch-up blocks
        debt_ghosts = [e for e in events if e.get("is_ghost") and e.get("id", "").startswith("ghost_debt_")]
        if not debt_ghosts:
            print("⚠️ No valid debt ghosts found in payload.")
            return {"status": "success", "refunded_mins": 0}

        print(f"💾 Saving {len(debt_ghosts)} reclaimed blocks to database...")
        batch = db.batch()
        events_ref = db.collection("users").document(user_id).collection("raw_events")
        tasks_ref = db.collection("users").document(user_id).collection("raw_tasks")
        user_ref = db.collection("users").document(user_id)
        
        total_refund = 0
        task_updates = {} # Aggregates multiple chunks belonging to the same task

        for ghost in debt_ghosts:
            ghost_dur = ghost.pop("debt_duration", 0)
            orig_task_id = ghost.get("linked_task_id")
            orig_event_id = ghost.get("linked_event_id")

            # 1. Clean the ghost and save it as a real event
            ghost.pop("is_ghost", None)
            ghost.pop("id", None)
            new_event_ref = events_ref.document()
            batch.set(new_event_ref, ghost)

            # 2. Track refunds and prepare parent updates
            if orig_task_id and not orig_task_id.startswith("orphan_"):
                if orig_task_id not in task_updates: 
                    task_updates[orig_task_id] = []
                task_updates[orig_task_id].append(new_event_ref.id)
                total_refund += ghost_dur
                
            elif orig_event_id and not orig_event_id.startswith("orphan_"):
                event_doc = events_ref.document(orig_event_id)
                # Setting debt_applied to False protects it from the Sweeper 
                # immediately marking it as missed again
                batch.update(event_doc, {
                    "debt_applied": False, 
                    "snooze_count": firestore.Increment(1)
                })
                total_refund += ghost_dur
            else:
                # It's an orphan block; just refund the global debt
                total_refund += ghost_dur

        # 3. Apply batched task updates (Using ArrayUnion to safely append IDs)
        for task_id, new_event_ids in task_updates.items():
            task_doc = tasks_ref.document(task_id)
            batch.update(task_doc, {
                "linked_event_ids": firestore.ArrayUnion(new_event_ids),
                "status": "scheduled",
                "debt_applied": False,
                "snooze_count": firestore.Increment(1)
            })

        # 4. Clean up Global Ledger
        if total_refund > 0:
            user_doc_snap = user_ref.get()
            if user_doc_snap.exists:
                current_debt = user_doc_snap.to_dict().get("total_time_debt", 0)
                # Floor it at 0 just in case
                new_debt = max(0, current_debt - total_refund)
                batch.update(user_ref, {"total_time_debt": new_debt})
                print(f"💰 Global Debt reduced by {total_refund} mins. New total: {new_debt}")

        batch.commit()
        print("✅ Commit successful.")
        print("="*60 + "\n")
        return {"status": "success", "refunded_mins": total_refund}

    except Exception as e:
        print(f"❌ [Commit Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    



from pydantic import BaseModel
import zoneinfo
from fastapi import HTTPException

class TimezoneUpdateRequest(BaseModel):
    user_id: str
    timezone: str

@app.post("/api/users/timezone")
async def update_user_timezone(req: TimezoneUpdateRequest):
    print("\n" + "="*60)
    print(f"🚀 [API] /api/users/timezone CALLED")
    
    try:
        # 1. Validate the IANA string
        try:
            zoneinfo.ZoneInfo(req.timezone)
        except zoneinfo.ZoneInfoNotFoundError:
            print(f"❌ Invalid timezone string received: {req.timezone}")
            raise HTTPException(status_code=400, detail="Invalid IANA timezone string.")

        # 2. Save to database using merge=True to preserve other user data
        user_ref = db.collection("users").document(req.user_id)
        user_ref.set({"timezone": req.timezone}, merge=True)
        
        print(f"✅ User {req.user_id} timezone updated to: {req.timezone}")
        print("="*60 + "\n")
        
        return {
            "status": "success", 
            "message": "Timezone updated successfully.",
            "timezone": req.timezone
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [Timezone Update Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


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