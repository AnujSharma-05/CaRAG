import os

from dotenv import load_dotenv

load_dotenv()

MILVUS_URI = os.getenv(
    "MILVUS_URI"
)

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