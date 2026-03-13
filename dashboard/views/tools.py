from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import streamlit as st

from dashboard.components.visualizations import section_header, styled_dataframe
from src.services.transcript_service import TranscriptOption, fetch_transcript_text, list_transcript_options, prepare_transcript_download
from src.services.youtube_tools import (
    PLAYLIST_PREVIEW_LIMIT_DEFAULT,
    STREAMLIT_DOWNLOAD_LIMIT_BYTES,
    BatchItemResult,
    FormatOption,
    PlaylistPreview,
    PreparedArtifact,
    VideoMetadata,
    fetch_playlist_preview,
    fetch_video_metadata,
    ffmpeg_available,
    get_available_formats,
    prepare_audio_download,
    prepare_batch_operation,
    prepare_playlist_operation,
    prepare_thumbnail_download,
    prepare_video_download,
    validate_youtube_url,
)
from src.utils.file_utils import cleanup_temp_dirs


TOOLS_STATE_KEYS = (
    "tools_single_preview",
    "tools_single_formats",
    "tools_single_transcripts",
    "tools_single_artifacts",
    "tools_single_transcript_text",
    "tools_single_error",
    "tools_batch_results",
    "tools_batch_error",
    "tools_playlist_preview",
    "tools_playlist_results",
    "tools_playlist_error",
    "tools_temp_paths",
    "tools_error",
    "tools_last_mode",
)

OPERATION_OPTIONS = {
    "Metadata Preview": "metadata",
    "Thumbnail Download": "thumbnail",
    "Transcript Export": "transcript",
    "Audio Download": "audio",
    "Video Download": "video",
}
THUMBNAIL_QUALITY_OPTIONS = ["Best Available", "High", "Medium", "Low"]
TRANSCRIPT_LANGUAGE_OPTIONS = {
    "Any Available": "",
    "English (en)": "en",
    "Spanish (es)": "es",
    "Hindi (hi)": "hi",
    "Portuguese (Brazil)": "pt-BR",
    "German (de-DE)": "de-DE",
    "French (fr)": "fr",
    "Japanese (ja)": "ja",
}
AUDIO_PROFILE_OPTIONS = {
    "Best Audio (Original Container)": "best_audio_original",
    "MP3 Conversion": "mp3_conversion",
}
VIDEO_PROFILE_OPTIONS = {
    "Best Available": "best_available",
    "Up To 1080p": "up_to_1080p",
    "Up To 720p": "up_to_720p",
    "Up To 480p": "up_to_480p",
}


def _inject_tools_css() -> None:
    st.markdown(
        """
        <style>
        .tools-page {
            max-width: var(--app-page-width);
            margin: 0 auto;
        }
        .tools-hero {
            max-width: 920px;
            margin: 0 auto 1.6rem;
            text-align: center;
        }
        .tools-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.45rem 0.78rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.08);
            color: #F7F8FC;
            font-size: 12px;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-bottom: 0.95rem;
        }
        .tools-kicker-dot {
            width: 8px;
            height: 8px;
            border-radius: 999px;
            background: linear-gradient(180deg, #A855F7, #8B5CF6);
            box-shadow: 0 0 16px rgba(139, 92, 246, 0.45);
        }
        .tools-title {
            font-family: "Space Grotesk", "Plus Jakarta Sans", system-ui, sans-serif;
            font-size: clamp(36px, 3.8vw, 52px);
            line-height: 1.02;
            font-weight: 700;
            color: #F7F8FC;
            letter-spacing: -0.04em;
            margin-bottom: 0.8rem;
        }
        .tools-subtitle {
            color: #B8C1DA;
            font-size: 16px;
            line-height: 1.65;
            max-width: 760px;
            margin: 0 auto;
        }
        .tools-pill-row {
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 1rem;
        }
        .tools-pill {
            padding: 0.42rem 0.78rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            color: #D7DDF0;
            font-size: 12px;
        }
        .tools-card {
            border-radius: 24px;
            border: 1px solid rgba(255,255,255,0.08);
            background:
                radial-gradient(circle at top left, rgba(139, 92, 246, 0.10) 0%, transparent 30%),
                linear-gradient(180deg, rgba(26, 33, 64, 0.95) 0%, rgba(15, 19, 36, 0.98) 100%);
            box-shadow: 0 20px 46px rgba(3, 6, 20, 0.40);
            padding: 1.2rem 1.25rem;
            margin-bottom: 1rem;
        }
        .tools-card-title {
            font-family: "Space Grotesk", "Plus Jakarta Sans", system-ui, sans-serif;
            color: #F7F8FC;
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 0.3rem;
        }
        .tools-card-copy {
            color: #B8C1DA;
            font-size: 13px;
            line-height: 1.55;
        }
        .tools-summary-grid {
            display: grid;
            gap: 0.7rem;
            margin-top: 0.95rem;
        }
        .tools-summary-item {
            padding: 0.75rem 0.85rem;
            border-radius: 18px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
        }
        .tools-summary-label {
            color: #8993B2;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.22rem;
        }
        .tools-summary-value {
            color: #F7F8FC;
            font-size: 14px;
            font-weight: 700;
        }
        .tools-meta-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.7rem;
            margin-top: 0.9rem;
        }
        .tools-meta-item {
            padding: 0.75rem 0.85rem;
            border-radius: 16px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
        }
        .tools-meta-label {
            color: #8993B2;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.22rem;
        }
        .tools-meta-value {
            color: #F7F8FC;
            font-size: 14px;
            line-height: 1.45;
            font-weight: 700;
        }
        .tools-status-ready,
        .tools-status-error,
        .tools-status-warning {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.24rem 0.6rem;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .tools-status-ready {
            color: #D1FAE5;
            background: rgba(52, 211, 153, 0.12);
        }
        .tools-status-warning {
            color: #FDE68A;
            background: rgba(251, 191, 36, 0.12);
        }
        .tools-status-error {
            color: #FCA5A5;
            background: rgba(239, 68, 68, 0.16);
        }
        .tools-note {
            color: #97A2C3;
            font-size: 12px;
            line-height: 1.55;
        }
        .tools-result-card {
            padding: 0.9rem 1rem;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.07);
            background: rgba(255,255,255,0.03);
            margin-bottom: 0.85rem;
        }
        .tools-empty {
            padding: 1rem 1.1rem;
            border-radius: 20px;
            border: 1px dashed rgba(255,255,255,0.12);
            background: rgba(255,255,255,0.02);
            color: #B8C1DA;
            font-size: 13px;
            line-height: 1.6;
        }
        .tools-download-note {
            margin-top: 0.65rem;
            color: #97A2C3;
            font-size: 12px;
            line-height: 1.5;
        }
        .tools-divider {
            height: 1px;
            background: rgba(255,255,255,0.08);
            margin: 1rem 0;
        }
        @media (max-width: 900px) {
            .tools-meta-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _clear_tools_state(*, keep_single_inputs: bool = True) -> None:
    cleanup_temp_dirs(st.session_state.get("tools_temp_paths", []))
    for key in TOOLS_STATE_KEYS:
        if keep_single_inputs and key in {"tools_single_preview", "tools_single_formats", "tools_single_transcripts", "tools_single_artifacts", "tools_single_transcript_text", "tools_single_error"}:
            st.session_state.pop(key, None)
            continue
        st.session_state.pop(key, None)
    st.session_state["tools_temp_paths"] = []


def _clear_mode_state(prefix: str) -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(prefix):
            st.session_state.pop(key, None)


def _register_artifacts(artifacts: Iterable[PreparedArtifact]) -> None:
    paths = set(st.session_state.get("tools_temp_paths", []))
    for artifact in artifacts:
        paths.add(str(Path(artifact.file_path).parent))
    st.session_state["tools_temp_paths"] = sorted(paths)


def _render_hero() -> None:
    st.markdown(
        (
            '<div class="tools-page">'
            '<div class="tools-hero">'
            '<div class="tools-kicker"><span class="tools-kicker-dot"></span>Tools</div>'
            '<div class="tools-title">Download YouTube Assets Without Leaving The Workspace</div>'
            '<div class="tools-subtitle">Preview metadata, export thumbnails and transcripts, and prepare audio or video downloads with clear format choices. All assets stay temporary, and all utilities live in one standalone tools page.</div>'
            '<div class="tools-pill-row">'
            '<span class="tools-pill">Single Videos</span>'
            '<span class="tools-pill">Batch Operations</span>'
            '<span class="tools-pill">Playlist Workflows</span>'
            '<span class="tools-pill">Temporary Files Only</span>'
            '</div>'
            '</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def _summary_card(title: str, copy: str, items: list[tuple[str, str]]) -> None:
    blocks = "".join(
        (
            '<div class="tools-summary-item">'
            f'<div class="tools-summary-label">{escape(label)}</div>'
            f'<div class="tools-summary-value">{escape(value)}</div>'
            "</div>"
        )
        for label, value in items
    )
    st.markdown(
        (
            '<div class="tools-card">'
            f'<div class="tools-card-title">{escape(title)}</div>'
            f'<div class="tools-card-copy">{escape(copy)}</div>'
            f'<div class="tools-summary-grid">{blocks}</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def _render_metadata_card(metadata: VideoMetadata, transcript_options: list[TranscriptOption]) -> None:
    rows = [
        ("Title", metadata.title),
        ("Channel", metadata.channel),
        ("Duration", metadata.duration_label),
        ("Published", metadata.publish_date or "Unknown"),
        ("Video ID", metadata.video_id),
        ("Content Type", metadata.content_type),
        ("Transcript", f"{len(transcript_options)} language options" if transcript_options else "Not available"),
        ("Canonical URL", metadata.webpage_url),
    ]
    blocks = "".join(
        (
            '<div class="tools-meta-item">'
            f'<div class="tools-meta-label">{escape(label)}</div>'
            f'<div class="tools-meta-value">{escape(value)}</div>'
            '</div>'
        )
        for label, value in rows
    )
    st.markdown(
        (
            '<div class="tools-card">'
            '<div class="tools-card-title">Metadata Preview</div>'
            '<div class="tools-card-copy">This preview is cached for one hour to keep repeat lookups fast and quota-friendly.</div>'
            f'<div class="tools-meta-grid">{blocks}</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def _artifact_too_large(artifact: PreparedArtifact) -> bool:
    return artifact.size_bytes > STREAMLIT_DOWNLOAD_LIMIT_BYTES


def _render_download_button(artifact: PreparedArtifact, *, label: str, key: str) -> None:
    if _artifact_too_large(artifact):
        size_mb = artifact.size_bytes / (1024 * 1024)
        limit_mb = STREAMLIT_DOWNLOAD_LIMIT_BYTES / (1024 * 1024)
        st.warning(
            f"This file is {size_mb:.1f} MB. In-app downloads are limited to about {limit_mb:.0f} MB to keep the Streamlit session stable."
        )
        return
    file_path = Path(artifact.file_path)
    if not file_path.exists():
        st.error("This temporary file is no longer available. Prepare it again.")
        return
    st.download_button(
        label,
        data=file_path.read_bytes(),
        file_name=artifact.file_name,
        mime=artifact.mime_type,
        use_container_width=True,
        key=key,
    )
    st.caption(f"{artifact.file_name} • {(artifact.size_bytes / (1024 * 1024)):.2f} MB")


def _render_artifact_card(title: str, artifact: PreparedArtifact, *, button_label: str, key_prefix: str) -> None:
    st.markdown(
        (
            '<div class="tools-result-card">'
            f'<div class="tools-card-title" style="font-size:16px;margin-bottom:0.2rem;">{escape(title)}</div>'
            f'<div class="tools-note">{escape(artifact.file_name)}</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )
    _render_download_button(artifact, label=button_label, key=f"{key_prefix}_download")


def _split_url_lines(raw_text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        value = line.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        urls.append(value)
    return urls


def _render_operation_help(operation: str) -> None:
    notes = {
        "metadata": "Metadata mode validates each URL and returns title, channel, duration, and status without preparing files.",
        "thumbnail": "Thumbnail mode prepares the selected thumbnail quality for each item and exposes one download button per result.",
        "transcript": "Transcript mode retrieves public manual or auto-generated captions when available and exports them as text files.",
        "audio": "Audio mode prepares one downloadable audio artifact per item. MP3 conversion requires FFmpeg.",
        "video": "Video mode uses format profiles rather than exact format IDs in Batch and Playlist mode so results stay predictable across different videos.",
    }
    st.markdown(f'<div class="tools-note">{escape(notes[operation])}</div>', unsafe_allow_html=True)


def _batch_options_ui(prefix: str, operation: str) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if operation == "thumbnail":
        options["thumbnail_quality"] = st.selectbox(
            "Thumbnail Quality",
            THUMBNAIL_QUALITY_OPTIONS,
            index=0,
            key=f"{prefix}_thumbnail_quality",
        )
    elif operation == "transcript":
        display = st.selectbox(
            "Preferred Transcript Language",
            list(TRANSCRIPT_LANGUAGE_OPTIONS.keys()),
            index=0,
            key=f"{prefix}_transcript_language",
        )
        options["language_code"] = TRANSCRIPT_LANGUAGE_OPTIONS[display] or None
        options["prefer_any"] = st.toggle(
            "Fallback To Any Available Transcript",
            value=True,
            key=f"{prefix}_transcript_fallback",
        )
    elif operation == "audio":
        audio_labels = list(AUDIO_PROFILE_OPTIONS.keys())
        if not ffmpeg_available():
            audio_labels = [label for label in audio_labels if "MP3" not in label]
        audio_display = st.selectbox(
            "Audio Profile",
            audio_labels,
            index=0,
            key=f"{prefix}_audio_profile",
        )
        options["audio_profile"] = AUDIO_PROFILE_OPTIONS[audio_display]
    elif operation == "video":
        video_display = st.selectbox(
            "Video Quality Profile",
            list(VIDEO_PROFILE_OPTIONS.keys()),
            index=0,
            key=f"{prefix}_video_profile",
        )
        options["video_profile"] = VIDEO_PROFILE_OPTIONS[video_display]
    return options


def _render_results_table(results: list[BatchItemResult], *, title: str) -> None:
    if not results:
        return
    rows = []
    for result in results:
        rows.append(
            {
                "Title": result.metadata.title if result.metadata else "Unavailable",
                "Channel": result.metadata.channel if result.metadata else "—",
                "Status": result.status.title(),
                "Message": result.message,
                "Artifacts": len(result.artifacts),
            }
        )
    styled_dataframe(pd.DataFrame(rows), title=title, precision=0)


def _render_batch_result_cards(results: list[BatchItemResult], *, key_prefix: str) -> None:
    for index, result in enumerate(results):
        status_class = f"tools-status-{result.status}"
        with st.expander(
            f"{result.metadata.title if result.metadata else result.source_url} • {result.status.title()}",
            expanded=index == 0 and result.status == "ready",
        ):
            st.markdown(
                (
                    f'<span class="{status_class}">{escape(result.status)}</span>'
                    f'<div class="tools-divider"></div>'
                ),
                unsafe_allow_html=True,
            )
            if result.metadata:
                _render_metadata_card(result.metadata, [])
            st.markdown(f'<div class="tools-note">{escape(result.message)}</div>', unsafe_allow_html=True)
            for artifact_index, artifact in enumerate(result.artifacts):
                _render_artifact_card(
                    artifact.artifact_type.title(),
                    artifact,
                    button_label=f"Download {artifact.artifact_type.title()}",
                    key_prefix=f"{key_prefix}_{index}_{artifact_index}",
                )


def _single_summary_items() -> list[tuple[str, str]]:
    preview: VideoMetadata | None = st.session_state.get("tools_single_preview")
    formats = st.session_state.get("tools_single_formats") or {}
    transcripts = st.session_state.get("tools_single_transcripts") or []
    return [
        ("Current Target", preview.content_type if preview else "No Video Loaded"),
        ("FFmpeg", "Available" if ffmpeg_available() else "Not Installed"),
        ("Transcript", "Available" if transcripts else "Unavailable"),
        (
            "Formats",
            f"{len(formats.get('video', []))} video / {len(formats.get('audio', []))} audio" if preview else "Load metadata first",
        ),
    ]


def _render_single_tab() -> None:
    left, right = st.columns([1.35, 0.95], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### Single Video")
            st.caption("Paste one public YouTube video or Short URL to preview metadata and prepare individual assets.")
            with st.form("tools_single_lookup_form", clear_on_submit=False):
                url = st.text_input(
                    "YouTube URL",
                    key="tools_single_url",
                    placeholder="https://www.youtube.com/watch?v=...",
                )
                submitted = st.form_submit_button("Fetch Metadata", type="primary", use_container_width=True)
            if submitted:
                try:
                    target = validate_youtube_url(url)
                    if target.target_type == "playlist":
                        raise ValueError("Use the Playlist tab for playlist URLs.")
                    cleanup_temp_dirs(st.session_state.get("tools_temp_paths", []))
                    st.session_state["tools_temp_paths"] = []
                    with st.spinner("Loading metadata, formats, and transcript options..."):
                        preview = fetch_video_metadata(target.canonical_url)
                        formats = get_available_formats(target.canonical_url)
                        transcripts = list_transcript_options(preview.video_id)
                    st.session_state["tools_single_preview"] = preview
                    st.session_state["tools_single_formats"] = formats
                    st.session_state["tools_single_transcripts"] = transcripts
                    st.session_state["tools_single_artifacts"] = {}
                    st.session_state["tools_single_transcript_text"] = ""
                    st.session_state.pop("tools_single_error", None)
                except Exception as exc:
                    st.session_state["tools_single_error"] = str(exc)
                    st.session_state.pop("tools_single_preview", None)
                    st.session_state.pop("tools_single_formats", None)
                    st.session_state.pop("tools_single_transcripts", None)
        if st.session_state.get("tools_single_error"):
            st.error(st.session_state["tools_single_error"])

    with right:
        _summary_card(
            "Current Run Summary",
            "Preview one public video or Short at a time. Downloads remain temporary and are cleaned when the page state resets.",
            _single_summary_items(),
        )

    preview: VideoMetadata | None = st.session_state.get("tools_single_preview")
    if not preview:
        st.markdown(
            '<div class="tools-empty">Start with a public video or Short URL to unlock metadata preview, thumbnail export, transcripts, and exact format choices for single-item downloads.</div>',
            unsafe_allow_html=True,
        )
        return

    transcripts: list[TranscriptOption] = st.session_state.get("tools_single_transcripts", [])
    formats: dict[str, list[FormatOption]] = st.session_state.get("tools_single_formats", {})
    artifacts: dict[str, PreparedArtifact] = st.session_state.get("tools_single_artifacts", {})

    preview_cols = st.columns([1.25, 0.85], gap="large")
    with preview_cols[0]:
        _render_metadata_card(preview, transcripts)
    with preview_cols[1]:
        with st.container(border=True):
            st.markdown("### Thumbnail Preview")
            if preview.thumbnail_url:
                st.image(preview.thumbnail_url, use_container_width=True)
            else:
                st.info("No thumbnail is available for this video.")
            st.markdown('<div class="tools-download-note">Thumbnail quality options depend on the variants exposed by YouTube for this video.</div>', unsafe_allow_html=True)

    thumb_tab, transcript_tab, audio_tab, video_tab = st.tabs(["Thumbnail", "Transcript", "Audio", "Video"])

    with thumb_tab:
        with st.container(border=True):
            quality_options = list(preview.thumbnail_variants.keys()) or ["Best Available"]
            selected_quality = st.selectbox(
                "Thumbnail Quality",
                quality_options,
                index=0,
                key="tools_single_thumbnail_quality",
            )
            if st.button("Prepare Thumbnail Download", type="primary", use_container_width=True, key="tools_prepare_thumbnail"):
                with st.spinner("Preparing thumbnail..."):
                    artifact = prepare_thumbnail_download(preview.webpage_url, selected_quality)
                _register_artifacts([artifact])
                artifacts["thumbnail"] = artifact
                st.session_state["tools_single_artifacts"] = artifacts
            if artifacts.get("thumbnail"):
                _render_artifact_card(
                    "Prepared Thumbnail",
                    artifacts["thumbnail"],
                    button_label="Download Thumbnail",
                    key_prefix="tools_single_thumbnail",
                )

    with transcript_tab:
        with st.container(border=True):
            if not transcripts:
                st.info("No public transcript is available for this video.")
            else:
                transcript_labels = [f"{option.language_label} ({option.language_code})" for option in transcripts]
                selected_label = st.selectbox(
                    "Transcript Language",
                    transcript_labels,
                    index=0,
                    key="tools_single_transcript_language",
                )
                option = transcripts[transcript_labels.index(selected_label)]
                if st.button("Prepare Transcript Export", type="primary", use_container_width=True, key="tools_prepare_transcript"):
                    with st.spinner("Fetching transcript..."):
                        transcript_text = fetch_transcript_text(preview.video_id, option.language_code)
                        artifact = prepare_transcript_download(preview.video_id, option.language_code, video_title=preview.title)
                    _register_artifacts([artifact])
                    artifacts["transcript"] = artifact
                    st.session_state["tools_single_artifacts"] = artifacts
                    st.session_state["tools_single_transcript_text"] = transcript_text
                if st.session_state.get("tools_single_transcript_text"):
                    st.text_area(
                        "Transcript Preview",
                        value=st.session_state["tools_single_transcript_text"],
                        height=240,
                        key="tools_single_transcript_preview",
                    )
                if artifacts.get("transcript"):
                    _render_artifact_card(
                        "Prepared Transcript",
                        artifacts["transcript"],
                        button_label="Download Transcript",
                        key_prefix="tools_single_transcript",
                    )

    with audio_tab:
        with st.container(border=True):
            audio_formats = formats.get("audio", [])
            if not audio_formats:
                st.info("No downloadable audio-only formats are available for this video.")
            else:
                selected_audio = st.selectbox(
                    "Audio Format",
                    options=audio_formats,
                    index=0,
                    format_func=lambda option: option.label,
                    key="tools_single_audio_format",
                )
                if selected_audio.filesize_estimate and selected_audio.filesize_estimate > STREAMLIT_DOWNLOAD_LIMIT_BYTES:
                    st.warning("This audio format may be too large for an in-app download button. You can still try preparing it.")
                if st.button("Prepare Audio Download", type="primary", use_container_width=True, key="tools_prepare_audio"):
                    with st.spinner("Preparing audio..."):
                        artifact = prepare_audio_download(preview.webpage_url, selected_audio.selector)
                    _register_artifacts([artifact])
                    artifacts["audio"] = artifact
                    st.session_state["tools_single_artifacts"] = artifacts
                if artifacts.get("audio"):
                    _render_artifact_card(
                        "Prepared Audio",
                        artifacts["audio"],
                        button_label="Download Audio",
                        key_prefix="tools_single_audio",
                    )

    with video_tab:
        with st.container(border=True):
            video_formats = formats.get("video", [])
            if not video_formats:
                st.info("No downloadable video formats are available in the current environment.")
            else:
                selected_video = st.selectbox(
                    "Video Format",
                    options=video_formats,
                    index=0,
                    format_func=lambda option: option.label,
                    key="tools_single_video_format",
                )
                if selected_video.requires_ffmpeg and not ffmpeg_available():
                    st.warning("This format requires FFmpeg for audio/video merging.")
                if selected_video.filesize_estimate and selected_video.filesize_estimate > STREAMLIT_DOWNLOAD_LIMIT_BYTES:
                    st.warning("This video format may be too large for an in-app download button. You can still try preparing it.")
                if st.button("Prepare Video Download", type="primary", use_container_width=True, key="tools_prepare_video"):
                    with st.spinner("Preparing video..."):
                        artifact = prepare_video_download(preview.webpage_url, selected_video.selector)
                    _register_artifacts([artifact])
                    artifacts["video"] = artifact
                    st.session_state["tools_single_artifacts"] = artifacts
                if artifacts.get("video"):
                    _render_artifact_card(
                        "Prepared Video",
                        artifacts["video"],
                        button_label="Download Video",
                        key_prefix="tools_single_video",
                    )


def _render_batch_tab() -> None:
    left, right = st.columns([1.35, 0.95], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### Batch")
            st.caption("Paste one public YouTube URL per line. Batch mode processes items sequentially and keeps each result separate.")
            with st.form("tools_batch_form", clear_on_submit=False):
                raw_urls = st.text_area(
                    "YouTube URLs",
                    key="tools_batch_urls",
                    height=180,
                    placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...\nhttps://www.youtube.com/shorts/...",
                )
                operation_label = st.selectbox(
                    "Operation",
                    list(OPERATION_OPTIONS.keys()),
                    index=0,
                    key="tools_batch_operation",
                )
                operation = OPERATION_OPTIONS[operation_label]
                options = _batch_options_ui("tools_batch", operation)
                _render_operation_help(operation)
                submitted = st.form_submit_button("Run Batch", type="primary", use_container_width=True)
            if submitted:
                urls = _split_url_lines(raw_urls)
                if not urls:
                    st.session_state["tools_batch_error"] = "Paste at least one public YouTube URL."
                    st.session_state.pop("tools_batch_results", None)
                else:
                    try:
                        cleanup_temp_dirs(st.session_state.get("tools_temp_paths", []))
                        st.session_state["tools_temp_paths"] = []
                        with st.spinner("Processing batch items..."):
                            results = prepare_batch_operation(urls, operation, options=options)
                        all_artifacts = [artifact for result in results for artifact in result.artifacts]
                        _register_artifacts(all_artifacts)
                        st.session_state["tools_batch_results"] = results
                        st.session_state["tools_batch_error"] = ""
                    except Exception as exc:
                        st.session_state["tools_batch_error"] = str(exc)
                        st.session_state.pop("tools_batch_results", None)

    with right:
        urls = _split_url_lines(st.session_state.get("tools_batch_urls", ""))
        batch_operation = OPERATION_OPTIONS.get(st.session_state.get("tools_batch_operation", "Metadata Preview"), "metadata")
        _summary_card(
            "Batch Configuration",
            "Batch mode is best for metadata, thumbnails, transcripts, and smaller media runs. Results stay itemized so failures do not block the whole batch.",
            [
                ("URL Count", str(len(urls))),
                ("Operation", batch_operation.replace("_", " ").title()),
                ("FFmpeg", "Available" if ffmpeg_available() else "Not Installed"),
                ("Delivery Limit", f"{STREAMLIT_DOWNLOAD_LIMIT_BYTES // (1024 * 1024)} MB In-App"),
            ],
        )

    if st.session_state.get("tools_batch_error"):
        st.error(st.session_state["tools_batch_error"])

    results: list[BatchItemResult] = st.session_state.get("tools_batch_results", [])
    if not results:
        st.markdown(
            '<div class="tools-empty">Batch mode will show a status table first, followed by one expandable result card per item. Media downloads stay per-item in this version instead of being bundled into archives.</div>',
            unsafe_allow_html=True,
        )
        return

    section_header("Batch Results", "Review item-level statuses first, then open individual result cards to download artifacts or inspect failures.")
    _render_results_table(results, title="Batch Status")
    _render_batch_result_cards(results, key_prefix="tools_batch")


def _render_playlist_tab() -> None:
    left, right = st.columns([1.35, 0.95], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("### Playlist")
            st.caption("Load a public playlist, choose which items to process, then run one operation across the selected videos.")
            with st.form("tools_playlist_load_form", clear_on_submit=False):
                playlist_url = st.text_input(
                    "Playlist URL",
                    key="tools_playlist_url",
                    placeholder="https://www.youtube.com/playlist?list=...",
                )
                playlist_limit = st.slider(
                    "Preview Item Limit",
                    min_value=5,
                    max_value=50,
                    value=PLAYLIST_PREVIEW_LIMIT_DEFAULT,
                    step=5,
                    key="tools_playlist_limit",
                )
                load_clicked = st.form_submit_button("Load Playlist", type="primary", use_container_width=True)
            if load_clicked:
                try:
                    preview = fetch_playlist_preview(playlist_url, max_items=playlist_limit)
                    st.session_state["tools_playlist_preview"] = preview
                    st.session_state["tools_playlist_error"] = ""
                    st.session_state.pop("tools_playlist_results", None)
                except Exception as exc:
                    st.session_state["tools_playlist_error"] = str(exc)
                    st.session_state.pop("tools_playlist_preview", None)

    preview: PlaylistPreview | None = st.session_state.get("tools_playlist_preview")
    with right:
        _summary_card(
            "Playlist Summary",
            "Playlist mode previews public entries first, then applies one operation across the selected subset with per-item statuses and downloads.",
            [
                ("Playlist", preview.title if preview else "Not Loaded"),
                ("Preview Items", str(len(preview.entries)) if preview else "0"),
                ("FFmpeg", "Available" if ffmpeg_available() else "Not Installed"),
                ("Delivery Limit", f"{STREAMLIT_DOWNLOAD_LIMIT_BYTES // (1024 * 1024)} MB In-App"),
            ],
        )

    if st.session_state.get("tools_playlist_error"):
        st.error(st.session_state["tools_playlist_error"])

    if not preview:
        st.markdown(
            '<div class="tools-empty">Load a public playlist to preview entries, select items, and run transcript, thumbnail, audio, or video operations with per-item results.</div>',
            unsafe_allow_html=True,
        )
        return

    options = {f"{entry.title} — {entry.channel}": entry.video_id for entry in preview.entries}
    with st.container(border=True):
        st.markdown("### Playlist Run Configuration")
        with st.form("tools_playlist_run_form", clear_on_submit=False):
            selected_labels = st.multiselect(
                "Select Playlist Items",
                options=list(options.keys()),
                default=list(options.keys()),
                key="tools_playlist_selected_labels",
            )
            operation_label = st.selectbox(
                "Operation",
                list(OPERATION_OPTIONS.keys()),
                index=0,
                key="tools_playlist_operation",
            )
            operation = OPERATION_OPTIONS[operation_label]
            playlist_options = _batch_options_ui("tools_playlist", operation)
            playlist_options["playlist_max_items"] = st.session_state.get("tools_playlist_limit", PLAYLIST_PREVIEW_LIMIT_DEFAULT)
            _render_operation_help(operation)
            run_clicked = st.form_submit_button("Run Playlist Operation", type="primary", use_container_width=True)
        if run_clicked:
            selected_ids = [options[label] for label in selected_labels]
            if not selected_ids:
                st.session_state["tools_playlist_error"] = "Select at least one playlist item."
                st.session_state.pop("tools_playlist_results", None)
            else:
                try:
                    cleanup_temp_dirs(st.session_state.get("tools_temp_paths", []))
                    st.session_state["tools_temp_paths"] = []
                    with st.spinner("Processing selected playlist items..."):
                        results = prepare_playlist_operation(
                            st.session_state.get("tools_playlist_url", ""),
                            selected_ids,
                            operation,
                            options=playlist_options,
                        )
                    all_artifacts = [artifact for result in results for artifact in result.artifacts]
                    _register_artifacts(all_artifacts)
                    st.session_state["tools_playlist_results"] = results
                    st.session_state["tools_playlist_error"] = ""
                except Exception as exc:
                    st.session_state["tools_playlist_error"] = str(exc)
                    st.session_state.pop("tools_playlist_results", None)

    results: list[BatchItemResult] = st.session_state.get("tools_playlist_results", [])
    if not results:
        return

    section_header("Playlist Results", "Selected items are processed sequentially so each entry can succeed or fail independently.")
    _render_results_table(results, title="Playlist Status")
    _render_batch_result_cards(results, key_prefix="tools_playlist")


def render() -> None:
    _inject_tools_css()
    st.markdown('<div class="tools-page">', unsafe_allow_html=True)
    _render_hero()
    single_tab, batch_tab, playlist_tab = st.tabs(["Single", "Batch", "Playlist"])
    with single_tab:
        _render_single_tab()
    with batch_tab:
        _render_batch_tab()
    with playlist_tab:
        _render_playlist_tab()
    st.markdown(
        (
            '<div class="tools-card" style="margin-top:1.5rem;">'
            '<div class="tools-card-title">Tools Notes</div>'
            '<div class="tools-card-copy">'
            'The Tools page works with public YouTube URLs only. Private, members-only, age-gated, or region-restricted videos may fail. '
            'Downloads are prepared into temporary files and are not persisted by the app. Large files may be blocked from in-app delivery to keep the Streamlit session stable.'
            '</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
