# 💻 Start-up Guide: JPL Task 0 — Rapid Foundation

Welcome to the Rapid Foundation Document RAG API! This project is a robust FastAPI-based application designed to upload PDF documents, extract and chunk text, generate vector embeddings, and answer queries about your documents using a Retrieval-Augmented Generation (RAG) architecture powered by Google's Gemini API.

---

## 🛠️ Tech Stack & Architecture

- **Web Framework:** FastAPI / Uvicorn
- **Relational Database:** PostgreSQL (via SQLAlchemy & Psycopg2)
- **Vector Database:** Milvus (via pymilvus)
- **Embeddings:** Sentence-Transformers (`all-MiniLM-L6-v2`)
- **LLM / Generation:** Google Gemini (`gemini-2.5-flash` via `google-generativeai`)
- **Document Processing:** `pypdf` for text extraction, `langchain-text-splitters` for chunking

---

## 📋 Prerequisites

Before setting up the project, ensure you have the following installed and running:

1. **Python 3.10+**
2. **PostgreSQL:** Running locally or remotely. Create a database for this project (e.g., `JPL_task0_RapidFoundation`).
3. **Milvus:** A running instance of Milvus (Standalone, Docker, or Lite). Usually available at `http://localhost:19530`.
4. **Gemini API Key:** Obtainable from Google AI Studio.

---

## 🚀 Environment Setup

### 1. Clone the Repository
Navigate to your desired directory and clone the project repository.
```bash
cd /path/to/your/workspace
```

### 2. Create and Activate a Virtual Environment
It is highly recommended to isolate your dependencies using a virtual environment.

**Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

**Mac/Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
Install the required packages listed in `requirements.txt`. Note: A few essential libraries used by the services need to be explicitly installed as well.

```bash
pip install -r requirements.txt
pip install langchain-text-splitters google-generativeai
```
*(You may want to add `langchain-text-splitters` and `google-generativeai` to your `requirements.txt` for future deployments).*

---

## ⚙️ Configuration

Create a `.env` file in the root directory (where `requirements.txt` is located) and configure your environment variables:

```env
# Database connection string
DATABASE_URL=postgresql+psycopg2://<username>:<password>@localhost:5432/<dbname>

# Gemini API Authentication
GEMINI_API_KEY=your_gemini_api_key_here

# Milvus Vector Store configuration
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
MILVUS_COLLECTION=document_chunks

# Embedding Model configuration
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384
CHUNK_SIZE=800
CHUNK_OVERLAP=120
```
*Note: Replace `<username>`, `<password>`, and `<dbname>` with your actual PostgreSQL credentials.*

---

## 🏃‍♂️ Running the Server

The application is built with FastAPI. The database tables are automatically initialized via SQLAlchemy upon startup.

Start the development server using Uvicorn:

```bash
uvicorn src.main:app --reload
```

- The API server will be live at: **http://127.0.0.1:8000**
- Interactive API Documentation (Swagger UI) is available at: **http://127.0.0.1:8000/docs**

---

## 📖 API Workflow Overview

1. **Upload Document (`POST /upload`):**
   Upload a PDF file. The file is saved locally in the `uploads/` directory, and its metadata is stored in PostgreSQL. A background task is triggered.
2. **Background Processing:**
   The `process_document_task` reads the PDF, chunks the text into pieces (800 chars), generates vector embeddings using Sentence Transformers, and stores the vectors into Milvus.
3. **Chat (`POST /chat`):**
   Submit a query. The API converts your question into an embedding, performs a vector similarity search in Milvus to retrieve the most relevant text chunks, and sends them to the Gemini API to construct a precise, cited answer.

---

## 🧪 Testing Utilities

The project root contains several helpful scripts to debug and verify your state:

- `check_state.py`: Quick check to count documents and chunks in both PostgreSQL and Milvus.
- `test_milvus_data.py`: Validates your Milvus connection, lists collections, and shows vector statistics.
- `gemini_testing.py`: A simple standalone test to verify your Gemini API key and completion functionality.

To run any of these, simply execute them from your virtual environment:
```bash
python check_state.py
```
