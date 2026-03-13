from src.services import cache_service, retrieval_service


def test_search_cached_answers_returns_near_duplicate(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "assistant_cache.db"
    monkeypatch.setattr(cache_service, "ASSISTANT_DB_PATH", db_path)
    retrieval_service.clear_retrieval_caches()

    cache_service.store_answer(
        query_text="How do I use Outlier Finder?",
        normalized_query="how do i use outlier finder",
        page_scope="outlier_finder",
        context_mode="page_only",
        intent_type="product_support",
        retrieval_text="how do i use outlier finder start with a broad query",
        answer_text="Start with a broad query, then read Top Outliers first.",
        answer_source_type="knowledge",
        confidence=0.81,
        source_refs=[{"title": "How To Use Outlier Finder", "source_label": "KB", "excerpt": "Start broad"}],
        related_questions=["How do I read the outlier score?"],
        page_context={"app_page": "outlier_finder"},
    )

    matches = retrieval_service.search_cached_answers("how do i use outlier finder page", "outlier_finder")

    assert matches
    assert matches[0].score > 0.8


def test_search_knowledge_returns_page_relevant_record() -> None:
    retrieval_service.clear_retrieval_caches()

    matches = retrieval_service.search_knowledge("what does language confidence mean", "outlier_finder")

    assert matches
    assert matches[0].record.id == "language-confidence-meaning"
