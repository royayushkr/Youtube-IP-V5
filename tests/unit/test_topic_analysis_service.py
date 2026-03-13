import pandas as pd

from src.services.topic_analysis_service import (
    add_channel_video_features,
    assign_topic_labels,
    build_topic_metrics,
    classify_title_pattern,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "video_id": "v1",
                "video_title": "How To Build A Better Shorts Strategy",
                "video_description": "shorts strategy tips for creators",
                "video_tags": "shorts|strategy|creator",
                "video_publishedAt": "2026-03-10T12:00:00Z",
                "views": 5000,
                "likes": 220,
                "comments": 24,
                "duration_seconds": 45,
            },
            {
                "video_id": "v2",
                "video_title": "AI Thumbnail Test: What Actually Improved CTR",
                "video_description": "thumbnail ctr test and packaging review",
                "video_tags": "thumbnail|ctr|packaging",
                "video_publishedAt": "2026-02-20T12:00:00Z",
                "views": 12000,
                "likes": 500,
                "comments": 40,
                "duration_seconds": 600,
            },
        ]
    )


def test_classify_title_pattern() -> None:
    assert classify_title_pattern("How To Build Better Hooks") == "How-To"
    assert classify_title_pattern("7 Thumbnail Ideas That Work") == "Numbered"


def test_topic_metrics_generation() -> None:
    df = add_channel_video_features(_sample_df())
    df = assign_topic_labels(df)
    df["performance_score"] = [80, 72]
    topic_metrics = build_topic_metrics(df)

    assert not topic_metrics.empty
    assert "topic_label" in topic_metrics.columns
    assert topic_metrics["video_count"].max() >= 1
