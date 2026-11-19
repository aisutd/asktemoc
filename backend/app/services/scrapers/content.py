"""
Page cleaning, validation and hashing for the scheduled re-scrape.

A page is only stored when it came back HTTP 200 and has real content. Combined
certificate pages and certificate pages that are copies of a degree page are cut down
to the one certificate section the document is about. The content hash is taken over
normalized text, so changes to the "Updated:" stamp or to whitespace do not count.
"""

import hashlib
import re
import unicodedata
from typing import Optional

MIN_WORDS = 30
CATALOG_HEADER = "UT Dallas 2025 Undergraduate Catalog"

# Must stay identical to the pattern used when the stored hashes were computed.
_UPDATED_RE = re.compile(r"^\s*Updated:\s*\d{4}-\d{2}-\d{2}.*$", re.MULTILINE)


def sanitize(name: str) -> str:
    """Folder-style name for a program, e.g. 'BA in Education - 4-8 Science' -> 'ba_in_education_4_8_science'."""
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


def word_count(text: str) -> int:
    return len(text.split())


def validate(text: Optional[str], status: Optional[int]) -> Optional[str]:
    """Return why a fetched page must not be stored, or None if it is fine."""
    if status is not None and status != 200:
        return f"HTTP {status}"
    if not text or word_count(text) < MIN_WORDS:
        return f"too short ({word_count(text or '')} words)"
    return None


# --- certificate sections -------------------------------------------------

def cert_headings(lines: list[str]) -> list[tuple[int, str]]:
    """Real certificate section headings: a 'Certificate in ...' line whose very next
    non-empty line is its credit-hours line (table-of-contents entries are not)."""
    out = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s.startswith("Certificate in "):
            continue
        following = [x for x in lines[i + 1:i + 6] if x.strip()][:1]
        if following and "credit hours" in following[0]:
            out.append((i, s))
    return out


def _is_combined(lines: list[str]) -> bool:
    return len(lines) > 6 and lines[6].strip() == "Certificates"


def needs_section(text: str) -> bool:
    """True when a certificate page holds more than its own certificate: a school's
    combined page, or a degree page with the certificate section at the end."""
    lines = text.splitlines()
    heads = cert_headings(lines)
    return len(heads) >= 2 or (len(heads) == 1 and not _is_combined(lines))


def sections(text: str, wanted: Optional[str] = None) -> list[tuple[str, str]]:
    """(folder_name, section_text) for every certificate section on the page, or only the one
    whose folder name equals `wanted`."""
    lines = text.splitlines()
    heads = cert_headings(lines)
    prefix = CATALOG_HEADER + "\n"
    if _is_combined(lines):
        prefix += lines[5].strip() + "\n"
    prefix += "Certificates\n\n"
    out = []
    for n, (idx, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        folder = sanitize(title)
        if wanted is None or folder == wanted:
            body = _UPDATED_RE.sub("", "\n".join(lines[idx:end])).strip()
            out.append((folder, prefix + body))
    return out


def prepare_catalog_text(folder: str, text: str) -> tuple[Optional[str], Optional[str]]:
    """Text to store for a catalog page, or (None, reason) if it cannot be stored."""
    text = text.strip()
    if folder.startswith("certificate_in_") and needs_section(text):
        found = sections(text, folder)
        if not found:
            return None, "no certificate section found on page"
        return found[0][1], None
    return text, None


# --- Crawl4AI markdown ----------------------------------------------------

def clean_markdown(md: str) -> str:
    """Strip navigation and footer from a Crawl4AI page and flatten links to their text."""
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
