import os

from dotenv import load_dotenv

load_dotenv()

# === Milvus Storage Configuration ===
MILVUS_URI = os.getenv("MILVUS_URI", "./carag_milvus.db")
MILVUS_COLLECTION_NAME = os.getenv("MILVUS_COLLECTION_NAME", "carag_document_chunks")
MILVUS_CATEGORIES_COLLECTION_NAME = os.getenv("MILVUS_CATEGORIES_COLLECTION_NAME", "carag_categories")

# HNSW Vector Index Parameters (for production scale)
MILVUS_INDEX_TYPE = os.getenv("MILVUS_INDEX_TYPE", "HNSW")
MILVUS_M = int(os.getenv("MILVUS_M", "16"))
MILVUS_EF_CONSTRUCTION = int(os.getenv("MILVUS_EF_CONSTRUCTION", "64"))
MILVUS_EF_SEARCH = int(os.getenv("MILVUS_EF_SEARCH", "64"))

# === Retrieval Optimization ===
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
# Defaulting to -999.0 (disabled) until score distributions are analyzed in production
CROSS_ENCODER_THRESHOLD = float(os.getenv("CROSS_ENCODER_THRESHOLD", "-999.0"))
LOG_RETRIEVAL_SCORES = os.getenv("LOG_RETRIEVAL_SCORES", "True").lower() == "true"

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

DATABASE_URL = os.getenv("DATABASE_URL")

MILVUS_COLLECTION = os.getenv(
    "MILVUS_COLLECTION",
    "document_chunks"
)
    
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)

EMBEDDING_DIM = int(
    os.getenv(
        "EMBEDDING_DIM",
        "384"
    )
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)


CHUNK_SIZE = int(
    os.getenv(
        "CHUNK_SIZE",
        "800"
    )
)

CHUNK_OVERLAP = int(
    os.getenv(
        "CHUNK_OVERLAP",
        "120"
    )
)