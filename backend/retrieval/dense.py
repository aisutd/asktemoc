"""Dense retrieval: pgvector cosine distance over the stored chunk embeddings."""

from retrieval.db import ENV_PATH, check_k, connect

# Must match the model that produced the stored vectors (embeddings.model).
EMBED_MODEL = "text-embedding-3-small"

# <=> is pgvector cosine distance; score = cosine similarity = 1 - distance.
# Exact scan (no ANN index exists), ties broken by chunk id so runs are stable.
SEARCH_SQL = """
    SELECT c.id, c.document_id, d.title, c.chunk_index, c.text,
           1 - (e.vector <=> %(qvec)s::vector) AS score
    FROM embeddings e
    JOIN chunks c ON c.id = e.chunk_id
    JOIN documents d ON d.id = c.document_id
    WHERE e.model = %(model)s AND NOT c.is_deleted AND NOT d.is_deleted
    ORDER BY e.vector <=> %(qvec)s::vector, c.id
    LIMIT %(k)s
"""


def openai_embed(text):
    """Embed one query with EMBED_MODEL, using OPENAI_API_KEY from backend/.env."""
    from dotenv import dotenv_values
    from openai import OpenAI

    client = OpenAI(api_key=dotenv_values(ENV_PATH).get("OPENAI_API_KEY"))
    return client.embeddings.create(model=EMBED_MODEL, input=[text]).data[0].embedding


def to_pgvector(vec):
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def retrieve(query, k, *, conn=None, embed=openai_embed):
    """
    Top-k chunks for query by cosine similarity. k is required (the API's
    retriever silently defaulted to 4). Pass conn to reuse a connection and
    embed to substitute the embedding function (tests, cached vectors).
    """
    check_k(k)
    params = {"qvec": to_pgvector(embed(query)), "model": EMBED_MODEL, "k": k}
    own = conn is None
    conn = connect() if own else conn
    try:
        with conn.cursor() as cur:
            cur.execute(SEARCH_SQL, params)
            rows = cur.fetchall()
    finally:
        if own:
            conn.close()
    return [
        {"chunk_id": cid, "document_id": did, "doc_title": title,
         "chunk_index": idx, "text": text, "score": float(score)}
        for cid, did, title, idx, text, score in rows
    ]
