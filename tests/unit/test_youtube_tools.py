from src.services import youtube_tools


def test_validate_youtube_url_supports_watch_short_and_playlist() -> None:
    watch = youtube_tools.validate_youtube_url("https://www.youtube.com/watch?v=abc123")
    short = youtube_tools.validate_youtube_url("https://www.youtube.com/shorts/xyz789")
    playlist = youtube_tools.validate_youtube_url("https://www.youtube.com/playlist?list=PL123")

    assert watch.target_type == "video"
    assert watch.video_id == "abc123"
    assert short.target_type == "short"
    assert short.video_id == "xyz789"
    assert playlist.target_type == "playlist"
    assert playlist.playlist_id == "PL123"


def test_fetch_playlist_preview_shapes_entries(monkeypatch) -> None:
    youtube_tools._cached_playlist_info.clear()
    monkeypatch.setattr(
        youtube_tools,
        "_cached_playlist_info",
        lambda url, max_items: {
            "title": "Test Playlist",
            "entries": [
                {
                    "id": "video-1",
                    "title": "First Video",
                    "channel": "Channel One",
                    "duration": 95,
                    "url": "https://www.youtube.com/watch?v=video-1",
                    "thumbnail": "https://img.youtube.com/vi/video-1/hqdefault.jpg",
                }
            ],
        },
    )

    preview = youtube_tools.fetch_playlist_preview("https://www.youtube.com/playlist?list=PL123", max_items=10)

    assert preview.title == "Test Playlist"
    assert len(preview.entries) == 1
    assert preview.entries[0].video_id == "video-1"
    assert preview.entries[0].duration_label == "1:35"


def test_get_available_formats_builds_audio_and_video_choices(monkeypatch) -> None:
    youtube_tools._cached_video_info.clear()
    monkeypatch.setattr(
        youtube_tools,
        "_cached_video_info",
        lambda url: {
            "id": "video-1",
            "formats": [
                {
                    "format_id": "140",
                    "ext": "m4a",
                    "acodec": "mp4a.40.2",
                    "vcodec": "none",
                    "abr": 128,
                    "filesize": 4_500_000,
                },
                {
                    "format_id": "18",
                    "ext": "mp4",
                    "acodec": "mp4a.40.2",
                    "vcodec": "avc1.42001E",
                    "height": 360,
                    "fps": 30,
                    "filesize": 11_000_000,
                },
                {
                    "format_id": "137",
                    "ext": "mp4",
                    "acodec": "none",
                    "vcodec": "avc1.640028",
                    "height": 1080,
                    "fps": 30,
                    "filesize": 40_000_000,
                },
                {
                    "format_id": "sb1",
                    "ext": "mhtml",
                    "acodec": "none",
                    "vcodec": "none",
                },
            ],
        },
    )
    monkeypatch.setattr(youtube_tools, "ffmpeg_available", lambda: True)

    formats = youtube_tools.get_available_formats("https://www.youtube.com/watch?v=video-1")

    assert len(formats["audio"]) == 1
    assert formats["audio"][0].format_id == "140"
    assert len(formats["video"]) == 2
    assert formats["video"][0].selector == "137+bestaudio/best"
    assert formats["video"][0].requires_ffmpeg is True


def test_prepare_batch_operation_returns_item_level_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        youtube_tools,
        "fetch_video_metadata",
        lambda url: youtube_tools.VideoMetadata(
            title="Example",
            channel="Channel",
            duration_seconds=120,
            duration_label="2:00",
            publish_date="2024-01-01",
            video_id="video-1",
            content_type="Video",
            webpage_url=url,
            thumbnail_url=None,
        ),
    )

    results = youtube_tools.prepare_batch_operation(
        [
            "https://www.youtube.com/watch?v=video-1",
            "https://www.youtube.com/playlist?list=PL123",
        ],
        "metadata",
    )

    assert results[0].status == "ready"
    assert results[1].status == "error"
    assert "Playlist mode" in results[1].message
