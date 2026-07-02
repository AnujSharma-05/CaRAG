"""
test_milvus_data.py — Full Milvus Collection Inspector
--------------------------------------------------------
Purpose : Deep inspection of all Milvus collections.
Checks  : Lists all collections, their row counts (stats),
          and prints up to 5 sample rows from each.
Run     : python test_milvus_data.py
Expect  : document_chunks and categorical_chunks collections
          with their respective row counts and sample data.
"""
from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530"
)

print("Collections:")
print(client.list_collections())

for collection in client.list_collections():

    print("\nCollection:", collection)

    stats = client.get_collection_stats(
        collection_name=collection
    )

    print("Stats:")
    print(stats)

    try:

        rows = client.query(
            collection_name=collection,
            filter="id > 0",
            limit=5
        )

        print("\nSample Rows:")
        print("total entities:", len(rows))

        for row in rows:
            print(row)

    except Exception as e:

        print("Query Error:")
        print(e)