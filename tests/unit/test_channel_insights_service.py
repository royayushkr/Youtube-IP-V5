from pathlib import Path

import pandas as pd

from src.services.channel_insights_service import load_channel_insights, refresh_channel_insights
from src.services.public_channel_service import PublicChannelWorkspace


def test_refresh_channel_insights_persists_snapshot(monkeypatch, tmp_path: Path) -> None:
    sample_df = pd.DataFrame(
        [
            {
                "channel_id": "UC123",
                "channel_title": "Demo Channel",
                "video_id": "v1",
                "video_title": "How To Build Better Hooks",
                "video_description": "hooks for creators",
                "video_tags": "hooks|creator|youtube",
                "video_publishedAt": "2026-03-10T12:00:00Z",
                "views": 10000,
                "likes": 600,
                "comments": 45,
                "duration": "PT8M0S",
                "duration_seconds": 480,
            },
            {
                "channel_id": "UC123",
                "channel_title": "Demo Channel",
                "video_id": "v2",
                "video_title": "Shorts Strategy That Actually Converts",
                "video_description": "shorts strategy and topic testing",
                "video_tags": "shorts|strategy|topic",
                "video_publishedAt": "2026-03-01T12:00:00Z",
                "views": 6000,
                "likes": 340,
                "comments": 20,
                "duration": "PT45S",
                "duration_seconds": 45,
            },
        ]
    )

    workspace = PublicChannelWorkspace(
        channel_df=sample_df,
        source="youtube_api",
        channel_id="UC123",
        channel_title="Demo Channel",
        canonical_url="https://www.youtube.com/channel/UC123",
        query_used="@demo",
    )

    monkeypatch.setattr(
        "src.services.channel_insights_service.load_public_channel_workspace",
        lambda channel_input, force_refresh=False: workspace,
    )
    monkeypatch.setattr(
        "src.services.channel_insights_service.maybe_generate_ai_overlay",
        lambda *args, **kwargs: "",
    )

    db_path = tmp_path / "channel_insights.db"
    payload = refresh_channel_insights("@demo", db_path=db_path)
    loaded = load_channel_insights("UC123", db_path=db_path)

    assert payload["channel"]["channel_id"] == "UC123"
    assert loaded is not None
    assert loaded["summary"]["strongest_theme"]
    assert not loaded["outliers_df"].empty
