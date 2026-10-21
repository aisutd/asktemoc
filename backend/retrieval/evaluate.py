"""
Pure evaluation logic for retrieval: parse eval_questions.md, collapse chunk
rankings to document rankings, build duplicate-aware relevance sets, and score.
No I/O here; scripts/eval_retrieval.py wires it to Neon and writes reports.
"""

import hashlib
import re
from difflib import SequenceMatcher

KS = (1, 3, 5, 10)
NEAR_THRESHOLD = 0.99


# ── questions ────────────────────────────────────────────────────────────────

_HEADER = re.compile(r"^## (Q\d+)([^\n]*)\n", re.M)
_QUESTION = re.compile(r"\*\*(.+?)\*\*")
_TARGETS = re.compile(r"^\*Target docs?\*:(.*)$", re.M)


def parse_questions(md):
    """
    Parse eval_questions.md into [{id, question, relevant, note}].
    relevant holds documents.title values: the target paths without ".txt".
    Raises ValueError on anything unexpected rather than guessing.
    """
    parts = _HEADER.split(md)
    out = []
    for qid, header, body in zip(parts[1::3], parts[2::3], parts[3::3]):
        q = _QUESTION.search(body)
        t = _TARGETS.search(body)
        if not q or not t:
            raise ValueError(f"{qid}: missing question or target line")
        paths = re.findall(r"`([^`]+)`", t.group(1))
        if not paths:
            raise ValueError(f"{qid}: no target paths")
        relevant = list(dict.fromkeys(p[:-4] if p.endswith(".txt") else p for p in paths))
        note = header.strip().strip("*").strip()
        out.append({"id": qid, "question": q.group(1).strip(), "relevant": relevant, "note": note})
    ids = [q["id"] for q in out]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate question ids: {ids}")
    return out


# ── rankings ─────────────────────────────────────────────────────────────────

def doc_ranking(hits):
    """
    Collapse a chunk ranking to a document ranking: keep the first chunk of each
    document, in order. Each entry records the chunk position it came from.
    """
    seen, out = set(), []
    for pos, h in enumerate(hits, start=1):
        if h["doc_title"] not in seen:
            seen.add(h["doc_title"])
            out.append({"doc_title": h["doc_title"], "chunk_rank": pos,
                        "chunk_index": h["chunk_index"], "score": h["score"]})
    return out


def repeat_stats(hits, n=10):
    """Repeats among the top-n chunks, and how many chunks it takes to reach n distinct docs."""
    top_docs = [h["doc_title"] for h in hits[:n]]
    ranking = doc_ranking(hits)
    return {
        "repeats_in_top_chunks": len(top_docs) - len(set(top_docs)),
        "chunks_to_fill": ranking[n - 1]["chunk_rank"] if len(ranking) >= n else None,
    }


# ── relevance ────────────────────────────────────────────────────────────────

def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def similarity(a, b):
    """difflib ratio, with cheap upper bounds checked first. Returns 0.0 if a bound rules it out."""
    if not a or not b:
        return 1.0 if a == b else 0.0
    if 2 * min(len(a), len(b)) / (len(a) + len(b)) < NEAR_THRESHOLD:
        return 0.0
    m = SequenceMatcher(None, a, b, autojunk=False)
    if m.real_quick_ratio() < NEAR_THRESHOLD or m.quick_ratio() < NEAR_THRESHOLD:
        return 0.0
    return m.ratio()


def strict_classes(targets):
    return {t: {t: "target"} for t in targets}


def duplicate_classes(doc_texts, targets, threshold=NEAR_THRESHOLD):
    """
    For each target title, the documents that count as relevant in DUPLICATE-AWARE
    mode: {title: label}, label one of "target", "exact", "near (0.994)".
    Exact = identical text (sha256). Near = difflib ratio >= threshold against
    the target itself (pairwise, not transitive).
    """
    hashes = {title: text_hash(t) for title, t in doc_texts.items()}
    out = {}
    for target in targets:
        cls = {target: "target"}
        for title, text in doc_texts.items():
            if title == target:
                continue
            if hashes[title] == hashes[target]:
                cls[title] = "exact"
            else:
                r = similarity(doc_texts[target], text)
                if r >= threshold:
                    cls[title] = f"near ({r:.3f})"
        out[target] = cls
    return out


# ── scoring ──────────────────────────────────────────────────────────────────

def score(ranking, targets, classes, k):
    """
    Precision@k, Recall@k and reciprocal rank@k over a document ranking (titles).

    A document is relevant if it is in classes[t] for any target t, so in strict
    mode (classes = {t: {t}}) this is plain P/R/MRR over the target titles, and
    widening the classes can only raise each metric. Precision counts every
    relevant document, including several copies of one text. Recall counts each
    target once, credited to the first document in its class.
    """
    credited = {}
    relevant = []
    for rank, doc in enumerate(ranking[:k], start=1):
        matched = {t: classes[t][doc] for t in targets if doc in classes[t]}
        for t, label in matched.items():
            credited.setdefault(t, {"rank": rank, "doc": doc, "label": label})
        if matched:
            relevant.append({"rank": rank, "doc": doc, "matches": matched})
    return {
        "precision": len(relevant) / k,
        "recall": len(credited) / len(targets),
        "rr": 1 / relevant[0]["rank"] if relevant else 0.0,
        "credited": credited,
        "relevant": relevant,
    }
