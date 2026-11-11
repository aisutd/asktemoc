"""
corpus_prep.py — turn raw scraped files into the documents that get embedded.

Fixes applied before ingestion:
  - combined certificate pages and degree-page copies are cut down to the one
    certificate section each document is about
  - the three identical catalog index pages become a single overview document
  - Crawl4AI markdown has its navigation and footer stripped
  - text_hash() gives every document a stable content hash (volatile stamps removed)
"""

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
CORPUS_DIR = HERE / "test_output"
WEB_DIR = HERE / "crawl4ai_output"

CATALOG_HEADER = "UT Dallas 2025 Undergraduate Catalog"
INDEX_FOLDERS = ("1", "2", "3")
OVERVIEW_FOLDER = "undergraduate_catalog_overview"

_UPDATED_RE = re.compile(r"^\s*Updated:\s*\d{4}-\d{2}-\d{2}.*$", re.MULTILINE)


def sanitize(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[-\s]+", "_", name)
    return name.strip("_").lower()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _UPDATED_RE.sub("", text)
    text = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


def cert_headings(lines: list[str]) -> list[tuple[int, str]]:
    """Real certificate section headings: a 'Certificate in …' line followed by a credit-hours line."""
    out = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s.startswith("Certificate in "):
            continue
        following = [x for x in lines[i + 1:i + 6] if x.strip()][:1]
        if following and "credit hours" in following[0]:
            out.append((i, s))
    return out


def _section_for(text: str, wanted: str | None) -> list[tuple[str, str]]:
    """Return (folder_name, section_text) for every certificate section on the page,
    or only the one whose folder name equals `wanted`."""
    lines = text.splitlines()
    heads = cert_headings(lines)
    combined = len(lines) > 6 and lines[6].strip() == "Certificates"
    prefix = CATALOG_HEADER + "\n"
    if combined:
        prefix += lines[5].strip() + "\n"
    prefix += "Certificates\n\n"
    sections = []
    for n, (idx, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        folder = sanitize(title)
        if wanted is None or folder == wanted:
            body = "\n".join(lines[idx:end]).strip()
            sections.append((folder, prefix + _UPDATED_RE.sub("", body).strip()))
    return sections


def extract_certificate_section(text: str, folder: str) -> str | None:
    found = _section_for(text, folder)
    return found[0][1] if found else None


def clean_markdown(md: str, name: str) -> str:
    """Strip nav/footer from a Crawl4AI page and flatten links to their text."""
    lines = md.splitlines()
    start = 0
    for i, ln in enumerate(lines):
        if ln.startswith("# ") and not ln.startswith("#  ["):
            start = i
            break
    else:
        for i, ln in enumerate(lines):
            if ln.startswith("## [News]"):
                start = i
                break
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## Copyright Information") or lines[i].startswith("[Privacy Policy]"):
            end = i
            break
    body = "\n".join(lines[start:end])
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    body = re.sub(r"\[([^\]]*)\]\((?:[^()]|\([^)]*\))*\)", r"\1", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _doc(key: str, title: str, source: str, text: str, kind: str, meta: dict | None = None) -> dict:
    return {
        "key": key,
        "title": title,
        "source": source,
        "text": text,
        "kind": kind,
        "metadata": {**(meta or {}), "content_hash": text_hash(text)},
    }


def prepare_documents() -> tuple[list[dict], list[str], list[str]]:
    """Build the documents to embed.

    Returns (documents, dropped_keys, flagged) where dropped_keys are corpus keys that
    must not exist in the database any more and flagged lists certificates whose own
    section could not be found (they need a re-scrape).
    """
    raw: dict[str, str] = {}
    for p in sorted(CORPUS_DIR.rglob("*.txt")):
        raw[str(p.relative_to(CORPUS_DIR))] = p.read_text(encoding="utf-8", errors="replace").strip()

    by_hash = defaultdict(list)
    for k, t in raw.items():
        by_hash[text_hash(t)].append(k)
    dup_keys = {k for ks in by_hash.values() if len(ks) > 1 for k in ks}

    docs, dropped, flagged = [], [], []
    existing_folders = {k.split("/")[0] for k in raw}
    overview_text = None

    for key, text in raw.items():
        folder, fname = key.split("/")
        stem = fname.removesuffix(".txt")
        title = f"{folder}/{stem}"
        meta = {"program": folder, "file": stem}
        src = f"test_output/{key}"

        if folder in INDEX_FOLDERS:
            dropped.append(key)
            if folder == INDEX_FOLDERS[0]:
                overview_text = text
            continue

        if folder.startswith("certificate_in_") and key in dup_keys:
            if stem != "requirements":
                dropped.append(key)
                continue
            section = extract_certificate_section(text, folder)
            if section is None:
                flagged.append(key)
                dropped.append(key)
                continue
            docs.append(_doc(key, title, src, section, "certificate-section", meta))
            for sec_folder, sec_text in _section_for(text, None):
                if sec_folder not in existing_folders and sec_folder not in {d["metadata"].get("program") for d in docs}:
                    skey = f"{sec_folder}/requirements.txt"
                    docs.append(_doc(skey, f"{sec_folder}/requirements", f"test_output/{skey}",
                                     sec_text, "certificate-section",
                                     {"program": sec_folder, "file": "requirements",
                                      "derived_from": key}))
            continue

        docs.append(_doc(key, title, src, text, "catalog", meta))

    if overview_text:
        okey = f"{OVERVIEW_FOLDER}/requirements.txt"
        docs.append(_doc(okey, f"{OVERVIEW_FOLDER}/requirements", f"test_output/{okey}",
                         overview_text, "catalog-overview",
                         {"program": OVERVIEW_FOLDER, "file": "requirements",
                          "derived_from": f"{INDEX_FOLDERS[0]}/requirements.txt"}))

    urls = {}
    summary = WEB_DIR / "summary.json"
    if summary.exists():
        urls = {d["name"]: d["url"] for d in json.loads(summary.read_text())}
    for p in sorted(WEB_DIR.glob("*.md")):
        text = clean_markdown(p.read_text(encoding="utf-8"), p.stem)
        url = urls.get(p.stem, f"crawl4ai_output/{p.name}")
        docs.append(_doc(f"web/{p.name}", f"web/{p.stem}", url, text, "web",
                         {"program": "web", "file": p.stem}))

    # de-duplicate by prepared content (keeps the first, remembers the rest)
    seen: dict[str, dict] = {}
    unique = []
    for d in docs:
        h = d["metadata"]["content_hash"]
        if h in seen:
            seen[h]["metadata"].setdefault("duplicate_sources", []).append(d["source"])
            dropped.append(d["key"])
            continue
        seen[h] = d
        unique.append(d)
    return unique, dropped, flagged
