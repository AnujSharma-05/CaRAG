import asyncio
import os
from typing import Any
from .config import EMBEDDING_MODEL

from sqlalchemy.orm import Session

from . import models
from .database import sessionLocal
from .milvus_store import milvus_store

from sentence_transformers import SentenceTransformer

from .llm_service import generate_answer
from .config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)
from sqlalchemy import text

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


EMBEDDING_MODEL_INSTANCE = SentenceTransformer(
    EMBEDDING_MODEL
)


def _extract_text_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()

def _extract_summary_text_from_pdf(file_path: str) -> str:
    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        if total_pages == 0:
            return ""
        
        first_pages_limit = min(5, total_pages)
        first_pages_text = []
        for i in range(first_pages_limit):
            txt = reader.pages[i].extract_text()
            if txt:
                first_pages_text.append(txt)
                
        last_pages_text = []
        if total_pages > 5:
            last_pages_start = max(5, total_pages - 2)
            for i in range(last_pages_start, total_pages):
                txt = reader.pages[i].extract_text()
                if txt:
                    last_pages_text.append(txt)
                    
        parts = []
        if first_pages_text:
            parts.append("--- START OF DOCUMENT ---\n" + "\n".join(first_pages_text))
        if last_pages_text:
            parts.append("--- END OF DOCUMENT ---\n" + "\n".join(last_pages_text))
            
        return "\n\n".join(parts).strip()
    except Exception as e:
        print("Failed to extract summary text from PDF:", e)
        return ""

def _chunk_text(
    text: str,
) -> list[str]:

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
            "",
        ],
    )

    return splitter.split_text(text)


def _embed_texts(texts: list[str]) -> list[list[float]]:
    vectors = EMBEDDING_MODEL_INSTANCE.encode(
        texts,
        normalize_embeddings=True
    )

    return [vector.tolist() for vector in vectors]


def _embed_query(text: str) -> list[float]:
    return _embed_texts([text])[0]


async def update_categorical_summary(category_name: str, group_id: int | None = None) -> None:
    """Consolidate document contents in the category and update its Milvus summary embedding."""
    if not category_name or category_name == "general":
        return

    db: Session = sessionLocal()
    try:
        # Fetch all documents in this category and group
        query = db.query(models.Document).join(models.Document.categories).filter(
            models.Category.name == category_name,
            models.Document.status == "ready"
        )
        if group_id is not None:
            query = query.filter(models.Document.group_id == group_id)
        docs = query.all()
        
        if not docs:
            return

        # Compile summaries or first/last chunks of documents to create a category context
        context_parts = []
        for doc in docs:
            # Extract first 5 and last 2 pages of PDF on-the-fly
            doc_context = _extract_summary_text_from_pdf(doc.file_path)
            meta_info = f"Document: {doc.filename}\nSize: {doc.file_size or 0} bytes\n"
            context_parts.append(meta_info + doc_context[:4000])

        category_context = "\n\n".join(context_parts)
        
        # Call LLM to generate summary
        prompt = f"""
            Generate a concise, unified 2-3 sentence summary describing the scope and topic of this category of documents.
            Category Name: {category_name}
            Documents Context:
            {category_context}
        """
        
        from .llm_service import model
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
        )
        summary_text = response.text.strip()
        
        # Generate summary embedding
        summary_vector = _embed_query(summary_text)
        
        # Upsert in Milvus
        milvus_store.upsert_category_summary(
            category_name=category_name,
            summary=summary_text,
            embedding=summary_vector,
            group_id=group_id
        )
        print(f"Updated category summary for '{category_name}' in group {group_id}: {summary_text[:100]}...")

    except Exception as exc:
        print("Failed to update categorical summary:", exc)
    finally:
        db.close()


async def consolidate_categories(group_id: int | None) -> None:
    """Consolidate/generalize specific categories under parent categories like 'Harry Potter Books', 'Novels', etc."""
    db: Session = sessionLocal()
    try:
        # Get all distinct categories in the group
        categories = db.query(models.Category).filter(models.Category.group_id == group_id).all()
        if len(categories) < 2:
            return

        # Prepare summary list for LLM analysis
        candidates = []
        for cat in categories:
            candidates.append({
                "id": cat.id,
                "name": cat.name,
                "summary": cat.summary or ""
            })

        # Prompt Gemini to identify relationships and recommend consolidation/grouping
        prompt = f"""
            You are an expert taxonomy and knowledge organization agent.
            Analyze the following active document categories and summaries in this user's workspace:
            
            {candidates}
            
            Determine if any of these categories can be grouped under broader, general parent categories (e.g. "Novels", "Research Papers", "User Manuals", "Company Policies", "Harry Potter Books").
            
            Rules:
            1. Suggest group pairings where sub-categories belong to a parent category.
            2. Suggest parent categories that are clean, concise, and meaningful (e.g., if there are multiple parts of "Harry Potter", they belong to "Harry Potter Books" AND "Novels").
            3. Each sub-category can map to MULTIPLE parent categories (e.g. "Sorcerer's Stone" belongs under "Harry Potter Books" and "Novels").
            4. Respond ONLY with a JSON list of objects matching this format (no markdown formatting, no code blocks, no other text):
            [
                {{"parent_category": "Harry Potter Books", "sub_category_ids": [1, 2]}},
                {{"parent_category": "Novels", "sub_category_ids": [1, 2, 3]}}
            ]
            
            If no consolidation is needed, return: []
        """
        
        from .llm_service import model
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
        )
        import json
        raw_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        if not raw_text or raw_text == "[]":
            return
            
        consolidations = json.loads(raw_text)
        for entry in consolidations:
            parent_name = entry.get("parent_category")
            sub_ids = entry.get("sub_category_ids", [])
            if not parent_name or not sub_ids:
                continue
                
            # Create or get parent category
            parent_cat = db.query(models.Category).filter(
                models.Category.name == parent_name,
                models.Category.group_id == group_id
            ).first()
            if not parent_cat:
                parent_cat = models.Category(name=parent_name, group_id=group_id)
                db.add(parent_cat)
                db.commit()
                db.refresh(parent_cat)

            # Associate all documents from sub-categories to this parent category
            sub_categories = db.query(models.Category).filter(models.Category.id.in_(sub_ids)).all()
            for sub_cat in sub_categories:
                for doc in sub_cat.documents:
                    if parent_cat not in doc.categories:
                        doc.categories.append(parent_cat)
            
            db.commit()
            
            # Rewrite parent category summary
            await update_categorical_summary(parent_name, group_id)

    except Exception as e:
        print("Failed to consolidate categories:", e)
    finally:
        db.close()


async def process_document_task(doc_id: int, filename: str) -> None:
    """Background ingestion pipeline for uploaded PDFs."""
    db: Session = sessionLocal()
    try:
        doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
        if not doc:
            return

        doc.status = "processing"
        db.commit()

        text = _extract_text_from_pdf(doc.file_path)
        if not text:
            doc.status = "failed"
            db.commit()
            return

        chunks = _chunk_text(text)
        if not chunks:
            doc.status = "failed"
            db.commit()
            return

        # --- Dynamic Automated Categorization ---
        if not doc.categories:
            summary_context_text = _extract_summary_text_from_pdf(doc.file_path)
            meta_info = f"Filename: {doc.filename}\nFile Size: {doc.file_size or 0} bytes\n"
            context_for_classification = meta_info + summary_context_text
            
            resolved_category_name = "general"
            # 1. Try vector-based matching against existing summaries
            first_chunk_vector = _embed_query(summary_context_text[:1000] if summary_context_text else chunks[0])
            try:
                matches = milvus_store.search_categories(first_chunk_vector, top_k=1, group_id=doc.group_id)
                if matches and matches[0]["score"] >= 0.60:
                    resolved_category_name = matches[0]["category_name"]
                    print(f"Vector-matched category: {resolved_category_name} (score: {matches[0]['score']})")
            except Exception as e:
                print("Milvus category search skipped/failed:", e)

            # 2. Fallback to LLM Classification
            if resolved_category_name == "general":
                try:
                    # Get unique category names in this group from PostgreSQL
                    categories_objs = db.query(models.Category).filter(models.Category.group_id == doc.group_id).all()
                    existing_categories = [c.name for c in categories_objs if c.name != "general"]
                    
                    from . import llm_service
                    resolved_category_name = await llm_service.classify_ingested_document(
                        text_sample=context_for_classification[:4000],
                        existing_categories=existing_categories
                    )
                    print(f"LLM-classified category: {resolved_category_name}")
                except Exception as e:
                    print("LLM classification failed, fallback to general:", e)
                    resolved_category_name = "general"

            # Create or get category in Postgres
            db_category = db.query(models.Category).filter(
                models.Category.name == resolved_category_name,
                models.Category.group_id == doc.group_id
            ).first()
            if not db_category:
                db_category = models.Category(name=resolved_category_name, group_id=doc.group_id)
                db.add(db_category)
                db.commit()
                db.refresh(db_category)
                
            doc.categories.append(db_category)
            db.commit()

        embeddings = _embed_texts(chunks)

        milvus_ids = milvus_store.upsert_chunks(document_id=doc_id, chunks=chunks, embeddings=embeddings)

        db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == doc_id).delete()
        db.bulk_save_objects(
            [
                models.DocumentChunk(
                    document_id=doc_id,
                    chunk_index=index,
                    content=chunk,
                    milvus_id=str(milvus_ids[index]) if index < len(milvus_ids) else None,
                )
                for index, chunk in enumerate(chunks)
            ]
        )

        doc.status = "ready"
        db.commit()
        print(
            f"DOCUMENT {doc_id} FINISHED"
        )   

        # Trigger summary update for all categories associated with this document
        for cat in doc.categories:
            await update_categorical_summary(cat.name, doc.group_id)

        # Trigger dynamic parent category consolidation / merging
        if doc.group_id is not None:
            await consolidate_categories(doc.group_id)

    except Exception as exc:  # pragma: no cover - safety path for async task
        db.rollback()
        doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
        if doc:
            doc.status = "failed"
            db.commit()
    finally:
        db.close()


async def answer_question(question: str, document_id: int | None = None, category: str | None = None, top_k: int = 5) -> dict[str, Any]:
    """Retrieve relevant chunks from Milvus and build a grounded response payload using hierarchical clustering."""
    db: Session = sessionLocal()
    try:
        ready_count = db.query(models.Document).filter(models.Document.status == "ready").count()
        if ready_count == 0:
            processing_count = db.query(models.Document).filter(models.Document.status.in_(["uploaded", "processing"])).count()
            if processing_count > 0:
                return {
                    "answer": "Your documents are currently being processed. Please wait a moment and try again.",
                    "citations": []
                }
            return {
                "answer": "No documents are available in the system. Please ingest some PDFs before starting the chat.",
                "citations": []
            }
        
        query_vector = _embed_query(question)
        hits = []

        # 1. Bypass check - Specific Document ID Filter
        if document_id is not None:
            doc = db.query(models.Document).filter(models.Document.id == document_id).first()
            if not doc:
                return {
                    "answer": "The selected document does not exist.",
                    "citations": []
                }
            if doc.status != "ready":
                return {
                    "answer": f"The selected document is not ready yet (current status: {doc.status}).",
                    "citations": []
                }
            hits = milvus_store.search(query_embedding=query_vector, top_k=max(1, min(top_k, 10)), document_id=document_id)

        # 2. Bypass check - Specific Category Filter
        elif category is not None:
            doc_ids_query = db.query(models.Document.id).filter(
                models.Document.category == category,
                models.Document.status == "ready"
            ).all()
            doc_ids = [r[0] for r in doc_ids_query]
            if doc_ids:
                hits = milvus_store.search(query_embedding=query_vector, top_k=max(1, min(top_k, 10)), document_ids=doc_ids)
            else:
                hits = []

        # 3. Two-Stage Routing Flow (No active manual filter)
        else:
            # Stage 1: Categorical Triage
            try:
                matches = milvus_store.search_categories(query_vector, top_k=5)
            except Exception as exc:
                print("Milvus search_categories failed:", exc)
                matches = []

            # Confidence-Score Fallback (or if no category summaries exist)
            if not matches or matches[0]["score"] < 0.35:
                print(f"Bypassing categorical routing (Top score: {matches[0]['score'] if matches else 'None'} < 0.35). Global search initiated.")
                hits = milvus_store.search(query_embedding=query_vector, top_k=max(1, min(top_k, 10)))
            else:
                # LLM Routing (LLM Call 1)
                from . import llm_service
                try:
                    chosen_category = await llm_service.classify_query_category(
                        question=question,
                        category_candidates=matches
                    )
                    print(f"LLM 1 classified query to category: '{chosen_category}' (Matches were: {[m['category_name'] for m in matches]})")
                except Exception as exc:
                    print("LLM query classification failed, falling back to top matched category:", exc)
                    chosen_category = matches[0]["category_name"]

                # Ensure chosen category exists in candidates, fallback if not
                candidate_names = [m["category_name"] for m in matches]
                if chosen_category not in candidate_names:
                    print(f"Chosen category '{chosen_category}' not in candidate list. Falling back to top match: '{matches[0]['category_name']}'")
                    chosen_category = matches[0]["category_name"]

                # Stage 2: Main Search (Relational Filter)
                doc_ids_query = db.query(models.Document.id).filter(
                    models.Document.category == chosen_category,
                    models.Document.status == "ready"
                ).all()
                doc_ids = [r[0] for r in doc_ids_query]
                if doc_ids:
                    hits = milvus_store.search(query_embedding=query_vector, top_k=max(1, min(top_k, 10)), document_ids=doc_ids)
                else:
                    # In case documents in chosen category are not found/ready, fallback to global
                    print(f"No documents ready in category '{chosen_category}'. Bypassing category filter.")
                    hits = milvus_store.search(query_embedding=query_vector, top_k=max(1, min(top_k, 10)))

    finally:
        db.close()

    print("\n========== RETRIEVED CHUNKS ==========")

    for idx, hit in enumerate(hits):
        print(
            f"\nChunk {idx+1}"
        )
        safe_content = hit["content"][:300].encode('ascii', errors='replace').decode('ascii')
        print(
            safe_content
        )

    print(
        "\n====================================="
    )

    if not hits:
        return {
            "answer": "The provided documents do not contain sufficient information to answer this question.",
            "citations": [],
        }

    citations = [
        {
            "document_id": hit["document_id"],
            "chunk_index": hit["chunk_index"],
            "score": hit["score"],
            "content_preview": hit["content"][:220],
        }
        for hit in hits
    ]

    context_lines = [
        f"[Source {idx + 1}] {hit['content']}" for idx, hit in enumerate(hits)
    ]
    context = "\n\n".join(context_lines)

    answer = await generate_answer(
        question=question,
        context=context,
    )

    return {
        "answer": answer,
        "citations": citations,
    }


async def delete_document_assets(document_id: int, file_path: str | None) -> None:
    """Delete physical file + Milvus vectors for a document."""
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    milvus_store.delete_document_chunks(document_id)

async def reset_system() -> None:

    print("RESET STARTED")

    db: Session = sessionLocal()

    try:

        print("STEP 1")

        uploads_dir = "uploads"

        if os.path.exists(uploads_dir):
            for file_name in os.listdir(uploads_dir):
                file_path = os.path.join(
                    uploads_dir,
                    file_name,
                )

                if os.path.isfile(file_path):
                    os.remove(file_path)

        print("STEP 2")

        milvus_store.delete_all_chunks()
        print("BEFORE TRUNCATE")

        db.execute(
            text(
                """
                TRUNCATE TABLE
                    document_chunks,
                    documents
                RESTART IDENTITY
                CASCADE
                """
            )
        )

        print("AFTER TRUNCATE")
        db.commit()
        result = db.execute(
            text(
                "SELECT nextval('documents_id_seq')"
            )
        )

        print(
            "NEXTVAL AFTER RESET =",
            result.scalar()
        )
    finally:

        print("STEP 7")

        db.close()
