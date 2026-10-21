# AskTemoc Backend - Database & API Documentation

## Overview

This implementation provides a complete SQLite-based relational schema with FastAPI endpoints for managing documents, chunks, embeddings, and Pinecone export operations. The system is designed for RAG (Retrieval-Augmented Generation) applications with scalable metadata management.

## Architecture

### Database Schema

#### Documents Table (`documents`)
Stores document metadata with soft-delete support.

| Column | Type | Purpose |
|--------|------|---------|
| id | String (Primary Key) | Unique document identifier (UUID) |
| title | String | Document title (indexed) |
| source | String | Document source (URL, file path, etc.) |
| metadata | JSON | Flexible metadata storage |
| created_at | DateTime | Creation timestamp (indexed) |
| updated_at | DateTime | Last update timestamp |
| is_deleted | Boolean | Soft delete flag (indexed) |

**Relationships:**
- One-to-Many with `Chunk` (cascade delete)

#### Chunks Table (`chunks`)
Stores text chunks extracted from documents with sequence ordering.

| Column | Type | Purpose |
|--------|------|---------|
| id | String (Primary Key) | Unique chunk identifier (UUID) |
| document_id | String (Foreign Key) | Reference to parent document |
| chunk_index | Integer | Sequence position within document (indexed with doc_id) |
| text | Text | Chunk content |
| metadata | JSON | Chunk-specific metadata |
| created_at | DateTime | Creation timestamp (indexed) |
| updated_at | DateTime | Last update timestamp |
| is_deleted | Boolean | Soft delete flag (indexed) |

**Relationships:**
- Many-to-One with `Document`
- One-to-Many with `Embedding` (cascade delete)

**Indexes:**
- Composite: (document_id, chunk_index) for efficient chunk retrieval

#### Embeddings Table (`embeddings`)
Stores embedding vectors and sync status with Pinecone.

| Column | Type | Purpose |
|--------|------|---------|
| id | String (Primary Key) | Unique embedding identifier (UUID) |
| chunk_id | String (Foreign Key) | Reference to parent chunk |
| vector | JSON | Embedding vector as JSON array |
| model | String | Embedding model name (e.g., "text-embedding-ada-002") |
| pinecone_id | String | Reference to Pinecone vector ID (indexed) |
| is_synced | Boolean | Sync status flag (indexed) |
| created_at | DateTime | Creation timestamp (indexed) |
| updated_at | DateTime | Last update timestamp |
| last_synced_at | DateTime | Last successful sync to Pinecone |

**Relationships:**
- Many-to-One with `Chunk`

**Indexes:**
- `pinecone_id`: For Pinecone reference lookups
- `is_synced`: For finding unsynced embeddings

## Setup Instructions

### 1. Prerequisites

- Python 3.9+
- SQLite (included with Python)
- Optional: PostgreSQL for production

### 2. Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or with pip tools
pip-sync requirements.txt
```

### 3. Environment Configuration

Create a `.env` file from the template:

```bash
cp .env.example .env
```

Update with your Pinecone credentials:

```env
PINECONE_API_KEY=your_api_key_here
PINECONE_ENVIRONMENT=us-east-1
PINECONE_INDEX_NAME=asktemoc
```

### 4. Database Initialization

Database tables are automatically created on application startup via the `init_db()` function in `app.main`.

To manually initialize:

```python
from app.db.database import init_db
init_db()
```

## API Endpoints

### Document Management

#### Create Document
```
POST /api/documents
Content-Type: application/json

{
  "title": "Document Title",
  "source": "https://example.com/doc",
  "metadata": {"author": "John Doe"}
}
```

#### List Documents
```
GET /api/documents?skip=0&limit=100&include_deleted=false
```

#### Get Document Details
```
GET /api/documents/{doc_id}
```

#### Update Document
```
PUT /api/documents/{doc_id}
Content-Type: application/json

{
  "title": "Updated Title",
  "metadata": {"updated": true}
}
```

#### Delete Document
```
DELETE /api/documents/{doc_id}?hard_delete=false
```

### Chunk Management

#### Create Chunk
```
POST /api/documents/{doc_id}/chunks
Content-Type: application/json

{
  "chunk_index": 0,
  "text": "Chunk content here...",
  "metadata": {"source_page": 1}
}
```

#### Batch Create Chunks
```
POST /api/documents/{doc_id}/chunks/batch
Content-Type: application/json

{
  "chunks": [
    {
      "chunk_index": 0,
      "text": "First chunk",
      "metadata": {}
    },
    {
      "chunk_index": 1,
      "text": "Second chunk",
      "metadata": {}
    }
  ]
}
```

#### List Document Chunks
```
GET /api/documents/{doc_id}/chunks?skip=0&limit=1000
```

#### Get Chunk Details
```
GET /api/chunks/{chunk_id}
```

#### Update Chunk
```
PUT /api/chunks/{chunk_id}
Content-Type: application/json

{
  "text": "Updated chunk text",
  "metadata": {"updated": true}
}
```

### Embedding Management

#### Create Embedding
```
POST /api/documents/chunks/{chunk_id}/embeddings
Content-Type: application/json

{
  "vector": [0.1, 0.2, 0.3, ...],
  "model": "text-embedding-ada-002"
}
```

#### Get Embedding
```
GET /api/embeddings/{embedding_id}
```

#### Update Embedding
```
PUT /api/embeddings/{embedding_id}
Content-Type: application/json

{
  "vector": [0.1, 0.2, 0.3, ...],
  "pinecone_id": "vector-123"
}
```

### Pinecone Export Operations

#### Export Document Embeddings
```
POST /api/pinecone/export/document/{doc_id}
```

Exports all embeddings for a specific document to Pinecone and updates sync status.

#### Export Unsynced Embeddings
```
POST /api/pinecone/export/unsynced?batch_size=100
```

Exports all embeddings not yet synced to Pinecone.

#### Batch Export Embeddings
```
POST /api/pinecone/export/batch
Content-Type: application/json

{
  "embedding_ids": ["emb-1", "emb-2", "emb-3"]
}
```

#### Delete Vectors from Pinecone
```
DELETE /api/pinecone/vectors
Content-Type: application/json

{
  "vector_ids": ["vec-1", "vec-2"]
}
```

#### Get Index Statistics
```
GET /api/pinecone/index/stats
```

Returns Pinecone index statistics including dimension, vector count, and more.

### Dashboard & Analytics

#### Dashboard Overview
```
GET /api/dashboard/overview
```

Returns comprehensive dashboard statistics with document list and sync status.

#### Document Statistics
```
GET /api/dashboard/document/{doc_id}/stats
```

Returns detailed statistics for a specific document.

#### Export Document as JSON
```
GET /api/dashboard/document/{doc_id}/export
```

Exports document with all chunks and embeddings in JSON format.

#### Duplicate Document
```
POST /api/dashboard/document/{doc_id}/duplicate?new_title=Copy+of+Document
```

Creates a complete copy of document with all chunks and embeddings.

#### Batch Delete Documents
```
POST /api/dashboard/documents/batch-delete?hard_delete=false
Content-Type: application/json

{
  "doc_ids": ["doc-1", "doc-2", "doc-3"]
}
```

#### Search Content
```
GET /api/dashboard/search?query=search_term&limit=100
```

Searches across all chunks and document titles.

#### Recent Activity
```
GET /api/dashboard/activity?days=7&limit=100
```

Returns recent changes to documents, chunks, and embeddings.

#### Sync Status
```
GET /api/dashboard/sync-status
```

Returns overall sync status and statistics.

## Service Layer

### DocumentService
High-level CRUD operations for documents:
- `create_document()`: Create new document
- `get_document()`: Retrieve document by ID
- `list_documents()`: List with pagination
- `update_document()`: Update document fields
- `delete_document()`: Soft or hard delete
- `search_documents()`: Search by title/source

### ChunkService
High-level CRUD operations for chunks:
- `create_chunk()`: Create chunk within document
- `get_chunk()`: Retrieve chunk by ID
- `list_chunks_by_document()`: Get all chunks for document
- `update_chunk()`: Update chunk content/metadata
- `delete_chunk()`: Soft or hard delete
- `get_chunks_by_ids()`: Retrieve multiple chunks

### EmbeddingService
High-level CRUD operations for embeddings:
- `create_embedding()`: Create embedding for chunk
- `get_embedding()`: Retrieve by ID
- `get_embedding_by_chunk()`: Get embedding for specific chunk
- `list_unsynced_embeddings()`: Get embeddings needing Pinecone sync
- `update_embedding()`: Update vector/sync status
- `mark_synced()`: Mark as synced with Pinecone
- `get_embeddings_by_document()`: Get all embeddings for document

### PineconeExportService
Manages Pinecone synchronization:
- `prepare_vectors_for_upsert()`: Format vectors with metadata
- `upsert_vectors()`: Sync to Pinecone with metadata
- `export_document_embeddings()`: Export specific document
- `export_unsynced_embeddings()`: Batch export unsynced
- `delete_from_pinecone()`: Remove vectors
- `search_pinecone()`: Query Pinecone index
- `get_index_stats()`: Retrieve index statistics

### DocumentManagementUtils
High-level utilities for dashboard and batch operations:
- `get_document_statistics()`: Comprehensive document stats
- `get_all_documents_dashboard()`: Dashboard view of all documents
- `batch_delete_documents()`: Delete multiple documents
- `duplicate_document_with_chunks()`: Clone document with data
- `export_document_to_json()`: Export as JSON
- `search_content_across_documents()`: Global content search
- `get_sync_status_summary()`: Overall sync statistics
- `get_recent_activity()`: Activity tracking

## Usage Examples

### Python Usage

```python
from app.db.database import SessionLocal, get_db
from app.db.services import DocumentService, ChunkService, EmbeddingService
from app.services.pinecone_service import PineconeExportService
from app.services.document_management import DocumentManagementUtils

# Get database session
db = SessionLocal()

# Create document
doc = DocumentService.create_document(
    db=db,
    title="My Document",
    source="https://example.com",
    metadata={"author": "John"}
)

# Create chunks
chunk1 = ChunkService.create_chunk(
    db=db,
    document_id=doc.id,
    chunk_index=0,
    text="First chunk content...",
    metadata={"page": 1}
)

chunk2 = ChunkService.create_chunk(
    db=db,
    document_id=doc.id,
    chunk_index=1,
    text="Second chunk content...",
    metadata={"page": 2}
)

# Create embeddings
import numpy as np

embedding1 = EmbeddingService.create_embedding(
    db=db,
    chunk_id=chunk1.id,
    vector=np.random.randn(1536).tolist(),
    model="text-embedding-ada-002"
)

# Export to Pinecone
pinecone_svc = PineconeExportService()
result = pinecone_svc.export_document_embeddings(db=db, document_id=doc.id)
print(f"Exported {result['upserted_count']} embeddings")

# Get statistics
stats = DocumentManagementUtils.get_document_statistics(db=db, doc_id=doc.id)
print(f"Document has {stats['chunk_count']} chunks")
print(f"Sync status: {stats['sync_percentage']}%")

db.close()
```

### FastAPI Usage

```bash
# Start server
uvicorn app.main:app --reload

# Create document
curl -X POST http://localhost:8000/api/documents \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","source":"http://example.com"}'

# Get dashboard overview
curl http://localhost:8000/api/dashboard/overview

# Export embeddings to Pinecone
curl -X POST http://localhost:8000/api/pinecone/export/unsynced
```

## Performance Considerations

### Indexing Strategy
- Documents are indexed by `created_at` for timeline queries
- Chunks use composite index `(document_id, chunk_index)` for fast retrieval
- Embeddings indexed by `pinecone_id` and `is_synced` for efficient sync operations

### Batch Operations
- Use `batch_create_chunks` for creating multiple chunks
- Use `export_unsynced_embeddings` with configurable batch size
- Pagination available on list endpoints (default limit: 100-1000)

### Soft Deletes
- All deletes are soft by default (marks `is_deleted=True`)
- Hard delete option available for permanent removal
- Soft deleted records are excluded from queries unless explicitly included

## Error Handling

All endpoints return appropriate HTTP status codes:
- `201 Created`: Successful creation
- `200 OK`: Successful retrieval/update
- `204 No Content`: Successful deletion
- `400 Bad Request`: Invalid input
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server-side error

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| DATABASE_URL | No | sqlite:///./asktemoc.db | Database connection string |
| DB_ECHO | No | false | Enable SQL logging |
| PINECONE_API_KEY | Yes | - | Pinecone API key |
| PINECONE_ENVIRONMENT | No | us-east-1 | Pinecone region |
| PINECONE_INDEX_NAME | No | asktemoc | Pinecone index name |

## Database Migration

To switch from SQLite to PostgreSQL:

1. Update `.env`:
```env
DATABASE_URL=postgresql://user:password@localhost/asktemoc
```

2. SQLAlchemy will automatically use the appropriate dialect

## Testing

```python
# Test document creation
def test_create_document(db):
    doc = DocumentService.create_document(
        db=db,
        title="Test Doc",
        source="test://doc"
    )
    assert doc.id is not None
    assert doc.title == "Test Doc"

# Test chunk creation
def test_create_chunk(db, document):
    chunk = ChunkService.create_chunk(
        db=db,
        document_id=document.id,
        chunk_index=0,
        text="Test chunk"
    )
    assert chunk.document_id == document.id
```

## Troubleshooting

### Issue: "PINECONE_API_KEY environment variable is required"
**Solution:** Ensure `.env` file has `PINECONE_API_KEY` set before initializing PineconeExportService.

### Issue: Database locked (SQLite)
**Solution:** Use WAL mode or switch to PostgreSQL for concurrent access:
```python
# In database.py
engine = create_engine(
    "sqlite:///asktemoc.db",
    connect_args={"timeout": 30},
)
```

### Issue: Large embeddings slow to query
**Solution:** Use pagination and consider indexing on `is_synced` for unsynced queries.

## Future Enhancements

- [ ] Bulk embedding import/export
- [ ] Vector dimension auto-detection
- [ ] Pinecone namespace management
- [ ] Advanced filtering and full-text search
- [ ] Document versioning
- [ ] Audit logging
- [ ] Rate limiting
- [ ] Authentication/Authorization
