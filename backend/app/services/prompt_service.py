from __future__ import annotations

import re
from typing import TypedDict

from langchain_core.prompts import PromptTemplate


class ParsedCitation(TypedDict):
    """One inline citation marker parsed from model output."""

    source_index: int
    quote: str


# Context is built by format_numbered_retrieval_context() — each chunk is ### Source n with URL/title/body.
template = """
You are an expert at answering questions about The University of Texas at Dallas (UTD).
Your audience is students, faculty, and staff. Be clear and accurate.

If you do not know the answer based on the sources below, say clearly that you do not know—do not guess or invent facts.
Do not make up an answer.

You are given NUMBERED SOURCES below. Each block is independent: Source 1, Source 2, …

CITATION PROTOCOL — read carefully; malformed citations are wrong answers.

WHAT [n, "…"] MUST BE:
• n = the source number from ### Source n.
• The quoted string MUST be copied character-for-character from THAT source’s BODY only — the text strictly between its two --- lines. Do not quote from the URL line, Title line, or anything outside the --- … --- block.
• The quote must be a SHORT span: usually one sentence or one clause (aim under ~220 characters). It must read like normal prose from the page, not a vocabulary list.

FORBIDDEN (never do this):
• Do not invent a long comma-separated list of topics/keywords and put it in quotes (e.g. "Telecommunication, Robotics, Navigation, …") — that is NOT a verbatim quote from the body.
• Do not use the page title (or the Title: field) as "EXACT_TEXT" unless that exact same title string appears inside the --- body --- text.
• Do not merge words from different sentences or paraphrase inside the quotes.
• If you cannot find a short literal substring in the body that supports the claim, do not fabricate a citation — rephrase the claim or say the source does not spell that out.

GOOD: one copied sentence or phrase you could Ctrl+F inside that source’s body.

Example shape (illustration only):
Students in the program take core courses in signals and systems [2, "The degree requires completing core coursework in circuits and signals analysis."]

---

NUMBERED SOURCES:
{context}

---

Question:
{question}

Answer in plain language. For each supported fact, add [n, "short verbatim quote from that source’s --- body --- only"] as above. If you cannot quote the body, do not fake a citation.
"""

rag_prompt_template = PromptTemplate.from_template(template)


def format_numbered_retrieval_context(
    chunks: list[tuple[str, str | None, str | None]],
) -> str:
    """
    Format retrieved chunks for the citation protocol.

    Each tuple is (body_text, url, title). Indices are 1-based ### Source n blocks.
    """
    parts: list[str] = []
    for i, (body, url, title) in enumerate(chunks, start=1):
        url_s = (url or "Unknown").strip()
        title_s = (title or "").strip()
        body_s = (body or "").strip()
        title_line = f"Title: {title_s}\n" if title_s else ""
        parts.append(
            f"### Source {i}\n"
            f"URL: {url_s}\n"
            f"{title_line}"
            f"---\n"
            f"{body_s}\n"
            f"---"
        )
    if not parts:
        return "(No retrieval context.)"
    return "\n\n".join(parts)


# Inline citations: [1, "verbatim quote"] possibly with escapes inside quotes
_INLINE_CITE_RE = re.compile(
    r"\[\s*(\d+)\s*,\s*\"((?:[^\"\\]|\\.)*)\"\s*\]"
)


def extract_inline_citations(answer: str) -> list[ParsedCitation]:
    """
    Parse citation markers from the assistant answer for the frontend.

    Returns ordered list of {source_index, quote}. Duplicates preserved if repeated.
    """
    out: list[ParsedCitation] = []
    for m in _INLINE_CITE_RE.finditer(answer or ""):
        idx = int(m.group(1))
        raw_q = m.group(2).replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")
        out.append({"source_index": idx, "quote": raw_q})
    return out
