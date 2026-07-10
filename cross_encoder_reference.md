# Cross-Encoder Reranking: Implementation Reference

## 1. The Why: Bi-Encoders vs. Cross-Encoders

### The Problem with Bi-Encoders
Standard RAG relies on **Bi-Encoders** (like `SentenceTransformer`). 
- A Bi-Encoder maps a 500-word paragraph into a single point in a 384-dimensional space. 
- It does the same for the user's question.
- It then calculates the distance between those two points (cosine similarity).

**The flaw:** Because the paragraph's meaning is highly compressed, the Bi-Encoder cannot look at the *interaction* between the specific words in the question and the specific words in the chunk. It only knows they share general semantic concepts. This leads to retrieval noise, where a chunk discussing a similar topic is retrieved over a chunk containing the exact factual answer.

### The Solution: Cross-Encoders
A **Cross-Encoder** does not produce vectors. Instead, it takes the user's question and a document chunk, concatenates them (`[CLS] Question [SEP] Chunk [SEP]`), and feeds them *together* through the Transformer layers. 
- **Deep Attention:** The model can perform self-attention *across* the question and the chunk simultaneously, allowing it to see exactly how the question's terms map to the chunk's terms.
- **The Catch:** It is computationally heavy. You cannot run a Cross-Encoder over 10,000 documents in real-time.

### The Architecture: 2-Stage Retrieval
To get the speed of Bi-Encoders and the accuracy of Cross-Encoders, we use a 2-stage pipeline:
1. **Stage 1 (Bi-Encoder):** Ask Milvus to return a wide net of candidates (e.g., Top 15 to 45). This is blazing fast.
2. **Stage 2 (Cross-Encoder):** Pass those 15-45 chunks into the Cross-Encoder. It re-scores and re-orders them, throwing away the irrelevant ones and passing only the absolute best (Top 5) to the LLM.

---

## 2. The Code: What Was Added

### `core_backend/src/config.py`
- Added `CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"`. This specific model is highly optimized for question-answering ranking.

### `core_backend/src/services.py`
- **Global Initialization:** Added `CROSS_ENCODER_INSTANCE = CrossEncoder(CROSS_ENCODER_MODEL)`. It loads once into memory to avoid startup latency per request.
- **`answer_question()` Modifications:**
  - Increased `top_k` fetched from Milvus from `N` to `max(15, N * 3)` to ensure a wide enough net is cast.
  - Implemented the reranking block before the LLM synthesis step:
    ```python
    # 1. Prepare pairs
    cross_input = [[question, hit["content"]] for hit in hits]
    
    # 2. Score them simultaneously
    scores = CROSS_ENCODER_INSTANCE.predict(cross_input)
    
    # 3. Attach scores and sort
    for idx, hit in enumerate(hits):
        hit["cross_score"] = float(scores[idx])
    
    hits.sort(key=lambda x: x["cross_score"], reverse=True)
    hits = hits[:top_k] # Slice the absolute best
    ```

### `live/backend/src/chat.py` (Live Adapter)
- Imported the initialized `CROSS_ENCODER_INSTANCE` from the core engine.
- Applied the exact same Stage 2 logic within the `POST /groups/{group_id}/chat` endpoint.
- **Security Check:** Reranking occurs *after* Milvus filters the initial fetch by `group_id`. The Cross-Encoder is only allowed to see chunks that the user is authorized to read.
