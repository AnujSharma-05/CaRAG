"""
check_vectors.py — Raw Milvus Vector Existence Check
------------------------------------------------------
Purpose : Minimal check to confirm vectors exist in Milvus.
Checks  : Queries document_chunks and prints first 3 row IDs.
Run     : python check_vectors.py
Expect  : A list of row dicts. Empty list means no documents ingested yet.
"""
from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530"
)

rows = client.query(
    collection_name="document_chunks",
    filter="id > 0",
    limit=3,
)

print(rows)