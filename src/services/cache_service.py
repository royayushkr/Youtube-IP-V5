from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Tuple


ASSISTANT_DB_PATH = Path(__file__).resolve().parents[2] / "outputs" / "assistant" / "assistant_cache.db"


@dataclass(frozen=True)
class CachedAnswerRecord:
    id: int
    query_text: str
    normalized_query: str
    page_scope: str
    context_mode: str
    intent_type: str
    retrieval_text: str
    answer_text: str
    answer_source_type: str
    confidence: float
    source_refs: Tuple[dict[str, Any], ...]
    related_questions: Tuple[str, ...]
    page_context: dict[str, Any]
    model_provider: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    created_at: str
    last_used_at: str
    use_count: int
    helpful_count: int
    unhelpful_count: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _connect() -> sqlite3.Connection:
    ASSISTANT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(ASSISTANT_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_cache_db() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS assistant_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                page_scope TEXT NOT NULL,
                context_mode TEXT NOT NULL,
                intent_type TEXT NOT NULL,
                retrieval_text TEXT NOT NULL,
                answer_text TEXT NOT NULL,
                answer_source_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                source_refs_json TEXT NOT NULL,
                related_questions_json TEXT NOT NULL,
                page_context_json TEXT NOT NULL,
                model_provider TEXT NOT NULL DEFAULT '',
                model_name TEXT NOT NULL DEFAULT '',
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                use_count INTEGER NOT NULL DEFAULT 1,
                helpful_count INTEGER NOT NULL DEFAULT 0,
                unhelpful_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS assistant_feedback_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                answer_id INTEGER NOT NULL,
                rating TEXT NOT NULL,
                created_at TEXT NOT NULL,
                page_scope TEXT NOT NULL,
                FOREIGN KEY(answer_id) REFERENCES assistant_answers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_assistant_answers_exact
                ON assistant_answers(normalized_query, page_scope, context_mode);
            CREATE INDEX IF NOT EXISTS idx_assistant_answers_scope
                ON assistant_answers(page_scope, created_at);
            CREATE INDEX IF NOT EXISTS idx_assistant_feedback_answer
                ON assistant_feedback_events(answer_id);
            """
        )


def _row_to_record(row: sqlite3.Row) -> CachedAnswerRecord:
    return CachedAnswerRecord(
        id=int(row["id"]),
        query_text=str(row["query_text"]),
        normalized_query=str(row["normalized_query"]),
        page_scope=str(row["page_scope"]),
        context_mode=str(row["context_mode"]),
        intent_type=str(row["intent_type"]),
        retrieval_text=str(row["retrieval_text"]),
        answer_text=str(row["answer_text"]),
        answer_source_type=str(row["answer_source_type"]),
        confidence=float(row["confidence"]),
        source_refs=tuple(_json_loads(row["source_refs_json"], [])),
        related_questions=tuple(_json_loads(row["related_questions_json"], [])),
        page_context=dict(_json_loads(row["page_context_json"], {})),
        model_provider=str(row["model_provider"] or ""),
        model_name=str(row["model_name"] or ""),
        prompt_tokens=int(row["prompt_tokens"] or 0),
        completion_tokens=int(row["completion_tokens"] or 0),
        created_at=str(row["created_at"]),
        last_used_at=str(row["last_used_at"]),
        use_count=int(row["use_count"] or 0),
        helpful_count=int(row["helpful_count"] or 0),
        unhelpful_count=int(row["unhelpful_count"] or 0),
    )


def fetch_answer_by_id(answer_id: int) -> CachedAnswerRecord | None:
    initialize_cache_db()
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM assistant_answers WHERE id = ?",
            (answer_id,),
        ).fetchone()
    return _row_to_record(row) if row else None


def fetch_exact_cached_answer(
    normalized_query: str,
    page_scope: str,
    context_mode: str,
    *,
    max_age_days: int = 30,
    min_confidence: float = 0.75,
) -> CachedAnswerRecord | None:
    initialize_cache_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM assistant_answers
            WHERE normalized_query = ?
              AND page_scope = ?
              AND context_mode = ?
              AND created_at >= ?
            ORDER BY helpful_count DESC, use_count DESC, created_at DESC
            LIMIT 1
            """,
            (normalized_query, page_scope, context_mode, cutoff),
        ).fetchone()
    if not row:
        return None
    record = _row_to_record(row)
    if record.helpful_count < record.unhelpful_count or record.confidence < min_confidence:
        return None
    return record


def list_cached_answers_for_scope(
    page_scope: str,
    *,
    max_age_days: int = 90,
) -> Tuple[CachedAnswerRecord, ...]:
    initialize_cache_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM assistant_answers
            WHERE page_scope IN (?, 'global')
              AND created_at >= ?
            ORDER BY created_at DESC
            """,
            (page_scope, cutoff),
        ).fetchall()
    return tuple(_row_to_record(row) for row in rows)


def store_answer(
    *,
    query_text: str,
    normalized_query: str,
    page_scope: str,
    context_mode: str,
    intent_type: str,
    retrieval_text: str,
    answer_text: str,
    answer_source_type: str,
    confidence: float,
    source_refs: Iterable[dict[str, Any]],
    related_questions: Iterable[str],
    page_context: dict[str, Any],
    model_provider: str = "",
    model_name: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> CachedAnswerRecord:
    initialize_cache_db()
    timestamp = _now_iso()
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO assistant_answers (
                query_text,
                normalized_query,
                page_scope,
                context_mode,
                intent_type,
                retrieval_text,
                answer_text,
                answer_source_type,
                confidence,
                source_refs_json,
                related_questions_json,
                page_context_json,
                model_provider,
                model_name,
                prompt_tokens,
                completion_tokens,
                created_at,
                last_used_at,
                use_count,
                helpful_count,
                unhelpful_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 0)
            """,
            (
                query_text,
                normalized_query,
                page_scope,
                context_mode,
                intent_type,
                retrieval_text,
                answer_text,
                answer_source_type,
                confidence,
                _json_dumps(list(source_refs)),
                _json_dumps([item for item in related_questions if str(item).strip()]),
                _json_dumps(page_context),
                model_provider,
                model_name,
                prompt_tokens,
                completion_tokens,
                timestamp,
                timestamp,
            ),
        )
        record_id = int(cursor.lastrowid)
    record = fetch_answer_by_id(record_id)
    if record is None:
        raise RuntimeError("Assistant cache write failed.")
    return record


def mark_answer_used(answer_id: int) -> None:
    initialize_cache_db()
    with _connect() as connection:
        connection.execute(
            """
            UPDATE assistant_answers
            SET use_count = use_count + 1,
                last_used_at = ?
            WHERE id = ?
            """,
            (_now_iso(), answer_id),
        )


def record_feedback(answer_id: int, rating: str, page_scope: str) -> None:
    initialize_cache_db()
    rating_value = "helpful" if rating == "helpful" else "not_helpful"
    column = "helpful_count" if rating_value == "helpful" else "unhelpful_count"
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO assistant_feedback_events (answer_id, rating, created_at, page_scope)
            VALUES (?, ?, ?, ?)
            """,
            (answer_id, rating_value, _now_iso(), page_scope),
        )
        connection.execute(
            f"""
            UPDATE assistant_answers
            SET {column} = {column} + 1
            WHERE id = ?
            """,
            (answer_id,),
        )
