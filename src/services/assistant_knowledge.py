from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Tuple


KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "assistant"
KNOWLEDGE_FILES = (
    "product_help.json",
    "metric_definitions.json",
    "troubleshooting.json",
    "workflow_guidance.json",
)


@dataclass(frozen=True)
class KnowledgeRecord:
    id: str
    category: str
    title: str
    page_scope: str
    intent_types: Tuple[str, ...]
    tags: Tuple[str, ...]
    content: str
    related_ids: Tuple[str, ...]
    source_label: str
    retrieval_text: str


def _coerce_tuple(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return tuple()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _record_from_payload(payload: dict[str, Any]) -> KnowledgeRecord:
    title = str(payload.get("title", "")).strip()
    tags = _coerce_tuple(payload.get("tags"))
    content = str(payload.get("content", "")).strip()
    retrieval_text = " ".join(
        part for part in [title, " ".join(tags), content, str(payload.get("source_label", "")).strip()] if part
    )
    return KnowledgeRecord(
        id=str(payload.get("id", "")).strip(),
        category=str(payload.get("category", "")).strip(),
        title=title,
        page_scope=str(payload.get("page_scope", "global")).strip() or "global",
        intent_types=_coerce_tuple(payload.get("intent_types")),
        tags=tags,
        content=content,
        related_ids=_coerce_tuple(payload.get("related_ids")),
        source_label=str(payload.get("source_label", "")).strip() or "Knowledge Base",
        retrieval_text=retrieval_text,
    )


@lru_cache(maxsize=1)
def load_knowledge_records() -> Tuple[KnowledgeRecord, ...]:
    records: list[KnowledgeRecord] = []
    for file_name in KNOWLEDGE_FILES:
        path = KNOWLEDGE_DIR / file_name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            record = _record_from_payload(item)
            if record.id and record.title and record.content:
                records.append(record)
    return tuple(records)


def get_knowledge_records(page_scope: str) -> Tuple[KnowledgeRecord, ...]:
    return tuple(
        record
        for record in load_knowledge_records()
        if record.page_scope in {"global", page_scope}
    )


def get_knowledge_record(record_id: str) -> KnowledgeRecord | None:
    for record in load_knowledge_records():
        if record.id == record_id:
            return record
    return None


def get_related_question_titles(record_ids: Iterable[str], *, limit: int = 3) -> Tuple[str, ...]:
    titles: list[str] = []
    seen: set[str] = set()
    for record_id in record_ids:
        record = get_knowledge_record(record_id)
        if not record or not record.title or record.title in seen:
            continue
        seen.add(record.title)
        titles.append(record.title)
        if len(titles) >= limit:
            break
    return tuple(titles)
