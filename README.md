# CaRAG — Categorical Routing Augmented Generation

> **A hierarchical, multi-LLM RAG system that thinks before it retrieves.**

Most RAG systems are a vector database with a search bar stapled to an LLM. You embed everything, you query everything, you hope the right chunks surface. At scale — with heterogeneous documents across dozens of topics — that hope fails loudly.

CaRAG was built to solve exactly that problem. It introduces a **routing layer between your question and your documents**, powered by category-level vector summaries and a lightweight LLM classification call. Before a single document chunk is searched, the system already knows *which slice of the knowledge base* is relevant. The result is lower noise, higher precision, and a retrieval pipeline that degrades gracefully even when the LLM is down.

Then we went further. We wrapped the whole engine with a **multi-tenant live layer** — JWT authentication, group-scoped knowledge bases, real-time WebSocket status updates — so the same core architecture can serve isolated teams on shared infrastructure without a single document leaking across a group boundary.

This is not a RAG wrapper. This is a RAG system with a nervous system.

---

## The Core Idea in One Paragraph

When a query arrives, CaRAG does not immediately search 50,000 document chunks. Instead, it embeds the query and compares it against a set of **category summary vectors** — high-level semantic fingerprints that describe entire families of documents. If one category scores above the confidence threshold (`0.35`), a small LLM call routes the query to that category. *Then* it searches — but only inside that category's documents. This two-stage funnel eliminates retrieval noise at scale and makes the final LLM answer dramatically more grounded.

---

## Architecture at a Glance

```
+---------------------------------------------------------+
¦                    CaRAG Live (Port 8001)                ¦
¦   JWT Auth | Group Isolation | WebSocket Events          ¦
¦                                                         ¦
¦   +-------------------------------------------------+   ¦
¦   ¦           CaRAG Core Engine (Port 8000)          ¦   ¦
¦   ¦   Ingestion | Auto-Categorization | RAG Routing  ¦   ¦
¦   +-------------------------------------------------+   ¦
+---------------------------------------------------------+
         ¦                          ¦
   PostgreSQL                  Milvus DB
   (metadata, users,           (chunk vectors +
    groups, categories)         category summaries)
```

The **Core Engine** is a fully standalone RAG service. It can run on its own, ingest documents, auto-discover categories, and answer queries. No users. No groups. Pure retrieval.

The **Live Adapter** wraps the Core Engine and adds identity, authorization, and multi-tenancy on top — without touching a single line of core retrieval logic. Every document uploaded through the Live layer carries a `group_id` all the way into Milvus, so group boundaries are enforced at the *vector search level*, not just at the API level.

---

## Folder Structure

```
CaRAG/
¦
+-- core_backend/               # The standalone RAG engine (Port 8000)
¦   +-- src/
¦   ¦   +-- main.py             # FastAPI app: /upload, /chat, /reset, /categories-with-docs
¦   ¦   +-- services.py         # All business logic: ingestion pipeline, RAG routing, reset
¦   ¦   +-- llm_service.py      # Gemini wrappers: classify, route, synthesize, stream
¦   ¦   +-- milvus_store.py     # Milvus client: upsert/search chunks + category summaries
¦   ¦   +-- models.py           # SQLAlchemy ORM: Document, Category, DocumentChunk
¦   ¦   +-- schemas.py          # Pydantic request/response schemas
¦   ¦   +-- config.py           # Env-var loading: DB URL, embedding model, chunk config
¦   ¦   +-- database.py         # SQLAlchemy session factory
¦   +-- requirements.txt
¦   +-- README.md               # Deep-dive into the core engine internals
¦
+-- live/                       # The multi-tenant adapter layer (Port 8001)
¦   +-- backend/
¦       +-- src/
¦           +-- main.py         # FastAPI app: mounts auth, groups, documents, chat, ws routers
¦           +-- auth.py         # Register, login, JWT issuance, get_current_user middleware, reset
¦           +-- groups.py       # Group CRUD, member invitation, categories-with-docs
¦           +-- documents.py    # Group-scoped upload, list, delete, category list
¦           +-- chat.py         # Group-scoped RAG chat (Mode A/B/C)
¦           +-- ws.py           # WebSocket manager: group-broadcast real-time events
¦           +-- models.py       # ORM: User, Group, GroupMember (+ Document, Category re-used)
¦
+-- demo_core.html              # Interactive testing UI for the Core Engine (Port 8000)
+-- demo_live.html              # Interactive testing UI for the Live Layer (Port 8001)
¦
+-- Files_for_reference/        # Original design docs, flow specs, and reference diagrams
+-- carag_architecture_testing_guide.md   # Step-by-step Postman/UI testing guide
+-- FLOWS.md                    # Complete sequence diagrams — every user flow, every edge case
¦
+-- start_core_api.bat          # One-click launcher for the Core Engine
+-- start_api.bat               # One-click launcher for the Live Layer
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **API Framework** | FastAPI + Uvicorn | Async-native, automatic OpenAPI docs, dependency injection for auth |
| **Vector Store** | Milvus (`milvus-lite` locally, or hosted) | Purpose-built for ANN search; supports metadata filters for group isolation |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, fast, high-quality semantic embeddings — runs on CPU |
| **LLM** | Google Gemini | 3 targeted calls per query cycle: classify document, route query, synthesize answer |
| **Relational DB** | PostgreSQL (production) / SQLite (dev) | Source of truth for all metadata — documents, categories, users, groups, members |
| **Text Chunking** | LangChain `RecursiveCharacterTextSplitter` | Chunk size 800 tokens, 120 overlap — tuned for semantic coherence |
| **PDF Parsing** | pypdf | Lightweight, no binary dependencies |
| **Auth** | JWT (HS256, `python-jose`) + bcrypt | Stateless tokens, 60-minute expiry, group membership validated per request |
| **Real-Time** | WebSocket (FastAPI native) | Push `doc_processing` / `doc_ready` / `doc_failed` events to all group members |

---

## How to Run It

**Prerequisites:** Python 3.10+, PostgreSQL running, Milvus accessible (or `milvus-lite` for local dev).

**1. Core Engine (Port 8000)**
```bash
# Set your .env in core_backend/ — see variables below
.\start_core_api.bat
# or: uvicorn src.main:app --reload --port 8000
```

**2. Live Layer (Port 8001)**
```bash
.\start_api.bat
# or: python -m uvicorn live.backend.src.main:app --reload --port 8001
```

**3. Testing UIs**

Open `demo_core.html` in your browser for the Core Engine testing console.
Open `demo_live.html` for the full multi-tenant flow — registration, groups, scoped upload, scoped chat, and WebSocket events all in one place.

Both pages have a fixed right-pane console that logs every API request, response, and status in real time. Every button maps to exactly one backend endpoint. Nothing is mocked.

**Environment variables (in `core_backend/.env`):**

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `GEMINI_API_KEY` | Google Gemini API key |
| `MILVUS_URI` | Milvus endpoint (`./milvus_lite.db` for local) |
| `JWT_SECRET_KEY` | Random secret for signing tokens |
| `EMBEDDING_MODEL` | Default: `sentence-transformers/all-MiniLM-L6-v2` |
| `CHUNK_SIZE` | Default: `800` |
| `CHUNK_OVERLAP` | Default: `120` |

---

## User Flows — Complete System Behaviour

The best way to understand CaRAG is to read the flow diagrams. They were written directly from source code. Every node is a real function call. Every branch is a real conditional. No hand-waving.

### ?? [FLOWS.md](./FLOWS.md) — Complete Sequence Diagrams

**What is covered:**

| Diagram | Flows Documented |
|---|---|
| **Core Engine** | Document ingestion (all code paths including PDF failure, chunk failure, auto-categorization, bypass_llm, Gemini 429 graceful fallback, taxonomy consolidation), 2-stage categorical RAG chat (Mode A: doc pin / Mode B: manual category / Mode C: automatic routing with confidence gate + LLM routing + hallucination guard), system reset |
| **Live Adapter** | Registration, login, JWT middleware, group creation, member invitation (5-step validation chain), group-scoped ingestion + WebSocket events, group-scoped chat with multi-layer isolation (Milvus group_doc_ids security boundary + category intersection), live layer reset |

Every happy path, every failure path, every graceful degradation is there. If you are integrating with this system, read that file first.

---

## What Makes This Different

Most production RAG systems hit one of three walls at scale:

**Wall 1 — Retrieval noise.** When your corpus grows past a few hundred documents, flat vector search starts surfacing marginally-related chunks. The answer quality degrades silently. Users stop trusting the system.

**Wall 2 — No graceful failure.** When your LLM is rate-limited or down, the system either crashes or returns nothing. Users get a 500. Support tickets arrive.

**Wall 3 — No isolation.** If multiple teams share one knowledge base, there's no clean way to scope queries to one team's documents without running completely separate infrastructure for each team.

CaRAG was designed specifically to solve all three.

**Against retrieval noise:** The two-stage routing funnel (category vector search ? LLM routing ? scoped chunk search) reduces the search space before a single document chunk is compared. You are not searching your entire corpus — you are searching the right 10% of it.

**Against LLM failure:** Every Gemini call has a fallback. Category classification falls back to vector similarity. Query routing falls back to the top vector match. Answer synthesis falls back to a structured mock response that still returns the raw retrieved chunks to the user. The system never crashes — it degrades to the next-best thing, transparently.

**Against isolation:** The Live adapter enforces group boundaries at the vector search level by scoping every Milvus query to a computed set of `group_doc_ids`. Even if a `document_id` or `category` is guessed by a client, the system validates group membership at the database level before searching anything. Two groups on the same server are completely invisible to each other. There is no configuration knob to accidentally flip.

---

## Status

> Core Engine — ? Production-ready
> Live Adapter — ? Production-ready
> Testing UIs — ? Fully functional (demo_core.html, demo_live.html)
> WebSocket real-time events — ? Working
> Docker — ?? Base compose available in `core_backend/Docker/`

---

*For architecture deep-dives, read [`core_backend/README.md`](./core_backend/README.md).
For the complete sequence diagrams of every user flow, read [`FLOWS.md`](./FLOWS.md).*
