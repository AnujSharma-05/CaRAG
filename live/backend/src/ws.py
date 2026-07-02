import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from . import config, models
from .database import sessionLocal
from .ws_manager import manager

router = APIRouter()

@router.websocket("/")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    group_id: int = Query(...)
):
    # 1. JWT validation
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            await websocket.close(code=4001, reason="Invalid token payload")
            return
        user_id = int(user_id_str)
    except JWTError:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # 2. Group membership validation
    db = sessionLocal()
    try:
        membership = db.query(models.GroupMember).filter(
            models.GroupMember.user_id == user_id,
            models.GroupMember.group_id == group_id
        ).first()
        if not membership:
            await websocket.close(code=4003, reason="Not a group member")
            return
    finally:
        db.close()

    # 3. Connection accepted and registered
    await manager.connect(user_id, group_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))
                elif msg_type == "chat":
                    question = message.get("question")
                    if not question:
                        await websocket.send_text(json.dumps({"event": "error", "message": "Missing question"}))
                        continue
                    
                    db_session = sessionLocal()
                    try:
                        group_doc_ids = [
                            row.id
                            for row in db_session.query(models.Document.id).filter(
                                models.Document.group_id == group_id,
                                models.Document.status == "ready",
                            ).all()
                        ]
                        
                        if not group_doc_ids:
                            await websocket.send_text(json.dumps({"event": "error", "message": "This group has no ready documents yet."}))
                            continue

                        from src.services import _embed_query
                        from src.llm_service import classify_query_category, generate_answer_stream
                        from src.milvus_store import milvus_store
                        
                        query_vector = _embed_query(question)
                        hits = []
                        top_k = message.get("top_k", 5)
                        document_id = message.get("document_id")
                        category = message.get("category")

                        if document_id is not None:
                            doc = db_session.query(models.Document).filter(
                                models.Document.id == document_id,
                                models.Document.group_id == group_id,
                                models.Document.status == "ready",
                            ).first()
                            if not doc:
                                await websocket.send_text(json.dumps({"event": "error", "message": "Document doesn't exist or isn't ready."}))
                                continue
                            hits = milvus_store.search(query_embedding=query_vector, top_k=top_k, document_id=document_id)
                        
                        elif category is not None:
                            category_doc_ids = [
                                row.id
                                for row in db_session.query(models.Document.id)
                                .join(models.Document.categories)
                                .filter(
                                    models.Document.group_id == group_id,
                                    models.Category.name == category,
                                    models.Document.status == "ready",
                                ).all()
                            ]
                            if not category_doc_ids:
                                await websocket.send_text(json.dumps({"event": "error", "message": f"No ready docs in category '{category}'."}))
                                continue
                            hits = milvus_store.search(query_embedding=query_vector, top_k=top_k, document_ids=category_doc_ids)
                        
                        else:
                            try:
                                category_matches = milvus_store.search_categories(query_vector, top_k=5, group_id=group_id)
                            except Exception:
                                category_matches = []
                            
                            if not category_matches or category_matches[0]["score"] < 0.35:
                                hits = milvus_store.search(query_embedding=query_vector, top_k=top_k, document_ids=group_doc_ids)
                            else:
                                try:
                                    chosen_category = await classify_query_category(question, category_matches)
                                except Exception:
                                    chosen_category = category_matches[0]["category_name"]
                                
                                candidate_names = [m["category_name"] for m in category_matches]
                                if chosen_category not in candidate_names:
                                    chosen_category = category_matches[0]["category_name"]

                                scoped_ids = [
                                    row.id
                                    for row in db_session.query(models.Document.id)
                                    .join(models.Document.categories)
                                    .filter(
                                        models.Document.group_id == group_id,
                                        models.Category.name == chosen_category,
                                        models.Document.status == "ready",
                                    ).all()
                                ]
                                hits = milvus_store.search(query_embedding=query_vector, top_k=top_k, document_ids=scoped_ids if scoped_ids else group_doc_ids)

                        if not hits:
                            await websocket.send_text(json.dumps({"event": "error", "message": "Not enough context found."}))
                            continue
                        
                        citations = [
                            {
                                "document_id": hit["document_id"],
                                "chunk_index": hit["chunk_index"],
                                "score": hit["score"],
                                "content_preview": hit["content"][:220],
                            }
                            for hit in hits
                        ]
                        context = "\n\n".join(f"[Source {i + 1}] {hit['content']}" for i, hit in enumerate(hits))

                        # Stream the answer
                        async for chunk_text in generate_answer_stream(question, context):
                            await websocket.send_text(json.dumps({"event": "chunk", "text": chunk_text}))
                        
                        await websocket.send_text(json.dumps({"event": "done", "citations": citations}))
                    
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        await websocket.send_text(json.dumps({"event": "error", "message": str(e)}))
                    finally:
                        db_session.close()
                else:
                    await websocket.send_text(json.dumps({"event": "error", "message": "Unknown message type"}))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"event": "error", "message": "Invalid JSON"}))
    except WebSocketDisconnect:
        await manager.disconnect(user_id, group_id)