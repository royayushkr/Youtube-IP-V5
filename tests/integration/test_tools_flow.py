from src.services import youtube_tools


def test_prepare_playlist_operation_respects_selected_ids(monkeypatch) -> None:
    preview = youtube_tools.PlaylistPreview(
        title="Testing Playlist",
        entries=(
            youtube_tools.VideoMetadata(
                title="Video One",
                channel="Channel One",
                duration_seconds=120,
                duration_label="2:00",
                publish_date=None,
                video_id="video-1",
                content_type="Video",
                webpage_url="https://www.youtube.com/watch?v=video-1",
                thumbnail_url=None,
            ),
            youtube_tools.VideoMetadata(
                title="Video Two",
                channel="Channel Two",
                duration_seconds=180,
                duration_label="3:00",
                publish_date=None,
                video_id="video-2",
                content_type="Video",
                webpage_url="https://www.youtube.com/watch?v=video-2",
                thumbnail_url=None,
            ),
        ),
    )
    monkeypatch.setattr(youtube_tools, "fetch_playlist_preview", lambda url, max_items=25: preview)

    captured = {}

    def fake_prepare_batch(urls, operation, options=None):
        captured["urls"] = urls
        captured["operation"] = operation
        return [
            youtube_tools.BatchItemResult(
                source_url=item_url,
                status="ready",
                message="Ready",
                metadata=preview.entries[0],
                artifacts=(),
            )
            for item_url in urls
        ]

    monkeypatch.setattr(youtube_tools, "prepare_batch_operation", fake_prepare_batch)

    results = youtube_tools.prepare_playlist_operation(
        "https://www.youtube.com/playlist?list=PL123",
        ["video-2"],
        "metadata",
        options={"playlist_max_items": 10},
    )

    assert captured["urls"] == ["https://www.youtube.com/watch?v=video-2"]
    assert captured["operation"] == "metadata"
    assert len(results) == 1


def test_prepare_batch_operation_with_thumbnail_artifacts(monkeypatch) -> None:
    metadata = youtube_tools.VideoMetadata(
        title="Example",
        channel="Channel",
        duration_seconds=95,
        duration_label="1:35",
        publish_date="2024-01-01",
        video_id="video-1",
        content_type="Video",
        webpage_url="https://www.youtube.com/watch?v=video-1",
        thumbnail_url="https://img.youtube.com/vi/video-1/hqdefault.jpg",
    )
    artifact = youtube_tools.PreparedArtifact(
        file_path="/tmp/thumbnail.jpg",
        file_name="thumbnail.jpg",
        mime_type="image/jpeg",
        size_bytes=1024,
        source_item_id="video-1",
        artifact_type="thumbnail",
    )

    monkeypatch.setattr(youtube_tools, "fetch_video_metadata", lambda url: metadata)
    monkeypatch.setattr(youtube_tools, "prepare_thumbnail_download", lambda url, quality_key=None: artifact)

    results = youtube_tools.prepare_batch_operation(
        ["https://www.youtube.com/watch?v=video-1"],
        "thumbnail",
        options={"thumbnail_quality": "Best Available"},
    )

    assert len(results) == 1
    assert results[0].status == "ready"
    assert results[0].artifacts[0].file_name == "thumbnail.jpg"
