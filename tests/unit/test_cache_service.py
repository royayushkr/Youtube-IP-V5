from src.services import cache_service


def test_exact_cache_hit_and_feedback_roundtrip(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "assistant_cache.db"
    monkeypatch.setattr(cache_service, "ASSISTANT_DB_PATH", db_path)

    record = cache_service.store_answer(
        query_text="What does the outlier score mean?",
        normalized_query="what does the outlier score mean",
        page_scope="outlier_finder",
        context_mode="page_only",
        intent_type="metric_interpretation",
        retrieval_text="outlier score meaning answer",
        answer_text="It is a scanned-cohort score.",
        answer_source_type="knowledge",
        confidence=0.86,
        source_refs=[{"title": "What The Outlier Score Means", "source_label": "KB", "excerpt": "Blended score"}],
        related_questions=["What does views per day mean?"],
        page_context={"app_page": "outlier_finder"},
    )

    fetched = cache_service.fetch_exact_cached_answer(
        "what does the outlier score mean",
        "outlier_finder",
        "page_only",
    )

    assert fetched is not None
    assert fetched.id == record.id

    cache_service.mark_answer_used(record.id)
    cache_service.record_feedback(record.id, "helpful", "outlier_finder")
    updated = cache_service.fetch_answer_by_id(record.id)

    assert updated is not None
    assert updated.use_count == 2
    assert updated.helpful_count == 1
