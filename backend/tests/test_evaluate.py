"""Unit tests for backend/retrieval/evaluate.py (pure functions, no I/O)."""

import pytest

from retrieval.evaluate import (
    doc_ranking, duplicate_classes, parse_questions, repeat_stats, score, similarity,
    strict_classes,
)

MD = """# Eval

## Q1
**What are the core requirements for the BS in CS?**
*Target doc*: `cs/requirements.txt`

## Q2 *(revised — target corrected)*
**Compare CS and EE.**
*Target docs*: `cs/requirements.txt`, `ee/requirements.txt`, `cs/requirements.txt`
"""


def test_parse_questions():
    qs = parse_questions(MD)
    assert qs == [
        {"id": "Q1", "question": "What are the core requirements for the BS in CS?",
         "relevant": ["cs/requirements"], "note": ""},
        {"id": "Q2", "question": "Compare CS and EE.",
         "relevant": ["cs/requirements", "ee/requirements"], "note": "(revised — target corrected)"},
    ]


def test_parse_questions_rejects_missing_targets():
    with pytest.raises(ValueError, match="Q1"):
        parse_questions("## Q1\n**A question?**\nno targets here\n")


def hits(*titles):
    return [{"doc_title": t, "chunk_index": i, "score": 1 - i / 10} for i, t in enumerate(titles)]


def test_doc_ranking_keeps_first_chunk_per_document():
    r = doc_ranking(hits("a", "a", "b", "a", "c"))
    assert [(d["doc_title"], d["chunk_rank"]) for d in r] == [("a", 1), ("b", 3), ("c", 5)]


def test_repeat_stats():
    s = repeat_stats(hits("a", "a", "b", "a", "c", "d"), n=3)
    assert s == {"repeats_in_top_chunks": 1, "chunks_to_fill": 5}
    assert repeat_stats(hits("a", "a"), n=3)["chunks_to_fill"] is None


def test_strict_score():
    ranking = ["x", "t1", "y", "t2"]
    cls = strict_classes(["t1", "t2"])
    s1, s3, s5 = (score(ranking, ["t1", "t2"], cls, k) for k in (1, 3, 5))
    assert (s1["precision"], s1["recall"], s1["rr"]) == (0, 0, 0)
    assert (s3["precision"], s3["recall"], s3["rr"]) == (pytest.approx(1 / 3), 0.5, 0.5)
    # precision@k divides by k even when fewer documents were ranked
    assert (s5["precision"], s5["recall"], s5["rr"]) == (pytest.approx(2 / 5), 1.0, 0.5)


def test_duplicate_aware_counts_copies_in_precision_but_target_once_in_recall():
    cls = {"t": {"t": "target", "copy": "exact", "copy2": "exact"}}
    s = score(["copy", "t", "x", "copy2"], ["t"], cls, 4)
    assert s["precision"] == pytest.approx(3 / 4)
    assert s["recall"] == 1.0 and s["rr"] == 1.0
    assert s["credited"] == {"t": {"rank": 1, "doc": "copy", "label": "exact"}}
    assert [(r["rank"], r["doc"], r["matches"]) for r in s["relevant"]] == [
        (1, "copy", {"t": "exact"}), (2, "t", {"t": "target"}), (4, "copy2", {"t": "exact"})]


def test_duplicate_aware_never_scores_below_strict():
    # Two targets with identical text (like Q13): strict counts both documents.
    targets = ["a", "b"]
    dup = {"a": {"a": "target", "b": "exact", "c": "exact"},
           "b": {"b": "target", "a": "exact", "c": "exact"}}
    ranking = ["c", "x", "a", "b"]
    for k in (1, 3, 4):
        s, d = score(ranking, targets, strict_classes(targets), k), score(ranking, targets, dup, k)
        assert d["precision"] >= s["precision"] and d["recall"] >= s["recall"] and d["rr"] >= s["rr"]


def test_chunk_budget_ranking_keeps_repeats_as_positions():
    # Raw chunk titles (no dedup), as used for the chunk-budget table.
    chunks = ["x", "x", "t", "x", "u"]
    cls = strict_classes(["t", "u"])
    s3, s5 = score(chunks, ["t", "u"], cls, 3), score(chunks, ["t", "u"], cls, 5)
    assert (s3["recall"], s3["rr"]) == (0.5, pytest.approx(1 / 3))
    assert (s5["recall"], s5["rr"]) == (1.0, pytest.approx(1 / 3))


def test_one_document_can_credit_two_targets_with_identical_text():
    cls = {"a": {"a": "target", "b": "exact"}, "b": {"b": "target", "a": "exact"}}
    s = score(["b"], ["a", "b"], cls, 1)
    assert (s["precision"], s["recall"], s["rr"]) == (1.0, 1.0, 1.0)


def test_duplicate_classes_exact_and_near():
    base = "Course list: " + " ".join(f"CS {1000 + i}" for i in range(200))
    docs = {
        "t": base,
        "same": base,
        "near": base.replace("CS 1005", "CS 1050"),
        "far": base[: len(base) // 2],
        "other": "Something else entirely " * 40,
    }
    cls = duplicate_classes(docs, ["t"])["t"]
    assert cls["t"] == "target" and cls["same"] == "exact"
    assert cls["near"].startswith("near (") and "far" not in cls and "other" not in cls


def test_similarity_bounds():
    assert similarity("abc", "abc") == 1.0
    assert similarity("a" * 100, "a" * 50) == 0.0  # ruled out by length alone
