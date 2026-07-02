# CaRAG: Complete Postman Testing & Startup Guide

This document is your centralized guide for initializing, running, and testing both the **Core Backend (Engine)** and the **Live Adapter API (Multi-tenant)** exclusively using **Postman**.

---

## 1. Preparing the Environment (Startup Steps)

Before opening Postman, both database instances and both backend servers must be running. Follow these simple startup steps:

### Step A: Verify the Databases are Running
1.  **Milvus (Docker Desktop)**: Open **Docker Desktop** on your computer. Start the Milvus Standalone container (ensure port `19530` is open).
2.  **PostgreSQL (Local System)**: Make sure your local Postgres service is running on port `5432`.
    *   *(Optional)* Run `.\verify_services.ps1` in PowerShell to verify that both ports (`19530` and `5432`) are responding.

### Step B: Start the Core Backend (Port 8000)
Open a new PowerShell terminal at the root directory of the project (`CaRAG`), and run:
```powershell
.\start_core_api.bat
```
This runs the Core Engine server on `http://127.0.0.1:8000`.

### Step C: Start the Live Adapter API (Port 8001)
Open another PowerShell terminal at the root directory of the project, and run:
```powershell
.\start_api.bat
```
This reads your credentials from the `.env` file and starts the Live API server on `http://127.0.0.1:8001`.

---

## 2. Postman Workspace Configuration

To run tests smoothly without hardcoding values:
1.  Create a new **Environment** in Postman (e.g., named `CaRAG Local`).
2.  Add the following variables:
    *   `core_url` = `http://localhost:8000`
    *   `live_url` = `http://localhost:8001`
    *   `jwt_token` = (Leave blank initially, populated after login)
3.  Ensure your active Environment is set to `CaRAG Local` in the top-right dropdown of Postman.

---

## 3. PART 1: Core Backend Endpoints (Port 8000)
These endpoints perform raw document chunking, Milvus ingestion, and standalone RAG without group/user scoping.

### 1. `GET /ping`
*   **Description**: Simple status check to verify the Core API is alive.
*   **Postman Setup**:
    *   **Method**: `GET`
    *   **URL**: `{{core_url}}/ping`
    *   **Headers**: None
    *   **Body**: `none`
*   **What to Expect** (200 OK):
    ```json
    {"status": "alive"}
    ```

### 2. `POST /upload`
*   **Description**: Uploads a PDF to the Core Backend, saves it in a flat `uploads/` directory on disk, creates category relationships, and starts the background ingestion task (extraction, chunking, Milvus embedding).
*   **Interacting with Different Attributes**:
    *   **Scenario 1: Upload with Specific Category**: 
        *   Pass `category` as a string (e.g. `engineering`). The document will be placed in that category.
    *   **Scenario 2: Upload without Category**: 
        *   Omit the `category` field or pass `null`. The backend will default it to `general`. This triggers the Core Engine's auto-categorization model (Gemini analysis) which dynamically assigns a category from the text content later.
    *   **Scenario 3: Comma-Separated Categories**:
        *   Pass `category` as `"engineering, jio"`. The database handles splitting and assigns the document to this category name.
*   **Postman Setup**:
    *   **Method**: `POST`
    *   **URL**: `{{core_url}}/upload`
    *   **Body**: `form-data`
        *   `file`: (Change type to `File`, upload any PDF)
        *   `category`: `engineering` (Text, Optional)
*   **What to Expect** (200 OK):
    ```json
    {
      "id": 1,
      "filename": "guide.pdf",
      "status": "uploaded",
      "file_size": 245902,
      "category": "engineering"
    }
    ```
*   **Error Scenarios**:
    *   **400 Bad Request**: Uploading a non-PDF file.
        ```json
        {"detail": "Invalid file type. Only PDF files are allowed."}
        ```

### 3. `GET /documents`
*   **Description**: Lists all documents currently stored in the SQLite database of the Core engine.
*   **Interacting with Different Attributes**:
    *   Observe how the `"status"` field updates from `"uploaded"` to `"processing"` and finally `"ready"` as the background ingestion executes.
*   **Postman Setup**:
    *   **Method**: `GET`
    *   **URL**: `{{core_url}}/documents`
*   **What to Expect** (200 OK):
    ```json
    [
      {
        "id": 1,
        "filename": "guide.pdf",
        "status": "ready",
        "file_size": 245902,
        "category": "engineering"
      }
    ]
    ```

### 4. `GET /documents/{document_id}`
*   **Description**: Fetches metadata for a single specific document by ID.
*   **Interacting with Different Attributes**:
    *   Change the ID in the path to verify details. Useful for tracking a single document's status.
*   **Postman Setup**:
    *   **Method**: `GET`
    *   **URL**: `{{core_url}}/documents/1`
*   **What to Expect** (200 OK): Document metadata.
*   **Error Scenarios**:
    *   **404 Not Found**: If the document ID does not exist in the database.
        ```json
        {"detail": "Document not found"}
        ```

### 5. `PATCH /documents/{document_id}`
*   **Description**: Manually updates a document's status (mainly for debugging status states).
*   **Interacting with Different Attributes**:
    *   **Scenario 1: Set Status to ready**:
        ```json
        { "status": "ready" }
        ```
    *   **Scenario 2: Set Status to failed**: (Simulating an ingestion failure)
        ```json
        { "status": "failed" }
        ```
*   **Postman Setup**:
    *   **Method**: `PATCH`
    *   **URL**: `{{core_url}}/documents/1`
    *   **Body**: `raw (JSON)`
*   **What to Expect** (200 OK): Returns the updated document object.

### 6. `DELETE /documents/{document_id}`
*   **Description**: Removes the document from SQLite, cleans up the local file on disk, and deletes all associated chunks and categorical summaries from the Milvus database.
*   **Postman Setup**:
    *   **Method**: `DELETE`
    *   **URL**: `{{core_url}}/documents/1`
*   **What to Expect** (200 OK):
    ```json
    {
      "message": "Document deleted",
      "id": 1
    }
    ```

### 7. `POST /chat`
*   **Description**: Standalone RAG QA endpoint. It embeds the query, searches Milvus, collects context chunks, and calls Gemini to generate an answer.
*   **Interacting with Different Attributes**:
    *   **Scenario 1: Global Search (Mode C Fallback)**:
        *   Pass `document_id: null` and `category: null`. The RAG model will search the entire vector space.
    *   **Scenario 2: Category Pinned Search (Mode B)**:
        *   Pass `category: "engineering"` and `document_id: null`. The system narrows search results to documents associated with `"engineering"`.
    *   **Scenario 3: Document Pinned Search (Mode A)**:
        *   Pass `document_id: 1` and `category: null`. It restricts semantic matches to document ID 1.
    *   **Scenario 4: Controlling Context Volume**:
        *   Pass `top_k: 3` (retrieves fewer matching chunks for speed) or `top_k: 10` (maximizes context breadth).
*   **Postman Setup**:
    *   **Method**: `POST`
    *   **URL**: `{{core_url}}/chat`
    *   **Body**: `raw (JSON)`
        ```json
        {
          "question": "What is the combustion pressure?",
          "document_id": null,
          "category": "engineering",
          "top_k": 5
        }
        ```
*   **What to Expect** (200 OK):
    ```json
    {
      "answer": "The nominal combustion chamber pressure is 3,500 PSI.",
      "citations": [
        {
          "document_id": 1,
          "chunk_index": 4,
          "score": 0.89,
          "content_preview": "..."
        }
      ]
    }
    ```
*   **Fallbacks**:
    *   **Gemini Mock Fallback**: If Gemini is rate-limited (429), it returns the top matches directly under a mock warning banner instead of failing.

### 8. `DELETE /documents` (System Reset)
*   **Description**: Wipes all files from the upload folder, deletes all DB rows, and drops the entire Milvus collection. Re-initializes the schema.
*   **Postman Setup**:
    *   **Method**: `DELETE`
    *   **URL**: `{{core_url}}/documents`
*   **What to Expect** (200 OK): Returns counts of deleted items.

### 9. `GET /debug/db`
*   **Description**: Fast debugging metrics showing current document and chunk counts.
*   **Postman Setup**:
    *   **Method**: `GET`
    *   **URL**: `{{core_url}}/debug/db`
*   **What to Expect** (200 OK): Document/chunk count dictionary.

### 10. `POST /clean-system`
*   **Description**: Force cleans system memory. Runs garbage collection and kills zombie Python processes.
*   **Postman Setup**:
    *   **Method**: `POST`
    *   **URL**: `{{core_url}}/clean-system`
*   **What to Expect** (200 OK): Returns `zombies_killed` count.

---

## 4. PART 2: Live Adapter API Endpoints (Port 8001)
Enforces multi-tenant JWT security, group routing, and handles real-time WebSocket communication.

### 11. `POST /auth/register`
*   **Description**: Registers a new user. Hashes the password using bcrypt.
*   **Postman Setup**:
    *   **Method**: `POST`
    *   **URL**: `{{live_url}}/auth/register`
    *   **Body**: `raw (JSON)`
        ```json
        {
          "email": "dev@carag.com",
          "password": "mypassword123"
        }
        ```
*   **What to Expect** (200 OK):
    ```json
    {
      "message": "User created successfully",
      "user_id": 1
    }
    ```

### 12. `POST /auth/login`
*   **Description**: Validates user credentials and issues a JWT token.
*   **Postman Setup**:
    *   **Method**: `POST`
    *   **URL**: `{{live_url}}/auth/login`
    *   **Body**: `x-www-form-urlencoded`
        *   `username`: `dev@carag.com`
        *   `password`: `mypassword123`
*   **What to Expect** (200 OK):
    ```json
    {
      "access_token": "eyJhbGciOiJIUzI1Ni...",
      "token_type": "bearer"
    }
    ```
    *Copy the value of `access_token` and save it directly to your Postman Environment variable `jwt_token`.*

### 13. `POST /groups`
*   **Description**: Creates a new group and adds the creator as the first member.
*   **Interacting with Different Attributes**:
    *   Create groups with different names. Verify that each group creates a unique entry in the `group_members` table linking back to the creator.
*   **Postman Setup**:
    *   **Method**: `POST`
    *   **URL**: `{{live_url}}/groups/`
    *   **Headers**: 
        *   `Authorization`: `Bearer {{jwt_token}}`
    *   **Body**: `raw (JSON)`
        ```json
        {
          "name": "Engineering Team"
        }
        ```
*   **What to Expect** (200 OK): Group details.

### 14. `GET /groups`
*   **Description**: Lists all groups that the authenticated user belongs to.
*   **Postman Setup**:
    *   **Method**: `GET`
    *   **URL**: `{{live_url}}/groups/`
    *   **Headers**:
        *   `Authorization`: `Bearer {{jwt_token}}`

### 15. `GET /groups/{group_id}`
*   **Description**: Retrieves detail about a specific group, listing all membership emails.
*   **Postman Setup**:
    *   **Method**: `GET`
    *   **URL**: `{{live_url}}/groups/1`
    *   **Headers**:
        *   `Authorization`: `Bearer {{jwt_token}}`
*   **Error Scenarios**:
    *   **403 Forbidden**: If the user is not a member of this group.

### 16. `POST /groups/{group_id}/invite`
*   **Description**: Invites another registered user to the group by their email address.
*   **Interacting with Different Attributes**:
    *   Try inviting a registered user's email.
    *   Try inviting an unregistered email to verify `404 Not Found`.
    *   Try inviting yourself to verify `400 Bad Request`.
*   **Postman Setup**:
    *   **Method**: `POST`
    *   **URL**: `{{live_url}}/groups/1/invite`
    *   **Headers**:
        *   `Authorization`: `Bearer {{jwt_token}}`
    *   **Body**: `raw (JSON)`
        ```json
        {
          "email": "colleague@carag.com"
        }
        ```

### 17. `DELETE /groups/{group_id}`
*   **Description**: Wipes all files from disk for this group, deletes all Milvus vector indices scoped to this group's documents, and drops the Postgres database tables cascading to memberships.
*   **Postman Setup**:
    *   **Method**: `DELETE`
    *   **URL**: `{{live_url}}/groups/1`
    *   **Headers**:
        *   `Authorization`: `Bearer {{jwt_token}}`

### 18. `POST /groups/{group_id}/documents`
*   **Description**: Uploads a PDF file into the group's storage directory (`uploads/group_{group_id}/`) and triggers background ingestion. Enforces group isolation.
*   **Interacting with Different Attributes**:
    *   **Scenario 1: Upload with category metadata**: Pass `category` as `"policies"`.
    *   **Scenario 2: Upload without category metadata**: Omit `category`. It starts with `general` and automatically updates based on LLM classification.
*   **Postman Setup**:
    *   **Method**: `POST`
    *   **URL**: `{{live_url}}/groups/1/documents`
    *   **Headers**:
        *   `Authorization`: `Bearer {{jwt_token}}`
    *   **Body**: `form-data`
        *   `file`: (Change type to `File`, upload any PDF)
        *   `category`: `policies` (Text, Optional)
*   **What to Expect** (200 OK):
    ```json
    {
      "id": 1,
      "filename": "security_policy.pdf",
      "file_path": "uploads\\group_1\\security_policy.pdf",
      "file_size": 245902,
      "status": "uploaded",
      "group_id": 1,
      "categories": ["policies"]
    }
    ```

### 19. `GET /groups/{group_id}/documents`
*   **Description**: Returns list of all documents belonging to this group.
*   **Postman Setup**:
    *   **Method**: `GET`
    *   **URL**: `{{live_url}}/groups/1/documents`
    *   **Headers**:
        *   `Authorization`: `Bearer {{jwt_token}}`

### 20. `DELETE /groups/{group_id}/documents/{doc_id}`
*   **Description**: Removes the document from Postgres, clears disk assets, removes Milvus chunks, and recalculates categorical taxonomy summaries.
*   **Postman Setup**:
    *   **Method**: `DELETE`
    *   **URL**: `{{live_url}}/groups/1/documents/1`
    *   **Headers**:
        *   `Authorization`: `Bearer {{jwt_token}}`

### 21. `GET /groups/{group_id}/categories`
*   **Description**: Lists all distinct, populated categories inside a group. Filters out the fallback `"general"` category.
*   **Postman Setup**:
    *   **Method**: `GET`
    *   **URL**: `{{live_url}}/groups/1/categories`
    *   **Headers**:
        *   `Authorization`: `Bearer {{jwt_token}}`

### 22. `POST /groups/{group_id}/chat`
*   **Description**: Group-scoped RAG QA (REST/JSON response). Restricts searching strictly to the document IDs belonging to `group_id`.
*   **Interacting with Different Attributes**:
    *   **Scenario 1: Mode C (Default automatic routing)**: Leave `document_id` and `category` as `null`. The backend automatically classifies which category to query.
    *   **Scenario 2: Mode B (Category Override)**: Set `category` to `"policies"`. The backend ignores all other documents and queries only category-associated docs.
    *   **Scenario 3: Mode A (Document Override)**: Set `document_id` to `1`. Restricts context retrieval to doc 1.
    *   **Scenario 4: Context Depth tuning**: Pass `top_k: 3` to limit query boundaries.
*   **Postman Setup**:
    *   **Method**: `POST`
    *   **URL**: `{{live_url}}/groups/1/chat`
    *   **Headers**:
        *   `Authorization`: `Bearer {{jwt_token}}`
    *   **Body**: `raw (JSON)`
        ```json
        {
          "question": "What is the password policy?",
          "document_id": null,
          "category": "policies",
          "top_k": 5
        }
        ```

### 23. `WS /ws` (Real-Time Ingestion & Streaming Chat)
*   **Description**: Handles long-lived WebSocket tunnels. Supports real-time status updates and tokens.
*   **Interacting with Different Attributes**:
    *   **Scenario 1: Requesting Streaming Chat**:
        Send JSON payload:
        ```json
        {
          "type": "chat",
          "question": "Give me summary.",
          "top_k": 3
        }
        ```
    *   **Scenario 2: Streaming Chat Pinned to a specific Document**:
        Send JSON payload:
        ```json
        {
          "type": "chat",
          "question": "Explain chapter 2",
          "document_id": 1
        }
        ```
    *   **Scenario 3: Streaming Chat Pinned to a specific Category**:
        Send JSON payload:
        ```json
        {
          "type": "chat",
          "question": "What are engineering policies?",
          "category": "policies"
        }
        ```
    *   **Scenario 4: Ping / Pong check**:
        Send payload:
        ```json
        { "type": "ping" }
        ```
        Expect:
        ```json
        { "event": "pong" }
        ```
*   **Postman Setup**:
    1. In Postman, click **New** -> **WebSocket**.
    2. Enter the URL: `ws://localhost:8001/ws/`
    3. Go to the **Params** tab and add:
       *   `token` = `{{jwt_token}}`
       *   `group_id` = `1`
    4. Click **Connect**.
*   **Disconnect Codes**:
    *   `4001`: Auth credentials (JWT signature or expiry) failed.
    *   `4003`: User is authenticated, but is not a member of the requested `group_id`.
