import os
import shutil
import asyncio
from typing import List
from . import config



from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, Form
from sqlalchemy.orm import Session

from fastapi.middleware.cors import CORSMiddleware
from . import models, schemas, services, config
from .database import engine, get_db
from .models import Document
from .milvus_store import milvus_store

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#the server startup command is: uvicorn src.main:app --reload
















@app.get("/ping")
async def ping():
    print("PING HIT")
    return {"status": "alive"}


#----upload document----

@app.post("/upload", response_model=schemas.DocumentResponse)
async def upload_pdf(
    background_tasks: BackgroundTasks, #This is a special parameter that allows us to run tasks in the background without blocking the main thread. In this case, we will use it to trigger the document processing task after the file is uploaded.(always kept as the first parameter in the function definition)
    file: UploadFile = File(...), 
    category: str | None = Form(None),
    db: Session = Depends(get_db)
    ):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are allowed.")

    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)

    new_doc = Document(
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        status="uploaded",
        category=category or "general",
    )

    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    # Trigger ingestion in background; task creates its own DB session.
    background_tasks.add_task(services.process_document_task, new_doc.id, file.filename)
    return new_doc

#----get all documents----

@app.get("/documents", response_model=List[schemas.DocumentResponse])
async def get_documents(
    db: Session = Depends(get_db)
):
    docs = db.query(models.Document).all()

    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "status": doc.status,
            "file_size": doc.file_size if getattr(doc, "file_size", None) is not None else (os.path.getsize(doc.file_path) if doc.file_path and os.path.exists(doc.file_path) else 0), #Explaination of this line: This line is checking if the file_size attribute exists on the doc object and is not None. If it does exist and is not None, it uses that value. If it does not exist or is None, it checks if the file_path attribute exists and if the file at that path exists. If both conditions are true, it gets the size of the file using os.path.getsize(doc.file_path). If either condition is false, it defaults to 0. This ensures that we have a valid file size value even if the file_size attribute is missing or None, or if the file itself is missing.
            "category": doc.category,
        }
        for doc in docs
    ]


@app.get("/documents/{document_id}", response_model=schemas.DocumentResponse)
async def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(
        models.Document.id == document_id
        ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "file_size": doc.file_size if doc.file_size is not None else (os.path.getsize(doc.file_path) if doc.file_path and os.path.exists(doc.file_path) else 0),
        "category": doc.category,
    }


@app.patch("/documents/{document_id}", response_model=schemas.DocumentResponse)
async def update_document_status(document_id: int, payload: schemas.DocumentStatusUpdate, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = payload.status
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "file_size": doc.file_size if doc.file_size is not None else (os.path.getsize(doc.file_path) if doc.file_path and os.path.exists(doc.file_path) else 0),
        "category": doc.category,
    }


@app.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    category_name = doc.category
    await services.delete_document_assets(document_id=doc.id, file_path=doc.file_path)
    db.delete(doc)
    db.commit()

    if category_name and category_name != "general":
        other_docs_exist = db.query(models.Document).filter(
            models.Document.category == category_name,
            models.Document.status == "ready"
        ).first()
        if not other_docs_exist:
            milvus_store.delete_category_summary(category_name)
        else:
            asyncio.create_task(services.update_categorical_summary(category_name))

    return {"message": "Document deleted", "id": document_id}


@app.post("/chat", response_model=schemas.ChatResponse)
async def chat(payload: schemas.ChatRequest):
    try:
        return await services.answer_question(
            question=payload.question,
            document_id=payload.document_id,
            category=payload.category,
            top_k=payload.top_k,
        )
    except Exception as exc:
        import traceback
        print("\n========== CHAT ERROR ==========")
        traceback.print_exc()
        print("================================\n")
        raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(exc)}") from exc


@app.delete("/documents")
async def delete_all_documents(



    db: Session = Depends(get_db)
):

    document_count = db.query(
        models.Document
    ).count()

    chunk_count = db.query(
        models.DocumentChunk
    ).count()

    await services.reset_system()

    return {
        "message": "System reset successful",
        "documents_deleted": document_count,
        "chunks_deleted": chunk_count,
    }



    db: Session = Depends(get_db)


@app.get("/debug/db")
async def debug_db(
    db: Session = Depends(get_db)
):
    return {
        "documents":
            db.query(models.Document).count(),

        "chunks":
            db.query(models.DocumentChunk).count(),
    }


@app.post("/clean-system")
async def clean_system():
    import gc
    import subprocess
    import csv

    # 1. Force Garbage Collection
    gc.collect()

    # 2. Terminate zombie python processes (excluding this server process)
    current_pid = os.getpid()
    killed_count = 0
    try:
        output = subprocess.check_output(
            'tasklist /FI "IMAGENAME eq python.exe" /FO CSV',
            shell=True,
            text=True
        )
        reader = csv.reader(output.strip().splitlines())
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                pid_str = row[1]
                try:
                    pid = int(pid_str)
                    if pid != current_pid:
                        subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                        killed_count += 1
                except ValueError:
                    continue
    except Exception as exc:
        print("Error cleaning processes:", exc)

    return {
        "status": "success",
        "message": "System resources cleared",
        "garbage_collected": True,
        "zombies_killed": killed_count
    }


