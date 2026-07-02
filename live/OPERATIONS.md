# CaRAG Live — Developer Operations Guide

> **One doc to rule them all.**
> Clone → Setup → Run → Test → Ship. Everything you need is here.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [First-Time Setup (from scratch)](#first-time-setup-from-scratch)
3. [Daily Startup (returning developer)](#daily-startup-returning-developer)
4. [Running the Backends](#running-the-backends)
5. [Testing](#testing)
6. [API Reference](#api-reference)
7. [Git Workflow](#git-workflow)
8. [Milestone Progress](#milestone-progress)
9. [Troubleshooting](#troubleshooting)
10. [Teardown / Cleanup](#teardown--cleanup)

---

## Architecture Overview

```
┌──────────────┐     ┌───────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Telegram /  │     │    OpenClaw        │     │  Live Backend    │     │  CaRAG Engine    │
│  WhatsApp    │────▶│  (Agent Framework) │────▶│  (Adapter API)   │────▶│  (Core RAG)      │
│  Client      │     │                   │     │  Port 8001       │     │  Port 8000       │
└──────────────┘     └───────────────────┘     └──────┬───────────┘     └──────┬───────────┘
                                                      │                        │
                                                      │   Shared Resources     │
                                                      ▼                        ▼
                                               ┌──────────────┐    ┌──────────────────┐
                                               │  PostgreSQL   │    │  Milvus          │
                                               │  Port 5432    │    │  Port 19530      │
                                               └──────────────┘    └──────────────────┘
```

**Key insight:** Both backends share the **same PostgreSQL database** and **same Milvus vector store**.
They also share the **same Python virtual environment** (`backend/venv/`).

---

## First-Time Setup (from scratch)

### Prerequisites

| Tool       | Install Command / Link                                   | Verify                   |
|------------|----------------------------------------------------------|--------------------------|
| **Git**    | https://git-scm.com/downloads                           | `git --version`          |
| **Python** | https://www.python.org/downloads/ (3.10+)                | `python --version`       |
| **Docker** | https://docs.docker.com/desktop/install/windows-install/ | `docker --version`       |
| **Node.js**| https://nodejs.org/ (for wscat WebSocket testing)        | `node --version`         |
| **wscat**  | `npm install -g wscat`                                   | `wscat --version`        |

---

### Step 1: Clone the repo

```powershell
git clone https://github.com/AnujSharma-05/CaRAG.git
cd CaRAG
```

---

### Step 2: Start PostgreSQL (Docker)

```powershell
# Pull and run PostgreSQL 15 as a named container
docker run -d `
  --name carag-postgres `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_PASSWORD=12345678 `
  -e POSTGRES_DB=carag_db `
  -p 5432:5432 `
  -v carag_pg_data:/var/lib/postgresql/data `
  postgres:15-alpine
```

**Verify:**
```powershell
docker ps --filter name=carag-postgres
# Should show STATUS = Up

# Optional: test connection
docker exec -it carag-postgres psql -U postgres -d carag_db -c "SELECT 1;"
```

---

### Step 3: Start Milvus (Docker)

```powershell
# Pull and run Milvus Standalone (includes etcd + minio internally)
docker run -d `
  --name carag-milvus `
  -p 19530:19530 `
  -p 9091:9091 `
  -v carag_milvus_data:/var/lib/milvus `
  milvusdb/milvus:latest `
  milvus run standalone
```

**Verify:**
```powershell
docker ps --filter name=carag-milvus
# Should show STATUS = Up

# Health check
curl http://localhost:9091/healthz
# Expected: {"status":"OK"}
```

> **Optional — Attu (Milvus GUI):**
> ```powershell
> docker run -d --name carag-attu -p 8100:3000 -e MILVUS_URL=host.docker.internal:19530 zilliz/attu:latest
> ```
> Then open http://localhost:8100 in your browser to visually inspect collections.

---

### Step 4: Create the Python virtual environment

```powershell
# From repo root: E:\Codes\JPL\CaRAG
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

> **IMPORTANT:** There is only ONE venv for the entire project at `backend/venv/`.
> The `live/backend/` directory does NOT have its own packages — it inherits everything from `backend/venv/`.
> **Always activate `backend\venv` regardless of which server you're running.**

---

### Step 5: Configure environment variables

Both backends need a `.env` file. They should already exist, but if not:

**`backend/.env`**
```env
DATABASE_URL=postgresql+psycopg2://postgres:12345678@localhost:5432/carag_db
GEMINI_API_KEY=your_gemini_api_key_here
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
JWT_SECRET_KEY=09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7
```

**`live/backend/.env`**
```env
DATABASE_URL=postgresql+psycopg2://postgres:12345678@localhost:5432/carag_db
GEMINI_API_KEY=your_gemini_api_key_here
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
JWT_SECRET_KEY=09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7
```

> Both `.env` files point to the **exact same** PostgreSQL and Milvus instances.

---

## Daily Startup (returning developer)

Already set up? Just run these **4 commands** every time you sit down to work:

```powershell
# 1. Start the databases (if not already running)
docker start carag-postgres carag-milvus

# 2. Verify they're up
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 3. Start Core Backend (Terminal 1) — see "Running the Backends" below
# 4. Start Live Backend (Terminal 2) — see "Running the Backends" below
```

---

## Running the Backends

Both servers share `backend/venv/`. You need **TWO terminal windows**.

### Terminal 1 — CaRAG Core Engine (port 8000)

```powershell
# From repo root: E:\Codes\JPL\CaRAG
.\backend\venv\Scripts\activate
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload --app-dir backend
```

### Terminal 2 — CaRAG Live API (port 8001)

**Option A — Run from repo root (recommended):**
```powershell
# From repo root: E:\Codes\JPL\CaRAG
.\backend\venv\Scripts\activate
python -m uvicorn src.main:app --host 127.0.0.1 --port 8001 --reload --app-dir live\backend
```

**Option B — Run from inside `live/backend/` (if you prefer):**
```powershell
# Navigate to live/backend first, then activate the CORRECT venv
cd E:\Codes\JPL\CaRAG\live\backend
..\..\backend\venv\Scripts\activate
python -m uvicorn src.main:app --host 127.0.0.1 --port 8001 --reload
```

> **Why the same venv?** The Live API imports `services.py` directly from the core engine.
> All dependencies (FastAPI, SQLAlchemy, pymilvus, torch, etc.) live in `backend/venv/`.

### Verify Both Are Up

```powershell
curl http://localhost:8000/ping
# → {"status": "alive"}

curl http://localhost:8001/ping
# → {"status": "Live API is running", "engine": "Connected"}
```

### Swagger UI (Interactive API Docs)

| Server      | URL                         |
|-------------|-----------------------------|
| Core Engine | http://localhost:8000/docs   |
| Live API    | http://localhost:8001/docs   |

---

## Testing

### Unit Tests

```powershell
# From repo root (with backend venv activated)
.\backend\venv\Scripts\python.exe live\backend\tests\test_chat_routing.py
```

### WebSocket Echo Test (Task 3.1)

```powershell
# In a separate terminal (server must be running on port 8001)
wscat -c ws://localhost:8001/ws/test

# Type anything → you'll see it echoed back
# Press Ctrl+C to disconnect
```

### WebSocket Authenticated (Task 3.3+)

```powershell
# 1. Register a user via Swagger: POST /auth/register  { "email": "...", "password": "..." }
# 2. Login to get JWT:            POST /auth/login     (use email as username)
# 3. Connect with token:
wscat -c "ws://localhost:8001/ws?token=YOUR_JWT_HERE&group_id=1"
```

### Quick Smoke Test (all services)

```powershell
# Run this from repo root to verify everything is alive
docker ps --format "table {{.Names}}\t{{.Status}}"      # DBs up?
curl http://localhost:8000/ping                           # Core up?
curl http://localhost:8001/ping                           # Live up?
```

---

## API Reference

### Auth
| Method | Route              | Body                | Description              |
|--------|--------------------|---------------------|--------------------------|
| POST   | `/auth/register`   | `{email, password}` | Create account           |
| POST   | `/auth/login`      | `{email, password}` | Login → returns JWT      |

### Groups
| Method | Route                  | Body       | Description                    |
|--------|------------------------|------------|--------------------------------|
| POST   | `/groups/`             | `{name}`   | Create a group                 |
| GET    | `/groups/`             | —          | List your groups               |
| GET    | `/groups/{id}`         | —          | Group detail + members         |
| DELETE | `/groups/{id}`         | —          | Delete group (owner only)      |
| POST   | `/groups/{id}/invite`  | `{email}`  | Invite user by email           |

### Documents
| Method | Route                               | Body                | Description              |
|--------|-------------------------------------|---------------------|--------------------------|
| POST   | `/groups/{id}/documents`            | `file + category?`  | Upload PDF (multipart)   |
| GET    | `/groups/{id}/documents`            | —                   | List docs in group       |
| DELETE | `/groups/{id}/documents/{doc_id}`   | —                   | Delete a document        |
| GET    | `/groups/{id}/categories`           | —                   | List categories in group |

### Chat
| Method | Route                | Body                                          | Description     |
|--------|----------------------|-----------------------------------------------|-----------------|
| POST   | `/groups/{id}/chat`  | `{question, top_k?, category?, document_id?}` | Ask a question  |

**Chat modes:**
- No `category` or `document_id` → **Auto 2-stage LLM routing** (default)
- `category: "legal"` → **Manual category pin** — search only that category
- `document_id: 42` → **Single document pin** — search only that doc

### WebSocket
| Route      | Query Params            | Description                        |
|------------|-------------------------|------------------------------------|
| `/ws/test` | —                       | Echo test (no auth)                |
| `/ws`      | `token=JWT&group_id=X`  | Authenticated group room (3.3+)    |

**WS message protocol (Task 4.2+):**
```json
// You send:
{ "type": "chat", "question": "What does the contract say?", "group_id": 1 }

// Server streams back:
{ "event": "chunk", "text": "The contract states..." }
{ "event": "chunk", "text": " that termination requires..." }
{ "event": "done", "citations": [...] }

// Server pushes (doc events):
{ "event": "doc_processing", "doc_id": 42, "filename": "report.pdf" }
{ "event": "doc_ready",      "doc_id": 42, "filename": "report.pdf", "category": "legal" }
{ "event": "doc_failed",     "doc_id": 42, "filename": "report.pdf" }
```

---

## Git Workflow

### Per task:
```powershell
# 1. Create issue on GitHub first, note the issue number (#XX)
# 2. Branch off the current feature branch
# 3. Code the task
# 4. Commit with a reference to the issue
git add .
git commit -m "feat: Task 3.X — description (closes #XX)"
git push
```

### At end of each milestone:
```powershell
gh pr create --title "[MX] Milestone Title" --body "Closes #XX. Closes #XX."
gh pr merge --squash --delete-branch
git checkout main
git pull origin main
git checkout -b feature/mX-next
```

---

## Milestone Progress

- [x] M0 — Monorepo setup
- [x] M1 — Auth layer
- [x] M2 — Groups layer (models, CRUD, invites, docs, chat)
- [x] M2.5 — 3-mode chat routing + categories endpoint
- [ ] **M3 — WebSocket infrastructure** ← YOU ARE HERE
  - [x] Task 3.1 — Echo server (`/ws/test`)
  - [ ] Task 3.2 — ConnectionManager with group rooms
  - [ ] Task 3.3 — JWT auth on WS connect
  - [ ] Task 3.4 — Broadcast doc_ready from background task
  - [ ] Task 3.5 — Heartbeat ping/pong
- [ ] M4 — WebSocket streaming chat
- [ ] M5 — OpenClaw plugin (TypeScript)
- [ ] M6 — Polish

Current branch: `feature/m3-websocket`

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `No module named uvicorn` | Wrong venv activated | `deactivate`, then `.\backend\venv\Scripts\activate` |
| `ModuleNotFoundError: No module named 'src'` | Wrong working directory | Run from `live\backend\` (not `live\backend\src\`) OR use `--app-dir` from repo root |
| `wscat error:` (blank) | Server isn't running | Start the Live API on port 8001 first |
| `401 Unauthorized` | Missing/expired JWT | Re-login via `POST /auth/login`, use the new token |
| Milvus connection error | Container not running | `docker start carag-milvus` |
| PostgreSQL connection error | Container not running | `docker start carag-postgres` |
| Port 8000/8001 already in use | Stale process | `netstat -ano \| findstr 8001` → kill the PID |
| `pip install -r requirements.txt` fails in `live/backend` | See note below | Run from `live/backend/` dir (NOT `src/`), it references `../../backend/requirements.txt` |

### The #1 Gotcha: Virtual Environment

```
E:\Codes\JPL\CaRAG\
├── backend\
│   └── venv\          ← ✅ THIS IS THE ONLY VENV. Always use this one.
│       └── Lib\site-packages\   (fastapi, uvicorn, torch, pymilvus, etc.)
│
└── live\
    └── backend\
        └── venv\      ← ❌ DO NOT USE. This is empty / outdated.
```

**Rule:** No matter which backend you're starting, always activate `backend\venv\Scripts\activate`.

---

## Teardown / Cleanup

### Stop the backends
Press `Ctrl+C` in each terminal running uvicorn.

### Stop the databases
```powershell
docker stop carag-postgres carag-milvus
```

### Full nuke (removes data volumes too — DESTRUCTIVE)
```powershell
docker rm -f carag-postgres carag-milvus
docker volume rm carag_pg_data carag_milvus_data

# Also remove Attu if you started it
docker rm -f carag-attu
```

### Kill orphan Python processes (if ports are stuck)
```powershell
# Windows
.\clean_processes.bat

# Or manually
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```
