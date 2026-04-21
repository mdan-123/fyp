"""
Authentication routes: WebAuthn passkey registration/login,
mobile biometrics, Google & Outlook OAuth.
"""
import json

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    RegistrationCredential,
    AuthenticationCredential,
    UserVerificationRequirement,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
import msal

import dependencies as deps
from dependencies import verify_firebase_token

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RegisterStartRequest(BaseModel):
    user_id: str
    email: str


class VerifyRequest(BaseModel):
    user_id: str
    credential: dict


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


# ---------------------------------------------------------------------------
# WebAuthn registration
# ---------------------------------------------------------------------------

@router.post("/api/auth/register/start")
async def start_registration(req: RegisterStartRequest):
    from firebase_admin import auth
    options = generate_registration_options(
        rp_id=deps.RP_ID,
        rp_name=deps.RP_NAME,
        user_id=req.user_id.encode("utf-8"),
        user_name=req.email,
    )
    options_dict = json.loads(options_to_json(options))
    deps.db.collection("webauthn_challenges").document(req.user_id).set(
        {"challenge": options_dict["challenge"]}
    )
    return options_dict


@router.post("/api/auth/register/verify")
async def verify_registration(req: VerifyRequest):
    doc = deps.db.collection("webauthn_challenges").document(req.user_id).get()
    if not doc.exists:
        raise HTTPException(status_code=400, detail="Challenge not found")

    expected_challenge_bytes = base64url_to_bytes(doc.to_dict()["challenge"])

    try:
        verification = verify_registration_response(
            credential=req.credential,
            expected_challenge=expected_challenge_bytes,
            expected_origin=deps.TRUSTED_ORIGINS,
            expected_rp_id=deps.RP_ID,
            require_user_verification=True,
        )

        deps.db.collection("users").document(req.user_id).collection("passkeys").add(
            {
                "credential_id": bytes_to_base64url(verification.credential_id),
                "public_key": bytes_to_base64url(verification.credential_public_key),
                "sign_count": verification.sign_count,
                "transports": req.credential.get("response", {}).get("transports", []),
            }
        )

        return {"status": "success", "message": "Passkey registered"}

    except Exception as e:
        print(f"Verification Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# WebAuthn login
# ---------------------------------------------------------------------------

@router.post("/api/auth/login/start")
async def start_login(req: LoginStartAuthRequest):
    from firebase_admin import auth
    try:
        user_record = auth.get_user_by_email(req.email)
        user_id = user_record.uid
    except Exception:
        raise HTTPException(status_code=400, detail="User not found")

    options = generate_authentication_options(
        rp_id=deps.RP_ID,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    options_dict = json.loads(options_to_json(options))
    deps.db.collection("webauthn_challenges").document(user_id).set(
        {"challenge": options_dict["challenge"]}
    )
    return options_dict


@router.post("/api/auth/login/verify")
async def verify_login(req: VerifyLoginRequest):
    from firebase_admin import auth
    try:
        user_record = auth.get_user_by_email(req.email)
        user_id = user_record.uid
    except Exception:
        raise HTTPException(status_code=400, detail="User not found")

    doc = deps.db.collection("webauthn_challenges").document(user_id).get()
    if not doc.exists:
        raise HTTPException(status_code=400, detail="Challenge not found")

    expected_challenge_bytes = base64url_to_bytes(doc.to_dict()["challenge"])

    passkeys = (
        deps.db.collection("users")
        .document(user_id)
        .collection("passkeys")
        .limit(1)
        .get()
    )
    if not passkeys:
        raise HTTPException(
            status_code=400, detail="No biometrics registered for this user"
        )

    saved_key_data = passkeys[0].to_dict()

    try:
        verification = verify_authentication_response(
            credential=req.credential,
            expected_challenge=expected_challenge_bytes,
            expected_origin=deps.TRUSTED_ORIGINS,
            expected_rp_id=deps.RP_ID,
            credential_public_key=base64url_to_bytes(saved_key_data["public_key"]),
            credential_current_sign_count=saved_key_data["sign_count"],
        )

        custom_token = auth.create_custom_token(user_id)
        return {"status": "success", "token": custom_token.decode("utf-8")}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Mobile biometrics
# ---------------------------------------------------------------------------

@router.post("/api/auth/register/mobile-biometrics")
async def register_mobile_biometrics(req: MobileBiometricRegisterRequest):
    try:
        deps.db.collection("users").document(req.user_id).set(
            {"has_mobile_biometrics": req.has_mobile_biometrics}, merge=True
        )
        return {"status": "success", "message": "Mobile biometrics flagged in database"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/auth/mobile-biometric-login")
async def mobile_biometric_login(req: MobileBiometricLoginRequest):
    from firebase_admin import auth
    try:
        user_record = auth.get_user_by_email(req.email)
        user_id = user_record.uid

        user_doc = deps.db.collection("users").document(user_id).get()
        if not user_doc.exists or not user_doc.to_dict().get("has_mobile_biometrics"):
            raise HTTPException(
                status_code=403,
                detail="Biometrics not enabled for this account. Please use password login.",
            )

        custom_token = auth.create_custom_token(user_id)
        return {"status": "success", "token": custom_token.decode("utf-8")}

    except auth.UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/auth/biometrics/status/{user_id}")
async def get_biometric_status(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    """Checks if the user has active Passkeys or Mobile Biometrics."""
    try:
        user_doc = deps.db.collection("users").document(user_id).get()
        has_mobile = False
        if user_doc.exists:
            has_mobile = user_doc.to_dict().get("has_mobile_biometrics", False)

        passkeys_ref = (
            deps.db.collection("users")
            .document(user_id)
            .collection("passkeys")
            .limit(1)
            .get()
        )
        has_passkey = len(passkeys_ref) > 0

        return {
            "status": "success",
            "mobile_enabled": has_mobile,
            "passkey_enabled": has_passkey,
        }
    except Exception as e:
        print(f"❌ Error checking biometric status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve biometric status")


@router.delete("/api/auth/biometrics/mobile/{user_id}")
async def remove_mobile_biometrics(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    """Disables FaceID / TouchID for the mobile app."""
    try:
        deps.db.collection("users").document(user_id).update(
            {"has_mobile_biometrics": False}
        )
        print(f"🔒 Disabled mobile biometrics for user {user_id}")
        return {"status": "success", "message": "Mobile biometrics disabled"}
    except Exception as e:
        print(f"❌ Error removing mobile biometrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to disable mobile biometrics")


@router.delete("/api/auth/biometrics/passkeys/{user_id}")
async def remove_passkeys(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    """Deletes all registered WebAuthn passkeys for the user."""
    try:
        passkeys_ref = (
            deps.db.collection("users").document(user_id).collection("passkeys")
        )
        docs = passkeys_ref.stream()

        batch = deps.db.batch()
        deleted_count = 0

        for doc in docs:
            batch.delete(doc.reference)
            deleted_count += 1

        if deleted_count > 0:
            batch.commit()

        print(f"🗑️ Deleted {deleted_count} passkey(s) for user {user_id}")
        return {"status": "success", "message": "Passkeys removed successfully"}
    except Exception as e:
        print(f"❌ Error removing passkeys: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove passkeys")


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------

@router.get("/api/auth/google/login")
async def google_login(user_id: str):
    flow = Flow.from_client_config(deps.CLIENT_CONFIG, scopes=deps.SCOPES)
    flow.redirect_uri = deps.GOOGLE_REDIRECT_URI
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        state=user_id,
        prompt="select_account consent",
    )
    return {"url": authorization_url}


@router.get("/api/auth/google/callback")
async def google_callback(request: Request):
    from firebase_admin import firestore as fs

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    flow = Flow.from_client_config(deps.CLIENT_CONFIG, scopes=deps.SCOPES)
    flow.redirect_uri = deps.GOOGLE_REDIRECT_URI
    flow.fetch_token(code=code)

    credentials = flow.credentials

    id_info = id_token.verify_oauth2_token(
        credentials.id_token, google_requests.Request(), deps.GOOGLE_CLIENT_ID
    )
    user_email = id_info.get("email")

    new_account = {
        "provider": "google",
        "email": user_email,
        "refresh_token": credentials.refresh_token,
    }

    deps.db.collection("users").document(state).set(
        {"linked_accounts": fs.ArrayUnion([new_account])}, merge=True
    )

    html_content = """
    <html>
        <head>
            <script>
                window.location.href = "schedulerai://callback";
                setTimeout(() => { window.close(); }, 1000);
            </script>
        </head>
        <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f9fafb;">
            <h2>Authentication complete! You can close this window.</h2>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ---------------------------------------------------------------------------
# Outlook OAuth
# ---------------------------------------------------------------------------

@router.get("/api/auth/outlook/login")
async def outlook_login(user_id: str):
    client = msal.ConfidentialClientApplication(
        deps.OUTLOOK_CLIENT_ID,
        client_credential=deps.OUTLOOK_CLIENT_SECRET,
        authority=deps.OUTLOOK_AUTHORITY,
    )
    auth_url = client.get_authorization_request_url(
        deps.OUTLOOK_SCOPES,
        redirect_uri=deps.OUTLOOK_REDIRECT_URI,
        state=user_id,
        prompt="select_account",
    )
    return {"url": auth_url}


@router.get("/api/auth/outlook/callback")
async def outlook_callback(request: Request):
    from firebase_admin import firestore as fs

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    client = msal.ConfidentialClientApplication(
        deps.OUTLOOK_CLIENT_ID,
        client_credential=deps.OUTLOOK_CLIENT_SECRET,
        authority=deps.OUTLOOK_AUTHORITY,
    )

    result = client.acquire_token_by_authorization_code(
        code, scopes=deps.OUTLOOK_SCOPES, redirect_uri=deps.OUTLOOK_REDIRECT_URI
    )

    if "error" in result:
        print(f"Outlook Auth Error: {result.get('error_description')}")
        return {"error": "Failed to authenticate with Microsoft"}

    id_claims = result.get("id_token_claims", {})
    email = id_claims.get("preferred_username") or id_claims.get("email")
    refresh_token = result.get("refresh_token")

    new_account = {
        "provider": "outlook",
        "email": email,
        "refresh_token": refresh_token,
    }

    deps.db.collection("users").document(state).set(
        {"linked_accounts": fs.ArrayUnion([new_account])}, merge=True
    )

    html_content = """
    <html>
        <head>
            <script>
                window.location.href = "schedulerai://callback";
                setTimeout(() => { window.close(); }, 1000);
            </script>
        </head>
        <body style="font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f9fafb;">
            <h2>Authentication complete! You can close this window.</h2>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)
