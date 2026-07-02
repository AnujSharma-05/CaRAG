"""
test_migration.py — Milvus Collection Creation Test
-----------------------------------------------------
Purpose : Verifies that a new collection can be created in Milvus.
Checks  : Creates a 'migration_test' collection and lists all collections.
Run     : python test_migration.py
Expect  : 'migration_test' appears in the printed collections list.
Note    : This creates a dummy collection. Clean it up manually in Attu
          (http://localhost:3000) after testing if needed.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.milvus_store import milvus_store

client = milvus_store._get_client()

client.create_collection(
    collection_name="migration_test",
    dimension=384
)

print(client.list_collections())