"""
Seed the Chroma collection the retriever reads from with the committed catalog
snapshot in data/catalog/*/{requirements,example}.txt.

Idempotent: every chunk previously written by this script is removed before the
catalog is re-added, so re-running replaces rather than duplicates. Uses the same
embeddings as the API (OpenAI if OPENAI_API_KEY is set, else Ollama); if the
collection was seeded with a different provider/model it is dropped and rebuilt,
since vectors from different models are not comparable.

    cd backend && python scripts/seed_catalog.py [--data-dir PATH]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chromadb  # noqa: E402
from langchain_chroma import Chroma  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from app.core.config import REPO_ROOT, get_settings  # noqa: E402
from app.services.data_ingestion_service import make_text_splitter  # noqa: E402
from app.services.retriever_service import embedding_signature, get_embeddings  # noqa: E402

CATALOG_INDEX_URL = "https://catalog.utdallas.edu/2025/undergraduate/programs"
FILES = {
    "requirements.txt": "requirements",
    "example.txt": "example degree plan",
}
CORPUS = "catalog"
BATCH_SIZE = 64


def load_documents(data_dir: Path) -> list[Document]:
    sources_file = data_dir / "sources.json"
    sources = json.loads(sources_file.read_text(encoding="utf-8")) if sources_file.exists() else {}

    docs = []
    for program_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        program = program_dir.name
        info = sources.get(program, {})
        title = info.get("title") or program.replace("_", " ").title()
        for filename, kind in FILES.items():
            path = program_dir / filename
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                continue
            try:
                rel = path.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                rel = path.as_posix()
            docs.append(Document(
                page_content=text,
                metadata={
                    "source": info.get("url", CATALOG_INDEX_URL),
                    "title": title if kind == "requirements" else f"{title} ({kind})",
                    "program": program,
                    "file_path": rel,
                    "doc_type": kind,
                    "corpus": CORPUS,
                },
            ))
    return docs


def split(docs: list[Document]) -> tuple[list[Document], list[str]]:
    splitter = make_text_splitter()
    chunks, ids = [], []
    for doc in docs:
        for i, chunk in enumerate(splitter.split_documents([doc])):
            chunk.metadata["chunk_index"] = i
            chunks.append(chunk)
            ids.append(f"{CORPUS}:{doc.metadata['file_path']}#{i}")
    return chunks, ids


def get_collection(client, name: str, signature: dict):
    try:
        existing = client.get_collection(name)
    except Exception:
        existing = None
    if existing is not None:
        seeded = {k: (existing.metadata or {}).get(k) for k in signature}
        if seeded != signature:
            print(f"Collection {name!r} was built with {seeded}; rebuilding for {signature}.")
            client.delete_collection(name)
    return client.get_or_create_collection(name, metadata=signature)


def main():
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data-dir", default=settings.catalog_data_dir)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help="chunks per embedding request (lower it if a local Ollama struggles)")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve()
    if not data_dir.is_dir():
        sys.exit(f"Catalog directory not found: {data_dir}")

    docs = load_documents(data_dir)
    chunks, ids = split(docs)
    programs = len({d.metadata["program"] for d in docs})
    print(f"Loaded {len(docs)} documents from {programs} programs in {data_dir}")
    print(f"Split into {len(chunks)} chunks")

    signature = embedding_signature(settings)
    print(f"Embeddings: {signature['embedding_provider']} / {signature['embedding_model']}")
    client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
    collection = get_collection(client, settings.chroma_collection_name, signature)
    collection.delete(where={"corpus": CORPUS})

    store = Chroma(
        client=client,
        collection_name=settings.chroma_collection_name,
        embedding_function=get_embeddings(settings),
    )
    batch = args.batch_size
    for start in range(0, len(chunks), batch):
        try:
            store.add_documents(chunks[start:start + batch], ids=ids[start:start + batch])
        except Exception as e:
            sys.exit(
                f"Embedding failed after {start} of {len(chunks)} chunks: {e}\n"
                "Check OPENAI_API_KEY (and its billing) or that Ollama is running with "
                f"{settings.ollama_embedding_model!r} pulled, then re-run; re-running is safe."
            )
        print(f"  embedded {min(start + batch, len(chunks))}/{len(chunks)}")

    print(
        f"Done: collection {settings.chroma_collection_name!r} at "
        f"{settings.chroma_persist_directory} now holds {collection.count()} chunks."
    )


if __name__ == "__main__":
    main()
