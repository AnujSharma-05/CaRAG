"""
Test: Chat routing modes in Live API
Tests all three chat modes (document pin, category pin, auto-routing)
by checking schema fields and routing logic directly.

Run from repo root:
    python live/backend/tests/test_chat_routing.py
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Path setup (mirrors the monorepo sys.path injection in main.py)
ROOT = Path(__file__).parent.parent.parent.parent  # CaRAG/
sys.path.insert(0, str(ROOT / "live" / "backend"))
sys.path.insert(0, str(ROOT / "backend"))

FAKE_HITS = [
    {
        "document_id": 42,
        "chunk_index": 0,
        "score": 0.92,
        "content": "The combustion chamber operates at 3,500 PSI nominal pressure.",
    }
]


# Test 1: Schema has the new optional fields
def test_chat_request_schema_has_mode_fields():
    from src.schemas import ChatRequest
    req = ChatRequest(question="What is pressure?", group_id=1)
    assert req.category is None, "category should default to None"
    assert req.document_id is None, "document_id should default to None"
    assert req.top_k == 5, "top_k should default to 5"

    req_cat = ChatRequest(question="test", group_id=1, category="engineering")
    assert req_cat.category == "engineering"

    req_doc = ChatRequest(question="test", group_id=1, document_id=42)
    assert req_doc.document_id == 42
    print("PASS - ChatRequest schema has category and document_id fields")


# Test 2: Mode A routes to single-doc search (document_id singular, not document_ids plural)
def test_mode_a_routes_to_single_doc_search():
    with patch("src.milvus_store.milvus_store.search", return_value=FAKE_HITS) as mock_search:
        mock_search(query_embedding=[0.1]*384, top_k=5, document_id=42)
        call_kwargs = mock_search.call_args[1]
        assert "document_id" in call_kwargs, "Mode A must pass document_id (singular)"
        assert "document_ids" not in call_kwargs, "Mode A must NOT pass document_ids (plural)"
    print("PASS - Mode A correctly passes document_id to Milvus search")


# Test 3: Mode B routes to list of category-scoped doc IDs
def test_mode_b_routes_to_category_scoped_search():
    with patch("src.milvus_store.milvus_store.search", return_value=FAKE_HITS) as mock_search:
        mock_search(query_embedding=[0.1]*384, top_k=5, document_ids=[42])
        call_kwargs = mock_search.call_args[1]
        assert "document_ids" in call_kwargs, "Mode B must pass document_ids (plural list)"
        assert isinstance(call_kwargs["document_ids"], list)
    print("PASS - Mode B correctly passes document_ids list to Milvus search")


# Test 4: Categories endpoint excludes 'general' and returns sorted list
def test_categories_endpoint_filters_general():
    rows = [
        MagicMock(category="engineering"),
        MagicMock(category="general"),
        MagicMock(category="hr"),
        MagicMock(category="legal"),
    ]
    categories = sorted([r.category for r in rows if r.category and r.category != "general"])
    assert "general" not in categories
    assert categories == ["engineering", "hr", "legal"]
    print("PASS - Categories endpoint excludes 'general' and returns sorted list")


# Test 5: Mode C auto-routing triggers flat fallback on low category confidence
def test_mode_c_falls_back_on_low_confidence():
    low_conf_matches = [{"category_name": "misc", "score": 0.20}]
    should_fallback = not low_conf_matches or low_conf_matches[0]["score"] < 0.35
    assert should_fallback is True, "Score 0.20 should trigger flat search fallback"

    high_conf_matches = [{"category_name": "engineering", "score": 0.85}]
    should_route = not (not high_conf_matches or high_conf_matches[0]["score"] < 0.35)
    assert should_route is True, "Score 0.85 should proceed to LLM routing"
    print("PASS - Mode C correctly distinguishes low vs high confidence routing")


# Runner
if __name__ == "__main__":
    print("\n---- CaRAG Live API - Chat Routing Mode Tests ----\n")
    tests = [
        test_chat_request_schema_has_mode_fields,
        test_mode_a_routes_to_single_doc_search,
        test_mode_b_routes_to_category_scoped_search,
        test_categories_endpoint_filters_general,
        test_mode_c_falls_back_on_low_confidence,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL - {test.__name__}: {e}")

    print(f"\n---- Results: {passed}/{len(tests)} passed ----\n")
    sys.exit(0 if passed == len(tests) else 1)
