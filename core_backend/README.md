# CaRAG Backend — Code-Level Reference

> Deep-dive documentation for every module, function, and service in the CaRAG backend. This document is intended for developers who want to understand the exact execution path, internal logic, and design rationale at the code level.

For the high-level system architecture and complete flow diagrams, see the [root README](../README.md).

---

## 📌 Table of Contents

1. [Project Layout](#1-project-layout)
2. [Running the Backend](#2-running-the-backend)
3. [Module-by-Module Breakdown](#3-module-by-module-breakdown)
   - [config.py](#configpy--environment-constants)
   - [database.py](#databasepy--session-factory)
   - [models.py](#modelspy--orm-definitions)
   - [schemas.py](#schemaspy--pydantic-contracts)
   - [milvus_store.py](#milvus_storepy--vector-db-wrapper)
   - [llm_service.py](#llm_servicepy--gemini-llm-calls)
   - [services.py](#servicespy--core-business-logic)
   - [main.py](#mainpy--fastapi-routes)
4. [Detailed Function Reference](#4-detailed-function-reference)
5. [Internal Data Flow Between Modules](#5-internal-data-flow-between-modules)
6. [Error Handling & Safety Patterns](#6-error-handling--safety-patterns)
7. [Development Nuances & Gotchas](#7-development-nuances--gotchas)

---

## 1. Project Layout

```
backend/
├── src/
│   ├── config.py          ← Reads .env, exposes typed constants
│   ├── database.py        ← SQLAlchemy engine + session factory
│   ├── models.py          ← ORM table definitions
│   ├── schemas.py         ← Pydantic request/response contracts
│   ├── milvus_store.py    ← All Milvus operations (isolated class)
│   ├── llm_service.py     ← All Gemini calls (isolated, stateless)
│   ├── services.py        ← Core pipeline logic (ingestion, RAG, cleanup)
│   ├── main.py            ← FastAPI app, routes, middleware
│   └── startupguide.md    ← Local environment setup instructions
├── uploads/               ← PDF files land here (runtime, gitignored)
└── venv/                  ← Python virtual environment
```

---

## 2. Running the Backend

### Prerequisites
Ensure the following services are running and reachable before starting:
- **PostgreSQL** — connection string must be set in `.env` as `DATABASE_URL`
- **Milvus** — URI must be set in `.env` as `MILVUS_URI`

### Environment Variables (`.env` file in `backend/`)
```ini
DATABASE_URL=postgresql://user:password@localhost:5432/carag
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=                      # Leave blank if no auth
MILVUS_COLLECTION=document_chunks  # Default if not set
GEMINI_API_KEY=your_key_here
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384
CHUNK_SIZE=800
CHUNK_OVERLAP=120
```

### Start Command
```powershell
# Navigate to backend directory
cd backend

# Activate virtual environment
.\venv\Scripts\activate

# Start the FastAPI server with hot-reload
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

> **Important:** Run as `python -m uvicorn src.main:app` (module mode), not `uvicorn src.main:app` directly. Module mode ensures Python's import resolution works correctly for relative imports within the `src` package.

- **API Base URL:** `http://127.0.0.1:8000`
- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

---

## 3. Module-by-Module Breakdown

### `config.py` — Environment Constants

The first module loaded. Uses `python-dotenv` to read a `.env` file, then exposes typed constants used across the project.

```python
MILVUS_URI     # str — Milvus server address
DATABASE_URL   # str — PostgreSQL connection string
MILVUS_COLLECTION = "document_chunks"  # default
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384    # int — must match model output
GEMINI_API_KEY # str — Google Gemini API key
CHUNK_SIZE = 800       # int — characters per chunk
CHUNK_OVERLAP = 120    # int — overlap between chunks
```

**Design note:** All magic numbers are centralized here. Changing chunk behavior, switching embedding models, or pointing to a different Milvus cluster requires editing only this one file (and the `.env`). Nothing is hardcoded in business logic.

---

### `database.py` — Session Factory

Sets up the SQLAlchemy connection pool and provides the `get_db` dependency for FastAPI routes.

Key objects:
- **`engine`** — SQLAlchemy `create_engine` using `DATABASE_URL` from config.
- **`sessionLocal`** — Session factory used in background tasks (which create their own DB sessions since they run outside FastAPI's request lifecycle).
- **`get_db()`** — FastAPI dependency that yields a DB session per request and ensures it's closed afterward (via `try/finally`).
- **`Base`** — SQLAlchemy declarative base class that all ORM models inherit from.

**Why two session mechanisms?**
- FastAPI routes use `Depends(get_db)` — the session is managed per HTTP request, automatically closed when the request ends.
- Background tasks (`process_document_task`, `update_categorical_summary`) cannot use `Depends` because they run outside the request context. They call `sessionLocal()` directly and manage their own `db.close()` in a `finally` block.

---

### `models.py` — ORM Definitions

Defines two SQLAlchemy ORM models that map to PostgreSQL tables.

#### `Document`
```python
class Document(Base):
    __tablename__ = "documents"
    id          = Column(Integer, primary_key=True, index=True)
    filename    = Column(String, index=True)
    file_size   = Column(Integer, nullable=True)
    file_path   = Column(String)
    status      = Column(String, default="uploaded")   # uploaded|processing|ready|failed
    category    = Column(String, default="general", index=True, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    chunks      = relationship("DocumentChunk", back_populates="document",
                               cascade="all, delete-orphan")
```

**`cascade="all, delete-orphan"`** — This SQLAlchemy relationship option means that when you call `db.delete(doc)`, SQLAlchemy automatically deletes all related `DocumentChunk` rows. You never have to manually delete chunks before deleting a document.

#### `DocumentChunk`
```python
class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id          = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index = Column(Integer, nullable=False)   # 0-based position within document
    content     = Column(Text, nullable=False)      # raw plaintext of this chunk
    milvus_id   = Column(String, nullable=True, index=True)  # Milvus record ID
    created_at  = Column(DateTime, default=datetime.utcnow)
    document    = relationship("Document", back_populates="chunks")
```

**`milvus_id`** is the FK-equivalent bridge to the Milvus world. It's nullable because it's populated only after the chunk is successfully upserted to Milvus. If ingestion fails mid-way, it will be null.

---

### `schemas.py` — Pydantic Contracts

Defines request and response shapes. FastAPI uses these for automatic request validation, serialization, and OpenAPI schema generation.

| Schema | Direction | Key Fields |
|---|---|---|
| `DocumentResponse` | Response (all doc endpoints) | `id`, `filename`, `status`, `file_size`, `category` |
| `DocumentStatusUpdate` | Request (`PATCH`) | `status: str` |
| `ChatRequest` | Request (`POST /chat`) | `question`, `document_id?`, `category?`, `top_k=5` |
| `ChatCitation` | Nested in response | `document_id`, `chunk_index`, `score`, `content_preview` |
| `ChatResponse` | Response (`POST /chat`) | `answer: str`, `citations: list[ChatCitation]` |

**`model_config = ConfigDict(from_attributes=True)`** on `DocumentResponse` — this tells Pydantic to read data from object attributes (like `doc.id`, `doc.filename`) rather than from a dictionary. This is what makes `return doc` work in route handlers when `doc` is a SQLAlchemy model instance.

---

### `milvus_store.py` — Vector DB Wrapper

A singleton class (`MilvusStore`) that wraps all Milvus operations. Instantiated once as `milvus_store = MilvusStore()` at module load and imported by `services.py`.

#### Connection Strategy: Lazy Initialization
`_get_client()` checks `self._client is not None` before creating a new `MilvusClient`. This means the connection to Milvus is only established on the first operation, not at import time. This avoids startup failures if Milvus is briefly unavailable when the server boots.

#### Collection Schema
Both collections use the same schema pattern but with different scalar fields:

**`document_chunks` collection schema:**
| Field | Type | Purpose |
|---|---|---|
| `id` | INT64 (PK) | Nanosecond timestamp-based unique ID |
| `vector` | FLOAT_VECTOR (dim=384) | The dense embedding vector |
| `document_id` | INT64 | Links back to PostgreSQL `documents.id` |
| `chunk_index` | INT64 | Position within its source document |
| `content` | VARCHAR (max 65535) | Plaintext of the chunk |

**`categorical_chunks` collection schema:**
| Field | Type | Purpose |
|---|---|---|
| `id` | INT64 (PK) | Nanosecond timestamp-based unique ID |
| `vector` | FLOAT_VECTOR (dim=384) | Embedding of the category summary |
| `category_name` | VARCHAR (max 255) | The category string |
| `summary` | VARCHAR (max 65535) | The Gemini-generated summary text |

**Index:** Both collections use `AUTOINDEX` with `COSINE` metric. `AUTOINDEX` lets Milvus choose the optimal algorithm (typically HNSW) based on data volume.

#### Key Methods

**`ensure_collection()`**
Called at the top of every operation method. Checks if both collections exist — if not, creates them via `_create_collection`. Then loads them into memory (`client.load_collection`). Without `load_collection`, Milvus collections aren't queryable.

**`upsert_chunks(document_id, chunks, embeddings)`**
- Generates nanosecond-based IDs (`time.time_ns() + idx`) to prevent primary key collisions even for near-simultaneous uploads.
- Calls `client.insert()` then `client.flush()`. **The flush is critical:** without it, inserted data stays in Milvus's in-memory write buffer ("growing segment") and won't show up in the Attu Data Explorer, even though `client.query()` can still read it. Flush forces the data into sealed (persisted) segments.

**`search(query_embedding, top_k, document_id?, document_ids?)`**
- If `document_id` is provided: adds Milvus filter `document_id == {id}`
- If `document_ids` list is provided: adds Milvus filter `document_id in [{ids}]`
- If neither: performs global search across all records in the collection
- Returns a list of dicts: `{milvus_id, score, document_id, chunk_index, content}`

**`search_categories(query_embedding, top_k)`**
- Searches only `categorical_chunks` collection
- Returns `[{category_name, summary, score}]` sorted by cosine similarity descending

**`upsert_category_summary(category_name, summary, embedding)`**
- Deletes any existing record for this category first (by `category_name` filter)
- Then inserts a fresh record with the new summary and embedding
- This is the "update" in upsert — Milvus doesn't support true in-place updates, so delete + insert is the pattern

---

### `llm_service.py` — Gemini LLM Calls

All Gemini interactions live here. The module is **stateless** — no conversation history, no session state. Every call is independent.

**Model:** `gemini-2.5-flash` — chosen for speed and cost efficiency in classification tasks.

#### `generate_answer(question, context)` — Synthesizer (Call 2)

System prompt enforces strict grounding:
```
You MUST follow these rules:
1. Answer ONLY from the provided context.
2. Do NOT invent information.
3. If the answer is not found in the context, say: "The provided document does not contain enough information..."
4. Keep answers concise and factual.
5. Use bullet points when appropriate.
```

Context is passed as labeled sources: `[Source 1] chunk... [Source 2] chunk...`

**Rate Limit Fallback:** On `429` errors, instead of crashing, it extracts the top 3 source chunks from the context string and returns them formatted as bullet points with a visible `⚠️ [Mock Mode]` warning banner. The user still gets *something useful* even when the API is throttled.

#### `classify_ingested_document(text_sample, existing_categories)` — Classifier (Call 0)

Prompt structure:
- Shows Gemini the first 4000 characters of the document (enough to understand the subject)
- Provides the list of all existing category names in the database
- Rules: match an existing category exactly, OR propose a new concise category name
- Response format: raw string only (no quotes, no markdown, no explanation)

**Why 4000 chars?** That's typically 1-3 pages of text — sufficient to identify the subject domain without spending excessive tokens.

**Rate Limit Fallback:** Uses keyword matching against common topics (e.g., "harry", "potter" → "Harry Potter and the Prisoner of Azkaban") as a deterministic mock.

#### `classify_query_category(question, category_candidates)` — Router (Call 1)

Prompt structure:
- Shows Gemini the user's question
- Provides all candidate categories with their Gemini-generated summaries
- Rules: pick the single most relevant category, respond with exact name only

**Why pass summaries, not just category names?** A bare category name like "Machine Learning" gives Gemini nothing to compare against. A summary like "Documents in this category cover neural network architectures, gradient descent optimization, and PyTorch implementations" allows for much more accurate semantic matching.

---

### `services.py` — Core Business Logic

The largest and most important module. Contains the entire ingestion pipeline, the RAG engine, and lifecycle management functions.

#### Helper Functions (private, prefixed with `_`)

**`_extract_text_from_pdf(file_path)`**
Uses `pypdf.PdfReader` to iterate over all pages and join their extracted text with newlines. Returns a single string of the full document text. Returns empty string if PDF has no extractable text (e.g., scanned image PDFs).

**`_chunk_text(text)`**
Uses LangChain's `RecursiveCharacterTextSplitter` with these separator priorities:
1. `\n\n` — paragraph breaks (most preferred split point)
2. `\n` — line breaks
3. `. ` — sentence ends
4. ` ` — word boundaries
5. `""` — character-level (last resort)

This hierarchy means the splitter always tries to split at the largest logical boundary first, only falling back to smaller splits if the chunk would still exceed `CHUNK_SIZE`. This preserves semantic coherence better than a naive character split.

**`_embed_texts(texts: list[str])` / `_embed_query(text: str)`**
Uses a single `SentenceTransformer` instance (`EMBEDDING_MODEL_INSTANCE`) loaded once at module import — not per request. This is the correct pattern; loading a 90MB model per request would be catastrophically slow. `normalize_embeddings=True` ensures all vectors are L2-normalized, making cosine similarity directly comparable to dot product similarity.

---

#### `process_document_task(doc_id, filename)` — Ingestion Pipeline

**Async background function.** Called via FastAPI `BackgroundTasks.add_task`. Creates its own `sessionLocal()` DB session since it runs outside the request lifecycle.

Full execution sequence:
1. Fetch document from DB, update status → `"processing"`
2. Extract PDF text via `_extract_text_from_pdf`. If empty → status `"failed"`, exit.
3. Chunk text via `_chunk_text`. If no chunks → status `"failed"`, exit.
4. **Auto-Categorization block** (only runs if `doc.category` is `"general"` or None):
   - Embed `chunks[0]` (the first chunk, which typically contains the document header/title/abstract)
   - Call `milvus_store.search_categories(first_chunk_vector, top_k=1)`
   - If top score `>= 0.60` → assign that category (no LLM needed)
   - If top score `< 0.60` → query Postgres for all existing distinct category names, call `llm_service.classify_ingested_document(text[:4000], existing_categories)`, assign returned category
   - Update `doc.category` in DB and commit
5. Embed all chunks (`_embed_texts(chunks)`) — this is the slow step for large documents
6. `milvus_store.upsert_chunks(doc_id, chunks, embeddings)` → get back list of Milvus IDs
7. Delete old chunk rows from Postgres for this `doc_id` (idempotency — safe to re-run)
8. Bulk insert new `DocumentChunk` rows with `milvus_id` values
9. Update status → `"ready"`, commit
10. If `resolved_category != "general"` → `asyncio.create_task(update_categorical_summary(category))` — fires off another async task to update the category cluster embedding without blocking

**Error handling:** Wrapped in `try/except/finally`. Any unhandled exception sets status to `"failed"` and rolls back the transaction. `db.close()` always runs in `finally`.

---

#### `update_categorical_summary(category_name)` — Category Cluster Refresh

**Async function** that refreshes the `categorical_chunks` Milvus entry for a given category.

Execution:
1. Skip immediately if `category_name` is `None` or `"general"` (no cluster summary for the catch-all category)
2. Query Postgres: all `Document` records where `category == category_name AND status == "ready"`
3. For each document, fetch its first `DocumentChunk` (lowest `chunk_index`) and take up to 1000 characters
4. Build `category_context` by joining all document first-chunks: `"Document 'filename': {first 1000 chars}"`
5. Call Gemini with a prompt: generate a 2-3 sentence summary of what this category encompasses
6. Embed the summary text
7. `milvus_store.upsert_category_summary(category_name, summary, embedding)` — atomically replaces the old embedding

**Why only the first chunk per document?** The category summary doesn't need the entire document — just enough to understand what domain it belongs to. The first chunk (intro, abstract, or table of contents) is the most information-dense portion for classification purposes.

---

#### `answer_question(question, document_id?, category?, top_k)` — RAG Engine

The core query function. Opens its own DB session, executes the routing logic, retrieves chunks, and calls the LLM synthesizer.

**Pre-flight checks:**
- Counts `"ready"` documents. If zero, checks for `"processing"` documents and returns an appropriate human-readable message. Exits early without hitting Milvus or Gemini.

**Pathway 1 — `document_id` provided (bypass routing):**
- Validates the document exists and is `"ready"` in Postgres
- Calls `milvus_store.search(query_vector, top_k, document_id=document_id)` with a direct equality filter

**Pathway 2 — `category` provided (bypass LLM routing):**
- Queries Postgres for all `document_ids` in that category with status `"ready"`
- Calls `milvus_store.search(query_vector, top_k, document_ids=doc_ids)` with an `in [...]` filter

**Pathway 3 — No filters (full two-stage routing):**
- **Stage 1:** `milvus_store.search_categories(query_vector, top_k=5)` → returns up to 5 category matches
- **Fallback condition:** `not matches or matches[0]["score"] < 0.35` → calls `milvus_store.search(query_vector, top_k)` globally (no filter)
- **LLM routing (Call 1):** If score `>= 0.35`, calls `llm_service.classify_query_category(question, matches)` → gets `chosen_category` string
- **Safety check:** Validates `chosen_category in [m["category_name"] for m in matches]`. If Gemini hallucinated a category that isn't in the candidate list, falls back to `matches[0]["category_name"]` (the highest vector-scored match)
- **Stage 2:** Resolves `chosen_category` to `doc_ids` via Postgres, calls filtered Milvus search

**Post-retrieval:**
- Logs all retrieved chunks to stdout (for debugging — safe with ASCII encoding to avoid Windows console encoding errors)
- Builds `citations` list from hits (doc_id, chunk_index, score, 220-char preview)
- Formats context: `"[Source 1] {content}\n\n[Source 2] {content}..."` — the numbered source labels help Gemini attribute which chunk each piece of information came from
- Calls `llm_service.generate_answer(question, context)` (Call 2)
- Returns `{answer, citations}`

---

#### `delete_document_assets(document_id, file_path)` — Storage Cleanup

Async function that handles the physical deletion before Postgres record deletion:
1. If `file_path` exists on disk → `os.remove(file_path)`
2. `milvus_store.delete_document_chunks(document_id)` → Milvus delete by filter `document_id == id`

Called from the `DELETE /documents/{id}` route before the Postgres `db.delete(doc)` call.

---

#### `reset_system()` — Factory Reset

Async function that wipes all three storage layers atomically:
1. Iterates `uploads/` directory and calls `os.remove()` on every file
2. Calls `milvus_store.delete_all_chunks()` — drops both collections and recreates them fresh
3. Executes:
   ```sql
   TRUNCATE TABLE document_chunks, documents RESTART IDENTITY CASCADE
   ```
   - `RESTART IDENTITY` resets all auto-increment sequences back to 1
   - `CASCADE` handles any remaining FK constraints not already resolved by the collection ordering

---

### `main.py` — FastAPI Routes

The entry point and HTTP routing layer. Keeps business logic thin — delegates to `services.py` for any complex operations.

**App Setup:**
```python
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
models.Base.metadata.create_all(bind=engine)  # Creates tables if they don't exist
```

`create_all` runs at startup. It's idempotent — if tables already exist, it skips creation. This means you never need to run manual `CREATE TABLE` SQL; the ORM manages schema creation.

**CORS:** `allow_origins=["*"]` accepts all origins. For production, this should be restricted to the actual frontend domain.

**Route handlers are deliberately thin.** For example:
```python
@app.post("/chat")
async def chat(payload: schemas.ChatRequest):
    return await services.answer_question(
        question=payload.question,
        document_id=payload.document_id,
        category=payload.category,
        top_k=payload.top_k,
    )
```

No business logic in the route. Pure delegation. This makes `services.py` independently testable.

**`POST /clean-system`** — Development utility. Uses `subprocess` to call `tasklist` and `taskkill` on Windows to terminate zombie Python processes (those left over from crashed background tasks) while preserving the current server PID.

---

## 4. Detailed Function Reference

| Function | Module | Async | Description |
|---|---|---|---|
| `_extract_text_from_pdf(file_path)` | services | No | pypdf page extraction |
| `_chunk_text(text)` | services | No | RecursiveCharacterTextSplitter |
| `_embed_texts(texts)` | services | No | Batch SentenceTransformer encode |
| `_embed_query(text)` | services | No | Single-text embed (wraps `_embed_texts`) |
| `process_document_task(doc_id, filename)` | services | **Yes** | Full async ingestion pipeline |
| `update_categorical_summary(category_name)` | services | **Yes** | Gemini summary + Milvus upsert |
| `answer_question(question, doc_id, category, top_k)` | services | **Yes** | Full RAG engine with routing |
| `delete_document_assets(doc_id, file_path)` | services | **Yes** | Disk + Milvus cleanup |
| `reset_system()` | services | **Yes** | Full 3-layer wipe |
| `generate_answer(question, context)` | llm_service | **Yes** | Gemini Call 2 — synthesizer |
| `classify_ingested_document(text_sample, categories)` | llm_service | **Yes** | Gemini Call 0 — doc classifier |
| `classify_query_category(question, candidates)` | llm_service | **Yes** | Gemini Call 1 — query router |
| `ensure_collection()` | milvus_store | No | Creates/loads Milvus collections |
| `upsert_chunks(doc_id, chunks, embeddings)` | milvus_store | No | Insert + flush document vectors |
| `search(query_emb, top_k, doc_id, doc_ids)` | milvus_store | No | Filtered vector similarity search |
| `search_categories(query_emb, top_k)` | milvus_store | No | Search categorical_chunks |
| `upsert_category_summary(name, summary, emb)` | milvus_store | No | Replace category cluster embedding |
| `delete_document_chunks(doc_id)` | milvus_store | No | Milvus delete by document_id filter |
| `delete_category_summary(category_name)` | milvus_store | No | Milvus delete by category_name filter |
| `delete_all_chunks()` | milvus_store | No | Drop + recreate both collections |

---

## 5. Internal Data Flow Between Modules

```
HTTP Request
    │
    ▼
main.py (FastAPI route)
    │
    ├── Depends(get_db) ──────────────────► database.py (session)
    │
    ├── schemas.py (request validation)
    │
    └── services.py (business logic)
            │
            ├── _embed_*() ───────────────► SentenceTransformer (in-process)
            │
            ├── milvus_store.py ──────────► Milvus (external)
            │       └── _get_client()
            │           ensure_collection()
            │           search() / upsert_chunks() / ...
            │
            ├── llm_service.py ───────────► Google Gemini API (external, async)
            │       └── asyncio.to_thread()   (wraps blocking SDK call)
            │
            └── database.py (sessionLocal for background tasks)
                    └── models.py (ORM query/update/insert)
```

**Key observation:** `asyncio.to_thread()` is used in `llm_service.py` for all Gemini calls because the `google-generativeai` Python SDK's `generate_content()` is a **blocking synchronous call**. Calling it directly from an `async` function would block the entire FastAPI event loop, preventing any other requests from being served. `asyncio.to_thread()` offloads it to a thread pool, keeping the event loop free.

---

## 6. Error Handling & Safety Patterns

### Pattern 1: Background Task Isolation
```python
async def process_document_task(doc_id, filename):
    db = sessionLocal()
    try:
        ...
    except Exception as exc:
        db.rollback()
        doc.status = "failed"
        db.commit()
    finally:
        db.close()
```
Every background task function owns its own DB session. If it crashes, it always closes the session and marks the document as `"failed"` so the frontend can display the correct state.

### Pattern 2: Milvus Operation Guards
Every public `MilvusStore` method starts with `ensure_collection()`. This means even if Milvus loses its in-memory state (e.g., after a restart), the next operation will automatically reload the collections rather than throwing a cryptic "collection not loaded" error.

### Pattern 3: LLM Confidence Validation
After `classify_query_category` returns a category name, the code checks:
```python
if chosen_category not in candidate_names:
    chosen_category = matches[0]["category_name"]  # safe fallback
```
This prevents Gemini's occasional tendency to slightly reformat or invent a category name from propagating into a broken Postgres query.

### Pattern 4: Graceful LLM Degradation
All three Gemini functions detect `429` / quota errors by checking the error message string for keywords (`"429"`, `"quota"`, `"limit"`, `"exhausted"`). On detection, they fall back to deterministic logic (keyword matching, raw chunk surfacing) instead of propagating a 503 error. Users get degraded but functional responses.

---

## 7. Development Nuances & Gotchas

### 1. The Milvus Flush Requirement
After `client.insert()`, you MUST call `client.flush()` if you want the data to be visible in:
- Milvus Attu Data Explorer
- Any monitoring/inspection tools
Without flush, the data is in a growing (write-buffer) segment that Python queries *can* read, but external tools can't see. This caused significant confusion during development.

### 2. The Windows Console Encoding Issue
When printing retrieved chunks in `answer_question`, the code uses:
```python
safe_content = hit["content"][:300].encode('ascii', errors='replace').decode('ascii')
```
PDF text often contains Unicode characters (em-dashes, curly quotes, special symbols) that crash Windows PowerShell's default `cp1252` console encoding. The `.encode('ascii', errors='replace')` replaces non-ASCII characters with `?` for safe logging.

### 3. Category `"general"` is a No-Op
The category `"general"` is the default placeholder. The system explicitly skips:
- Category summary generation for `"general"`
- Categorical triage for documents in `"general"`

Documents categorized as `"general"` are only reachable via a global search (no filter) or an explicit `document_id` or `category="general"` filter in the chat request.

### 4. Idempotent Chunk Ingestion
Before inserting new chunks into Postgres during `process_document_task`, the function always runs:
```python
db.query(models.DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
```
This makes re-processing a document safe. If a document is reprocessed (e.g., after a partial failure), it won't accumulate duplicate chunk rows.

### 5. Nanosecond IDs in Milvus
Milvus requires integer primary keys. Instead of a separate ID counter, chunks use:
```python
base_id = time.time_ns()
"id": int(base_id + idx)
```
`time.time_ns()` returns the current time in nanoseconds (e.g., `1749359671000000000`). Adding `idx` (0, 1, 2...) to the base ensures uniqueness within a batch. Two concurrent uploads happening within the same nanosecond would collide — an acceptable risk for the current scale, but worth replacing with UUID-based IDs for production.

### 6. `asyncio.create_task` Inside a Non-Event-Loop Context
In `process_document_task`, the summary update is spawned with:
```python
asyncio.create_task(update_categorical_summary(resolved_category))
```
This works because `process_document_task` itself is an `async` function running on FastAPI's event loop. `create_task` schedules the coroutine on the same event loop, so it starts after `process_document_task` completes. This is the correct pattern for "fire and forget" async chaining without blocking the current task.
