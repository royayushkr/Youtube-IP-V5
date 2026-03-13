from src.services import assistant_service, cache_service, retrieval_service


def test_answer_question_uses_exact_cache_first(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "assistant_cache.db"
    monkeypatch.setattr(cache_service, "ASSISTANT_DB_PATH", db_path)
    retrieval_service.clear_retrieval_caches()

    cache_service.store_answer(
        query_text="What does the outlier score mean?",
        normalized_query="what does the outlier score mean",
        page_scope="outlier_finder",
        context_mode="page_only",
        intent_type="metric_interpretation",
        retrieval_text="outlier score meaning blended signal",
        answer_text="It is a weighted scanned-cohort signal.",
        answer_source_type="knowledge",
        confidence=0.85,
        source_refs=[{"title": "What The Outlier Score Means", "source_label": "KB", "excerpt": "Weighted signal"}],
        related_questions=["What does views per day mean?"],
        page_context={"app_page": "outlier_finder"},
    )

    reply = assistant_service.answer_question("What does the outlier score mean?", page_scope="Outlier Finder")

    assert reply.source_type == "exact_cache"
    assert "weighted" in reply.answer_text.lower()


def test_answer_question_uses_semantic_cache_when_similarity_is_high(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "assistant_cache.db"
    monkeypatch.setattr(cache_service, "ASSISTANT_DB_PATH", db_path)
    retrieval_service.clear_retrieval_caches()

    record = cache_service.store_answer(
        query_text="How do I use Outlier Finder?",
        normalized_query="how do i use outlier finder",
        page_scope="outlier_finder",
        context_mode="page_only",
        intent_type="product_support",
        retrieval_text="how do i use outlier finder start broad then inspect top outliers",
        answer_text="Start broad, then inspect Top Outliers first.",
        answer_source_type="knowledge",
        confidence=0.9,
        source_refs=[{"title": "How To Use Outlier Finder", "source_label": "KB", "excerpt": "Start broad"}],
        related_questions=["How do I read the outlier score?"],
        page_context={"app_page": "outlier_finder"},
    )
    cache_service.record_feedback(record.id, "helpful", "outlier_finder")
    semantic_match = retrieval_service.CachedAnswerMatch(record=cache_service.fetch_answer_by_id(record.id), score=0.93)
    monkeypatch.setattr(assistant_service, "search_cached_answers", lambda query, page_scope, limit=5: (semantic_match,))

    reply = assistant_service.answer_question("How do I use Outlier Finder Page?", page_scope="Outlier Finder")

    assert reply.source_type == "semantic_cache"


def test_answer_question_uses_knowledge_when_match_is_strong(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "assistant_cache.db"
    monkeypatch.setattr(cache_service, "ASSISTANT_DB_PATH", db_path)
    retrieval_service.clear_retrieval_caches()

    reply = assistant_service.answer_question("What does language confidence mean?", page_scope="Outlier Finder")

    assert reply.source_type in {"knowledge", "hybrid"}
    assert reply.answer_id is not None
    assert reply.source_refs


def test_answer_question_uses_llm_only_after_retrieval(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "assistant_cache.db"
    monkeypatch.setattr(cache_service, "ASSISTANT_DB_PATH", db_path)
    retrieval_service.clear_retrieval_caches()

    calls = {"llm": 0}

    def fake_llm(**kwargs):
        calls["llm"] += 1
        return assistant_service.AssistantReply(
            answer_id=999,
            question=kwargs["question"],
            normalized_query=kwargs["normalized_query"],
            page_scope=kwargs["page_scope"],
            intent_type=kwargs["intent_type"],
            source_type="llm",
            confidence=0.7,
            confidence_label="Medium",
            answer_text="Test stronger hooks by clarifying the payoff early.",
            source_refs=tuple(),
            related_questions=("What title angle should I test next?",),
        )

    monkeypatch.setattr(assistant_service, "_available_provider", lambda: ("gemini", assistant_service.GEMINI_MODEL))
    monkeypatch.setattr(assistant_service, "_render_llm_reply", fake_llm)

    reply = assistant_service.answer_question(
        "What hooks should I test for my python productivity channel?",
        page_scope="Ytuber",
    )

    assert calls["llm"] == 1
    assert reply.source_type == "llm"


def test_extract_page_context_outlier_and_tools_states(monkeypatch) -> None:
    class Candidate:
        video_title = "Top Video"

    class Result:
        scanned_videos = 51
        scanned_channels = 23
        warnings = ("Language confidence is mixed.",)
        candidates = (Candidate(),)

    monkeypatch.setattr(assistant_service, "ffmpeg_available", lambda: True)

    outlier_context = assistant_service.extract_page_context(
        "outlier_finder",
        {
            "outlier_page_query": "ai automation",
            "outlier_page_result": Result(),
            "outlier_page_sort": "Outlier Score",
        },
    )
    tools_context = assistant_service.extract_page_context(
        "tools",
        {
            "tools_last_mode": "Single",
            "tools_single_transcripts": ["en"],
            "tools_single_error": "",
        },
    )

    assert outlier_context["top_result_title"] == "Top Video"
    assert outlier_context["scanned_videos"] == 51
    assert tools_context["ffmpeg_available"] is True
    assert tools_context["transcript_available"] is True
