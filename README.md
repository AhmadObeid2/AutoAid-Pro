# AutoAid Pro 🚗🤖
AI-Powered Car Troubleshooting Assistant (Capstone Project)

AutoAid Pro is a safety-first AI assistant that helps users troubleshoot car problems using:
- structured LLM diagnosis,
- optional Mini-RAG document grounding,
- deterministic safety checks,
- and agent-style case actions (checklist/escalate/resolve).

It is built as a full-stack system:
- **Backend:** Django + Django REST Framework
- **Frontend:** React + TypeScript (Vite)

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Core Features](#core-features)
3. [UI Overview](#ui-overview)
4. [Architecture](#architecture)
5. [Project Structure](#project-structure)
6. [How to Run](#how-to-run)
7. [Environment Variables](#environment-variables)
8. [API Endpoints](#api-endpoints)
9. [RAG Document Upload Notes](#rag-document-upload-notes)
10. [Testing Flow](#testing-flow)
11. [Safety and Hardening](#safety-and-hardening)
12. [Troubleshooting](#troubleshooting)
13. [Future Improvements](#future-improvements)
14. [License](#license)

---

## System Overview

AutoAid Pro guides a user from symptom input to actionable, safe recommendations.

**Main flow:**
1. User creates a vehicle profile manually.
2. User opens a troubleshooting case.
3. User can upload local documents (manuals/notes) for Mini-RAG.
4. User chats with the assistant about symptoms.
5. Backend retrieves relevant context (if docs exist), calls LLM, applies safety guardrails.
6. System returns triage + causes + actions + follow-up questions.
7. Agent module can create/checklist/escalation/resolution actions and notes.

---

## Core Features

### 1) Manual Vehicle Creation
No auto-seeding. User fills vehicle fields:
- make/model/year
- engine cc
- transmission
- fuel type
- mileage

### 2) Manual Case Creation
User starts a case linked to vehicle:
- channel
- initial problem title
- initial user message

### 3) Chat Troubleshooting
`/api/chat/` returns:
- `triage_level` (`green`, `yellow`, `red`)
- `confidence`
- `likely_causes`
- `recommended_actions`
- `stop_driving_reasons`
- `follow_up_questions`

### 4) Mini-RAG
Upload local documents to improve grounding:
- retrieval context is injected into diagnosis prompt
- citations can be returned in response

### 5) Agent Actions
Agent supports:
- `auto`
- `checklist`
- `escalate`
- `resolve`

Logs are available via:
- `/api/cases/{case_id}/actions/`
- `/api/cases/{case_id}/notes/`

### 6) Fallback Reliability
If LLM is unavailable or quota fails, backend falls back to safe rule-based response (`rule_based_fallback`) instead of crashing.

---

## UI Overview

The frontend is organized into clear sections:

1. **Create Vehicle (Manual Form)**
2. **Create Case (Manual Form)**
3. **Upload Knowledge Document (Local File)**
4. **Chat Panel**
   - assistant messages
   - triage badge
   - optional citations
   - follow-up prompt support
5. **Agent Manual Controls**
6. **Case Actions / Notes Logs**

This makes the demo easy to follow end-to-end.

---

## Architecture

```text
React UI (Vite + TS)
   |
   v
Django REST API
   |
   +--> Core models (Vehicle, Case, Symptom, Diagnosis, Action, Note)
   +--> LLM service (structured JSON diagnosis)
   |       +--> deterministic red-flag override
   |       +--> unsafe action sanitizer
   |
   +--> Mini-RAG service (upload -> chunk/index -> retrieve -> citations)
   |
   +--> Agent service (auto/checklist/escalate/resolve)
```

---

## Project Structure

```text
AutoAid Pro/
├─ autoaid-pro/                 # Django backend
│  ├─ api/
│  ├─ core/
│  ├─ llm/
│  ├─ rag/
│  ├─ integrations/
│  ├─ config/
│  ├─ media/
│  ├─ manage.py
│  └─ requirements.txt
│
├─ autoaid-ui/                  # React frontend
│  ├─ src/
│  │  ├─ api/
│  │  ├─ App.tsx
│  │  └─ ...
│  ├─ package.json
│  └─ vite.config.ts
│
└─ docs/
   ├─ TECHNICAL_DOCUMENTATION.md
   ├─ 02_ARCHITECTURE.md
   └─ 03_API_REFERENCE.md
```

---

## How to Run

### 1) Backend (Django)

```bash
cd autoaid-pro
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
# source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Backend URL:
- `http://127.0.0.1:8000`

API docs:
- `http://127.0.0.1:8000/api/docs/`
- `http://127.0.0.1:8000/api/schema/`

### 2) Frontend (React)

```bash
cd autoaid-ui
npm install
npm run dev
```

Frontend URL (default Vite):
- `http://127.0.0.1:5173`

---

## Environment Variables

### Backend `.env` (example)

Create `autoaid-pro/.env`:

```env
DJANGO_SECRET_KEY=change_me
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4o-mini

CORS_ALLOW_ALL_ORIGINS=False
```

### Frontend `.env` (example)

Create `autoaid-ui/.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

> Do **not** commit real `.env` files. Keep `.env.example` in repo.

---

## API Endpoints

### Health
- `GET /api/health/`

### Vehicles
- `POST /api/vehicles/`
- `GET /api/vehicles/{vehicle_id}/`

### Cases
- `POST /api/cases/`
- `GET /api/cases/{case_id}/`
- `POST /api/cases/{case_id}/symptoms/`

### Chat
- `POST /api/chat/`

### Mini-RAG
- `POST /api/rag/documents/upload/`

### Agent
- `POST /api/cases/{case_id}/agent/run/`
- `GET /api/cases/{case_id}/actions/`
- `GET /api/cases/{case_id}/notes/`

---

## RAG Document Upload Notes

Use `multipart/form-data` with a real file field named **`file`**.

Common fields:
- `title`
- `file`
- `source_type` (must be valid backend choice)
- `vehicle_make` (optional)
- `vehicle_model` (optional)
- `year_from` (optional)
- `year_to` (optional)
- `is_active` (optional)

If you get `400`:
- check `source_type` enum value expected by backend serializer,
- ensure request is multipart form (not JSON),
- ensure `file` is actually attached.

---

## Testing Flow

Recommended full demo test:

1. Create vehicle from UI form.
2. Create case linked to that vehicle.
3. Upload one local knowledge document.
4. Send first symptom message in chat.
5. Reply to follow-up question once/twice.
6. Check:
   - triage level,
   - recommendations,
   - citations (if doc matched),
   - actions/notes logs.
7. Trigger manual agent action (e.g., `escalate`) and confirm logs update.

---

## Safety and Hardening

### Safety
- deterministic red-flag escalation for critical phrases (e.g., cannot stop, smoke, fuel leak)
- unsafe DIY instructions replaced with safe mechanic-oriented actions
- safety disclaimer in assistant response

### Hardening / Observability
- latency tracked (`latency_ms`)
- token usage tracked (`tokens_input`, `tokens_output`)
- fallback behavior tracked through `model_name=rule_based_fallback`
- agent action/note audit trail

---

## Troubleshooting

### 1) `duplicates: corsheaders`
`corsheaders` exists twice in `INSTALLED_APPS`. Keep only one entry.

### 2) `NameError: include is not defined`
Add:
```python
from django.urls import path, include
```
in urls file where `include()` is used.

### 3) Swagger schema generation errors
Check serializer field definitions and enum/type hints. Ensure custom fields have proper types.

### 4) Upload endpoint returns 400
Usually one of:
- wrong `Content-Type`
- invalid `source_type`
- missing `file` in form-data

### 5) OpenAI quota error (429 insufficient_quota)
Backend will fallback to rule-based mode. Add billing/quota to enable real LLM output.

---

## Future Improvements

- Better retrieval ranking/reranking
- Richer conversational memory and deeper follow-up strategy
- Arabic-native prompting and localization
- Auth and user roles
- PostgreSQL + background workers for production
- Monitoring dashboards (latency/fallback/safety metrics)

---

## License

For educational/capstone use unless otherwise specified.

---

## Author

**Ahmad Obeid**
AI Engineering Bootcamp — Final Capstone
