"""Checks on the hand-labeled query-router data in backend/router/data/."""

import csv
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "router" / "data"
EVAL_SET = BACKEND / "eval" / "eval_set.json"

LABELS = {"housing", "academics", "general"}
IN_CORPUS = {"yes", "no", "unsure"}


def read(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def norm(query):
    return " ".join(query.lower().split())


@pytest.mark.parametrize("name", ["labels_batch1.csv", "eval_set_check.csv"])
def test_no_duplicate_queries(name):
    queries = [norm(row["query"]) for row in read(name)]
    assert len(queries) == len(set(queries))


@pytest.mark.parametrize("name", ["labels_batch1.csv", "eval_set_check.csv"])
def test_valid_label_and_in_corpus(name):
    for row in read(name):
        assert row["label"] in LABELS, row
        assert row["in_corpus"] in IN_CORPUS, row


def test_every_batch1_row_has_a_split():
    for row in read("labels_batch1.csv"):
        assert row["split"] in {"train", "test"}, row


def test_eval_set_check_matches_eval_set():
    questions = json.loads(EVAL_SET.read_text(encoding="utf-8"))["questions"]
    rows = read("eval_set_check.csv")
    assert [norm(r["query"]) for r in rows] == [norm(q["question"]) for q in questions]
    assert {r["label"] for r in rows} == {"academics"}
    assert {r["source"] for r in rows} == {"eval_set"}


def test_no_eval_set_question_in_batch1():
    questions = json.loads(EVAL_SET.read_text(encoding="utf-8"))["questions"]
    eval_queries = {norm(q["question"]) for q in questions}
    leaked = [row["id"] for row in read("labels_batch1.csv") if norm(row["query"]) in eval_queries]
    assert leaked == []
