from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence, Tuple

import requests

from src.services.assistant_knowledge import KnowledgeRecord, get_related_question_titles
from src.services.cache_service import (
    CachedAnswerRecord,
    fetch_exact_cached_answer,
    mark_answer_used,
    record_feedback,
    store_answer,
)
from src.services.retrieval_service import CachedAnswerMatch, KnowledgeMatch, search_cached_answers, search_knowledge
from src.services.youtube_tools import ffmpeg_available
from src.utils.api_keys import get_provider_key_count, run_with_provider_keys
from src.utils.text_normalization import expand_follow_up_query, infer_context_mode, normalize_page_scope, normalize_query


GEMINI_MODEL = "gemini-2.5-flash-lite"
OPENAI_MODEL = "gpt-4o-mini"
SOURCE_LABELS = {
    "exact_cache": "Cached Answer",
    "semantic_cache": "Similar Answer",
    "knowledge": "Knowledge Base",
    "hybrid": "Hybrid",
    "llm": "AI Generated",
    "clarifying": "Clarification",
}
INTENT_TYPES = (
    "product_support",
    "metric_interpretation",
    "creator_strategy",
    "troubleshooting",
    "workflow_recommendation",
    "feature_onboarding",
)
STARTER_PROMPTS = {
    "global": (
        "Which Page Should I Start With",
        "What Should I Optimize First",
        "How Do I Interpret The Main Metrics",
        "Why Is My Video Not Performing",
    ),
    "outlier_finder": (
        "How Do I Read The Outlier Score",
        "Why Did This Scan Return Weak Results",
        "What Should I Look At First In Breakout Snapshot",
        "How Should I Use These Outliers For New Ideas",
    ),
    "ytuber": (
        "How Do I Use Ytuber Most Effectively",
        "What Does Title And SEO Lab Tell Me",
        "What Should I Optimize First On This Channel",
        "When Should I Use AI Studio",
    ),
    "channel_insights": (
        "What Does Channel Insights Tell Me",
        "How Should I Use Snapshot History",
        "What Should I Double Down On Here",
        "How Are These Topic Trends Calculated",
    ),
    "tools": (
        "How Do I Export A Transcript",
        "Why Did My Download Fail",
        "When Should I Use Batch Versus Playlist",
        "Why Does FFmpeg Matter Here",
    ),
    "channel_analysis": (
        "What Does This Benchmark View Tell Me",
        "Which Metrics Matter Most Here",
        "How Should I Use This With Ytuber",
        "How Do I Turn This Into A Plan",
    ),
    "recommendations": (
        "How Should I Use Recommendations",
        "What Should I Copy From High Performers",
        "When Should I Generate Thumbnail Ideas",
        "How Do I Turn This Into A Publishing Plan",
    ),
}


@dataclass(frozen=True)
class AssistantReply:
    answer_id: int | None
    question: str
    normalized_query: str
    page_scope: str
    intent_type: str
    source_type: str
    confidence: float
    confidence_label: str
    answer_text: str
    source_refs: Tuple[dict[str, str], ...]
    related_questions: Tuple[str, ...]
    retrieval_only_notice: str = ""
    clarifying: bool = False


def starter_prompts_for_page(page_scope: str) -> Tuple[str, ...]:
    return STARTER_PROMPTS.get(page_scope, STARTER_PROMPTS["global"])


def _confidence_label(value: float) -> str:
    if value >= 0.85:
        return "High"
    if value >= 0.6:
        return "Medium"
    return "Low"


def _source_ref(title: str, source_label: str, excerpt: str) -> dict[str, str]:
    return {
        "title": title.strip(),
        "source_label": source_label.strip(),
        "excerpt": excerpt.strip(),
    }


def _cache_record_source_refs(record: CachedAnswerRecord) -> Tuple[dict[str, str], ...]:
    refs = tuple(
        _source_ref(
            str(item.get("title", "")),
            str(item.get("source_label", "Assistant Cache")),
            str(item.get("excerpt", "")),
        )
        for item in record.source_refs
        if isinstance(item, dict)
    )
    if refs:
        return refs
    excerpt = record.answer_text[:220].strip()
    return (_source_ref("Previously Resolved Question", "Assistant Cache", excerpt),)


def _knowledge_match_refs(matches: Sequence[KnowledgeMatch], *, limit: int = 3) -> Tuple[dict[str, str], ...]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in matches:
        key = match.record.id
        if key in seen:
            continue
        seen.add(key)
        refs.append(_source_ref(match.record.title, match.record.source_label, match.record.content[:220]))
        if len(refs) >= limit:
            break
    return tuple(refs)


def _cached_match_refs(matches: Sequence[CachedAnswerMatch], *, limit: int = 2) -> Tuple[dict[str, str], ...]:
    refs: list[dict[str, str]] = []
    seen: set[int] = set()
    for match in matches:
        if match.record.id in seen:
            continue
        seen.add(match.record.id)
        refs.append(
            _source_ref(
                "Similar Resolved Question",
                "Assistant Cache",
                match.record.answer_text[:220],
            )
        )
        if len(refs) >= limit:
            break
    return tuple(refs)


def _dedupe_texts(values: Iterable[str], *, limit: int = 3) -> Tuple[str, ...]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
        if len(items) >= limit:
            break
    return tuple(items)


def _extract_sentences(text: str, *, limit: int = 3) -> Tuple[str, ...]:
    parts = [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]
    return _dedupe_texts((f"{part}." for part in parts), limit=limit)


def _build_direct_knowledge_answer(
    match: KnowledgeMatch,
    *,
    normalized_query: str,
    related_questions: Sequence[str],
    confidence: float,
    question: str,
    page_scope: str,
    context_mode: str,
    intent_type: str,
    page_context: dict[str, Any],
) -> AssistantReply:
    confidence = max(confidence, 0.78)
    supporting_points = _extract_sentences(match.record.content, limit=3)
    bullet_lines = "\n".join(f"{index}. {line}" for index, line in enumerate(supporting_points, start=1))
    answer_text = match.record.content
    if bullet_lines:
        answer_text = f"{answer_text}\n\nWhat To Do Next:\n{bullet_lines}"
    source_refs = (_source_ref(match.record.title, match.record.source_label, match.record.content[:220]),)
    cached = store_answer(
        query_text=question,
        normalized_query=normalized_query,
        page_scope=page_scope,
        context_mode=context_mode,
        intent_type=intent_type,
        retrieval_text=f"{normalize_query(question)} {match.record.retrieval_text} {answer_text}",
        answer_text=answer_text,
        answer_source_type="knowledge",
        confidence=confidence,
        source_refs=source_refs,
        related_questions=related_questions,
        page_context=page_context,
    )
    return AssistantReply(
        answer_id=cached.id,
        question=question,
        normalized_query=normalized_query,
        page_scope=page_scope,
        intent_type=intent_type,
        source_type="knowledge",
        confidence=confidence,
        confidence_label=_confidence_label(confidence),
        answer_text=answer_text,
        source_refs=source_refs,
        related_questions=tuple(related_questions),
    )


def _build_hybrid_answer(
    question: str,
    *,
    normalized_query: str,
    page_scope: str,
    context_mode: str,
    intent_type: str,
    page_context: dict[str, Any],
    knowledge_matches: Sequence[KnowledgeMatch],
    cached_matches: Sequence[CachedAnswerMatch],
    retrieval_only_notice: str = "",
) -> AssistantReply:
    knowledge_lines = []
    for match in knowledge_matches[:2]:
        knowledge_lines.extend(_extract_sentences(match.record.content, limit=1))
    cached_lines = []
    for match in cached_matches[:2]:
        cached_lines.extend(_extract_sentences(match.record.answer_text, limit=1))
    bullets = _dedupe_texts((*knowledge_lines, *cached_lines), limit=4)

    intro = "Here is the strongest answer based on the product knowledge and similar resolved questions."
    if bullets:
        answer_text = intro + "\n\n" + "\n".join(f"{index}. {bullet}" for index, bullet in enumerate(bullets, start=1))
    else:
        answer_text = intro

    source_refs = _dedupe_source_refs((*_knowledge_match_refs(knowledge_matches), *_cached_match_refs(cached_matches)))
    related_questions = _dedupe_texts(
        (
            *get_related_question_titles([match.record.id for match in knowledge_matches[:3]], limit=3),
            *(question for match in cached_matches[:2] for question in match.record.related_questions),
        ),
        limit=3,
    )
    confidence = max(
        [0.0]
        + [match.score for match in knowledge_matches[:2]]
        + [match.score for match in cached_matches[:2]]
    )
    cached = store_answer(
        query_text=question,
        normalized_query=normalized_query,
        page_scope=page_scope,
        context_mode=context_mode,
        intent_type=intent_type,
        retrieval_text=_build_retrieval_text(question, source_refs, answer_text),
        answer_text=answer_text,
        answer_source_type="hybrid",
        confidence=confidence,
        source_refs=source_refs,
        related_questions=related_questions,
        page_context=page_context,
    )
    return AssistantReply(
        answer_id=cached.id,
        question=question,
        normalized_query=normalized_query,
        page_scope=page_scope,
        intent_type=intent_type,
        source_type="hybrid",
        confidence=confidence,
        confidence_label=_confidence_label(confidence),
        answer_text=answer_text,
        source_refs=source_refs,
        related_questions=related_questions,
        retrieval_only_notice=retrieval_only_notice,
    )


def _dedupe_source_refs(refs: Iterable[dict[str, str]], *, limit: int = 4) -> Tuple[dict[str, str], ...]:
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = (ref.get("title", ""), ref.get("source_label", ""))
        if key in seen or not key[0]:
            continue
        seen.add(key)
        items.append(ref)
        if len(items) >= limit:
            break
    return tuple(items)


def _build_retrieval_text(question: str, source_refs: Iterable[dict[str, str]], answer_text: str) -> str:
    return " ".join(
        part
        for part in [
            normalize_query(question),
            " ".join(ref.get("title", "") for ref in source_refs),
            " ".join(ref.get("excerpt", "") for ref in source_refs),
            answer_text,
        ]
        if part
    )


def _extract_json_block(text: str) -> dict[str, Any] | None:
    candidate = str(text or "").strip()
    if not candidate:
        return None
    if "```json" in candidate:
        candidate = candidate.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in candidate:
        candidate = candidate.split("```", 1)[1].split("```", 1)[0].strip()
    else:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    try:
        payload = json.loads(candidate)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _available_provider() -> tuple[str, str] | None:
    if get_provider_key_count("gemini") > 0:
        return ("gemini", GEMINI_MODEL)
    if get_provider_key_count("openai") > 0:
        return ("openai", OPENAI_MODEL)
    return None


def _gemini_generate_text(api_key: str, model: str, prompt: str) -> tuple[str, int, int]:
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=90,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini API error ({response.status_code}): {response.text[:400]}")
    body = response.json()
    text = (
        body.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    usage = body.get("usageMetadata", {}) or {}
    return text, int(usage.get("promptTokenCount", 0) or 0), int(usage.get("candidatesTokenCount", 0) or 0)


def _openai_generate_text(api_key: str, model: str, prompt: str) -> tuple[str, int, int]:
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a concise product and creator assistant. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=90,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI API error ({response.status_code}): {response.text[:400]}")
    body = response.json()
    text = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = body.get("usage", {}) or {}
    return text, int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0)


def _build_llm_prompt(
    *,
    question: str,
    intent_type: str,
    page_scope: str,
    page_context: Mapping[str, Any],
    knowledge_matches: Sequence[KnowledgeMatch],
    cached_matches: Sequence[CachedAnswerMatch],
    history: Sequence[Mapping[str, str]],
) -> str:
    return (
        "You are the YouTube IP assistant for a Streamlit creator intelligence app.\n"
        "Return valid JSON only with this schema:\n"
        "{\n"
        '  "answer_text": "120-220 words max",\n'
        '  "related_questions": ["", "", ""],\n'
        '  "confidence_label": "High|Medium|Low",\n'
        '  "warnings": ["", ""],\n'
        '  "citations": ["", ""]\n'
        "}\n"
        "Rules:\n"
        "- Be concrete and product-aware.\n"
        "- Use the provided context only.\n"
        "- If advice is inferred from public data, say so explicitly.\n"
        "- Prefer short paragraphs or numbered steps.\n"
        "- Do not invent unavailable app features.\n\n"
        f"Question: {question}\n"
        f"Intent Type: {intent_type}\n"
        f"Page Scope: {page_scope}\n"
        f"Page Context: {json.dumps(dict(page_context), ensure_ascii=True)}\n"
        f"Retrieved Knowledge: {json.dumps([{'title': m.record.title, 'content': m.record.content, 'source_label': m.record.source_label} for m in knowledge_matches[:3]], ensure_ascii=True)}\n"
        f"Similar Cached Answers: {json.dumps([{'answer_text': m.record.answer_text, 'source_type': m.record.answer_source_type} for m in cached_matches[:2]], ensure_ascii=True)}\n"
        f"Recent Conversation: {json.dumps(list(history), ensure_ascii=True)}\n"
    )


def _generate_with_llm(
    *,
    question: str,
    intent_type: str,
    page_scope: str,
    page_context: Mapping[str, Any],
    knowledge_matches: Sequence[KnowledgeMatch],
    cached_matches: Sequence[CachedAnswerMatch],
    history: Sequence[Mapping[str, str]],
) -> tuple[str, str, int, int]:
    provider_choice = _available_provider()
    if provider_choice is None:
        raise RuntimeError("No AI provider keys are configured.")

    provider, model = provider_choice
    prompt = _build_llm_prompt(
        question=question,
        intent_type=intent_type,
        page_scope=page_scope,
        page_context=page_context,
        knowledge_matches=knowledge_matches,
        cached_matches=cached_matches,
        history=history,
    )
    if provider == "gemini":
        raw_text, prompt_tokens, completion_tokens = run_with_provider_keys(
            "gemini",
            lambda key: _gemini_generate_text(key, model, prompt),
        )
    else:
        raw_text, prompt_tokens, completion_tokens = run_with_provider_keys(
            "openai",
            lambda key: _openai_generate_text(key, model, prompt),
        )
    return provider, model, raw_text, prompt_tokens, completion_tokens


def _render_llm_reply(
    *,
    question: str,
    normalized_query: str,
    page_scope: str,
    context_mode: str,
    intent_type: str,
    page_context: dict[str, Any],
    knowledge_matches: Sequence[KnowledgeMatch],
    cached_matches: Sequence[CachedAnswerMatch],
    history: Sequence[Mapping[str, str]],
) -> AssistantReply:
    provider, model, raw_text, prompt_tokens, completion_tokens = _generate_with_llm(
        question=question,
        intent_type=intent_type,
        page_scope=page_scope,
        page_context=page_context,
        knowledge_matches=knowledge_matches,
        cached_matches=cached_matches,
        history=history,
    )
    payload = _extract_json_block(raw_text) or {}
    answer_text = str(payload.get("answer_text", "")).strip() or str(raw_text or "").strip()
    related_questions = _dedupe_texts(payload.get("related_questions", []), limit=3)
    if not related_questions:
        related_questions = _dedupe_texts(
            (
                *get_related_question_titles([match.record.id for match in knowledge_matches[:3]], limit=3),
                *(item for match in cached_matches[:2] for item in match.record.related_questions),
            ),
            limit=3,
        )
    confidence_label = str(payload.get("confidence_label", "")).strip() or "Medium"
    confidence_map = {"high": 0.9, "medium": 0.72, "low": 0.52}
    confidence = confidence_map.get(confidence_label.lower(), 0.72)
    source_refs = _dedupe_source_refs((*_knowledge_match_refs(knowledge_matches), *_cached_match_refs(cached_matches)))
    cached = store_answer(
        query_text=question,
        normalized_query=normalized_query,
        page_scope=page_scope,
        context_mode=context_mode,
        intent_type=intent_type,
        retrieval_text=_build_retrieval_text(question, source_refs, answer_text),
        answer_text=answer_text,
        answer_source_type="llm",
        confidence=confidence,
        source_refs=source_refs,
        related_questions=related_questions,
        page_context=page_context,
        model_provider=provider,
        model_name=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return AssistantReply(
        answer_id=cached.id,
        question=question,
        normalized_query=normalized_query,
        page_scope=page_scope,
        intent_type=intent_type,
        source_type="llm",
        confidence=confidence,
        confidence_label=confidence_label,
        answer_text=answer_text,
        source_refs=source_refs,
        related_questions=related_questions,
    )


def _intent_from_query(normalized_query: str) -> str:
    if not normalized_query:
        return "feature_onboarding"
    if any(token in normalized_query for token in ("error", "failed", "not working", "unavailable", "cant ", "can't", "fail", "missing")):
        return "troubleshooting"
    if any(token in normalized_query for token in ("what does", "what is", "mean", "metric", "score", "views per day", "language confidence", "ctr", "impressions")):
        return "metric_interpretation"
    if any(token in normalized_query for token in ("how do i use", "where do i", "what does this page", "button", "setting", "page", "tool", "filter")):
        return "product_support"
    if any(token in normalized_query for token in ("workflow", "which page", "start with", "sequence", "next step")):
        return "workflow_recommendation"
    if any(token in normalized_query for token in ("what should i do", "optimize", "hook", "growth", "niche", "idea", "strategy", "why is my video not performing")):
        return "creator_strategy"
    return "feature_onboarding"


def extract_page_context(page_scope: str, session_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    state = session_state or {}
    context: dict[str, Any] = {"app_page": page_scope}
    if page_scope == "outlier_finder":
        result = state.get("outlier_page_result")
        query = state.get("outlier_page_query", "")
        context["query"] = str(query or "")
        if result is not None:
            context["scanned_videos"] = int(getattr(result, "scanned_videos", 0) or 0)
            context["scanned_channels"] = int(getattr(result, "scanned_channels", 0) or 0)
            context["warnings"] = list(getattr(result, "warnings", ())[:2]) if hasattr(result, "warnings") else []
            candidates = getattr(result, "candidates", ()) or ()
            if candidates:
                top = candidates[0]
                context["top_result_title"] = getattr(top, "video_title", "")
        context["active_sort"] = str(state.get("outlier_page_sort", "Outlier Score"))
    elif page_scope == "ytuber":
        hints = state.get("ytuber_keyword_hints") or ()
        context.update(
            {
                "channel_title": str(state.get("ytuber_channel_title", "")),
                "channel_id": str(state.get("ytuber_channel_id", "")),
                "active_module": str(state.get("ytuber_active_module", "")),
                "source": str(state.get("ytuber_source", "")),
                "keyword_hints": list(hints[:5]) if isinstance(hints, (list, tuple)) else [],
            }
        )
    elif page_scope == "tools":
        preview = state.get("tools_single_preview")
        context.update(
            {
                "mode": str(state.get("tools_last_mode", "Single")),
                "preview_title": getattr(preview, "title", "") if preview is not None else "",
                "transcript_available": bool(state.get("tools_single_transcripts")),
                "ffmpeg_available": bool(ffmpeg_available()),
                "current_error": str(
                    state.get("tools_error")
                    or state.get("tools_single_error")
                    or state.get("tools_batch_error")
                    or state.get("tools_playlist_error")
                    or ""
                ),
            }
        )
    elif page_scope == "channel_insights":
        latest_payload = state.get("channel_insights_selected_channel")
        context.update(
            {
                "selected_channel_id": str(latest_payload or ""),
                "current_error": str(state.get("channel_insights_error", "")),
            }
        )
    elif page_scope in {"channel_analysis", "recommendations"}:
        context["page"] = page_scope
    return context


def _reply_from_cached_record(
    question: str,
    page_scope: str,
    intent_type: str,
    source_type: str,
    record: CachedAnswerRecord,
) -> AssistantReply:
    mark_answer_used(record.id)
    return AssistantReply(
        answer_id=record.id,
        question=question,
        normalized_query=normalize_query(question),
        page_scope=page_scope,
        intent_type=intent_type,
        source_type=source_type,
        confidence=record.confidence,
        confidence_label=_confidence_label(record.confidence),
        answer_text=record.answer_text,
        source_refs=_cache_record_source_refs(record),
        related_questions=record.related_questions,
    )


def _clarifying_reply(question: str, page_scope: str) -> AssistantReply:
    related = starter_prompts_for_page(page_scope)[:3]
    return AssistantReply(
        answer_id=None,
        question=question,
        normalized_query=normalize_query(question),
        page_scope=page_scope,
        intent_type="feature_onboarding",
        source_type="clarifying",
        confidence=0.35,
        confidence_label="Low",
        answer_text=(
            "I can help best if you tell me the page, metric, or problem you are dealing with. "
            "For example, ask what a score means, why a result looks off, or what to optimize first."
        ),
        source_refs=tuple(),
        related_questions=tuple(related),
        clarifying=True,
    )


def answer_question(
    question: str,
    *,
    page_scope: str,
    session_state: Mapping[str, Any] | None = None,
    history: Sequence[Mapping[str, str]] | None = None,
) -> AssistantReply:
    page_scope = normalize_page_scope(page_scope)
    history = history or ()
    previous_user_query = next((item.get("content", "") for item in reversed(history) if item.get("role") == "user"), "")
    normalized_query = expand_follow_up_query(question, previous_user_query)
    if len(normalized_query.split()) < 2 and len(normalized_query) < 12:
        return _clarifying_reply(question, page_scope)

    context_mode = infer_context_mode(question)
    intent_type = _intent_from_query(normalized_query)
    page_context = extract_page_context(page_scope, session_state)

    exact_match = fetch_exact_cached_answer(
        normalized_query,
        page_scope,
        context_mode,
        max_age_days=30,
        min_confidence=0.75,
    )
    if exact_match is not None:
        return _reply_from_cached_record(question, page_scope, intent_type, "exact_cache", exact_match)

    cached_matches = search_cached_answers(normalized_query, page_scope, limit=5)
    if cached_matches:
        top_cached = cached_matches[0]
        if top_cached.score >= 0.88 and top_cached.record.helpful_count > top_cached.record.unhelpful_count:
            return _reply_from_cached_record(question, page_scope, intent_type, "semantic_cache", top_cached.record)

    knowledge_matches = search_knowledge(normalized_query, page_scope, limit=5)
    direct_knowledge = knowledge_matches[0] if knowledge_matches else None
    score_gap = 0.0
    if len(knowledge_matches) > 1:
        score_gap = knowledge_matches[0].score - knowledge_matches[1].score

    if direct_knowledge and direct_knowledge.score >= 0.42 and score_gap >= 0.08:
        related = _dedupe_texts(get_related_question_titles(direct_knowledge.record.related_ids, limit=3), limit=3)
        return _build_direct_knowledge_answer(
            direct_knowledge,
            related_questions=related,
            confidence=direct_knowledge.score,
            question=question,
            normalized_query=normalized_query,
            page_scope=page_scope,
            context_mode=context_mode,
            intent_type=intent_type,
            page_context=page_context,
        )

    top_cached_score = cached_matches[0].score if cached_matches else 0.0
    top_knowledge_score = knowledge_matches[0].score if knowledge_matches else 0.0
    combined_evidence = max(top_cached_score, top_knowledge_score, (top_cached_score + top_knowledge_score) / 2 if cached_matches and knowledge_matches else 0.0)
    hybrid_available = top_cached_score >= 0.74 or top_knowledge_score >= 0.30 or combined_evidence >= 0.55

    if intent_type in {"product_support", "metric_interpretation", "troubleshooting", "workflow_recommendation", "feature_onboarding"} and hybrid_available:
        return _build_hybrid_answer(
            question,
            normalized_query=normalized_query,
            page_scope=page_scope,
            context_mode=context_mode,
            intent_type=intent_type,
            page_context=page_context,
            knowledge_matches=knowledge_matches,
            cached_matches=cached_matches,
        )

    if _available_provider() is not None:
        contextual_history = tuple(history[-2:]) if history and infer_context_mode(question) == "page_state" else tuple()
        return _render_llm_reply(
            question=question,
            normalized_query=normalized_query,
            page_scope=page_scope,
            context_mode=context_mode,
            intent_type=intent_type,
            page_context=page_context,
            knowledge_matches=knowledge_matches,
            cached_matches=cached_matches,
            history=contextual_history,
        )

    if hybrid_available:
        return _build_hybrid_answer(
            question,
            normalized_query=normalized_query,
            page_scope=page_scope,
            context_mode=context_mode,
            intent_type=intent_type,
            page_context=page_context,
            knowledge_matches=knowledge_matches,
            cached_matches=cached_matches,
            retrieval_only_notice="AI keys are unavailable, so this answer was assembled from cached answers and product knowledge only.",
        )

    return AssistantReply(
        answer_id=None,
        question=question,
        normalized_query=normalized_query,
        page_scope=page_scope,
        intent_type=intent_type,
        source_type="clarifying",
        confidence=0.4,
        confidence_label="Low",
        answer_text=(
            "I do not have enough grounded context to answer that confidently from the current knowledge base. "
            "Try naming the page, metric, or workflow you are asking about, or ask one of the related starter questions."
        ),
        source_refs=tuple(),
        related_questions=starter_prompts_for_page(page_scope)[:3],
        retrieval_only_notice="No AI provider keys are configured, so I can only answer from retrieval and cached knowledge.",
        clarifying=True,
    )


def submit_feedback(answer_id: int, rating: str, page_scope: str) -> None:
    if rating not in {"helpful", "not_helpful"}:
        raise ValueError("Unsupported feedback rating.")
    record_feedback(answer_id, rating, normalize_page_scope(page_scope))
