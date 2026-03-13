from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.services.assistant_knowledge import KnowledgeRecord, get_knowledge_records
from src.services.cache_service import CachedAnswerRecord, list_cached_answers_for_scope


_VECTORIZER_KWARGS = {
    "ngram_range": (1, 2),
    "strip_accents": "unicode",
    "lowercase": True,
    "min_df": 1,
}
_knowledge_state: dict[str, object] = {}
_cache_state: dict[str, object] = {}


@dataclass(frozen=True)
class KnowledgeMatch:
    record: KnowledgeRecord
    score: float


@dataclass(frozen=True)
class CachedAnswerMatch:
    record: CachedAnswerRecord
    score: float


def _fingerprint(items: Sequence[tuple[object, ...]]) -> tuple[object, ...]:
    return tuple(items)


def _build_matrix_state(state: dict[str, object], fingerprint: tuple[object, ...], texts: Sequence[str]) -> tuple[TfidfVectorizer, object]:
    if state.get("fingerprint") == fingerprint and state.get("vectorizer") is not None and state.get("matrix") is not None:
        return state["vectorizer"], state["matrix"]

    vectorizer = TfidfVectorizer(**_VECTORIZER_KWARGS)
    matrix = vectorizer.fit_transform(texts)
    state["fingerprint"] = fingerprint
    state["vectorizer"] = vectorizer
    state["matrix"] = matrix
    return vectorizer, matrix


def search_knowledge(query_text: str, page_scope: str, *, limit: int = 5) -> Tuple[KnowledgeMatch, ...]:
    records = list(get_knowledge_records(page_scope))
    if not records:
        return tuple()
    fingerprint = _fingerprint([(record.id, record.page_scope, record.title) for record in records])
    vectorizer, matrix = _build_matrix_state(_knowledge_state, fingerprint, [record.retrieval_text for record in records])
    query_vector = vectorizer.transform([query_text])
    scores = cosine_similarity(query_vector, matrix).ravel()
    order = np.argsort(scores)[::-1]
    matches = [
        KnowledgeMatch(record=records[index], score=float(scores[index]))
        for index in order[:limit]
        if float(scores[index]) > 0
    ]
    return tuple(matches)


def search_cached_answers(query_text: str, page_scope: str, *, limit: int = 5) -> Tuple[CachedAnswerMatch, ...]:
    records = list(list_cached_answers_for_scope(page_scope))
    if not records:
        return tuple()
    fingerprint = _fingerprint(
        [
            (
                record.id,
                record.page_scope,
                record.created_at,
                record.helpful_count,
                record.unhelpful_count,
                record.use_count,
            )
            for record in records
        ]
    )
    vectorizer, matrix = _build_matrix_state(
        _cache_state,
        fingerprint,
        [f"{record.normalized_query} {record.retrieval_text}" for record in records],
    )
    query_vector = vectorizer.transform([query_text])
    scores = cosine_similarity(query_vector, matrix).ravel()
    order = np.argsort(scores)[::-1]
    matches = [
        CachedAnswerMatch(record=records[index], score=float(scores[index]))
        for index in order[:limit]
        if float(scores[index]) > 0
    ]
    return tuple(matches)


def clear_retrieval_caches() -> None:
    _knowledge_state.clear()
    _cache_state.clear()
