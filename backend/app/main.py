from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import query, documents, chroma, dashboard, rag_endpoint, health
from app.db.database import init_db

app = FastAPI(title="AskTemoc Backend")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
@app.on_event("startup")
def startup_event():
    init_db()

# Include routers
app.include_router(query.router, prefix="/api/query", tags=['query'])
app.include_router(documents.router, prefix="/api", tags=['documents'])
app.include_router(chroma.router, prefix="/api", tags=['chroma'])
app.include_router(dashboard.router, prefix="/api", tags=['dashboard'])
app.include_router(rag_endpoint.router, prefix="/api", tags=['rag'])
app.include_router(health.router, prefix="/api/health", tags=['health'])