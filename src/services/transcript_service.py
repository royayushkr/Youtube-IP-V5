from __future__ import annotations

from dataclasses import dataclass

import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

from src.services.youtube_tools import PreparedArtifact
from src.utils.file_utils import guess_mime_type, safe_temp_dir, sanitize_filename


_CACHE_TTL_SECONDS = 60 * 60


@dataclass(frozen=True)
class TranscriptOption:
    language_code: str
    language_label: str
    is_generated: bool
    is_translatable: bool


def _api() -> YouTubeTranscriptApi:
    return YouTubeTranscriptApi()


@st.cache_data(ttl=_CACHE_TTL_SECONDS, show_spinner=False)
def list_transcript_options(video_id: str) -> list[TranscriptOption]:
    try:
        transcript_list = _api().list(video_id)
    except (TranscriptsDisabled, NoTranscriptFound):
        return []
    except VideoUnavailable as exc:
        raise ValueError("This video is unavailable or does not expose public transcripts.") from exc

    options: list[TranscriptOption] = []
    for transcript in transcript_list:
        options.append(
            TranscriptOption(
                language_code=transcript.language_code,
                language_label=transcript.language,
                is_generated=bool(transcript.is_generated),
                is_translatable=bool(transcript.is_translatable),
            )
        )
    return options


@st.cache_data(ttl=_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_transcript_text(
    video_id: str,
    language_code: str | None,
    *,
    prefer_generated: bool | None = None,
    prefer_any: bool = False,
) -> str:
    options = list_transcript_options(video_id)
    if not options:
        raise ValueError("No transcript is available for this video.")

    candidate_languages: list[str] = []
    if language_code:
        candidate_languages.append(language_code)
    if prefer_any and not language_code:
        candidate_languages.extend(option.language_code for option in options)
    elif prefer_any and language_code:
        candidate_languages.extend(
            option.language_code for option in options if option.language_code != language_code
        )

    try:
        fetched = _api().fetch(
            video_id,
            languages=tuple(candidate_languages or [options[0].language_code]),
            preserve_formatting=False,
        )
    except NoTranscriptFound as exc:
        raise ValueError("The requested transcript language is not available for this video.") from exc
    except TranscriptsDisabled as exc:
        raise ValueError("Transcripts are disabled for this video.") from exc

    header = [
        f"Language: {fetched.language} ({fetched.language_code})",
        f"Type: {'Auto-generated' if fetched.is_generated else 'Manual'}",
        "",
    ]
    lines = header + [snippet.text.strip() for snippet in fetched if snippet.text.strip()]
    return "\n".join(lines).strip()


def prepare_transcript_download(
    video_id: str,
    language_code: str | None,
    *,
    prefer_generated: bool | None = None,
    prefer_any: bool = False,
    video_title: str | None = None,
) -> PreparedArtifact:
    transcript_text = fetch_transcript_text(
        video_id,
        language_code,
        prefer_generated=prefer_generated,
        prefer_any=prefer_any,
    )
    temp_dir = safe_temp_dir("yt-tools-transcript-")
    base_name = sanitize_filename(video_title or video_id, video_id)
    suffix = language_code or "transcript"
    file_path = temp_dir / f"{base_name}-{suffix}.txt"
    file_path.write_text(transcript_text, encoding="utf-8")
    return PreparedArtifact(
        file_path=str(file_path),
        file_name=file_path.name,
        mime_type=guess_mime_type(file_path),
        size_bytes=file_path.stat().st_size,
        source_item_id=video_id,
        artifact_type="transcript",
    )
