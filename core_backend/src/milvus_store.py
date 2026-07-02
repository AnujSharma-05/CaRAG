import os
import time
from typing import Any

from .config import (
    MILVUS_COLLECTION,
    EMBEDDING_DIM,
    MILVUS_URI,
)

from pymilvus import MilvusClient, DataType

print("milvus_store import started")

class MilvusStore:
    """Small Milvus wrapper to keep vector DB operations isolated."""

    def __init__(self) -> None:
        self.collection_name = MILVUS_COLLECTION
        self.category_collection_name = "categorical_chunks"
        self.dim = EMBEDDING_DIM
        self._client: MilvusClient | None = None

    def _get_client(self) -> MilvusClient:

        if self._client is not None:
            return self._client

        uri = os.getenv("MILVUS_URI")

        if not uri:
            raise RuntimeError(
                "MILVUS_URI is not configured"
            )

        print(
            f"CONNECTED TO MILVUS SERVER: {uri}"
        )

        token = os.getenv("MILVUS_TOKEN")

        self._client = MilvusClient(
            uri=uri,
            token=token,
        )

        return self._client

    def _create_collection(self, client: MilvusClient, collection_name: str) -> None:
        schema = client.create_schema(
            auto_id=False,
            enable_dynamic_field=True
        )
        
        # Primary Key
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        # Vector Field
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=self.dim)
        
        if collection_name == self.collection_name:
            # Custom Scalar Fields for document chunks
            schema.add_field(field_name="document_id", datatype=DataType.INT64)
            schema.add_field(field_name="chunk_index", datatype=DataType.INT64)
            schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
        else:
            # Custom Scalar Fields for categorical summaries
            schema.add_field(field_name="category_name", datatype=DataType.VARCHAR, max_length=255)
            schema.add_field(field_name="summary", datatype=DataType.VARCHAR, max_length=65535)
            schema.add_field(field_name="group_id", datatype=DataType.INT64, nullable=True)
        
        client.create_collection(
            collection_name=collection_name,
            schema=schema
        )
        
        # Prepare vector index
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="AUTOINDEX",
            metric_type="COSINE"
        )
        client.create_index(
            collection_name=collection_name,
            index_params=index_params
        )
        print(f"CREATED COLLECTION & INDEX: {collection_name}")

    def ensure_collection(self) -> None: 
        client = self._get_client()

        # Document chunks
        if not client.has_collection(collection_name=self.collection_name):
            self._create_collection(client, self.collection_name)
        client.load_collection(collection_name=self.collection_name)

        # Categorical chunks
        if not client.has_collection(collection_name=self.category_collection_name):
            self._create_collection(client, self.category_collection_name)
        client.load_collection(collection_name=self.category_collection_name)
        print(f"ALL COLLECTIONS ENSURED & LOADED")

    def upsert_chunks(self, document_id: int, chunks: list[str], embeddings: list[list[float]]) -> list[int]:
        self.ensure_collection()
        client = self._get_client()

        base_id = time.time_ns()
        data = [
            {
                "id": int(base_id + idx),
                "vector": embeddings[idx],
                "document_id": document_id,
                "chunk_index": idx,
                "content": chunks[idx],
            }
            for idx in range(len(chunks))
        ]
        print(
                f"INSERTING {len(chunks)} CHUNKS"
            )
        result = client.insert(collection_name=self.collection_name, data=data)
        client.load_collection(
            collection_name=self.collection_name
        )
        print(result)

        # Flush pushes the in-memory growing segment to sealed segments.
        # Without this, Attu's Data Explorer shows 'No data found' because
        # it only reads sealed (persisted) segments, not the write buffer.
        # Python client.query() reads both, which is why queries worked but
        # Attu showed nothing.
        client.flush(collection_name=self.collection_name)
        print(f"FLUSHED {len(chunks)} CHUNKS TO MILVUS")

        return [int(i) for i in result.get("ids", [])]

    def search(self, query_embedding: list[float], top_k: int = 5, document_id: int | None = None, document_ids: list[int] | None = None) -> list[dict[str, Any]]:
        self.ensure_collection()  # also loads the collection
        client = self._get_client()
        search_kwargs: dict[str, Any] = {
            "collection_name": self.collection_name,
            "data": [query_embedding],
            "limit": top_k,
            "output_fields": ["document_id", "chunk_index", "content"],
        }
        if document_id is not None:
            search_kwargs["filter"] = f"document_id == {document_id}"
        elif document_ids is not None:
            if document_ids:
                ids_str = ", ".join(str(i) for i in document_ids)
                search_kwargs["filter"] = f"document_id in [{ids_str}]"
            else:
                return []

        results = client.search(**search_kwargs)

        formatted: list[dict[str, Any]] = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            formatted.append(
                {
                    "milvus_id": int(hit.get("id")),
                    "score": float(hit.get("distance", 0.0)),
                    "document_id": int(entity.get("document_id")),
                    "chunk_index": int(entity.get("chunk_index")),
                    "content": str(entity.get("content")),
                }
            )
        return formatted

    def delete_document_chunks(self, document_id: int) -> None:
        self.ensure_collection()
        client = self._get_client()
        client.delete(collection_name=self.collection_name, filter=f"document_id == {document_id}")

    def delete_category_summary(self, category_name: str, group_id: int | None = None) -> None:
        self.ensure_collection()
        client = self._get_client()
        filter_str = f"category_name == '{category_name}'"
        if group_id is not None:
            filter_str += f" and group_id == {group_id}"
        client.delete(
            collection_name=self.category_collection_name,
            filter=filter_str
        )
        print(f"DELETED SUMMARY FOR CATEGORY: {category_name} (Group: {group_id})")

    def upsert_category_summary(self, category_name: str, summary: str, embedding: list[float], group_id: int | None = None) -> None:
        self.ensure_collection()
        client = self._get_client()

        # Clean existing summaries for this category and group
        filter_str = f"category_name == '{category_name}'"
        if group_id is not None:
            filter_str += f" and group_id == {group_id}"
        
        client.delete(
            collection_name=self.category_collection_name,
            filter=filter_str
        )

        base_id = time.time_ns()
        data = [
            {
                "id": int(base_id),
                "vector": embedding,
                "category_name": category_name,
                "summary": summary,
                "group_id": group_id if group_id is not None else 0
            }
        ]
        client.insert(collection_name=self.category_collection_name, data=data)
        client.flush(collection_name=self.category_collection_name)
        print(f"UPSERTED SUMMARY FOR CATEGORY: {category_name} (Group: {group_id})")

    def search_categories(self, query_embedding: list[float], top_k: int = 5, group_id: int | None = None) -> list[dict[str, Any]]:
        self.ensure_collection()
        client = self._get_client()
        search_kwargs: dict[str, Any] = {
            "collection_name": self.category_collection_name,
            "data": [query_embedding],
            "limit": top_k,
            "output_fields": ["category_name", "summary", "group_id"],
        }
        
        if group_id is not None:
            search_kwargs["filter"] = f"group_id == {group_id}"
            
        results = client.search(**search_kwargs)

        formatted: list[dict[str, Any]] = []
        if results and results[0]:
            for hit in results[0]:
                entity = hit.get("entity", {})
                formatted.append(
                    {
                        "category_name": str(entity.get("category_name")),
                        "summary": str(entity.get("summary")),
                        "group_id": int(entity.get("group_id")) if entity.get("group_id") is not None else None,
                        "score": float(hit.get("distance", 0.0))
                    }
                )
        return formatted

    # def delete_all_chunks(self) -> None:
    #     client = self._get_client()

    #     if client.has_collection(
    #         collection_name=self.collection_name
    #     ):
    #         client.drop_collection(
    #             collection_name=self.collection_name
    #         )

    #     client.create_collection(
    #         collection_name=self.collection_name,
    #         dimension=self.dim,
    #     )

    def delete_all_chunks(self) -> None:
        client = self._get_client()
        for col in [self.collection_name, self.category_collection_name]:
            if client.has_collection(collection_name=col):
                client.drop_collection(collection_name=col)
            self._create_collection(client, col)
        print("ALL MILVUS DATA WIPED")

print("creating milvus_store singleton")

milvus_store = MilvusStore()

print("milvus_store singleton created")

