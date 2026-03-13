from src.utils import text_normalization


def test_normalize_query_applies_synonyms_and_keeps_percent() -> None:
    normalized = text_normalization.normalize_query("  SEO Lab CTR% ??? ")

    assert normalized == "title and seo lab ctr%"


def test_infer_context_mode_detects_page_state_language() -> None:
    assert text_normalization.infer_context_mode("Why are these results weak here?") == "page_state"
    assert text_normalization.infer_context_mode("How do I use Outlier Finder") == "page_only"


def test_expand_follow_up_query_uses_previous_user_question() -> None:
    expanded = text_normalization.expand_follow_up_query("What about this?", "Why did my scan return weak results")

    assert expanded == "why did my scan return weak results what about this"
