import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "seed_catalog", Path(__file__).resolve().parents[1] / "scripts" / "seed_catalog.py"
)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def _catalog(tmp_path):
    cs = tmp_path / "bachelor_of_science_in_computer_science"
    cs.mkdir()
    (cs / "requirements.txt").write_text("CS 1337 Computer Science I\n" * 120, encoding="utf-8")
    (cs / "example.txt").write_text("Freshman year: CS 1337", encoding="utf-8")
    orphan = tmp_path / "1"
    orphan.mkdir()
    (orphan / "requirements.txt").write_text("footnote page", encoding="utf-8")
    (tmp_path / "sources.json").write_text(json.dumps({
        cs.name: {"url": "https://catalog.utdallas.edu/cs", "title": "Bachelor of Science in Computer Science"},
    }), encoding="utf-8")
    return tmp_path


def test_load_documents_sets_source_metadata(tmp_path):
    docs = seed.load_documents(_catalog(tmp_path))
    meta = {(d.metadata["program"], d.metadata["doc_type"]): d.metadata for d in docs}

    req = meta[("bachelor_of_science_in_computer_science", "requirements")]
    assert req["source"] == "https://catalog.utdallas.edu/cs"
    assert req["title"] == "Bachelor of Science in Computer Science"
    example = meta[("bachelor_of_science_in_computer_science", "example degree plan")]
    assert example["title"].endswith("(example degree plan)")
    # Folders missing from sources.json fall back to the programs index.
    assert meta[("1", "requirements")]["source"] == seed.CATALOG_INDEX_URL
    assert all(m["corpus"] == "catalog" for m in meta.values())


def test_split_ids_are_stable_and_unique(tmp_path):
    docs = seed.load_documents(_catalog(tmp_path))
    chunks, ids = seed.split(docs)
    _, ids_again = seed.split(seed.load_documents(tmp_path))
    assert len(chunks) == len(ids) > len(docs)
    assert len(set(ids)) == len(ids)
    assert ids == ids_again
    assert max(len(c.page_content) for c in chunks) <= 1000
