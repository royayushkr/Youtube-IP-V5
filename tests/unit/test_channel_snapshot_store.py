from pathlib import Path

import pandas as pd

from src.services.channel_snapshot_store import (
    get_tracked_channel,
    list_channel_snapshot_history,
    load_latest_channel_snapshot,
    store_channel_snapshot,
    upsert_tracked_channel,
)


def test_store_and_load_channel_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "channel_insights.db"
    snapshot_at = "2026-03-13T12:00:00+00:00"

    upsert_tracked_channel(
        channel_id="UC123",
        input_value="@demo",
        canonical_url="https://www.youtube.com/@demo",
        channel_title="Demo Channel",
        channel_handle="@demo",
        source="youtube_api",
        added_at=snapshot_at,
        last_refresh_at=snapshot_at,
        db_path=db_path,
    )

    videos_df = pd.DataFrame(
        [
            {
                "video_id": "v1",
                "video_title": "Demo Video",
                "video_publishedAt": snapshot_at,
                "views": 1000,
                "likes": 80,
                "comments": 5,
                "duration_seconds": 300,
                "is_short": False,
                "duration_bucket": "4-8 Minutes",
                "views_per_day": 250,
                "engagement_rate": 0.085,
                "topic_labels": ["science", "experiment"],
                "title_pattern": "Explainer",
            }
        ]
    )
    topic_metrics_df = pd.DataFrame(
        [
            {
                "topic_label": "Science",
                "video_count": 1,
                "median_views_per_day": 250,
                "median_views": 1000,
                "outlier_count": 1,
                "trend_score": 0.45,
                "avg_engagement": 0.085,
            }
        ]
    )

    store_channel_snapshot(
        channel_id="UC123",
        snapshot_at=snapshot_at,
        source="youtube_api",
        summary={"strongest_theme": "Science", "median_views_per_day": 250},
        videos_df=videos_df,
        topic_metrics_df=topic_metrics_df,
        insights_payload={"recommendations": {"summary": "Lean into science."}},
        db_path=db_path,
    )

    tracked = get_tracked_channel("UC123", db_path=db_path)
    latest = load_latest_channel_snapshot("UC123", db_path=db_path)
    history = list_channel_snapshot_history("UC123", db_path=db_path)

    assert tracked is not None
    assert tracked["channel_title"] == "Demo Channel"
    assert latest is not None
    assert latest["summary"]["strongest_theme"] == "Science"
    assert latest["videos"][0]["video_id"] == "v1"
    assert not history.empty
