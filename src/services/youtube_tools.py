from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Literal, Optional
from urllib.parse import parse_qs, urlparse

import requests
import streamlit as st
import yt_dlp

from src.utils.file_utils import guess_mime_type, safe_temp_dir, sanitize_filename


TargetType = Literal["video", "short", "playlist"]
ArtifactType = Literal["thumbnail", "transcript", "audio", "video"]
BatchOperation = Literal["metadata", "thumbnail", "transcript", "audio", "video"]
AudioProfile = Literal["best_audio_original", "mp3_conversion"]
VideoProfile = Literal["best_available", "up_to_1080p", "up_to_720p", "up_to_480p"]

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
PLAYLIST_PREVIEW_LIMIT_DEFAULT = 25
STREAMLIT_DOWNLOAD_LIMIT_BYTES = 100 * 1024 * 1024
_CACHE_TTL_SECONDS = 60 * 60


@dataclass(frozen=True)
class ResolvedYoutubeTarget:
    input_url: str
    canonical_url: str
    target_type: TargetType
    video_id: str | None = None
    playlist_id: str | None = None


@dataclass(frozen=True)
class VideoMetadata:
    title: str
    channel: str
    duration_seconds: int | None
    duration_label: str
    publish_date: str | None
    video_id: str
    content_type: str
    webpage_url: str
    thumbnail_url: str | None
    thumbnail_variants: dict[str, str] = field(default_factory=dict)
    transcript_available: bool | None = None
    transcript_languages: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlaylistPreview:
    title: str
    entries: tuple[VideoMetadata, ...]


@dataclass(frozen=True)
class FormatOption:
    format_id: str
    selector: str
    label: str
    ext: str
    resolution: str
    filesize_estimate: int | None
    audio_codec: str | None
    video_codec: str | None
    is_audio_only: bool
    is_video_only: bool
    requires_ffmpeg: bool


@dataclass(frozen=True)
class PreparedArtifact:
    file_path: str
    file_name: str
    mime_type: str
    size_bytes: int
    source_item_id: str
    artifact_type: ArtifactType


@dataclass(frozen=True)
class BatchItemResult:
    source_url: str
    status: Literal["ready", "error"]
    message: str
    metadata: VideoMetadata | None = None
    artifacts: tuple[PreparedArtifact, ...] = ()


class _SilentYTDLPLogger:
    def debug(self, msg: str) -> None:  # pragma: no cover - deliberately silent
        return

    def warning(self, msg: str) -> None:  # pragma: no cover - deliberately silent
        return

    def error(self, msg: str) -> None:  # pragma: no cover - deliberately silent
        return


def _seconds_to_label(seconds: int | None) -> str:
    if not seconds:
        return "Unknown"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def _format_upload_date(upload_date: str | None) -> str | None:
    if not upload_date:
        return None
    try:
        return datetime.strptime(upload_date, "%Y%m%d").date().isoformat()
    except ValueError:
        return upload_date


def _clean_host(host: str) -> str:
    return host.lower().split(":", 1)[0]


def _normalize_input_url(url: str) -> str:
    stripped = (url or "").strip()
    if not stripped:
        raise ValueError("Enter a YouTube URL to continue.")
    if "://" not in stripped:
        stripped = f"https://{stripped}"
    return stripped


def _canonical_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _canonical_short_url(video_id: str) -> str:
    return f"https://www.youtube.com/shorts/{video_id}"


def _canonical_playlist_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def validate_youtube_url(url: str) -> ResolvedYoutubeTarget:
    normalized = _normalize_input_url(url)
    parsed = urlparse(normalized)
    host = _clean_host(parsed.netloc)
    if host not in YOUTUBE_HOSTS:
        raise ValueError("Use a public YouTube video, Short, or playlist URL.")

    query = parse_qs(parsed.query)
    path_parts = [part for part in parsed.path.split("/") if part]

    if host.endswith("youtu.be"):
        video_id = path_parts[0] if path_parts else ""
        if not video_id:
            raise ValueError("This shortened YouTube URL is missing a video ID.")
        return ResolvedYoutubeTarget(
            input_url=url,
            canonical_url=_canonical_video_url(video_id),
            target_type="video",
            video_id=video_id,
        )

    if path_parts[:1] == ["shorts"] and len(path_parts) >= 2:
        video_id = path_parts[1]
        return ResolvedYoutubeTarget(
            input_url=url,
            canonical_url=_canonical_short_url(video_id),
            target_type="short",
            video_id=video_id,
        )

    if path_parts[:1] == ["playlist"] or ("list" in query and "v" not in query):
        playlist_id = query.get("list", [""])[0]
        if not playlist_id:
            raise ValueError("This playlist URL is missing a playlist ID.")
        return ResolvedYoutubeTarget(
            input_url=url,
            canonical_url=_canonical_playlist_url(playlist_id),
            target_type="playlist",
            playlist_id=playlist_id,
        )

    if path_parts[:1] in (["watch"], ["embed"], ["live"]):
        video_id = query.get("v", [None])[0]
        if not video_id and len(path_parts) >= 2 and path_parts[0] in {"embed", "live"}:
            video_id = path_parts[1]
        if video_id:
            return ResolvedYoutubeTarget(
                input_url=url,
                canonical_url=_canonical_video_url(video_id),
                target_type="video",
                video_id=video_id,
                playlist_id=query.get("list", [None])[0],
            )

    raise ValueError("Use a standard YouTube watch URL, Short URL, or playlist URL.")


def _yt_dlp_base_options() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _SilentYTDLPLogger(),
        "skip_download": True,
    }


@st.cache_data(ttl=_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_video_info(url: str) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(
        {
            **_yt_dlp_base_options(),
            "noplaylist": True,
        }
    ) as ydl:
        return ydl.extract_info(url, download=False)


@st.cache_data(ttl=_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_playlist_info(url: str, max_items: int) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(
        {
            **_yt_dlp_base_options(),
            "extract_flat": "in_playlist",
            "playlistend": max_items,
            "noplaylist": False,
        }
    ) as ydl:
        return ydl.extract_info(url, download=False)


def _thumbnail_variants_from_info(info: dict[str, Any]) -> dict[str, str]:
    thumbnails = info.get("thumbnails") or []
    collected: list[tuple[int, str]] = []
    for thumb in thumbnails:
        url = thumb.get("url")
        if not url:
            continue
        score = int((thumb.get("height") or 0) * (thumb.get("width") or 0))
        collected.append((score, url))
    fallback = info.get("thumbnail")
    if fallback:
        collected.append((0, fallback))
    unique_urls: list[str] = []
    for _, url in sorted(collected, key=lambda item: item[0], reverse=True):
        if url not in unique_urls:
            unique_urls.append(url)
    labels = ["Best Available", "High", "Medium", "Low"]
    variants: dict[str, str] = {}
    for index, url in enumerate(unique_urls[:4]):
        label = labels[index] if index < len(labels) else f"Option {index + 1}"
        variants[label] = url
    return variants


def _build_video_metadata(info: dict[str, Any], *, target_type: TargetType | None = None) -> VideoMetadata:
    inferred_type = target_type or ("short" if "/shorts/" in (info.get("webpage_url") or "") else "video")
    transcript_languages = tuple(sorted(set((info.get("subtitles") or {}).keys()) | set((info.get("automatic_captions") or {}).keys())))
    variants = _thumbnail_variants_from_info(info)
    thumbnail_url = variants.get("Best Available") or info.get("thumbnail")
    return VideoMetadata(
        title=info.get("title") or "Untitled Video",
        channel=info.get("uploader") or info.get("channel") or "Unknown Channel",
        duration_seconds=info.get("duration"),
        duration_label=_seconds_to_label(info.get("duration")),
        publish_date=_format_upload_date(info.get("upload_date")),
        video_id=info.get("id") or "",
        content_type="Short" if inferred_type == "short" else "Video",
        webpage_url=info.get("webpage_url") or _canonical_video_url(info.get("id") or ""),
        thumbnail_url=thumbnail_url,
        thumbnail_variants=variants,
        transcript_available=bool(transcript_languages),
        transcript_languages=transcript_languages,
    )


def _filesize_estimate(format_info: dict[str, Any]) -> int | None:
    return format_info.get("filesize") or format_info.get("filesize_approx")


def _format_size_label(size_bytes: int | None) -> str:
    if not size_bytes:
        return "Size Unknown"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def _audio_label(format_info: dict[str, Any]) -> str:
    bitrate = format_info.get("abr")
    bitrate_label = f"{int(bitrate)} kbps" if bitrate else "Audio"
    size_label = _format_size_label(_filesize_estimate(format_info))
    ext = (format_info.get("ext") or "audio").upper()
    return f"{ext} Audio • {bitrate_label} • {size_label}"


def _video_label(format_info: dict[str, Any], *, merged: bool) -> str:
    height = format_info.get("height")
    fps = format_info.get("fps")
    ext = (format_info.get("ext") or "video").upper()
    resolution = f"{height}p" if height else "Video"
    fps_label = f"{fps:.0f} fps" if fps else "Unknown fps"
    size_label = _format_size_label(_filesize_estimate(format_info))
    suffix = " • Merged With Best Audio" if merged else ""
    return f"{resolution} • {ext} • {fps_label} • {size_label}{suffix}"


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def fetch_video_metadata(url: str) -> VideoMetadata:
    target = validate_youtube_url(url)
    if target.target_type == "playlist":
        raise ValueError("Use Playlist mode for playlist URLs.")
    return _build_video_metadata(_cached_video_info(target.canonical_url), target_type=target.target_type)


def fetch_playlist_preview(url: str, *, max_items: int = PLAYLIST_PREVIEW_LIMIT_DEFAULT) -> PlaylistPreview:
    target = validate_youtube_url(url)
    if target.target_type != "playlist":
        raise ValueError("Use a playlist URL in Playlist mode.")
    info = _cached_playlist_info(target.canonical_url, max_items)
    entries: list[VideoMetadata] = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        video_id = entry.get("id") or ""
        thumb = entry.get("thumbnail")
        raw_entry_url = entry.get("url") or ""
        entry_url = raw_entry_url if str(raw_entry_url).startswith("http") else _canonical_video_url(video_id)
        entries.append(
            VideoMetadata(
                title=entry.get("title") or "Untitled Video",
                channel=entry.get("channel") or entry.get("uploader") or "Unknown Channel",
                duration_seconds=entry.get("duration"),
                duration_label=_seconds_to_label(entry.get("duration")),
                publish_date=None,
                video_id=video_id,
                content_type="Short" if "/shorts/" in entry_url else "Video",
                webpage_url=entry_url,
                thumbnail_url=thumb,
                thumbnail_variants={"Best Available": thumb} if thumb else {},
                transcript_available=None,
                transcript_languages=(),
            )
        )
    return PlaylistPreview(
        title=info.get("title") or "Untitled Playlist",
        entries=tuple(entries),
    )


def fetch_playlist_entries(url: str, *, max_items: int = PLAYLIST_PREVIEW_LIMIT_DEFAULT) -> list[VideoMetadata]:
    return list(fetch_playlist_preview(url, max_items=max_items).entries)


def get_available_formats(url: str) -> dict[str, list[FormatOption]]:
    target = validate_youtube_url(url)
    if target.target_type == "playlist":
        raise ValueError("Formats are only available for single videos and Shorts.")
    info = _cached_video_info(target.canonical_url)
    audio_options: list[FormatOption] = []
    video_options: list[FormatOption] = []
    ffmpeg_ready = ffmpeg_available()
    seen_video_selectors: set[str] = set()

    for format_info in info.get("formats") or []:
        format_id = str(format_info.get("format_id") or "")
        ext = str(format_info.get("ext") or "")
        if not format_id or ext == "mhtml":
            continue

        audio_codec = format_info.get("acodec")
        video_codec = format_info.get("vcodec")
        is_audio_only = audio_codec not in {None, "none"} and video_codec in {None, "none"}
        is_video_capable = video_codec not in {None, "none"}

        if is_audio_only:
            audio_options.append(
                FormatOption(
                    format_id=format_id,
                    selector=format_id,
                    label=_audio_label(format_info),
                    ext=ext,
                    resolution="Audio",
                    filesize_estimate=_filesize_estimate(format_info),
                    audio_codec=audio_codec,
                    video_codec=video_codec,
                    is_audio_only=True,
                    is_video_only=False,
                    requires_ffmpeg=False,
                )
            )
            continue

        if not is_video_capable:
            continue

        has_audio = audio_codec not in {None, "none"}
        if has_audio:
            selector = format_id
            requires_merge = False
        elif ffmpeg_ready:
            selector = f"{format_id}+bestaudio/best"
            requires_merge = True
        else:
            continue

        if selector in seen_video_selectors:
            continue
        seen_video_selectors.add(selector)
        height = format_info.get("height")
        resolution = f"{height}p" if height else "Video"
        video_options.append(
            FormatOption(
                format_id=format_id,
                selector=selector,
                label=_video_label(format_info, merged=requires_merge),
                ext="mp4" if requires_merge else ext,
                resolution=resolution,
                filesize_estimate=_filesize_estimate(format_info),
                audio_codec=audio_codec,
                video_codec=video_codec,
                is_audio_only=False,
                is_video_only=not has_audio,
                requires_ffmpeg=requires_merge,
            )
        )

    audio_options.sort(key=lambda item: (item.filesize_estimate or 0, item.label), reverse=True)
    video_options.sort(
        key=lambda item: (
            int(item.resolution.replace("p", "")) if item.resolution.endswith("p") else 0,
            item.filesize_estimate or 0,
        ),
        reverse=True,
    )
    return {"audio": audio_options, "video": video_options}


def _audio_profile_selector(profile: str) -> tuple[str, list[dict[str, Any]] | None]:
    if profile == "best_audio_original":
        return "bestaudio/best", None
    if profile == "mp3_conversion":
        if not ffmpeg_available():
            raise ValueError("FFmpeg is required for MP3 conversion.")
        return "bestaudio/best", [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    return profile, None


def _video_profile_selector(profile: str) -> str:
    selectors = {
        "best_available": "bestvideo*+bestaudio/best",
        "up_to_1080p": "bestvideo*[height<=1080]+bestaudio/best[height<=1080]",
        "up_to_720p": "bestvideo*[height<=720]+bestaudio/best[height<=720]",
        "up_to_480p": "bestvideo*[height<=480]+bestaudio/best[height<=480]",
    }
    return selectors.get(profile, profile)


def _locate_downloaded_file(temp_dir: Path) -> Path:
    candidates = [
        path
        for path in temp_dir.rglob("*")
        if path.is_file()
        and not path.name.endswith((".part", ".ytdl", ".info.json", ".description"))
    ]
    if not candidates:
        raise RuntimeError("No downloadable file was produced for this request.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _download_with_ytdlp(
    url: str,
    *,
    format_selector: str,
    artifact_type: ArtifactType,
    file_stem: str,
    postprocessors: list[dict[str, Any]] | None = None,
    merge_output_format: str | None = None,
) -> PreparedArtifact:
    metadata = fetch_video_metadata(url)
    temp_dir = safe_temp_dir(f"yt-tools-{artifact_type}-")
    output_template = str(temp_dir / f"{sanitize_filename(file_stem, metadata.video_id)}.%(ext)s")
    options: dict[str, Any] = {
        **_yt_dlp_base_options(),
        "skip_download": False,
        "noplaylist": True,
        "format": format_selector,
        "outtmpl": {"default": output_template},
    }
    if postprocessors:
        options["postprocessors"] = postprocessors
    if merge_output_format:
        options["merge_output_format"] = merge_output_format

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(validate_youtube_url(url).canonical_url, download=True)

    file_path = _locate_downloaded_file(temp_dir)
    return PreparedArtifact(
        file_path=str(file_path),
        file_name=file_path.name,
        mime_type=guess_mime_type(file_path),
        size_bytes=file_path.stat().st_size,
        source_item_id=metadata.video_id,
        artifact_type=artifact_type,
    )


def prepare_thumbnail_download(url: str, quality_key: str | None = None) -> PreparedArtifact:
    metadata = fetch_video_metadata(url)
    variants = metadata.thumbnail_variants or {}
    thumbnail_url = variants.get(quality_key or "", metadata.thumbnail_url) if quality_key else metadata.thumbnail_url
    if not thumbnail_url:
        raise ValueError("No thumbnail is available for this video.")

    response = requests.get(thumbnail_url, timeout=30)
    response.raise_for_status()
    suffix = Path(urlparse(thumbnail_url).path).suffix or ".jpg"
    temp_dir = safe_temp_dir("yt-tools-thumbnail-")
    filename = f"{sanitize_filename(metadata.title, metadata.video_id)}-thumbnail{suffix}"
    file_path = temp_dir / filename
    file_path.write_bytes(response.content)
    return PreparedArtifact(
        file_path=str(file_path),
        file_name=filename,
        mime_type=response.headers.get("content-type") or guess_mime_type(file_path),
        size_bytes=file_path.stat().st_size,
        source_item_id=metadata.video_id,
        artifact_type="thumbnail",
    )


def prepare_audio_download(url: str, profile: str) -> PreparedArtifact:
    metadata = fetch_video_metadata(url)
    selector, postprocessors = _audio_profile_selector(profile)
    return _download_with_ytdlp(
        url,
        format_selector=selector,
        artifact_type="audio",
        file_stem=f"{metadata.title}-audio",
        postprocessors=postprocessors,
    )


def prepare_video_download(url: str, profile_or_format: str) -> PreparedArtifact:
    metadata = fetch_video_metadata(url)
    selector = _video_profile_selector(profile_or_format)
    merge_output_format = "mp4" if "+" in selector else None
    if "+" in selector and not ffmpeg_available():
        raise ValueError("FFmpeg is required for merged video downloads.")
    return _download_with_ytdlp(
        url,
        format_selector=selector,
        artifact_type="video",
        file_stem=metadata.title,
        merge_output_format=merge_output_format,
    )


def prepare_batch_operation(
    urls: list[str],
    operation: BatchOperation,
    options: dict[str, Any] | None = None,
) -> list[BatchItemResult]:
    from src.services.transcript_service import prepare_transcript_download

    options = options or {}
    results: list[BatchItemResult] = []
    for raw_url in urls:
        try:
            target = validate_youtube_url(raw_url)
            if target.target_type == "playlist":
                raise ValueError("Playlist URLs belong in Playlist mode.")
            metadata = fetch_video_metadata(target.canonical_url)
            artifacts: list[PreparedArtifact] = []
            if operation == "thumbnail":
                artifacts.append(prepare_thumbnail_download(target.canonical_url, options.get("thumbnail_quality")))
            elif operation == "transcript":
                artifacts.append(
                    prepare_transcript_download(
                        metadata.video_id,
                        options.get("language_code"),
                        prefer_any=bool(options.get("prefer_any")),
                        video_title=metadata.title,
                    )
                )
            elif operation == "audio":
                artifacts.append(prepare_audio_download(target.canonical_url, options.get("audio_profile", "best_audio_original")))
            elif operation == "video":
                artifacts.append(prepare_video_download(target.canonical_url, options.get("video_profile", "best_available")))
            results.append(
                BatchItemResult(
                    source_url=raw_url,
                    status="ready",
                    message="Ready",
                    metadata=metadata,
                    artifacts=tuple(artifacts),
                )
            )
        except Exception as exc:
            results.append(
                BatchItemResult(
                    source_url=raw_url,
                    status="error",
                    message=str(exc),
                    metadata=None,
                    artifacts=(),
                )
            )
    return results


def prepare_playlist_operation(
    playlist_url: str,
    selected_ids: list[str],
    operation: BatchOperation,
    options: dict[str, Any] | None = None,
) -> list[BatchItemResult]:
    preview = fetch_playlist_preview(playlist_url, max_items=int((options or {}).get("playlist_max_items", PLAYLIST_PREVIEW_LIMIT_DEFAULT)))
    selected_set = set(selected_ids)
    selected_urls = [
        entry.webpage_url or _canonical_video_url(entry.video_id)
        for entry in preview.entries
        if entry.video_id in selected_set
    ]
    return prepare_batch_operation(selected_urls, operation, options=options)
