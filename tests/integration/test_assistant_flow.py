from src.services import assistant_service, cache_service, retrieval_service


def test_assistant_flow_supports_cache_knowledge_and_feedback(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "assistant_cache.db"
    monkeypatch.setattr(cache_service, "ASSISTANT_DB_PATH", db_path)
    retrieval_service.clear_retrieval_caches()

    first = assistant_service.answer_question("What does the outlier score mean?", page_scope="Outlier Finder")
    second = assistant_service.answer_question("What does the outlier score mean?", page_scope="Outlier Finder")

    assert first.source_type == "knowledge"
    assert second.source_type == "exact_cache"
    assert second.answer_id is not None

    assistant_service.submit_feedback(second.answer_id, "helpful", "Outlier Finder")
    cached = cache_service.fetch_answer_by_id(second.answer_id)

    assert cached is not None
    assert cached.helpful_count == 1


def test_assistant_flow_uses_retrieval_notice_when_no_ai_keys(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "assistant_cache.db"
    monkeypatch.setattr(cache_service, "ASSISTANT_DB_PATH", db_path)
    retrieval_service.clear_retrieval_caches()
    monkeypatch.setattr(assistant_service, "_available_provider", lambda: None)

    reply = assistant_service.answer_question(
        "What should I optimize first when growth is slow?",
        page_scope="Ytuber",
    )

    assert reply.source_type in {"knowledge", "hybrid", "clarifying"}
    if reply.source_type == "hybrid":
        assert "AI keys are unavailable" in reply.retrieval_only_notice
