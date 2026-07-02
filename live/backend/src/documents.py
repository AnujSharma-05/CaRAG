#Group-scoped document routes for uploading, deleting and listing group specific documents.

import os
import shutil
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from . import models, schemas
from .database import get_db
from .auth import get_current_user
from src import services
from src.milvus_store import milvus_store
import asyncio

router = APIRouter()


def _assert_membership(db: Session, group_id: int, user_id: int) -> models.Group: #This function is used to check if the user is a member of the group
    """Shared guard: raises 403 if user is not in the group, 404 if group doesn't exist."""
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    member = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == user_id
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="You are not a member of this group.")
    return group


# ─────────────────────────────────────────────────────────────────────────────
# POST /groups/{group_id}/documents — Upload a PDF into a specific group
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/{group_id}/documents", response_model=schemas.DocumentResponse) # Upload a PDF into a group. Saves to uploads/group_{id}/ on disk. Kicks off the CaRAG engine ingestion in background
async def upload_document(
    group_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), # Upload the PDF file
    category: str | None = Form(None), # Optional category for the document
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _assert_membership(db, group_id, current_user.id)

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Scope uploads directory to the group for clean separation on disk
    upload_dir = os.path.join("uploads", f"group_{group_id}")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)

    new_doc = models.Document(
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        status="uploaded",
        group_id=group_id,         # <-- SCOPED to this group
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    # If category is explicitly provided, map it immediately
    if category and category != "general":
        db_category = db.query(models.Category).filter(
            models.Category.name == category,
            models.Category.group_id == group_id
        ).first()
        if not db_category:
            db_category = models.Category(name=category, group_id=group_id)
            db.add(db_category)
            db.commit()
            db.refresh(db_category)
        new_doc.categories.append(db_category)
        db.commit()

    # Kick off the original CaRAG engine's ingestion pipeline in the background with WS events
    async def process_document_task_with_ws(doc_id: int, filename: str, group_id: int):
        from .ws_manager import manager
        from .database import sessionLocal
        
        await manager.broadcast_to_group(group_id, {
            "event": "doc_processing",
            "doc_id": doc_id,
            "filename": filename
        })
        
        # Run the synchronous CPU-bound task in a thread
        await asyncio.to_thread(services.process_document_task, doc_id, filename)
        
        # Fetch the updated doc status
        db_session = sessionLocal()
        try:
            doc = db_session.query(models.Document).filter(models.Document.id == doc_id).first()
            if doc:
                if doc.status == "ready":
                    categories = [cat.name for cat in doc.categories]
                    await manager.broadcast_to_group(group_id, {
                        "event": "doc_ready",
                        "doc_id": doc_id,
                        "filename": filename,
                        "categories": categories
                    })
                else:
                    await manager.broadcast_to_group(group_id, {
                        "event": "doc_failed",
                        "doc_id": doc_id,
                        "filename": filename
                    })
        finally:
            db_session.close()

    background_tasks.add_task(process_document_task_with_ws, new_doc.id, file.filename, group_id)
    return new_doc


# ─────────────────────────────────────────────────────────────────────────────
# GET /groups/{group_id}/documents — List all docs in a group
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{group_id}/documents", response_model=List[schemas.DocumentResponse])
async def list_documents(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _assert_membership(db, group_id, current_user.id)

    docs = db.query(models.Document).filter(models.Document.group_id == group_id).all()
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /groups/{group_id}/documents/{doc_id} — Delete a single document
# ─────────────────────────────────────────────────────────────────────────────
@router.delete("/{group_id}/documents/{doc_id}")
async def delete_document(
    group_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _assert_membership(db, group_id, current_user.id)

    doc = db.query(models.Document).filter(
        models.Document.id == doc_id,
        models.Document.group_id == group_id,   # Prevent cross-group deletions
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found in this group.")

    # Keep track of categories associated with this document before deletion
    doc_categories = [cat for cat in doc.categories]

    # Step 1: Wipe disk file + Milvus vectors via the engine's utility
    await services.delete_document_assets(document_id=doc.id, file_path=doc.file_path)

    # Step 2: Remove from Postgres (cascades to document_chunks and document_categories relation)
    db.delete(doc)
    db.commit()

    # Step 3: Refresh or remove category summaries in Milvus
    for cat in doc_categories:
        # Check if other documents exist in this category and group
        other_docs_in_category = db.query(models.Document).join(models.Document.categories).filter(
            models.Document.group_id == group_id,
            models.Category.id == cat.id,
            models.Document.status == "ready"
        ).first()
        
        if not other_docs_in_category:
            milvus_store.delete_category_summary(cat.name, group_id)
            # Clean up empty category row from database
            db.delete(cat)
            db.commit()
        else:
            asyncio.create_task(services.update_categorical_summary(cat.name, group_id))

    return {"message": "Document deleted.", "id": doc_id}


# ─────────────────────────────────────────────────────────────────────────────
# GET /groups/{group_id}/categories — List all distinct categories in a group
# Used by the frontend to show a category picker for Mode B chat.
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{group_id}/categories")
async def list_group_categories(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _assert_membership(db, group_id, current_user.id)

    rows = (
        db.query(models.Category.name)
        .filter(
            models.Category.group_id == group_id,
            models.Category.name != "general"
        )
        .distinct()
        .all()
    )

    # Return list of category names
    categories = sorted([r[0] for r in rows if r[0]])
    return {"group_id": group_id, "categories": categories}
