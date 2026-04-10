from __future__ import annotations

import math
import re
from typing import Iterable

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: object) -> list[str]:
    if text is None:
        value = ""
    elif isinstance(text, float) and math.isnan(text):
        value = ""
    elif isinstance(text, str):
        value = text
    else:
        value = str(text)
    return TOKEN_PATTERN.findall(value.lower())


def unique_join(parts: Iterable[str]) -> str:
    seen: list[str] = []
    for part in parts:
        value = (part or "").strip()
        if value and value not in seen:
            seen.append(value)
    return "\n".join(seen)


def lexical_overlap_score(query: str, document: str) -> float:
    query_tokens = tokenize(query)
    doc_tokens = tokenize(document)
    if not query_tokens or not doc_tokens:
        return 0.0
    query_set = set(query_tokens)
    doc_set = set(doc_tokens)
    shared = len(query_set & doc_set)
    phrase_bonus = 0.25 if " ".join(query_tokens) in " ".join(doc_tokens) else 0.0
    return (shared / len(query_set)) + phrase_bonus
