# Changelog

## Date: February 17, 2026

-   **feat**: Migrated from Pinecone to ChromaDB for vector storage, removing external API dependency and simplifying the architecture

### Files Created

1.  **app/services/chroma_service.py** (NEW) - 264 lines
    -   ChromaService class replacing PineconeExportService
    -   Local persistent storage using ChromaDB
    -   Methods: upsert_vectors, export_document_embeddings, export_unsynced_embeddings, delete_from_chroma, search_chroma, get_collection_stats

2.  **app/api/endpoints/chroma.py** (NEW) - 175 lines
    -   6 ChromaDB API endpoints replacing Pinecone endpoints
    -   Endpoints: export/document, export/unsynced, export/batch, delete vectors, index stats, search

### Files Modified

1.  **app/db/models.py** (MODIFIED)
    -   Renamed `pinecone_id` column to `chroma_id` in Embedding model
    -   Updated index from `idx_pinecone_id` to `idx_chroma_id`
    -   Updated repr method

2.  **app/db/services.py** (MODIFIED)
    -   Updated EmbeddingService methods to use `chroma_id` instead of `pinecone_id`
    -   Methods updated: create_embedding, update_embedding, mark_synced, list_unsynced_embeddings

3.  **app/services/document_management.py** (MODIFIED)
    -   Updated export_document_to_json to use `chroma_id`
    -   Updated get_sync_status_summary docstring to reference ChromaDB

4.  **app/schemas/db_schemas.py** (MODIFIED)
    -   Renamed PineconeExportResponse → ChromaExportResponse
    -   Renamed PineconeIndexStats → ChromaIndexStats
    -   Updated EmbeddingUpdate and EmbeddingResponse to use `chroma_id`
    -   Updated BatchEmbeddingSync docstring

5.  **app/api/endpoints/documents.py** (MODIFIED)
    -   Updated update_embedding endpoint to pass `chroma_id`

6.  **app/api/endpoints/dashboard.py** (MODIFIED)
    -   Updated sync-status endpoint docstring

7.  **app/main.py** (MODIFIED)
    -   Changed import from pinecone to chroma
    -   Updated router inclusion

8.  **.env.example** (MODIFIED)
    -   Removed Pinecone configuration variables
    -   Kept ChromaDB configuration

9.  **app/.env** (MODIFIED)
    -   Removed Pinecone configuration variables

### Files Deleted

1.  **app/services/pinecone_service.py** (DELETED)
    -   Removed PineconeExportService class

2.  **app/api/endpoints/pinecone.py** (DELETED)
    -   Removed Pinecone API endpoints

### API Changes

- Endpoint prefix changed from `/api/pinecone` to `/api/chroma`
- All endpoint functionality preserved with ChromaDB backend

### Configuration Changes

- Removed: PINECONE_API_KEY, PINECONE_ENVIRONMENT, PINECONE_INDEX_NAME
- Using: CHROMA_PERSIST_DIRECTORY, CHROMA_COLLECTION_NAME

### Benefits

- No external API dependency
- Local persistent storage
- Simplified architecture
- Cost reduction (no Pinecone subscription needed)

## Date: November 20, 2025

-   **feat**: Connected ChromaDB RAG pipeline to existing asktemoc.db database with university program data
-   **feat**: Integrated Ollama LLM with streaming API for real-time responses
-   **fix**: Resolved import path issues from relative to absolute imports

### Files Modified/Created:

#### Data Ingestion Service
1.  **app/services/data_ingestion_service.py** (CREATED)
    -   Implemented data ingestion service for ChromaDB
    -   Successfully ingested 116 university program files (1483 document chunks)
    -   Created proper document chunking and embedding generation

#### Environment Configuration
2.  **app/.env** (CREATED)
    -   Added ChromaDB persistence configuration
    -   Configured Ollama model settings (OLLAMA_MODEL, OLLAMA_EMBEDDING_MODEL)

#### RAG Pipeline Updates
3.  **app/services/retriever_service.py** (MODIFIED)
    -   Updated to use chroma_db/chroma.sqlite3 persistence path
    -   Enhanced ChromaDB integration with Ollama embeddings
4.  **app/services/rag_chain_service.py** (MODIFIED)
    -   Fixed import paths from relative to absolute imports
    -   Enhanced RAG chain with proper ChromaDB retriever integration
5.  **app/services/prompt_service.py** (WORKING)
    -   Existing prompt template working correctly

#### API Endpoint Updates
6.  **app/api/endpoints/rag_endpoint.py** (MODIFIED)
    -   Enhanced to work with real RAG pipeline instead of mock data
    -   Streams responses from actual Ollama LLM with ChromaDB context

#### Documentation
7.  **plan.md** (MODIFIED)
    -   Wiped old plan and documented completed implementation status

## Date: November 19, 2025

-   **feat**: Implemented LangChain RAG pipeline for conversational AI.

### Files Modified/Created:

#### Prompt Template
1.  **app/services/prompt_service.py** (MODIFIED)
    -   Defined a structured prompt template for RAG chain using `langchain_core.prompts.PromptTemplate`.

#### Services
2.  **app/services/retriever_service.py** (CREATED)
    -   Implemented `RetrieverService` to integrate ChromaDB with `OllamaEmbeddings`.
3.  **app/services/rag_chain_service.py** (MODIFIED)
    -   Constructed the core RAG chain using `Ollama` for LLM and configured to output generated text and source documents.

#### API Endpoints
4.  **app/api/endpoints/rag_endpoint.py** (CREATED)
    -   Exposed the RAG chain through a new streaming API endpoint `/api/chat`.
    -   Designed to accept user messages and stream responses, including text and source documents, conforming to frontend requirements.

#### Core Application
5.  **app/main.py** (MODIFIED)
    -   Integrated the new `rag_endpoint` router.

#### Testing
6.  **tests/test_rag_pipeline.py** (CREATED)
    -   Added comprehensive unit and integration tests for the RAG pipeline.
    -   Implemented mocking for `rag_chain_service.get_chain` and `Ollama` components to ensure robust and independent testing.

---

### Summary of Changes

-   **RAG Integration Complete**: Successfully connected ChromaDB with existing university program data (116 files, 1483 chunks)
-   **Ollama Integration**: Configured and tested with llama3.1:8b model for text generation
-   **Real-time Streaming**: Enhanced `/api/chat` endpoint to stream responses from actual RAG pipeline
-   **Import Fixes**: Resolved module resolution issues by converting relative to absolute imports
-   **Data Ingestion**: Created service to ingest and embed all university program requirements

### Dependencies Added
- `langchain-chroma`
- `chromadb`
- `pytest-mock` (for testing)
- `langchain-community` (for Ollama integrations)

---

## Date: November 16, 2025

-   **a7e7157**: Updated README with setup instructions and included new dependencies to requirements.txt
-   **0e514cb**: Added the html document chunking class
-   **ab7c5f7**: Added the general web scraping

---

# Implementation Changes Log

## Date: November 13, 2025

### Files Created (9 NEW files)

#### Database Layer
1. **app/db/__init__.py** (NEW)
   - Module initialization with exports
   - Clean import interface for database components

2. **app/db/models.py** (NEW) - 96 lines
   - Document ORM model (soft-delete, metadata)
   - Chunk ORM model (sequence ordering, metadata)
   - Embedding ORM model (vector storage, sync tracking)
   - Relationships and cascade delete configuration

3. **app/db/database.py** (NEW) - 42 lines
   - SQLAlchemy engine initialization
   - Session factory and dependency injection
   - Database initialization and cleanup functions

4. **app/db/services.py** (NEW) - 328 lines
   - DocumentService: 8 CRUD + search methods
   - ChunkService: 7 CRUD + batch methods
   - EmbeddingService: 10 CRUD + sync methods

#### Services
5. **app/services/pinecone_service.py** (NEW) - 216 lines
   - PineconeExportService class
   - Vector preparation with metadata
   - Batch upsert to Pinecone
   - Vector deletion and search
   - Index statistics

6. **app/services/document_management.py** (NEW) - 305 lines
   - DocumentManagementUtils class
   - Dashboard and analytics functions
   - Document statistics and overview
   - Batch operations (delete, duplicate)
   - JSON export and content search
   - Activity tracking

#### API Endpoints
7. **app/api/endpoints/documents.py** (NEW) - 287 lines
   - Document CRUD endpoints (6)
   - Chunk CRUD and batch endpoints (7)
   - Embedding CRUD endpoints (4)
   - Total: 17 endpoints

8. **app/api/endpoints/pinecone.py** (NEW) - 172 lines
   - Document export endpoint
   - Unsynced export endpoint
   - Batch export endpoint
   - Vector deletion endpoint
   - Index statistics endpoint
   - Vector search endpoint
   - Total: 6 endpoints

9. **app/api/endpoints/dashboard.py** (NEW) - 99 lines
   - Dashboard overview endpoint
   - Document statistics endpoint
   - Export/duplicate endpoints
   - Batch delete endpoint
   - Content search endpoint
   - Activity tracking endpoint
   - Sync status endpoint
   - Total: 8 endpoints

### Files Modified (3 files)

#### Configuration
1. **requirements.txt** (MODIFIED)
   - Added: `pinecone-client==5.0.1`
   - No other changes needed

2. **app/main.py** (MODIFIED)
   - Added startup event for database initialization
   - Integrated all new routers (documents, pinecone, dashboard)
   - Organized by feature

#### Schemas
3. **app/schemas/db_schemas.py** (MODIFIED)
   - Added: DocumentCreate, DocumentUpdate, DocumentResponse, DocumentDetailResponse
   - Added: ChunkCreate, ChunkUpdate, ChunkResponse, ChunkDetailResponse
   - Added: EmbeddingCreate, EmbeddingUpdate, EmbeddingResponse
   - Added: BatchChunkCreate, BatchEmbeddingSync
   - Added: PineconeExportResponse, PineconeIndexStats
   - Added: DocumentSearch, SearchResponse
   - Total: 20+ new Pydantic models

### Files Created for Documentation (3 files)

1. **.env.example** (NEW)
   - Environment variable template
   - Database configuration options
   - Pinecone credentials setup

2. **DATABASE_API_DOCS.md** (NEW)
   - 400+ lines of comprehensive documentation
   - Database schema design and explanation
   - Complete API endpoint reference
   - Usage examples (Python and curl)
   - Service layer documentation
   - Performance considerations
   - Troubleshooting guide

3. **QUICK_START.md** (NEW)
   - Quick reference guide
   - File structure overview
   - Key components explanation
   - Common workflows
   - Database schema diagrams
   - Service class references

### Files Updated (1 file)

1. **IMPLEMENTATION_STATUS.md** (NEW)
   - Implementation status report
   - Comprehensive checklist
   - Statistics and metrics
   - Verification results

---

## Summary of Changes

### Code Statistics
- **Total Lines of Code Added**: 1,825
- **Total Files Created**: 9 (code) + 3 (documentation)
- **Total Files Modified**: 3

### Feature Summary

#### Database (3 tables)
- ✅ Documents table with metadata
- ✅ Chunks table with sequence ordering
- ✅ Embeddings table with Pinecone sync
- ✅ Proper relationships and cascade deletes
- ✅ Soft delete support
- ✅ 6 optimized indexes

#### Services (40+ methods)
- ✅ DocumentService (8 methods)
- ✅ ChunkService (7 methods)
- ✅ EmbeddingService (10 methods)
- ✅ PineconeExportService (7 methods)
- ✅ DocumentManagementUtils (8 methods)

#### API Endpoints (40+)
- ✅ Documents endpoints (6)
- ✅ Chunks endpoints (7)
- ✅ Embeddings endpoints (4)
- ✅ Pinecone endpoints (6)
- ✅ Dashboard endpoints (8)

#### Pinecone Integration
- ✅ Vector upsert with metadata
- ✅ Batch sync operations
- ✅ Sync status tracking
- ✅ Vector deletion
- ✅ Index statistics
- ✅ Vector search

#### Dashboard Features
- ✅ Document statistics
- ✅ Sync status monitoring
- ✅ Batch operations
- ✅ Content search
- ✅ Activity tracking
- ✅ JSON export

### Breaking Changes
None - All new functionality, no existing code modified except main.py and requirements.txt

### Dependencies Added
- `pinecone-client==5.0.1` (for Pinecone integration)

### Database Migration
None required - Tables created automatically on startup

---

## Verification Checklist

- ✅ All Python files compile without errors
- ✅ All imports work correctly
- ✅ Database models properly defined
- ✅ Service classes instantiate correctly
- ✅ FastAPI app initializes with all routes
- ✅ Pydantic schemas validate correctly
- ✅ No reserved name conflicts
- ✅ Documentation is comprehensive
- ✅ Code is well-commented

---

## How to Use

1. Install dependencies: `pip install -r requirements.txt`
2. Set up environment: `cp .env.example .env`
3. Configure Pinecone: Edit `.env` with API key
4. Run server: `uvicorn app.main:app --reload`
5. Access API: `http://localhost:8000`
6. View documentation: `http://localhost:8000/docs`

---

## Documentation

- **DATABASE_API_DOCS.md** - Complete API reference
- **QUICK_START.md** - Setup and quick reference
- **IMPLEMENTATION_STATUS.md** - Detailed report
- **Inline code comments** - Well-documented methods
