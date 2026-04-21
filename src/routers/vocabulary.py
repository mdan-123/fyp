"""
Vocabulary routes: add alias, get aliases, delete alias.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from firebase_admin import firestore

import dependencies as deps
from dependencies import verify_firebase_token, _load_aliases

router = APIRouter()


class VocabularyRequest(BaseModel):
    user_id: str
    alias: str
    full: str


@router.post("/api/vocabulary")
async def add_vocabulary(
    req: VocabularyRequest,
    _token=Depends(verify_firebase_token),
):
    try:
        vocab_ref = (
            deps.db.collection("users")
            .document(req.user_id)
            .collection("vocabulary")
            .document("aliases")
        )
        vocab_ref.set({"aliases": {req.alias.lower(): req.full.strip()}}, merge=True)
        print(f"[Vocabulary] Saved: '{req.alias}' → '{req.full}' for {req.user_id}")
        return {
            "status": "success",
            "message": f"Got it — I'll treat '{req.alias}' as '{req.full}' from now on.",
        }
    except Exception as e:
        print(f"[Vocabulary] Save failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/vocabulary/{user_id}")
async def get_vocabulary(
    user_id: str,
    _token=Depends(verify_firebase_token),
):
    try:
        aliases = _load_aliases(user_id)
        return {"status": "success", "aliases": aliases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/vocabulary/{user_id}/{alias}")
async def delete_vocabulary(
    user_id: str,
    alias: str,
    _token=Depends(verify_firebase_token),
):
    try:
        vocab_ref = (
            deps.db.collection("users")
            .document(user_id)
            .collection("vocabulary")
            .document("aliases")
        )
        vocab_ref.update({f"aliases.{alias.lower()}": firestore.DELETE_FIELD})
        return {"status": "success", "message": f"Removed alias '{alias}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
