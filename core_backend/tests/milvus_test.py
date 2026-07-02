"""
milvus_test.py — Milvus Document Chunk Query
----------------------------------------------
Purpose : Directly queries the document_chunks collection in Milvus.
Checks  : Returns up to 5 stored chunk rows with their document_id,
          chunk_index, and content.
Run     : python milvus_test.py
Expect  : Rows printed to console after at least one upload.
"""
from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530"
)


rows = client.query(
    collection_name="document_chunks",
    filter="id > 0",
    output_fields=["document_id", "chunk_index", "content"],
    limit=5
)

for row in rows:
    print(row)
    