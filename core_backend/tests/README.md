# 🧪 CaRAG Backend — Test Suite

All test scripts are meant to be run from the `tests/` directory with the venv activated:
```
(venv) PS E:\Codes\JPL\CaRAG\backend\tests> python <script_name>.py
```

---

## 📋 Test Scripts

| Script | What it Tests |
|---|---|
| `check_state.py` | PostgreSQL + Milvus row counts — quick health check |
| `check_vectors.py` | Raw Milvus query — verifies vector data exists |
| `test_milvus_data.py` | Full Milvus inspection — lists all collections, stats, and sample rows |
| `milvus_test.py` | Simple Milvus query — checks document_chunks collection directly |
| `test_migration.py` | Creates a test collection in Milvus — used to verify connectivity |
| `gemini_testing.py` | Tests the RAG answer generation via Gemini API |
| `test_gemini.py` | Full Gemini integration test with error tracing |

---

## 🔄 Typical Debug Order

1. **Start here** → `check_state.py` (is the DB and Milvus alive?)
2. **If Milvus empty** → `test_milvus_data.py` (what's actually in Milvus?)
3. **If Gemini broken** → `test_gemini.py` (is the API key working?)
4. **After uploading a doc** → `check_state.py` again to confirm counts went up
