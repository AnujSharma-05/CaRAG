# Hybrid Retrieval (BM25 + Dense): Implementation Reference

## 1. The Why: Semantic vs. Keyword Search

### The Limitation of Pure Vector Search
Dense Vector Search (Milvus + SentenceTransformers) is incredible for **semantic** understanding. If you search for "dog", it will find chunks containing "canine" or "puppy". 
However, it is notoriously bad at **exact keyword matching**. If a user searches for a specific part number like "AX-4099-B", the vector model might dilute this into a generic concept of "manufacturing part", retrieving entirely wrong part numbers that share the same general context.

### The Solution: Hybrid Retrieval with BM25
BM25 (Best Matching 25) is the gold standard algorithm for sparse (keyword) search. It scores documents based on exact term frequency and inverse document frequency (IDF). It rewards chunks containing rare, exact terms.

By combining both, we get the best of both worlds:
1. **Milvus** pulls chunks that conceptually match the query.
2. **BM25** pulls chunks that exactly contain the rare keywords from the query.
3. We fuse them using **Reciprocal Rank Fusion (RRF)**, ensuring the final list given to the Cross-Encoder is robust against both semantic and keyword misses.

---

## 2. The Code: What Was Added

### `core_backend/requirements.txt`
- Added `rank-bm25`.

### `core_backend/src/bm25_store.py` (New File)
- **`InMemoryBM25Store`**: A singleton class managing the BM25 index.
- **`load_from_db()`**: Fetches all `DocumentChunk` rows that belong to `ready` documents from PostgreSQL and builds the tokenized index in memory.
- **`search()`**: Takes a query, tokenizes it, scores all chunks using BM25, applies any `document_ids` filters (preserving group security), and returns the `top_k` hits.

### `core_backend/src/services.py` & `live/backend/src/chat.py`
- **`reciprocal_rank_fusion()`**: A mathematical function added to fuse multiple ranked lists. It uses the standard formula `1 / (k + rank)` where `k=60`.
- **Parallel Fetching**: Instead of just calling Milvus, the pipeline now calls both and fuses them before the Cross-Encoder stage.
  ```python
  # 1. Fetch from Milvus
  milvus_hits = milvus_store.search(query_embedding, top_k*3, document_ids=doc_ids)
  
  # 2. Fetch from BM25
  bm25_hits = bm25_store.search(question, top_k*3, document_ids=doc_ids)
  
  # 3. Fuse mathematically
  hits = reciprocal_rank_fusion(milvus_hits, bm25_hits)
  ```

### Scale & Architecture Note
At ~2,500 chunks, `rank-bm25` running purely in Python memory is incredibly fast and takes virtually zero RAM. However, at a true scale of 10M documents, this in-memory index would need to be replaced by a distributed engine like Elasticsearch or Milvus 2.4+ Sparse Vectors. The current pipeline cleanly abstracts the `bm25_store.search()` call, making that future migration trivial.
