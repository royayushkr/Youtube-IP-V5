from __future__ import annotations

import re
from typing import Mapping


SYNONYM_MAP = {
    "seo lab": "title and seo lab",
    "outlierfinder": "outlier finder",
}
PAGE_SCOPE_MAP = {
    "channel analysis": "channel_analysis",
    "recommendations": "recommendations",
    "ytuber": "ytuber",
    "outlier finder": "outlier_finder",
    "tools": "tools",
    "deployment": "deployment",
    "global": "global",
}
PAGE_STATE_MARKERS = {
    "this",
    "my",
    "these",
    "shown",
    "here",
    "current",
    "above",
    "below",
    "result",
    "results",
    "screen",
    "page",
}
FOLLOW_UP_MARKERS = {
    "this",
    "that",
    "those",
    "it",
    "them",
    "why",
    "how",
    "what next",
    "which one",
    "what about",
    "and that",
    "can i",
}


def normalize_query(text: str) -> str:
    normalized = str(text or "").strip().lower()
    for source, target in SYNONYM_MAP.items():
        normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized)
    normalized = re.sub(r"[^\w\s%]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def normalize_page_scope(page_name: str) -> str:
    normalized = normalize_query(page_name)
    return PAGE_SCOPE_MAP.get(normalized, normalized.replace(" ", "_") or "global")


def infer_context_mode(text: str) -> str:
    normalized = normalize_query(text)
    tokens = set(normalized.split())
    if tokens & PAGE_STATE_MARKERS:
        return "page_state"
    return "page_only"


def is_follow_up_query(text: str) -> bool:
    normalized = normalize_query(text)
    if not normalized:
        return False
    if len(normalized.split()) < 6:
        if set(normalized.split()) & FOLLOW_UP_MARKERS:
            return True
    return any(marker in normalized for marker in FOLLOW_UP_MARKERS)


def expand_follow_up_query(text: str, previous_user_query: str | None) -> str:
    normalized = normalize_query(text)
    if not normalized:
        return ""
    if previous_user_query and is_follow_up_query(text):
        previous = normalize_query(previous_user_query)
        if previous and previous not in normalized:
            return f"{previous} {normalized}".strip()
    return normalized


def apply_synonym_map(value: str, extra_synonyms: Mapping[str, str] | None = None) -> str:
    text = normalize_query(value)
    mapping = dict(SYNONYM_MAP)
    if extra_synonyms:
        mapping.update({normalize_query(k): normalize_query(v) for k, v in extra_synonyms.items()})
    for source, target in mapping.items():
        text = re.sub(rf"\b{re.escape(source)}\b", target, text)
    return normalize_query(text)
