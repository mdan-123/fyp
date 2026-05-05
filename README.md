# AI Scheduler

An intelligent task scheduling and productivity application that combines natural language understanding, AI-powered optimisation, and calendar integration into a unified platform. Users can create and manage tasks through natural language input, receive AI-generated schedule suggestions, and access analytics — all from a web or native iOS interface.

---

## Tech Stack

**Backend**
- Python 3.11+ / FastAPI
- Firebase Admin SDK (Firestore + Authentication)
- ModernBERT (intent classification + NER) — local fine-tuned models
- Google Gemini API (LLM reasoning)
- Google Calendar API + Outlook Calendar API
- Google Maps / Places API
- Tailscale (secure networking / OAuth callback routing)

**Frontend**
- Next.js 16 (React 19, TypeScript)
- Tailwind CSS v4
- Firebase JS SDK
- Capacitor 8 (iOS native wrapper)

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Xcode 15+ *(iOS only)*
- Tailscale *(required for OAuth redirect URIs — see [Cannot Be Run section](#why-this-cannot-be-run-as-is))*

### Backend

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add environment variables (create src/.env.local)
GEMINI_API_KEY=...
GOOGLE_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_MAPS_API_KEY=...
OUTLOOK_CLIENT_ID=...
OUTLOOK_CLIENT_SECRET=...

# 4. Start the server
cd src
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# in a separate terminal
tailscale funnel 8000
```


### Frontend — Web

```bash
cd frontend
npm install
npm run dev
```

### Frontend — iOS

```bash
cd frontend
npm install
npm run build
npx cap sync ios
npx cap open ios   # Opens Xcode; build and run from there
```

---

## Usage

| Interface | Command | URL / Notes |
|-----------|---------|-------------|
| Backend API | `uvicorn main:app --host 0.0.0.0 --port 8000 --reload` (run from `src/`) | `http://localhost:8000` |
| Web app | `npm run dev` (run from `frontend/`) | `http://localhost:3000` |
| iOS app | `npm run build` → `npx cap sync ios` → `npx cap open ios` | Deploy via Xcode |

The API exposes endpoints under `/api/` for tasks, reminders, calendar, AI scheduling, analytics, location, and user preferences. Interactive API docs are available at `http://localhost:8000/docs` once the server is running.

---

## Project Structure

```
PROJECT/
├── src/                        # FastAPI backend
│   ├── main.py                 # App entry point, lifespan, CORS, router registration
│   ├── dependencies.py         # Shared globals, Firebase client, API keys
│   ├── router.py               # Multi-signal NLU request router
│   ├── scheduler_engine.py     # NLU scheduling engine (ModernBERT)
│   ├── IntentEngine.py         # Intent execution engine
│   ├── task.py                 # Task scheduling & optimisation logic
│   ├── optimiser.py            # Schedule optimiser
│   ├── llm_parser.py           # Gemini-backed natural language parser
│   ├── llm_duration.py         # AI duration estimator
│   ├── categorise.py           # Task categorisation
│   ├── routers/                # One file per feature domain
│   │   ├── tasks.py
│   │   ├── reminders.py
│   │   ├── calendar.py
│   │   ├── ai.py
│   │   ├── analytics.py
│   │   ├── auth.py
│   │   ├── location.py
│   │   ├── places.py
│   │   ├── preferences.py
│   │   └── ...
│   ├── ai/                          # Model training & dataset scripts
│   │   ├── modernbert-intent.py     # Intent model definition
│   │   ├── modernbert-intenttrain.py  # Intent model training script
│   │   ├── modernbert-intentval.py  # Intent model validation script
│   │   ├── modernbert-ner.py        # NER model definition
│   │   ├── modernbert-nertrain.py   # NER model training script
│   │   └── modernbert-nerval.py     # NER model validation script
│   ├── modernbert_intent_modelv2/   # Fine-tuned intent classification model
│   ├── modernbert_ner_model/        # Fine-tuned NER model
│   └── firebase-service-account.json  # ⚠ Not in repo
│
├── frontend/                   # Next.js + Capacitor frontend
│   ├── src/
│   │   ├── app/                # Next.js app router pages
│   │   │   ├── page.tsx        # Dashboard
│   │   │   ├── tasks/
│   │   │   ├── reminders/
│   │   │   ├── ai/
│   │   │   ├── analytics/
│   │   │   ├── settings/
│   │   │   ├── login/
│   │   │   └── register/
│   │   ├── components/         # Shared React components
│   │   └── lib/                # Utility helpers, Firebase config
│   ├── ios/                    # Capacitor-generated Xcode project
│   └── package.json
│
├── requirements.txt
└── README.md
```

---

## Why This Cannot Be Run As-Is

This repository is intentionally incomplete. The following are required to run the project but are **not included**:

| Missing item | Reason |
|---|---|
| `src/firebase-service-account.json` | Contains private Firebase credentials; excluded for security |
| `src/.env.local` | Holds all API keys (Gemini, Google, Outlook, Maps) |
| `frontend/src/lib/firebaseConfig` | Firebase web app config with API keys |
| Fine-tuned ML models (`modernbert_intent_modelv2/`, `modernbert_ner_model/`) | Large model checkpoints are not committed to the repo |
| **Tailscale** | OAuth redirect URIs in `dependencies.py` are hardcoded to the developer's Tailscale machine hostname (`danishs-macbook-pro.tail79ab0c.ts.net`). Anyone wishing to run the project must install Tailscale, provision their own machine, and update `GOOGLE_REDIRECT_URI` and `OUTLOOK_REDIRECT_URI` in `src/dependencies.py` to match their own hostname |
| **Xcode** | Required to build and deploy the iOS app; macOS only |


