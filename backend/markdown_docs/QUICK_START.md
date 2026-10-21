# AskTemoc Backend - Quick Start Guide

## File Structure

```
app/
├── db/                           # Database layer
│   ├── __init__.py              # Module exports
│   ├── models.py                # SQLAlchemy ORM models (Document, Chunk, Embedding)
│   ├── database.py              # Database connection & session management
│   └── services.py              # CRUD service classes
│
├── services/                    # Business logic services
│   ├── chroma_service.py      # ChromaDB export & sync operations
│   ├── document_management.py   # High-level document utilities & dashboard helpers
│   ├── rag_service.py           # (existing) RAG operations
│   └── ...other services
│
├── api/endpoints/               # FastAPI route handlers
│   ├── documents.py             # Document/Chunk/Embedding CRUD endpoints
│   ├── chroma.py              # ChromaDB sync/export endpoints
│   ├── dashboard.py             # Analytics & dashboard endpoints
│   ├── query.py                 # (existing) Query endpoints
│   └── __init__.py
│
├── models/                      # Pydantic schemas (requests/responses)
│   ├── requests.py
│   ├── response.py
│   └── responses.py
│
├── schemas/
│   ├── db_schemas.py            # NEW: All DB-related Pydantic schemas
│   └── __init__.py
│
└── main.py                      # FastAPI app initialization with all routers

config/
├── .env.example                 # Environment configuration template
└── asktemoc.db                  # SQLite database (auto-created)
```

## Key Components

### 1. Database Models (`app/db/models.py`)
- **Document**: Stores document metadata (title, source, custom metadata)
- **Chunk**: Text fragments extracted from documents with sequence ordering
- **Embedding**: Vector embeddings with ChromaDB sync tracking

### 2. Service Layer (`app/db/services.py`)
- `DocumentService`: Create, read, update, delete documents
- `ChunkService`: Manage document chunks
- `EmbeddingService`: Handle embeddings and sync status

### 3. API Endpoints

#### Document Management (`/api/documents`)
```
POST   /documents              - Create document
GET    /documents              - List documents
GET    /documents/{id}         - Get document details
PUT    /documents/{id}         - Update document
DELETE /documents/{id}         - Delete document
POST   /documents/search       - Search documents
```

#### Chunks (`/api/documents/{id}/chunks`)
```
POST   /documents/{id}/chunks          - Create chunk
POST   /documents/{id}/chunks/batch    - Batch create chunks
GET    /documents/{id}/chunks          - List document chunks
PUT    /chunks/{id}                    - Update chunk
DELETE /chunks/{id}                    - Delete chunk
```

#### Embeddings (`/api/documents/chunks/{id}/embeddings`)
```
POST   /chunks/{id}/embeddings   - Create embedding
GET    /embeddings/{id}          - Get embedding
PUT    /embeddings/{id}          - Update embedding
DELETE /embeddings/{id}          - Delete embedding
```

#### ChromaDB Export (`/api/chroma`)
```
POST   /export/document/{id}     - Export document embeddings
POST   /export/unsynced          - Export unsynced embeddings
POST   /export/batch             - Export specific embeddings
DELETE /vectors                  - Delete from ChromaDB
GET    /index/stats              - Get index statistics
GET    /search                   - Search ChromaDB
```

#### Dashboard (`/api/dashboard`)
```
GET    /overview                    - Dashboard overview
GET    /document/{id}/stats         - Document statistics
GET    /document/{id}/export        - Export as JSON
POST   /document/{id}/duplicate     - Duplicate document
POST   /documents/batch-delete      - Batch delete
GET    /search                      - Global content search
GET    /activity                    - Recent activity
GET    /sync-status                 - Sync statistics
```

## Quick Start

### Requirements

- Python 3.13+
- [`ollama`](https://ollama.com/) installed and running (for future integration, currently mocked)
- `pip` (Python package installer)
- Git

---

### Clone the Repository

```bash
git clone https://github.com/Conwenu/AskTemoc_Backend.git
cd path/to/project-root
```

---

### Install Dependencies

Make sure you're in a **virtual environment**:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install required packages:

```bash
pip install -r requirements.txt
```

---

### Make Sure Ollama is Installed

Ensure [`ollama`](https://ollama.com/) is installed and running locally.

```bash
ollama run llama3  # Or any other model you plan to use
```

---

### Run the FastAPI Server

You can start the server using:

```bash
uvicorn app.main:app --reload
```

- Visit Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)


### Example: Create Document with Chunks

```bash
# 1. Create document
DOCUMENT_ID=$(curl -X POST http://localhost:8000/api/documents \
  -H "Content-Type: application/json" \
  -d '{"title":"My Document","source":"https://example.com"}' | jq -r '.id')

# 2. Create chunks
curl -X POST http://localhost:8000/api/documents/$DOCUMENT_ID/chunks/batch \
  -H "Content-Type: application/json" \
  -d '{
    "chunks": [
      {"chunk_index":0,"text":"First chunk content..."},
      {"chunk_index":1,"text":"Second chunk content..."}
    ]
  }'

# 3. View dashboard
curl http://localhost:8000/api/dashboard/overview
```

## Database Schema

### Documents Table
```sql
CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  source VARCHAR(512),
  metadata JSON,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  is_deleted BOOLEAN DEFAULT 0
);
```

### Chunks Table
```sql
CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  metadata JSON,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  is_deleted BOOLEAN DEFAULT 0
);
CREATE INDEX idx_document_chunk_index ON chunks(document_id, chunk_index);
```

### Embeddings Table
```sql
CREATE TABLE embeddings (
  id TEXT PRIMARY KEY,
  chunk_id TEXT NOT NULL REFERENCES chunks(id),
  vector JSON,
  model VARCHAR(100),
  chroma_id VARCHAR(255),
  is_synced BOOLEAN DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_synced_at DATETIME
);
CREATE INDEX idx_chroma_id ON embeddings(chroma_id);
CREATE INDEX idx_is_synced ON embeddings(is_synced);
```

## Service Classes

### DocumentService
```python
DocumentService.create_document(db, title, source, metadata)
DocumentService.get_document(db, doc_id)
DocumentService.list_documents(db, skip, limit, include_deleted)
DocumentService.update_document(db, doc_id, title, source, metadata)
DocumentService.delete_document(db, doc_id, hard_delete)
DocumentService.search_documents(db, query_str)
```

### ChunkService
```python
ChunkService.create_chunk(db, document_id, chunk_index, text, metadata)
ChunkService.get_chunk(db, chunk_id)
ChunkService.list_chunks_by_document(db, document_id, skip, limit)
ChunkService.update_chunk(db, chunk_id, text, metadata)
ChunkService.delete_chunk(db, chunk_id, hard_delete)
ChunkService.get_chunks_by_ids(db, chunk_ids)
```

### EmbeddingService
```python
EmbeddingService.create_embedding(db, chunk_id, vector, model)
EmbeddingService.get_embedding(db, embedding_id)
EmbeddingService.list_unsynced_embeddings(db, limit)
EmbeddingService.mark_synced(db, embedding_id, chroma_id)
EmbeddingService.update_embedding(db, embedding_id, vector, chroma_id, is_synced)
EmbeddingService.delete_embedding(db, embedding_id)
EmbeddingService.get_embeddings_by_document(db, document_id)
```

### ChromaService
```python
chroma_svc = ChromaService()
chroma_svc.upsert_vectors(db, embeddings)  # Send to ChromaDB
chroma_svc.export_document_embeddings(db, document_id)
chroma_svc.export_unsynced_embeddings(db, batch_size)
chroma_svc.delete_from_chroma(vector_ids)
chroma_svc.search_chroma(query_vector, top_k)
```

### DocumentManagementUtils
```python
DocumentManagementUtils.get_document_statistics(db, doc_id)
DocumentManagementUtils.get_all_documents_dashboard(db)
DocumentManagementUtils.batch_delete_documents(db, doc_ids, hard_delete)
DocumentManagementUtils.duplicate_document_with_chunks(db, source_doc_id, new_title)
DocumentManagementUtils.export_document_to_json(db, doc_id)
DocumentManagementUtils.search_content_across_documents(db, search_query, limit)
DocumentManagementUtils.get_sync_status_summary(db)
DocumentManagementUtils.get_recent_activity(db, days, limit)
```

## Common Workflows

### Workflow 1: Ingest Document with Embeddings
```python
# 1. Create document
doc = DocumentService.create_document(db, title, source)

# 2. Create chunks (batch)
for i, text in enumerate(chunks_text):
    chunk = ChunkService.create_chunk(db, doc.id, i, text)

# 3. Generate and create embeddings
chunks = ChunkService.list_chunks_by_document(db, doc.id)
for chunk in chunks:
    vector = embedding_model.encode(chunk.text)
    embedding = EmbeddingService.create_embedding(db, chunk.id, vector)

# 4. Export to ChromaDB
chroma_svc = ChromaService()
result = chroma_svc.export_document_embeddings(db, doc.id)
```

### Workflow 2: Query with RAG
```python
# 1. Search ChromaDB with query embedding
query_vector = embedding_model.encode(user_query)
chroma_svc = ChromaService()
results = chroma_svc.search_chroma(query_vector, top_k=5)

# 2. Retrieve full chunk data from database
for match in results['matches']:
    chroma_id = match['id']
    embedding = db.query(Embedding).filter(Embedding.chroma_id == chroma_id).first()
    chunk = EmbeddingService.get_embedding(db, embedding.id).chunk
    # Use chunk.text in LLM context
```

### Workflow 3: Dashboard Overview
```python
overview = DocumentManagementUtils.get_all_documents_dashboard(db)
sync_status = DocumentManagementUtils.get_sync_status_summary(db)
activity = DocumentManagementUtils.get_recent_activity(db, days=7)

# Returns statistics for UI rendering
```

## API Documentation

Full API documentation available at: `/DATABASE_API_DOCS.md`

Interactive API docs (Swagger UI): `http://localhost:8000/docs`

## Environment Variables

```
DATABASE_URL              SQLite or PostgreSQL connection string
DB_ECHO                  Enable SQL query logging (true/false)
CHROMA_PERSIST_DIRECTORY Directory for ChromaDB persistence (default: ./app/chroma_db)
CHROMA_COLLECTION_NAME   ChromaDB collection name (default: asktemoc)
```

## Troubleshooting

### Database not initializing
- Check DATABASE_URL in .env
- Ensure write permissions in working directory
- For PostgreSQL, verify connection string format

### ChromaDB export fails
- Verify CHROMA_PERSIST_DIRECTORY is writable
- Check embeddings have valid vectors
- Ensure ChromaDB collection can be created

### Slow queries
- Use pagination (limit parameter)
- Leverage indexes on (document_id, chunk_index)
- Filter by is_synced for efficient unsynced queries

## Next Steps

1. Integrate with embedding generation service
2. Add authentication/authorization
3. Implement rate limiting
4. Add comprehensive logging
5. Set up monitoring and alerting
6. Consider document versioning
7. Implement full-text search
8. Add audit logging

## Support

For detailed documentation, see: `/DATABASE_API_DOCS.md`
