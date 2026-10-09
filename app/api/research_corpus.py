"""Server-side Bible/ancient-text corpus for /v1/research/ask.

Authoritative for retrieval + citation metadata. The client independently
re-validates citations, but the server is the source of truth for which
references are canonical vs apocrypha/non-canonical so a non-canonical text
can NEVER be returned as Scripture.

Corpus currently bundles the public-domain WEB + KJV (canonical). The catalog
below also recognizes deuterocanonical / apocryphal / pseudepigraphal works so
their references are classified honestly (status != canonical) even before
those texts are added to the retrievable corpus.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bible")

CANONICAL_BOOKS = {
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA", "1KI",
    "2KI", "1CH", "2CH", "EZR", "NEH", "EST", "JOB", "PSA", "PRO", "ECC", "SNG",
    "ISA", "JER", "LAM", "EZE", "DAN", "HOS", "JOL", "AMO", "OBA", "JON", "MIC",
    "NAH", "HAB", "ZEP", "HAG", "ZEC", "MAL", "MAT", "MRK", "LUK", "JOH", "ACT",
    "ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI",
    "TIT", "PHM", "HEB", "JAM", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV",
}

# Titles that are deuterocanonical/apocryphal/pseudepigraphal — NOT canonical.
NON_CANON_TITLES = {
    "tobit", "judith", "wisdom", "sirach", "baruch", "1 maccabees", "2 maccabees",
    "1 enoch", "2 enoch", "jubilees", "testament of", "psalms of solomon",
    "dead sea scrolls", "community rule", "damascus document",
}

_BOOK_NAME_TO_ID = {
    "genesis": "GEN", "exodus": "EXO", "leviticus": "LEV", "numbers": "NUM",
    "deuteronomy": "DEU", "joshua": "JOS", "judges": "JDG", "ruth": "RUT",
    "1 samuel": "1SA", "2 samuel": "2SA", "1 kings": "1KI", "2 kings": "2KI",
    "1 chronicles": "1CH", "2 chronicles": "2CH", "ezra": "EZR", "nehemiah": "NEH",
    "esther": "EST", "job": "JOB", "psalms": "PSA", "psalm": "PSA", "proverbs": "PRO",
    "ecclesiastes": "ECC", "song of solomon": "SNG", "isaiah": "ISA", "jeremiah": "JER",
    "lamentations": "LAM", "ezekiel": "EZE", "daniel": "DAN", "hosea": "HOS",
    "joel": "JOL", "amos": "AMO", "obadiah": "OBA", "jonah": "JON", "micah": "MIC",
    "nahum": "NAH", "habakkuk": "HAB", "zephaniah": "ZEP", "haggai": "HAG",
    "zechariah": "ZEC", "malachi": "MAL", "matthew": "MAT", "mark": "MRK", "luke": "LUK",
    "john": "JOH", "jhn": "JOH", "acts": "ACT", "romans": "ROM",
    "1 corinthians": "1CO", "2 corinthians": "2CO", "galatians": "GAL",
    "ephesians": "EPH", "philippians": "PHP", "colossians": "COL",
    "1 thessalonians": "1TH", "2 thessalonians": "2TH", "1 timothy": "1TI",
    "2 timothy": "2TI", "titus": "TIT", "philemon": "PHM", "hebrews": "HEB",
    "james": "JAM", "1 peter": "1PE", "2 peter": "2PE", "1 john": "1JN",
    "2 john": "2JN", "3 john": "3JN", "jude": "JUD", "revelation": "REV",
}

_EDITIONS = {
    "WEB": {"title": "World English Bible", "date": "2000 (public domain)", "edition": "World English Bible"},
    "KJV": {"title": "King James Version", "date": "1769 (Blayney revision)", "edition": "King James Version, 1769"},
}


def _load(work: str) -> Optional[dict]:
    path = os.path.join(_DIR, f"{work.lower()}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


_CORPUS: dict[str, dict] = {}
for _w in ("WEB", "KJV"):
    _CORPUS[_w] = _load(_w) or {}


def classify_ref(ref: str, work: str = "WEB") -> dict:
    """Server-authoritative source metadata for a reference.

    Returns {ref, work, status, tradition, classification, date, edition,
    unverified?}. A non-canonical reference is NEVER returned with
    status='canonical' — that is enforced here, not by any model output.
    """
    raw = ref.strip()
    ed = _EDITIONS.get(work.upper(), _EDITIONS.get(work.upper(), {"title": work, "date": "unknown", "edition": work}))
    m = re.match(r"^([A-Z0-9]+):(\d+)(?::(\d+))?$", raw)
    book_id = None
    if m and m.group(1) in CANONICAL_BOOKS:
        book_id = m.group(1)
    else:
        nm = re.match(r"^([1-3]?\s*[A-Za-z][A-Za-z ]*?)\s*(\d+)", raw)
        if nm:
            br = nm.group(1).strip().lower()
            book_id = _BOOK_NAME_TO_ID.get(br) or (br.upper().replace(" ", "") if br.upper().replace(" ", "") in CANONICAL_BOOKS else None)
    if book_id and book_id in CANONICAL_BOOKS:
        return {"ref": ref, "work": work, "status": "canonical", "tradition": "protestant",
                "classification": "canonical", "date": ed["date"], "edition": ed["edition"]}
    low = raw.lower()
    if any(t in low for t in NON_CANON_TITLES):
        return {"ref": ref, "work": work, "status": "non-canonical", "tradition": "general",
                "classification": "apocrypha", "date": "see catalog", "edition": raw.split(" ")[0]}
    return {"ref": ref, "work": work, "unverified": True}


def verse_text(ref: str, work: str = "WEB") -> Optional[str]:
    """Return the verse text for BOOK:CH:V (colon form) or None."""
    m = re.match(r"^([A-Z0-9]+):(\d+):(\d+)$", ref.strip())
    if not m:
        return None
    bid, ch, vs = m.group(1), int(m.group(2)), int(m.group(3))
    corpus = _CORPUS.get(work.upper())
    if not corpus:
        return None
    book = next((b for b in corpus["books"] if b["id"] == bid), None)
    if not book or len(book["chapters"]) < ch:
        return None
    verses = book["chapters"][ch - 1]
    if len(verses) < vs:
        return None
    return verses[vs - 1]


_STOP = {"the", "and", "of", "to", "a", "in", "is", "that", "for", "with", "on", "as", "are",
         "be", "this", "it", "from", "by", "an", "or", "at", "his", "he", "was", "were", "will"}


def retrieve(question: str, works: list[str] | None = None, top_k: int = 6) -> list[dict]:
    """Grounded lexical retrieval over the bundled canonical corpus.

    ponytail: TF-style word-overlap scoring, not embeddings — the corpus is
    small (2 translations) and this needs no external service. Swap for a
    vector index when more translations/ancient texts are added.
    """
    q = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in _STOP}
    works = works or ["WEB", "KJV"]
    hits: list[dict] = []
    for work in works:
        corpus = _CORPUS.get(work.upper())
        if not corpus:
            continue
        for book in corpus["books"]:
            for ci, verses in enumerate(book["chapters"], start=1):
                for vi, text in enumerate(verses, start=1):
                    if not text:
                        continue
                    words = set(re.findall(r"[a-z0-9]+", text.lower()))
                    score = len(q & words)
                    if score == 0:
                        continue
                    ref = f"{book['id']}:{ci}:{vi}"
                    hits.append({
                        "ref": ref, "text": text, "work": work.upper(), "score": score,
                        "meta": classify_ref(ref, work),
                    })
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:top_k]
