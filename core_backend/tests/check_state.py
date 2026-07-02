"""
check_state.py — System Health Check
-------------------------------------
Purpose : Quick snapshot of the entire system state.
Checks  : (1) PostgreSQL document + chunk counts
          (2) Milvus document_chunks collection row count
Run     : python check_state.py
Expect  : Non-zero counts after uploading at least one document.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import sessionLocal
from src.models import Document, DocumentChunk
from src.milvus_store import milvus_store

db = sessionLocal()

print("Documents:", db.query(Document).count())
print("Chunks:", db.query(DocumentChunk).count())

client = milvus_store._get_client()

print(
    "Milvus:",
    client.get_collection_stats(
        collection_name="document_chunks"
    )
)