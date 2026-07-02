from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas
from .database import get_db
from .auth import get_current_user
from src.milvus_store import milvus_store

router = APIRouter()


def _assert_membership(db: Session, group_id: int, user_id: int) -> models.Group:
    """Shared guard: raises 403/404 if user has no access to the group."""
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    member = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="You are not a member of this group.")
    return group


@router.post("/{group_id}/chat", response_model=schemas.ChatResponse)
async def group_chat(
    group_id: int,
    payload: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _assert_membership(db, group_id, current_user.id)

    # ── STEP 1: Get all ready doc IDs scoped to this group ─────────────────────
    # This is the security boundary. Only these IDs will ever be searched.
    group_doc_ids = [
        row.id
        for row in db.query(models.Document.id).filter(
            models.Document.group_id == group_id,
            models.Document.status == "ready",
        ).all()
    ]

    if not group_doc_ids:
        pending_count = db.query(models.Document).filter(
            models.Document.group_id == group_id,
            models.Document.status.in_(["uploaded", "processing"]),
        ).count()
        if pending_count > 0:
            return schemas.ChatResponse(
                answer="Your documents are still being processed. Please wait a moment.",
                citations=[],
            )
        return schemas.ChatResponse(
            answer="This group has no documents yet. Upload some PDFs first!",
            citations=[],
        )

    try:
        from src.services import _embed_query
        from src.llm_service import generate_answer, classify_query_category
        query_vector = _embed_query(payload.question)
        hits = []

        # ── MODE A: User pinned to a specific document ───────────────────────────
        # Most precise scope possible. We still validate the doc belongs to THIS
        # group to prevent cross-group data leaks even if a doc_id is guessed.
        if payload.document_id is not None:
            doc = db.query(models.Document).filter(
                models.Document.id == payload.document_id,
                models.Document.group_id == group_id,   # security: must be in this group
                models.Document.status == "ready",
            ).first()
            if not doc:
                return schemas.ChatResponse(
                    answer="That document doesn't exist in this group or isn't ready yet.",
                    citations=[],
                )
            hits = milvus_store.search(
                query_embedding=query_vector,
                top_k=max(1, min(payload.top_k, 100)),
                document_id=payload.document_id,  # single-doc Milvus filter
            )

        # ── MODE B: User manually selected a category ────────────────────────────
        # User picked from the list returned by GET /groups/{id}/categories.
        # Double-filtered: must be in this group AND in the chosen category.
        elif payload.category is not None:
            category_doc_ids = [
                row.id
                for row in db.query(models.Document.id)
                .join(models.Document.categories)
                .filter(
                    models.Document.group_id == group_id,
                    models.Category.name == payload.category,
                    models.Document.status == "ready",
                ).all()
            ]
            if not category_doc_ids:
                return schemas.ChatResponse(
                    answer=f"No ready documents found in category '{payload.category}' within this group.",
                    citations=[],
                )
            hits = milvus_store.search(
                query_embedding=query_vector,
                top_k=max(1, min(payload.top_k, 100)),
                document_ids=category_doc_ids,
            )

        # ── MODE C: Automatic 2-stage categorical routing (default) ─────────────
        # No manual override — engine figures out the best category automatically.
        else:
            # STEP 2: Search Milvus category summary collection
            try:
                category_matches = milvus_store.search_categories(query_vector, top_k=5, group_id=group_id)
            except Exception:
                category_matches = []

            # STEP 3: Confidence gate — flat search if no strong category match
            if not category_matches or category_matches[0]["score"] < 0.35:
                print(f"Low category confidence. Running flat search across group {group_id}.")
                hits = milvus_store.search(
                    query_embedding=query_vector,
                    top_k=max(1, min(payload.top_k, 100)),
                    document_ids=group_doc_ids,
                )
            else:
                # STEP 4: LLM routing — cheap classification call, returns category name
                try:
                    chosen_category = await classify_query_category(
                        question=payload.question,
                        category_candidates=category_matches,
                    )
                except Exception:
                    chosen_category = category_matches[0]["category_name"]

                # Guard: if LLM hallucinated a category name, fall back to top match
                candidate_names = [m["category_name"] for m in category_matches]
                if chosen_category not in candidate_names:
                    chosen_category = category_matches[0]["category_name"]

                print(f"LLM routed to category: '{chosen_category}'")

                # STEP 5: Intersection of group + category filters
                scoped_ids = [
                    row.id
                    for row in db.query(models.Document.id)
                    .join(models.Document.categories)
                    .filter(
                        models.Document.group_id == group_id,
                        models.Category.name == chosen_category,
                        models.Document.status == "ready",
                    ).all()
                ]
                hits = milvus_store.search(
                    query_embedding=query_vector,
                    top_k=max(1, min(payload.top_k, 100)),
                    document_ids=scoped_ids if scoped_ids else group_doc_ids,
                )

        if not hits:
            return schemas.ChatResponse(
                answer="The group's documents don't contain enough information to answer this question.",
                citations=[],
            )

        # ── STEP 6: Build Response ───────────────────────────────────────────────
        citations = [
            schemas.Citation(
                document_id=hit["document_id"],
                chunk_index=hit["chunk_index"],
                score=hit["score"],
                content_preview=hit["content"][:220],
            )
            for hit in hits
        ]

        context = "\n\n".join(
            f"[Source {i + 1}] {hit['content']}" for i, hit in enumerate(hits)
        )

        # LLM Call #2 — the actual answer generation
        answer = await generate_answer(question=payload.question, context=context, bypass_llm=payload.bypass_llm)

        return schemas.ChatResponse(answer=answer, citations=citations)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=f"Chat service error: {str(exc)}")
