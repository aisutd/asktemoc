from fastapi import FastAPI
from pydantic import BaseModel
from langchain_community.embeddings import HuggingFaceEmbeddings
import chromadb

# --- Initialize app ---
app = FastAPI(title="Embeddings Service")

# --- Initialize embedding model and Chroma vector store ---
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# persist_directory means Chroma will save data in /db/chroma/
client = chromadb.Client()
collection = client.get_or_create_collection(name="chunks")

# --- Define request models ---
class EmbedItem(BaseModel):
    chunk_id: str
    text: str
    metadata: dict = {}

class EmbedBatch(BaseModel):
    items: list[EmbedItem]

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


# --- Endpoints ---

@app.get("/")
def root():
    """Health check endpoint"""
    return {"message": "Embeddings service is running 🚀"}

@app.post("/embed_batch")
def embed_batch(req: EmbedBatch):
    """Store text chunks as vectors in Chroma"""
    texts = [i.text for i in req.items]
    ids = [i.chunk_id for i in req.items]
    metadatas = [i.metadata for i in req.items]

    vectors = embedding_model.embed_documents(texts)
    collection.add(ids=ids, embeddings=vectors, metadatas=metadatas, documents=texts)

    return {"status": "ok", "count": len(vectors)}

@app.post("/search")
def search(req: QueryRequest):
    """Search for the most similar chunks to a given query"""
    query_vec = embedding_model.embed_query(req.query)
    results = collection.query(query_embeddings=[query_vec], n_results=req.top_k)
    return {"results": results}

