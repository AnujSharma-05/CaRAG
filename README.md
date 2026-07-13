# CaRAG - Categorical Routing Augmented Generation

> **A hierarchical, multi-LLM hybrid RAG system that thinks before it retrieves.**

---

## okay so... here's how this started

Honestly? I was just brushing up my RAG skills. Nothing grand. No product vision. No "10-year roadmap." Just me, a laptop, and a half-baked curiosity about whether I could build something *actually* useful with LLMs.

Then two things happened at the same time.

My mate **[Jayneel Mahival](https://github.com/hyper099)** started throwing ideas at me (shoutout bro, this thing exists partly because of your relentless "but what if we also..." energy). And I stumbled on [this Medium article](https://medium.com/@visrow/how-to-design-a-rag-pipeline-for-10-million-documents-with-zero-hallucination-live-demo-057e37bcdbf6) about designing a zero-hallucination RAG pipeline at 10M document scale.

That article broke my brain a little. In a good way.

Because I realized that what most people call "RAG" is just... vibes. You embed stuff. You search stuff. You hope the LLM says something smart. And that works - until it doesn't. At any real scale, with any real document diversity, flat vector search becomes a noise machine.

So I started thinking: what if the retrieval step was actually intelligent? What if failure was designed in, not bolted on as an afterthought?

That's how CaRAG was born. But it didn't stay simple for long.

---

## the evolution: from basic RAG to enterprise-grade engine

CaRAG went through an insane evolution over the last few weeks. What started as a basic semantic search script has mutated into a production-level, hallucination-resistant retrieval beast. Let me walk you through the journey:

### 1. The Funnel (Categorical Routing)
**The Problem:** Searching 50,000 chunks across distinct domains (e.g., HR policies vs. technical manuals) yields terrible, diluted results.
**The Fix:** I introduced **Categorical Routing**. Before searching documents, CaRAG compares your query against high-level category summaries. If it matches, a fast LLM routes the query exclusively to that category. We don't search the whole corpus; we search the right 10%.

### 2. Multi-Tenancy (The Live Adapter)
**The Problem:** How do you serve multiple organizations without data leakage?
**The Fix:** I built the **Live Adapter** on top of the Core Engine. Every document uploaded carries a `group_id`. Group boundaries are enforced securely at the *vector search level*. You can't retrieve what you don't own.

### 3. The Best of Both Worlds (Hybrid Retrieval & RRF)
**The Problem:** Dense vectors (Milvus) are great for meaning (e.g., "puppy" matches "dog"), but they suck at exact keywords (e.g., "Section 4.1.a"). 
**The Fix:** I integrated **BM25** (a sparse keyword algorithm). Now, CaRAG fetches candidates from Milvus AND BM25 in parallel, then fuses them mathematically using **Reciprocal Rank Fusion (RRF)**. You get semantic understanding *and* exact keyword matching.

### 4. The Critic (Cross-Encoder Reranking)
**The Problem:** Standard embeddings compress paragraphs into vectors, losing the granular relationship between the question and the text.
**The Fix:** I dropped a **Stage-2 Cross-Encoder (MS-MARCO)** into the pipeline. It takes the top hits from the hybrid search, reads the question and the chunk *together*, and brutally re-scores and re-orders them based on pure relevance.

### 5. The Hallucination Killer (Confidence Gate)
**The Problem:** If the user asks about "cake recipes" in a finance database, the engine will still pass the "least irrelevant" tax document to Gemini, forcing it to hallucinate.
**The Fix:** I built a **Retrieval Confidence Gate**. If the Cross-Encoder decides the best chunk is still garbage (negative confidence score), the pipeline *halts completely*. No Gemini call. No hallucination. Just a polite: "I could not find sufficiently relevant information."

### 6. Scaling to Millions (HNSW Indexing)
**The Problem:** Flat brute-force vector search works at 2,000 chunks. At 10,000,000 chunks, it destroys your CPU.
**The Fix:** I transitioned the Milvus engine from flat search to **HNSW (Hierarchical Navigable Small World)** indexing. By structuring vectors in a multi-layered skip-graph, we transformed our search time complexity from `O(N)` to `O(log N)`. 

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
|   |  BM25 Hybrid|  RRF Fusion         |  Cross-Encoder  |  |
|   +----------------------------------------------------+  |
+----------------------------------------------------------+
          |                           |
    PostgreSQL                    Milvus DB
    (metadata, users,             (HNSW indices, chunk vectors,
     groups, categories)           category summaries)
```

The **Core Engine** is a fully standalone, hyper-optimized RAG service. It handles the heavy lifting: Hybrid BM25, HNSW Milvus, RRF, Cross-Encoder reranking, and the Confidence Gate.

The **Live Adapter** wraps the Core Engine and adds identity, authorization, and multi-tenancy - without touching a single line of core retrieval logic.

---

## folder structure

```
CaRAG/
|
+-- core_backend/               # The standalone RAG engine (Port 8000)
|   +-- src/
|   |   +-- main.py             # FastAPI app: /upload, /chat, /reset
|   |   +-- services.py         # Hybrid pipeline, RRF, Cross-Encoder, Confidence Gate
|   |   +-- llm_service.py      # Gemini wrappers: classify, route, synthesize, stream
|   |   +-- milvus_store.py     # Milvus client: HNSW indices + scoped chunk search
|   |   +-- bm25_store.py       # In-memory keyword sparse indexing wrapper
|   |   +-- models.py           # SQLAlchemy ORM: Document, Category, DocumentChunk
|   |   +-- config.py           # Configurable thresholds, HNSW params, logging
|
+-- live/                       # The multi-tenant adapter layer (Port 8001)
|   +-- backend/
|       +-- src/
|           +-- main.py         # FastAPI app: auth, groups, documents, chat, ws
|           +-- chat.py         # Scoped RAG chat executing the full hybrid pipeline
|           +-- ws.py           # WebSocket manager: group-broadcast real-time events
|
+-- demo_core.html              # Interactive testing UI for the Core Engine (Port 8000)
+-- demo_live.html              # Interactive testing UI for the Live Layer (Port 8001)
|
+-- FLOWS.md                    # Complete sequence diagrams - every user flow, every edge case
+-- cross_encoder_reference.md  # Tech specs for reranking mechanics
+-- bm25_hybrid_reference.md    # Tech specs for sparse keyword retrieval
```

---

## tech stack

| Layer | Technology | Why |
|---|---|---|
| **API Framework** | FastAPI + Uvicorn | Async-native, dependency injection for auth |
| **Vector Store** | Milvus (`milvus-lite`) | HNSW ANN indexing; `O(log N)` scale with metadata filters |
| **Sparse Index** | `rank-bm25` | Exact keyword matching, run in-memory for speed |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Deep-attention textual relevance scoring |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | Fast, high-quality semantic embeddings |
| **LLM** | Google Gemini | Classification, routing, answer synthesis |
| **Relational DB** | PostgreSQL | Source of truth for all metadata |

---

## how to run it

**Prerequisites:** Python 3.10+, PostgreSQL running, Milvus accessible (or `milvus-lite` for local dev).

**1. Core Engine (Port 8000)**
```bash
.\start_core_api.bat
```

**2. Live Layer (Port 8001)**
```bash
.\start_api.bat
```

**3. Testing UIs**
Open `demo_core.html` or `demo_live.html` in your browser. Both have a fixed right-pane console that logs every API call and metric (including the new Cross-Encoder distribution logs) in real-time.

---

## user flows - every scenario, every edge case

The best way to understand CaRAG is to read the flow diagrams. They were written directly from source code. Every node is a real function call. Every branch is a real conditional. No hand-waving, no aspirational arrows.

### [FLOWS.md](./FLOWS.md) - Complete Sequence Diagrams

Read this file before touching any code. It contains the complete mapping of the Stage-1 Hybrid BM25 retrieval, the Stage-2 Reranking, the Confidence Gate halt blocks, and the full multi-tenant isolation lifecycle.

---

## status

- Core Engine - production-ready
- Live Adapter - production-ready
- Hybrid retrieval (BM25 + embeddings) - ✅ Implemented
- Cross-encoder reranking - ✅ Implemented
- Confidence Gate & HNSW Indexing - ✅ Implemented

---

*For architecture deep-dives, read the reference markdown files in this repository. Built by Anuj Sharma. Thanks to Jayneel Mahival for the push that started this.*
