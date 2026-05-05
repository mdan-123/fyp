"""
Application entry point.

Responsibilities:
- Firebase / Firestore initialisation
- NLU engine startup
- AI model lifespan loading
- FastAPI app creation + CORS
- Router registration

All endpoint logic lives in src/routers/*.
"""
import os
import json
import pickle
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv("./.env.local")

import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import dependencies as deps

# ---------------------------------------------------------------------------
# Firebase initialisation
# ---------------------------------------------------------------------------
cred = credentials.Certificate("./firebase-service-account.json")
firebase_admin.initialize_app(cred)
deps.db = firestore.client()

# ---------------------------------------------------------------------------
# NLU / routing engines  (synchronous, loaded once at module level)
# ---------------------------------------------------------------------------
from scheduler_engine import SchedulerNLU
from router import MultiSignalRouter
from IntentEngine import IntentExecutionEngine
from llm_duration import DurationEstimator

INTENT_PATH = "./modernbert_intent_modelv2/checkpoint-2160"
NER_PATH = "./modernbert_ner_model/checkpoint-3987"
CENTROIDS_PATH = "./intent_centroids.npy"

GEMINI_KEY = deps.GEMINI_KEY
GOOGLE_API_KEY = deps.GOOGLE_API_KEY

if not GEMINI_KEY:
    raise ValueError("GEMINI_API_KEY is not set")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY is not set")

print("Loading NLU models into memory...")
deps.nlu_engine = SchedulerNLU(
    intent_path=INTENT_PATH, ner_path=NER_PATH, gemini_api_key=GEMINI_KEY
)
deps.routing_engine = MultiSignalRouter(deps.nlu_engine, centroids_path=CENTROIDS_PATH)
deps.db_engine = IntentExecutionEngine(db_client=deps.db)
deps.estimator = DurationEstimator()
print("NLU models loaded.")

# ---------------------------------------------------------------------------
# Lifespan: load AI risk-prediction model files
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Loading AI Risk Prediction Model...")
    try:
        with open("risk_prediction_model.pkl", "rb") as f:
            deps.ai_model = pickle.load(f)
        with open("risk_prediction_model_shap_explainer.pkl", "rb") as f:
            deps.ai_explainer = pickle.load(f)
        with open("risk_prediction_model_meta.json", "r") as f:
            deps.ai_meta = json.load(f)
        print("AI Model Loaded Successfully.")
    except Exception as e:
        print(f"Warning: Could not load AI model files. Error: {e}")

    # Start the preference-parsing background worker
    import asyncio
    from routers.pref_queue import worker as pref_worker
    from routers.risk_alerts import risk_alert_worker
    pref_task = asyncio.create_task(pref_worker())
    risk_task = asyncio.create_task(risk_alert_worker())
    print("Preference queue worker started.")
    print("Risk alert background scanner started.")
    yield
    pref_task.cancel()
    risk_task.cancel()
    print("Shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "capacitor://localhost",
        "http://192.168.1.50:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------
from routers import auth, calendar, tasks, reminders, preferences
from routers import analytics, ai, users, places, location, search, vocabulary
from routers import risk_alerts

app.include_router(auth.router)
app.include_router(calendar.router)
app.include_router(tasks.router)
app.include_router(reminders.router)
app.include_router(preferences.router)
app.include_router(analytics.router)
app.include_router(ai.router)
app.include_router(users.router)
app.include_router(places.router)
app.include_router(location.router)
app.include_router(search.router)
app.include_router(vocabulary.router)
app.include_router(risk_alerts.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
