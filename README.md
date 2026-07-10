# CaRAG - Categorical Routing Augmented Generation

> **A hierarchical, multi-LLM RAG system that thinks before it retrieves.**

---

## okay so... here's how this started

Honestly? I was just brushing up my RAG skills. Nothing grand. No product vision. No "10-year roadmap." Just me, a laptop, and a half-baked curiosity about whether I could build something *actually* useful with LLMs.

Then two things happened at the same time.

My mate **[Jayneel Mahival](https://github.com/jayneelmahival)** started throwing ideas at me (shoutout bro, this thing exists partly because of your relentless "but what if we also..." energy). And I stumbled on [this Medium article](https://medium.com/@visrow/how-to-design-a-rag-pipeline-for-10-million-documents-with-zero-hallucination-live-demo-057e37bcdbf6) about designing a zero-hallucination RAG pipeline at 10M document scale.

That article broke my brain a little. In a good way.

Because I realized that what most people call "RAG" is just... vibes. You embed stuff. You search stuff. You hope the LLM says something smart. And that works - until it doesn't. At any real scale, with any real document diversity, flat vector search becomes a noise machine.

So I started thinking: what if the retrieval step was actually intelligent? What if the system *routed* the question to the right slice of knowledge before doing any search? What if failure was designed in, not bolted on as an afterthought?

That's CaRAG.

---

## the core idea (for real this time)

When a query arrives, CaRAG does NOT immediately search 50,000 document chunks.

Instead, it embeds the query and compares it against a set of **category summary vectors** - high-level semantic fingerprints that describe entire families of documents. If one category scores above the confidence threshold (`0.35`), a lightweight LLM call routes the query to that category. *Then* it searches - but only inside that category's documents.

Two-stage. Scoped. Intentional.

This funnel kills retrieval noise at scale and makes the final LLM answer dramatically more grounded. Because you're not searching your entire corpus - you're searching the right 10% of it.

---

## the architecture (two layers, one brain)

```
+----------------------------------------------------------+
|                  CaRAG Live  (Port 8001)                  |
|      JWT Auth  |  Group Isolation  |  WebSocket Events    |
|                                                           |
|   +----------------------------------------------------+  |
|   |          CaRAG Core Engine  (Port 8000)             |  |
|   |  Ingestion  |  Auto-Categorization  |  RAG Routing  |  |
|   +----------------------------------------------------+  |
+----------------------------------------------------------+
          |                           |
    PostgreSQL                    Milvus DB
    (metadata, users,             (chunk vectors +
     groups, categories)           category summaries)
```

The **Core Engine** is a fully standalone RAG service. It can run on its own, ingest documents, auto-discover categories, and answer queries. No users. No groups. Just pure retrieval doing its thing.

The **Live Adapter** wraps the Core Engine and adds identity, authorization, and multi-tenancy - without touching a single line of core retrieval logic. Every document uploaded through the Live layer carries a `group_id` all the way into Milvus. Group boundaries are enforced at the *vector search level*, not just at the API level. That's not a config setting. That's the architecture.

---

## folder structure

```
CaRAG/
|
+-- core_backend/               # The standalone RAG engine (Port 8000)
|   +-- src/
|   |   +-- main.py             # FastAPI app: /upload, /chat, /reset, /categories-with-docs
|   |   +-- services.py         # All business logic: ingestion pipeline, RAG routing, reset
|   |   +-- llm_service.py      # Gemini wrappers: classify, route, synthesize, stream
|   |   +-- milvus_store.py     # Milvus client: upsert/search chunks + category summaries
|   |   +-- models.py           # SQLAlchemy ORM: Document, Category, DocumentChunk
|   |   +-- schemas.py          # Pydantic request/response schemas
|   |   +-- config.py           # Env-var loading: DB URL, embedding model, chunk config
|   |   +-- database.py         # SQLAlchemy session factory
|   +-- requirements.txt
|   +-- README.md               # Deep-dive into the core engine internals
|
+-- live/                       # The multi-tenant adapter layer (Port 8001)
|   +-- backend/
|       +-- src/
|           +-- main.py         # FastAPI app: mounts auth, groups, documents, chat, ws routers
|           +-- auth.py         # Register, login, JWT issuance, get_current_user middleware, reset
|           +-- groups.py       # Group CRUD, member invitation, categories-with-docs
|           +-- documents.py    # Group-scoped upload, list, delete, category list
|           +-- chat.py         # Group-scoped RAG chat (Mode A/B/C)
|           +-- ws.py           # WebSocket manager: group-broadcast real-time events
|           +-- models.py       # ORM: User, Group, GroupMember (+ Document, Category re-used)
|
+-- demo_core.html              # Interactive testing UI for the Core Engine (Port 8000)
+-- demo_live.html              # Interactive testing UI for the Live Layer (Port 8001)
|
+-- Files_for_reference/        # Original design docs, flow specs, and reference diagrams
+-- carag_architecture_testing_guide.md   # Step-by-step Postman/UI testing guide
+-- FLOWS.md                    # Complete sequence diagrams - every user flow, every edge case
|
+-- start_core_api.bat          # One-click launcher for the Core Engine
+-- start_api.bat               # One-click launcher for the Live Layer
```

---

## tech stack

| Layer | Technology | Why |
|---|---|---|
| **API Framework** | FastAPI + Uvicorn | Async-native, automatic OpenAPI docs, dependency injection for auth |
| **Vector Store** | Milvus (`milvus-lite` locally, or hosted) | Purpose-built for ANN search; supports metadata filters for group isolation |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, fast, high-quality semantic embeddings - runs on CPU |
| **LLM** | Google Gemini | 3 targeted calls per query cycle: classify document, route query, synthesize answer |
| **Relational DB** | PostgreSQL (production) / SQLite (dev) | Source of truth for all metadata - documents, categories, users, groups, members |
| **Text Chunking** | LangChain `RecursiveCharacterTextSplitter` | Chunk size 800 tokens, 120 overlap - tuned for semantic coherence |
| **PDF Parsing** | pypdf | Lightweight, no binary dependencies |
| **Auth** | JWT (HS256, `python-jose`) + bcrypt | Stateless tokens, 60-minute expiry, group membership validated per request |
| **Real-Time** | WebSocket (FastAPI native) | Push `doc_processing` / `doc_ready` / `doc_failed` events to all group members |

---

## how to run it

**Prerequisites:** Python 3.10+, PostgreSQL running, Milvus accessible (or `milvus-lite` for local dev).

**1. Core Engine (Port 8000)**
```bash
# configure your .env in core_backend/ - see variables below
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
Open `demo_live.html` for the full multi-tenant flow - registration, groups, scoped upload, scoped chat, and WebSocket events all in one page.

Both pages have a fixed right-pane console that logs every API call, response, and status in real time. Every button maps to exactly one backend endpoint. Nothing is mocked.

**Environment variables (`core_backend/.env`):**

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

## user flows - every scenario, every edge case

The best way to understand CaRAG is to read the flow diagrams. They were written directly from source code. Every node is a real function call. Every branch is a real conditional. No hand-waving, no aspirational arrows.

### [FLOWS.md](./FLOWS.md) - Complete Sequence Diagrams

| Diagram | What is covered |
|---|---|
| **Core Engine** | Document ingestion (PDF failure, chunk failure, auto-categorization, bypass_llm, Gemini 429 graceful fallback, taxonomy consolidation), 2-stage categorical RAG chat (Mode A: doc pin / Mode B: manual category / Mode C: automatic routing with confidence gate + LLM routing + hallucination guard), system reset |
| **Live Adapter** | Registration, login, JWT middleware, group creation, member invitation (5-step validation chain), group-scoped ingestion + WebSocket events, group-scoped chat with multi-layer isolation (Milvus group_doc_ids security boundary + category intersection), live layer reset |

Every happy path, every failure path, every graceful degradation is documented. If you are building on top of this, read that file before touching any code.

---

## what makes this not a regular RAG wrapper

Most production RAG systems quietly die on three walls:

**Wall 1 - Retrieval noise.** Once you're past a few hundred documents, flat vector search starts surfacing marginally-related chunks. The answer quality degrades. Silently. Users stop trusting the system and you don't even know why.

**Wall 2 - No graceful failure.** LLM rate-limited? System returns a 500. LLM quota hit? System returns nothing. Nobody designed the unhappy path.

**Wall 3 - No isolation.** Shared knowledge base, multiple teams. You either run separate infra per team (expensive) or you accept that team A might see team B's documents (unacceptable).

CaRAG solves all three at the architecture level, not the config level:

**Against retrieval noise:** The two-stage routing funnel (category vector search -> LLM routing -> scoped chunk search) reduces the search space before a single chunk is compared. You're searching the right 10% of your corpus, not all of it.

**Against LLM failure:** Every Gemini call has a defined fallback. Category classification falls back to vector similarity. Query routing falls back to the top vector match. Answer synthesis falls back to a structured response with the raw retrieved chunks still returned. The system never crashes - it degrades to the next-best thing, transparently, every time.

**Against isolation:** Group boundaries are enforced at the Milvus query level by scoping every search to a computed `group_doc_ids` set. Even if a doc_id or category name is guessed by a client, group membership is validated at the database layer before anything is searched. Two groups on the same server are completely invisible to each other. No config knob can break this.

---

## where this is going

This project started as a skills refresh and turned into something I actually care about.

I am currently working on making the retrieval layer bulletproof - experimenting with **hybrid retrieval (BM25 + dense embeddings)**, **cross-encoder reranking**, and potentially **ScaNN** for ANN search at scale. The goal is zero-hallucination retrieval, or at least a system that knows when it doesn't know.

I'll be sharing progress here as I build. No polish. Just real updates.

If you're building something similar or have opinions on the retrieval optimization path, open an issue. I read them.

---

## status

- Core Engine - production-ready
- Live Adapter - production-ready
- Testing UIs - fully functional (demo_core.html, demo_live.html)
- WebSocket real-time events - working
- Docker - base compose available in `core_backend/Docker/`, full-stack compose in progress
- Hybrid retrieval (BM25 + embeddings) - in research
- Cross-encoder reranking - in research
- ScaNN integration - in research

---

*For architecture deep-dives, read [`core_backend/README.md`](./core_backend/README.md).
For the complete sequence diagrams of every user flow, read [`FLOWS.md`](./FLOWS.md).*

*Built by Anuj Sharma. Thanks to Jayneel Mahival for the push that started this.*