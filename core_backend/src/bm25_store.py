import re
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
from .database import sessionLocal
from . import models

def tokenize(text: str) -> List[str]:
    """Simple tokenizer: lowercase, strip punctuation, split by whitespace."""
    if not text:
        return []
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return text.split()

class InMemoryBM25Store:
    def __init__(self):
        self.corpus: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25: Optional[BM25Okapi] = None
        self._is_loaded = False
        
    def load_from_db(self):
        """Loads all chunks from 'ready' documents into memory."""
        db = sessionLocal()
        try:
            # Only load chunks for documents that are ready
            ready_doc_ids_query = db.query(models.Document.id).filter(models.Document.status == "ready").subquery()
            
            chunks = db.query(models.DocumentChunk).filter(
                models.DocumentChunk.document_id.in_(ready_doc_ids_query)
            ).all()
            
            self.corpus = []
            self.tokenized_corpus = []
            
            for chunk in chunks:
                item = {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content
                }
                self.corpus.append(item)
                self.tokenized_corpus.append(tokenize(chunk.content))
                
            if self.tokenized_corpus:
                self.bm25 = BM25Okapi(self.tokenized_corpus)
            else:
                self.bm25 = None
                
            self._is_loaded = True
            print(f"[BM25Store] Loaded {len(self.corpus)} chunks into memory.")
        finally:
            db.close()
            
    def ensure_loaded(self):
        if not self._is_loaded:
            self.load_from_db()

    def search(
        self, 
        query: str, 
        top_k: int = 15, 
        document_ids: Optional[List[int]] = None,
        document_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        self.ensure_loaded()
        if not self.bm25 or not self.corpus:
            return []
            
        tokenized_query = tokenize(query)
        # Get scores for the entire corpus
        scores = self.bm25.get_scores(tokenized_query)
        
        # Filter and rank
        results = []
        for idx, score in enumerate(scores):
            if score <= 0:
                continue
                
            chunk = self.corpus[idx]
            
            # Apply filters
            if document_id is not None and chunk["document_id"] != document_id:
                continue
            if document_ids is not None and chunk["document_id"] not in document_ids:
                continue
                
            results.append({
                "document_id": chunk["document_id"],
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "score": float(score),
                "type": "bm25"
            })
            
        # Sort descending by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

# Global singleton
bm25_store = InMemoryBM25Store()
