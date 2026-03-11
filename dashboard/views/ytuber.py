import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:
    build = None
    HttpError = Exception

from dashboard.components.visualizations import (
    kpi_row,
    plotly_bar_chart,
    plotly_gauge_chart,
    plotly_heatmap,
    plotly_line_chart,
    plotly_radar_chart,
    plotly_scatter,
    plotly_treemap,
    section_header,
    styled_dataframe,
    styled_keyword_chips,
)
from src.llm_integration.thumbnail_generator import ThumbnailGenerator
from src.utils.api_keys import get_provider_key_count, run_with_provider_keys


DATASET_PATH = os.path.join("data", "youtube api data", "research_science_channels_videos.csv")
DEFAULT_CATEGORY = "research_science"
THUMB_KEYS = ["default", "medium", "high", "standard", "maxres"]
STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "for", "with", "on", "and", "or", "at", "is", "are", "was", "were",
    "this", "that", "how", "why", "what", "when", "from", "your", "you", "my", "we", "our", "it", "vs", "into",
}
POWER_WORDS = {
    "secret", "ultimate", "proven", "easy", "fast", "best", "shocking", "truth", "mistake", "science",
    "future", "breakthrough", "insane", "new", "critical", "warning", "guide", "explained", "hidden", "top",
}
WORKSPACE_MODULES = [
    "Overview",
    "Channel Audit",
    "Keyword Intel",
    "Title & SEO Lab",
    "Competitor Benchmark",
    "Trend Radar",
    "Content Planner",
    "AI Studio",
]
AI_STUDIO_TASKS = [
    "Full Pack (titles + descriptions + scripts + thumbnail concepts)",
    "Video Ideas",
    "Niche Expansion",
    "Titles Only",
    "Descriptions Only",
    "Scripts Only",
    "Hooks + CTAs",
    "Shorts Ideas",
    "Thumbnail Concepts",
]
QUICK_ACTIONS = [
    "Audit my channel",
    "Find niche",
    "New thumbnail",
    "Find keywords",
    "Video ideas",
    "Write script",
    "Make clips",
    "AI Shorts",
]
QUICK_ACTION_TO_MODULE = {
    "Audit my channel": "Channel Audit",
    "Find niche": "Keyword Intel",
    "New thumbnail": "AI Studio",
    "Find keywords": "Keyword Intel",
    "Video ideas": "AI Studio",
    "Write script": "AI Studio",
    "Make clips": "AI Studio",
    "AI Shorts": "AI Studio",
}
QUICK_ACTION_TO_TASK = {
    "Audit my channel": "Full Pack (titles + descriptions + scripts + thumbnail concepts)",
    "Find niche": "Niche Expansion",
    "New thumbnail": "Thumbnail Concepts",
    "Find keywords": "Titles Only",
    "Video ideas": "Video Ideas",
    "Write script": "Scripts Only",
    "Make clips": "Hooks + CTAs",
    "AI Shorts": "Shorts Ideas",
}
PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openai": "OpenAI / ChatGPT",
}
TEXT_MODEL_CATALOG = {
    "gemini": [
        {
            "id": "gemini-2.5-flash-lite",
            "label": "Gemini 2.5 Flash-Lite",
            "summary": "Fastest and lowest-cost Gemini text model",
            "input_per_million": 0.10,
            "output_per_million": 0.40,
        },
        {
            "id": "gemini-2.5-flash",
            "label": "Gemini 2.5 Flash",
            "summary": "Balanced reasoning, speed, and quality",
            "input_per_million": 0.30,
            "output_per_million": 2.50,
        },
    ],
    "openai": [
        {
            "id": "gpt-4o-mini",
            "label": "GPT-4o mini",
            "summary": "Fast, affordable model for production tasks",
            "input_per_million": 0.15,
            "output_per_million": 0.60,
        },
        {
            "id": "gpt-4.1-mini",
            "label": "GPT-4.1 mini",
            "summary": "Stronger instruction following at moderate cost",
            "input_per_million": 0.40,
            "output_per_million": 1.60,
        },
        {
            "id": "gpt-4.1",
            "label": "GPT-4.1",
            "summary": "Higher-quality non-reasoning model",
            "input_per_million": 2.00,
            "output_per_million": 8.00,
        },
        {
            "id": "gpt-4o",
            "label": "GPT-4o",
            "summary": "Flagship general-purpose model",
            "input_per_million": 2.50,
            "output_per_million": 10.00,
        },
    ],
}
IMAGE_MODEL_CATALOG = {
    "gemini": [
        {
            "id": "gemini-2.5-flash-image",
            "label": "Gemini 2.5 Flash Image",
            "summary": "Native Gemini image generation optimized for speed",
            "per_image": 0.039,
            "input_per_million": 0.30,
            "size_options": ["1024x1024"],
            "quality_options": ["standard"],
        },
    ],
    "openai": [
        {
            "id": "gpt-image-1-mini",
            "label": "GPT Image 1 Mini",
            "summary": "Lower-cost thumbnail generation",
            "pricing": {
                "low": {"1024x1024": 0.005, "1024x1536": 0.006, "1536x1024": 0.006},
                "medium": {"1024x1024": 0.011, "1024x1536": 0.015, "1536x1024": 0.015},
                "high": {"1024x1024": 0.036, "1024x1536": 0.052, "1536x1024": 0.052},
            },
            "size_options": ["1024x1024", "1024x1536", "1536x1024"],
            "quality_options": ["low", "medium", "high"],
        },
        {
            "id": "gpt-image-1",
            "label": "GPT Image 1",
            "summary": "Higher-fidelity image generation",
            "pricing": {
                "low": {"1024x1024": 0.011, "1024x1536": 0.016, "1536x1024": 0.016},
                "medium": {"1024x1024": 0.042, "1024x1536": 0.063, "1536x1024": 0.063},
                "high": {"1024x1024": 0.167, "1024x1536": 0.250, "1536x1024": 0.250},
            },
            "size_options": ["1024x1024", "1024x1536", "1536x1024"],
            "quality_options": ["low", "medium", "high"],
        },
    ],
}
AUDIENCE_OPTIONS = ["Broad", "Beginner", "Intermediate", "Advanced"]
FORMAT_OPTIONS = ["Long-form", "Shorts", "Mixed"]
STRATEGY_FILTERS = [
    "Evergreen",
    "Search-first",
    "Trend-reactive",
    "Authority-building",
    "High CTR",
    "Sponsor-safe",
]


def _safe_get(d: Dict[str, Any], path: List[str], default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _join_list(x: Optional[List[str]]) -> str:
    if not x:
        return ""
    return "|".join([str(i) for i in x])


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_channel_query(prompt_text: str) -> str:
    text = prompt_text.strip()
    if not text:
        return ""

    match = re.search(r"(UC[\w-]{20,}|@[A-Za-z0-9._-]+)", text)
    if match:
        return match.group(1)
    return text


def _goal_from_prompt(prompt_text: str) -> str:
    cleaned = re.sub(r"(UC[\w-]{20,}|@[A-Za-z0-9._-]+)", "", prompt_text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned


def _inject_ytuber_css() -> None:
    st.markdown(
        """
        <style>
        .ytuber-hero {
            max-width: 1080px;
            margin: 0 auto 1.5rem;
        }
        .ytuber-brand-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            justify-content: center;
            margin-bottom: 1rem;
        }
        .ytuber-brand-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.45rem 0.75rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.08);
            color: #FFFFFF;
            font-size: 12px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .ytuber-brand-badge.soft {
            color: #A8B0CC;
        }
        .ytuber-kicker {
            font-size: 12px;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: #7D8AB1;
            margin-bottom: 0.6rem;
            text-align: center;
        }
        .ytuber-title {
            font-size: clamp(38px, 5vw, 64px);
            line-height: 0.98;
            font-weight: 800;
            color: #FFFFFF;
            margin-bottom: 0.8rem;
            text-align: center;
        }
        .ytuber-subtitle {
            font-size: 17px;
            color: #A8B0CC;
            max-width: 820px;
            margin: 0 auto;
            text-align: center;
        }
        .ytuber-feature-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            justify-content: center;
            margin: 1.15rem auto 0;
            max-width: 900px;
        }
        .ytuber-feature-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.55rem 0.85rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.08);
            color: #E8EBF8;
            font-size: 13px;
        }
        .ytuber-command-card {
            max-width: 1040px;
            margin: 0 auto 1.1rem;
            padding: 1.35rem 1.35rem 1.1rem;
            border-radius: 28px;
            background: linear-gradient(180deg, rgba(20,23,42,0.95) 0%, rgba(11,13,28,0.96) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 30px 80px rgba(0,0,0,0.45);
        }
        .ytuber-command-title {
            font-size: 26px;
            color: #FFFFFF;
            font-weight: 700;
            margin-bottom: 0.25rem;
            text-align: center;
        }
        .ytuber-command-subtitle {
            font-size: 14px;
            color: #A8B0CC;
            text-align: center;
            margin-bottom: 0.95rem;
        }
        .ytuber-status-card {
            min-height: 96px;
        }
        .ytuber-status-label {
            font-size: 11px;
            color: #7D8AB1;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }
        .ytuber-status-value {
            font-size: 24px;
            color: #FFFFFF;
            font-weight: 700;
        }
        .ytuber-status-detail {
            font-size: 12px;
            color: #A8B0CC;
            margin-top: 0.15rem;
        }
        .ytuber-detected {
            font-size: 12px;
            color: #A8B0CC;
            margin-top: 0.5rem;
        }
        .ytuber-banner {
            border-radius: 22px;
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
            background: radial-gradient(circle at top left, rgba(255,255,255,0.07) 0%, rgba(22,33,62,0.95) 40%, rgba(6,6,20,0.98) 100%);
            border: 1px solid rgba(255,255,255,0.10);
            box-shadow: 0 16px 40px rgba(0,0,0,0.35);
        }
        .ytuber-banner-title {
            font-size: 20px;
            font-weight: 700;
            color: #FFFFFF;
            margin-bottom: 0.25rem;
        }
        .ytuber-banner-meta {
            font-size: 13px;
            color: #A8B0CC;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_connection_cards(provider_counts: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    if provider_counts is None:
        provider_counts = {
            "youtube": get_provider_key_count("youtube"),
            "gemini": get_provider_key_count("gemini"),
            "openai": get_provider_key_count("openai"),
        }

    cards = [
        ("YouTube Pool", provider_counts["youtube"], "Live channel fetch and benchmarking"),
        ("Gemini Pool", provider_counts["gemini"], "Text and image generation"),
        ("OpenAI Pool", provider_counts["openai"], "ChatGPT text and image generation"),
    ]

    cols = st.columns(3)
    for col, (label, count, detail) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="yt-card ytuber-status-card">
                    <div class="ytuber-status-label">{escape(label)}</div>
                    <div class="ytuber-status-value">{count}</div>
                    <div class="ytuber-status-detail">{escape(detail)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    return provider_counts


def _catalog_map(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {item["id"]: item for item in items}


def _format_text_model_option(provider: str, model_id: str) -> str:
    meta = _catalog_map(TEXT_MODEL_CATALOG[provider])[model_id]
    return f"{meta['label']}  •  ${meta['input_per_million']}/${meta['output_per_million']} per 1M in/out"


def _format_image_model_option(provider: str, model_id: str) -> str:
    meta = _catalog_map(IMAGE_MODEL_CATALOG[provider])[model_id]
    if provider == "gemini":
        return f"{meta['label']}  •  ~${meta['per_image']:.3f} per image"
    default_quality = meta["quality_options"][1] if len(meta["quality_options"]) > 1 else meta["quality_options"][0]
    default_size = meta["size_options"][0]
    default_cost = meta["pricing"][default_quality][default_size]
    return f"{meta['label']}  •  from ${default_cost:.3f} per image"


def _estimate_text_cost(
    provider: str,
    model_id: str,
    task: str,
    idea_count: int,
    script_count: int,
    thumbnail_count: int,
) -> Tuple[int, int, float]:
    meta = _catalog_map(TEXT_MODEL_CATALOG[provider])[model_id]

    base_input_tokens = 1800
    output_tokens = 0
    if task == "Full Pack (titles + descriptions + scripts + thumbnail concepts)":
        output_tokens = idea_count * 240 + script_count * 1100 + thumbnail_count * 80
    elif task == "Video Ideas":
        output_tokens = idea_count * 180
    elif task == "Niche Expansion":
        output_tokens = idea_count * 220
    elif task == "Titles Only":
        output_tokens = max(idea_count, 1) * 90
    elif task == "Descriptions Only":
        output_tokens = max(idea_count, 1) * 180
    elif task == "Scripts Only":
        output_tokens = script_count * 1400
    elif task == "Hooks + CTAs":
        output_tokens = max(idea_count, 1) * 120
    elif task == "Shorts Ideas":
        output_tokens = idea_count * 130
    elif task == "Thumbnail Concepts":
        output_tokens = thumbnail_count * 75

    estimated_cost = (
        (base_input_tokens / 1_000_000) * meta["input_per_million"]
        + (output_tokens / 1_000_000) * meta["output_per_million"]
    )
    return base_input_tokens, output_tokens, estimated_cost


def _estimate_image_cost(
    provider: str,
    model_id: str,
    image_count: int,
    size: str,
    quality: str,
) -> Tuple[float, float]:
    meta = _catalog_map(IMAGE_MODEL_CATALOG[provider])[model_id]
    if provider == "gemini":
        per_image = meta["per_image"]
    else:
        per_image = meta["pricing"][quality][size]
    return per_image, per_image * image_count


def _is_youtube_retryable_error(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status in (400, 401, 403, 429, 500, 503):
        return True

    message = str(exc).lower()
    retry_tokens = (
        "quota",
        "rate limit",
        "resource exhausted",
        "api key",
        "403",
        "429",
        "500",
        "503",
        "backenderror",
        "service unavailable",
        "daily limit",
        "forbidden",
        "access not configured",
    )
    return any(token in message for token in retry_tokens)


def _is_ai_retryable_error(exc: Exception) -> bool:
    message = str(exc).lower()
    retry_tokens = (
        "quota",
        "rate limit",
        "resource exhausted",
        "too many requests",
        "insufficient_quota",
        "api key",
        "401",
        "403",
        "429",
        "500",
        "503",
        "overloaded",
    )
    return any(token in message for token in retry_tokens)


def _generate_text_with_provider_pool(provider: str, model: str, prompt: str) -> str:
    provider_name = provider.lower().strip()
    if provider_name == "gemini":
        return run_with_provider_keys(
            "gemini",
            lambda key: _gemini_generate_text(key, model, prompt),
            retryable_error=_is_ai_retryable_error,
        )
    if provider_name == "openai":
        return run_with_provider_keys(
            "openai",
            lambda key: _openai_generate_text(key, model, prompt),
            retryable_error=_is_ai_retryable_error,
        )
    raise RuntimeError(f"Unsupported text provider: {provider}")


def _generate_images_with_provider_pool(
    provider: str,
    model: str,
    *,
    title: str,
    context: str,
    style: str,
    negative_prompt: str,
    count: int,
    size: str,
    quality: str,
) -> List[Any]:
    provider_name = provider.lower().strip()
    def _run_generate(key: str) -> List[Any]:
        generator = ThumbnailGenerator(
            provider=provider_name,
            api_key=key,
            model=model,
        )
        try:
            return generator.generate(
                title=title,
                context=context,
                style=style,
                negative_prompt=negative_prompt,
                count=count,
                size=size,
                quality=quality,
            )
        except TypeError as exc:
            if "unexpected keyword argument 'quality'" not in str(exc):
                raise
            return generator.generate(
                title=title,
                context=context,
                style=style,
                negative_prompt=negative_prompt,
                count=count,
                size=size,
            )

    return run_with_provider_keys(
        provider_name,
        _run_generate,
        retryable_error=_is_ai_retryable_error,
    )


def _api_call_with_backoff(fn, max_retries: int = 7):
    delay = 1.0
    last_exc = None
    for _ in range(max_retries):
        try:
            return fn()
        except HttpError as e:
            last_exc = e
            status = getattr(e.resp, "status", None)
            if status in (403, 429, 500, 503):
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
        except Exception as e:
            last_exc = e
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
    raise RuntimeError(f"API call failed after retries: {last_exc}")


def _yt_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _resolve_channel_id(youtube, handle_or_query: str) -> str:
    q = handle_or_query.strip()
    if q.startswith("UC") and len(q) >= 20:
        return q

    req = youtube.search().list(part="snippet", q=q, type="channel", maxResults=1)
    resp = _api_call_with_backoff(req.execute)
    items = resp.get("items", [])

    if not items and q.startswith("@"):
        q2 = q[1:]
        req2 = youtube.search().list(part="snippet", q=q2, type="channel", maxResults=1)
        resp2 = _api_call_with_backoff(req2.execute)
        items = resp2.get("items", [])

    if not items:
        raise RuntimeError(f"No channel found for: {handle_or_query}")

    channel_id = _safe_get(items[0], ["snippet", "channelId"])
    if not channel_id:
        raise RuntimeError(f"Search returned item without channelId for: {handle_or_query}")
    return channel_id


def _fetch_channel_details(youtube, channel_id: str) -> Dict[str, Any]:
    req = youtube.channels().list(
        part="snippet,contentDetails,statistics,brandingSettings,status,topicDetails",
        id=channel_id,
        maxResults=1,
    )
    resp = _api_call_with_backoff(req.execute)
    items = resp.get("items", [])
    if not items:
        raise RuntimeError(f"No channel details returned for channelId: {channel_id}")
    return items[0]


def _fetch_recent_video_ids(
    youtube,
    uploads_playlist_id: str,
    published_after_utc: datetime,
    max_videos: int = 600,
) -> List[str]:
    video_ids: List[str] = []
    page_token: Optional[str] = None
    stop = False

    while len(video_ids) < max_videos and not stop:
        req = youtube.playlistItems().list(
            part="contentDetails,snippet",
            playlistId=uploads_playlist_id,
            maxResults=min(50, max_videos - len(video_ids)),
            pageToken=page_token,
        )
        resp = _api_call_with_backoff(req.execute)

        for it in resp.get("items", []):
            vid = _safe_get(it, ["contentDetails", "videoId"])
            published_at = _safe_get(it, ["snippet", "publishedAt"])
            if not vid or not published_at:
                continue
            dt = pd.to_datetime(published_at, errors="coerce", utc=True)
            if pd.isna(dt):
                continue
            if dt.to_pydatetime() < published_after_utc:
                stop = True
                break
            video_ids.append(vid)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def _fetch_videos_details(youtube, video_ids: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        if not chunk:
            continue
        req = youtube.videos().list(
            part="snippet,contentDetails,statistics,status,topicDetails",
            id=",".join(chunk),
            maxResults=50,
        )
        resp = _api_call_with_backoff(req.execute)
        out.extend(resp.get("items", []))
    return out


def _extract_thumbnails(thumbnails: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not isinstance(thumbnails, dict):
        thumbnails = {}

    for k in THUMB_KEYS:
        v = thumbnails.get(k, {}) if isinstance(thumbnails.get(k, {}), dict) else {}
        out[f"thumb_{k}_url"] = v.get("url", "")
        out[f"thumb_{k}_width"] = v.get("width", "")
        out[f"thumb_{k}_height"] = v.get("height", "")
    return out


def _channel_fields(channel: Dict[str, Any], handle: str) -> Dict[str, Any]:
    snippet = channel.get("snippet", {}) or {}
    stats = channel.get("statistics", {}) or {}
    branding = _safe_get(channel, ["brandingSettings", "channel"], {}) or {}
    status = channel.get("status", {}) or {}
    topic = channel.get("topicDetails", {}) or {}

    uploads_pid = _safe_get(channel, ["contentDetails", "relatedPlaylists", "uploads"], "")

    return {
        "snapshot_utc": _iso_now(),
        "category_name": DEFAULT_CATEGORY,
        "channel_handle_used": handle,
        "channel_id": channel.get("id", ""),
        "channel_title": snippet.get("title", ""),
        "channel_description": snippet.get("description", ""),
        "channel_publishedAt": snippet.get("publishedAt", ""),
        "uploads_playlist_id": uploads_pid,
        "channel_country": branding.get("country", ""),
        "channel_keywords": branding.get("keywords", ""),
        "channel_defaultLanguage": branding.get("defaultLanguage", ""),
        "channel_madeForKids": status.get("madeForKids", ""),
        "channel_isLinked": status.get("isLinked", ""),
        "channel_subscriberCount": stats.get("subscriberCount", ""),
        "channel_viewCount": stats.get("viewCount", ""),
        "channel_videoCount": stats.get("videoCount", ""),
        "channel_topicCategories": _join_list(topic.get("topicCategories")),
        "channel_topicIds": _join_list(topic.get("topicIds")),
    }


def _video_row(video: Dict[str, Any], ch: Dict[str, Any]) -> Dict[str, Any]:
    sn = video.get("snippet", {}) or {}
    cd = video.get("contentDetails", {}) or {}
    stx = video.get("statistics", {}) or {}
    vs = video.get("status", {}) or {}
    tp = video.get("topicDetails", {}) or {}

    thumbs = sn.get("thumbnails", {}) or {}
    thumb_cols = _extract_thumbnails(thumbs)

    return {
        **ch,
        "video_id": video.get("id", ""),
        "video_title": sn.get("title", ""),
        "video_description": sn.get("description", ""),
        "video_publishedAt": sn.get("publishedAt", ""),
        "video_channelId": sn.get("channelId", ""),
        "video_categoryId": sn.get("categoryId", ""),
        "video_tags": _join_list(sn.get("tags")),
        "video_defaultLanguage": sn.get("defaultLanguage", ""),
        "video_defaultAudioLanguage": sn.get("defaultAudioLanguage", ""),
        **thumb_cols,
        "views": stx.get("viewCount", ""),
        "likes": stx.get("likeCount", ""),
        "comments": stx.get("commentCount", ""),
        "duration": cd.get("duration", ""),
        "caption": cd.get("caption", ""),
        "licensedContent": cd.get("licensedContent", ""),
        "definition": cd.get("definition", ""),
        "projection": cd.get("projection", ""),
        "madeForKids": vs.get("madeForKids", ""),
        "embeddable": vs.get("embeddable", ""),
        "video_topicCategories": _join_list(tp.get("topicCategories")),
        "video_topicIds": _join_list(tp.get("topicIds")),
    }


def _load_dataset() -> pd.DataFrame:
    if not os.path.exists(DATASET_PATH):
        return pd.DataFrame()
    return pd.read_csv(DATASET_PATH)


def _append_rows_to_dataset(new_rows: pd.DataFrame, existing_df: pd.DataFrame) -> None:
    if new_rows.empty:
        return

    if existing_df.empty:
        os.makedirs(os.path.dirname(DATASET_PATH), exist_ok=True)
        new_rows.to_csv(DATASET_PATH, index=False)
        return

    existing_cols = existing_df.columns.tolist()
    for c in existing_cols:
        if c not in new_rows.columns:
            new_rows[c] = ""

    for c in new_rows.columns:
        if c not in existing_cols:
            existing_df[c] = ""
            existing_cols.append(c)

    new_rows = new_rows[existing_cols]
    new_rows.to_csv(DATASET_PATH, mode="a", header=False, index=False)


def _parse_iso_duration_seconds(duration: str) -> int:
    if not isinstance(duration, str):
        return 0
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def _ensure_numeric_and_dates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ["views", "likes", "comments"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    if "video_publishedAt" in out.columns:
        out["video_publishedAt"] = pd.to_datetime(out["video_publishedAt"], errors="coerce", utc=True)
    out["engagement_rate"] = (out["likes"].fillna(0) + out["comments"].fillna(0)) / out["views"].clip(lower=1)
    out["publish_month"] = out["video_publishedAt"].dt.to_period("M").astype(str)
    out["publish_day"] = out["video_publishedAt"].dt.day_name()
    out["publish_hour"] = out["video_publishedAt"].dt.hour
    out["duration_seconds"] = out["duration"].fillna("").astype(str).map(_parse_iso_duration_seconds)
    out["is_short"] = out["duration_seconds"] <= 60
    return out


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", str(text).lower())
    return [t for t in tokens if len(t) > 2 and t not in STOPWORDS]


def _top_keywords(df: pd.DataFrame, top_n: int = 30) -> List[str]:
    counter: Counter = Counter()
    for title in df["video_title"].fillna("").astype(str):
        counter.update(_tokenize(title))
    return [k for k, _ in counter.most_common(top_n)]


def _keyword_intel(df: pd.DataFrame, top_n: int = 40) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for _, row in df.iterrows():
        title = str(row.get("video_title", ""))
        views = float(row.get("views") or 0)
        eng = float(row.get("engagement_rate") or 0)
        published = row.get("video_publishedAt")
        recency_weight = 1.0
        if pd.notna(published):
            days = (now - published.to_pydatetime()).days
            recency_weight = max(0.1, 1 - min(days / 365, 0.9))

        seen = set(_tokenize(title))
        for token in seen:
            rows.append(
                {
                    "keyword": token,
                    "views": views,
                    "engagement": eng,
                    "recency_weight": recency_weight,
                }
            )

    if not rows:
        return pd.DataFrame(columns=["keyword", "videos", "avg_views", "avg_engagement", "momentum", "score"])

    kdf = pd.DataFrame(rows)
    out = (
        kdf.groupby("keyword", dropna=False)
        .agg(
            videos=("keyword", "count"),
            avg_views=("views", "mean"),
            avg_engagement=("engagement", "mean"),
            momentum=("recency_weight", "mean"),
        )
        .reset_index()
    )

    if out.empty:
        return out

    max_views = max(out["avg_views"].max(), 1)
    max_eng = max(out["avg_engagement"].max(), 0.0001)
    max_momentum = max(out["momentum"].max(), 0.0001)
    competition_proxy = out["videos"] / max(out["videos"].max(), 1)

    out["score"] = (
        (out["avg_views"] / max_views) * 40
        + (out["avg_engagement"] / max_eng) * 30
        + (out["momentum"] / max_momentum) * 20
        + (1 - competition_proxy) * 10
    )

    return out.sort_values("score", ascending=False).head(top_n)


def _title_score(title: str, keyword_hints: List[str]) -> Tuple[int, Dict[str, int], List[str]]:
    text = title.strip()
    lower = text.lower()

    length = len(text)
    word_count = len(text.split())

    length_score = max(0, 30 - int(abs(length - 55) * 0.8))
    clarity_score = 20 if 6 <= word_count <= 12 else max(6, 20 - abs(word_count - 9) * 2)
    number_score = 12 if re.search(r"\d", text) else 0
    curiosity_score = 10 if any(p in text for p in ["?", "!", ":"]) else 0
    power_score = min(15, sum(1 for w in POWER_WORDS if w in lower) * 5)
    keyword_matches = sum(1 for k in keyword_hints[:12] if k and k in lower)
    keyword_score = min(13, keyword_matches * 3)

    total = max(0, min(100, length_score + clarity_score + number_score + curiosity_score + power_score + keyword_score))

    suggestions: List[str] = []
    if length < 40:
        suggestions.append("Make title more specific; 45-65 chars usually performs better.")
    if length > 70:
        suggestions.append("Shorten title for stronger mobile readability.")
    if number_score == 0:
        suggestions.append("Consider adding a number or quantified claim.")
    if curiosity_score == 0:
        suggestions.append("Try adding a curiosity trigger such as '?' or a strong contrast.")
    if power_score == 0:
        suggestions.append("Use at least one strong power word (e.g., proven, hidden, breakthrough).")
    if keyword_score == 0 and keyword_hints:
        suggestions.append(f"Include one of your high-opportunity keywords: {', '.join(keyword_hints[:5])}.")

    parts = {
        "Length": int(length_score),
        "Clarity": int(clarity_score),
        "Numbers": int(number_score),
        "Curiosity": int(curiosity_score),
        "Power Words": int(power_score),
        "Keyword Match": int(keyword_score),
    }
    return total, parts, suggestions


def _description_score(description: str, keyword_hints: List[str]) -> Tuple[int, Dict[str, int], List[str]]:
    text = description.strip()
    lower = text.lower()
    length = len(text)

    length_score = 30 if 400 <= length <= 1800 else max(6, 30 - int(abs(length - 900) / 80))
    cta_score = 20 if any(x in lower for x in ["subscribe", "comment", "watch", "join", "follow", "link"]) else 5
    keyword_matches = sum(1 for k in keyword_hints[:15] if k in lower)
    keyword_score = min(25, keyword_matches * 4)
    structure_score = 15 if "\n" in text else 8
    hashtags = re.findall(r"#\w+", text)
    hashtag_score = 10 if 1 <= len(hashtags) <= 3 else 4

    total = max(0, min(100, length_score + cta_score + keyword_score + structure_score + hashtag_score))

    tips = []
    if length < 300:
        tips.append("Description is short; add context, value bullets, and timestamps if possible.")
    if cta_score < 20:
        tips.append("Add a clear CTA (subscribe, watch next, comment).")
    if keyword_score < 8 and keyword_hints:
        tips.append(f"Add relevant keywords: {', '.join(keyword_hints[:5])}.")
    if hashtag_score < 10:
        tips.append("Use 1-3 relevant hashtags, not more.")

    parts = {
        "Length": int(length_score),
        "CTA": int(cta_score),
        "Keywords": int(keyword_score),
        "Structure": int(structure_score),
        "Hashtags": int(hashtag_score),
    }
    return total, parts, tips


def _compute_channel_audit(df: pd.DataFrame) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    ordered = df.sort_values("video_publishedAt").copy()

    out["videos"] = len(ordered)
    out["median_views"] = float(ordered["views"].median()) if not ordered.empty else 0
    out["avg_engagement"] = float(ordered["engagement_rate"].mean()) if not ordered.empty else 0
    out["shorts_ratio"] = float(ordered["is_short"].mean()) if not ordered.empty else 0

    if len(ordered) > 2:
        gaps = ordered["video_publishedAt"].diff().dt.total_seconds().dropna() / 86400
        mean_gap = float(gaps.mean()) if not gaps.empty else 0
        std_gap = float(gaps.std()) if not gaps.empty else 0
        consistency = max(0.0, 100 - (std_gap / max(mean_gap, 1)) * 40)
    else:
        mean_gap = 0
        consistency = 0

    out["avg_upload_gap_days"] = mean_gap
    out["consistency_score"] = float(consistency)

    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    previous_cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    recent = ordered[ordered["video_publishedAt"] >= recent_cutoff]
    previous = ordered[(ordered["video_publishedAt"] < recent_cutoff) & (ordered["video_publishedAt"] >= previous_cutoff)]

    recent_avg = float(recent["views"].mean()) if not recent.empty else 0
    previous_avg = float(previous["views"].mean()) if not previous.empty else 0
    growth = ((recent_avg - previous_avg) / previous_avg * 100) if previous_avg > 0 else 0
    out["view_growth_90d_pct"] = growth

    threshold = max(float(ordered["views"].median()) * 2.0, 1.0)
    out["outlier_rate"] = float((ordered["views"] >= threshold).mean()) if not ordered.empty else 0

    return out


def _fetch_or_get_cached_channel(
    channel_query: str,
    force_refresh: bool,
    youtube_api_key: Optional[str] = None,
) -> Tuple[pd.DataFrame, str, str, str]:
    existing_df = _load_dataset()
    existing_df = _ensure_numeric_and_dates(existing_df) if not existing_df.empty else existing_df
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)

    def _load_with_key(api_key: str) -> Tuple[pd.DataFrame, str, str, str]:
        youtube = _yt_client(api_key)
        channel_id = _resolve_channel_id(youtube, channel_query)

        cached = pd.DataFrame()
        if not existing_df.empty and "channel_id" in existing_df.columns:
            cached = existing_df[existing_df["channel_id"].astype(str) == str(channel_id)].copy()

        if not cached.empty and not force_refresh:
            cached_recent = cached[cached["video_publishedAt"] >= pd.Timestamp(cutoff)]
            if not cached_recent.empty:
                title = (
                    cached_recent["channel_title"].dropna().iloc[0]
                    if "channel_title" in cached_recent.columns
                    else channel_id
                )
                return cached_recent, "dataset_cache", channel_id, title

        channel = _fetch_channel_details(youtube, channel_id)
        uploads_pid = _safe_get(channel, ["contentDetails", "relatedPlaylists", "uploads"], "")
        if not uploads_pid:
            raise RuntimeError("Channel uploads playlist not found.")

        video_ids = _fetch_recent_video_ids(youtube, uploads_pid, cutoff, max_videos=600)
        if not video_ids:
            if not cached.empty:
                title = (
                    cached["channel_title"].dropna().iloc[0]
                    if "channel_title" in cached.columns
                    else channel_id
                )
                return cached, "dataset_cache", channel_id, title
            raise RuntimeError("No videos found in last 1 year for this channel.")

        videos = _fetch_videos_details(youtube, video_ids)
        ch = _channel_fields(channel, channel_query)
        rows = []
        for v in videos:
            vid = str(v.get("id", "")).strip()
            if not vid:
                continue
            rows.append(_video_row(v, ch))

        new_df = pd.DataFrame(rows)
        if new_df.empty:
            raise RuntimeError("API returned no usable video rows.")

        if not existing_df.empty and "video_id" in existing_df.columns:
            existing_ids = set(existing_df["video_id"].dropna().astype(str).tolist())
            new_df = new_df[~new_df["video_id"].astype(str).isin(existing_ids)]

        _append_rows_to_dataset(new_df, _load_dataset())

        full = _ensure_numeric_and_dates(_load_dataset())
        channel_df = full[full["channel_id"].astype(str) == str(channel_id)].copy()
        recent_df = channel_df[channel_df["video_publishedAt"] >= pd.Timestamp(cutoff)]
        title = _safe_get(channel, ["snippet", "title"], channel_id)
        return recent_df if not recent_df.empty else channel_df, "youtube_api", channel_id, str(title)

    if youtube_api_key and youtube_api_key.strip():
        return _load_with_key(youtube_api_key.strip())

    return run_with_provider_keys(
        "youtube",
        _load_with_key,
        retryable_error=_is_youtube_retryable_error,
    )


def _gemini_generate_text(gemini_key: str, model: str, prompt: str) -> str:
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={gemini_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(endpoint, json=payload, timeout=90)
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini text API error ({response.status_code}): {response.text[:500]}")

    body = response.json()
    texts: List[str] = []
    for candidate in body.get("candidates", []):
        for part in _safe_get(candidate, ["content", "parts"], []) or []:
            txt = part.get("text")
            if txt:
                texts.append(txt)

    if not texts:
        raise RuntimeError("Gemini did not return text output.")
    return "\n\n".join(texts)


def _openai_generate_text(openai_key: str, model: str, prompt: str) -> str:
    """Call OpenAI chat completions to generate strategy text."""
    endpoint = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an advanced YouTube strategist supporting the "
                    "YouTube IP V3 creator analytics platform. "
                    "Keep outputs concise, structured, and actionable."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }
    response = requests.post(endpoint, headers=headers, json=payload, timeout=90)
    if response.status_code >= 400:
        raise RuntimeError(
            f"OpenAI text API error ({response.status_code}): {response.text[:500]}"
        )
    body = response.json()
    choices = body.get("choices", [])
    if not choices:
        raise RuntimeError("OpenAI did not return any choices.")
    message = choices[0].get("message", {}) or {}
    content = message.get("content") or ""
    if not content:
        raise RuntimeError("OpenAI returned an empty message content.")
    return content


def _render_overview(channel_df: pd.DataFrame) -> None:
    section_header("Channel Overview", icon="📈")

    total_videos = len(channel_df)
    total_views = int(channel_df["views"].fillna(0).sum())
    total_likes = int(channel_df["likes"].fillna(0).sum())
    total_comments = int(channel_df["comments"].fillna(0).sum())
    avg_views = int(channel_df["views"].fillna(0).mean())
    med_eng = channel_df["engagement_rate"].median() * 100

    kpi_row(
        [
            {"label": "Videos (1Y)", "value": f"{total_videos:,}", "icon": "🎬"},
            {"label": "Total Views", "value": f"{total_views:,}", "icon": "👁️"},
            {"label": "Total Likes", "value": f"{total_likes:,}", "icon": "❤️"},
            {"label": "Total Comments", "value": f"{total_comments:,}", "icon": "💬"},
            {"label": "Avg Views / Video", "value": f"{avg_views:,}", "icon": "📊"},
            {"label": "Median Engagement", "value": f"{med_eng:.2f} %", "icon": "💡"},
        ]
    )

    left, right = st.columns(2)

    with left:
        section_header("Monthly Video + Views Trend", icon="📆")
        trend = (
            channel_df.groupby("publish_month")
            .agg(videos=("video_id", "count"), views=("views", "sum"))
            .reset_index()
            .sort_values("publish_month")
        )
        fig = plotly_line_chart(
            trend,
            x="publish_month",
            y_cols=["videos", "views"],
            title="Uploads and Views",
            secondary_y=["views"],
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        section_header("Top 12 Videos", icon="⭐")
        top_videos = channel_df[
            [
                "video_title",
                "views",
                "likes",
                "comments",
                "engagement_rate",
                "video_publishedAt",
                "video_id",
            ]
        ].sort_values("views", ascending=False).head(12)
        styled_dataframe(top_videos, title=None, precision=2)


def _render_channel_audit(channel_df: pd.DataFrame) -> None:
    section_header("Channel Audit", icon="🧪")
    audit = _compute_channel_audit(channel_df)

    kpi_row(
        [
            {
                "label": "Consistency Score",
                "value": f"{audit['consistency_score']:.1f}/100",
                "icon": "📆",
            },
            {
                "label": "Avg Upload Gap",
                "value": f"{audit['avg_upload_gap_days']:.1f} days",
                "icon": "⏱️",
            },
            {
                "label": "90d View Growth",
                "value": f"{audit['view_growth_90d_pct']:.1f}%",
                "icon": "📈",
            },
            {
                "label": "Outlier Rate",
                "value": f"{audit['outlier_rate'] * 100:.1f}%",
                "icon": "✨",
            },
        ]
    )

    st.markdown("**Audit Notes**")
    notes = []
    if audit["consistency_score"] < 45:
        notes.append("Upload cadence is inconsistent. Use a fixed weekly posting pattern.")
    if audit["view_growth_90d_pct"] < 0:
        notes.append("Views are down vs previous 90 days. Test stronger hooks and tighter titles.")
    if audit["outlier_rate"] < 0.08:
        notes.append("Few breakout videos detected. Increase experimentation with bold concepts.")
    if audit["shorts_ratio"] > 0.7:
        notes.append("Channel is heavily shorts-weighted; blend long-form to deepen session time.")
    if not notes:
        notes.append("Performance is stable. Focus on scaling repeatable winning formats.")

    for item in notes:
        st.markdown(
            f"""
            <div class="yt-card" style="padding:0.5rem 0.75rem;margin-bottom:0.35rem;">
                <span style="font-size:12px;color:#FFFFFF;">{item}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_keyword_intel(channel_df: pd.DataFrame) -> List[str]:
    section_header("Keyword Intelligence", icon="🔑")
    intel = _keyword_intel(channel_df)
    if intel.empty:
        st.info("Not enough text data to compute keyword insights.")
        return []

    styled_dataframe(intel, title=None, precision=2)

    top10 = intel.head(10)["keyword"].tolist()
    st.markdown("**High-opportunity keywords:**")
    styled_keyword_chips(top10)

    # Treemap and bar chart views
    if "score" in intel.columns:
        tree_fig = plotly_treemap(
            intel.head(40),
            path=["keyword"],
            values="score",
            title="Keyword Opportunity Treemap",
        )
        st.plotly_chart(tree_fig, use_container_width=True)

        bar_fig = plotly_bar_chart(
            intel.head(20).sort_values("score", ascending=False),
            x="keyword",
            y="score",
            title="Top Keyword Opportunities",
            horizontal=True,
        )
        st.plotly_chart(bar_fig, use_container_width=True)
    return intel["keyword"].tolist()


def _render_title_seo_lab(keyword_hints: List[str]) -> None:
    section_header("Title & SEO Lab", icon="🧪")
    test_title = st.text_input("Test title", value="The Hidden Physics Trick That Changes Everything")
    test_desc = st.text_area(
        "Test description",
        value="In this video we break down the science, show real examples, and explain how to apply this idea. Subscribe for more! #science #learning",
        height=120,
    )

    title_score, parts, tips = _title_score(test_title, keyword_hints)
    desc_score, desc_parts, desc_tips = _description_score(test_desc, keyword_hints)

    c1, c2 = st.columns(2)
    with c1:
        gauge = plotly_gauge_chart(title_score, "Title Score", max_val=100)
        st.plotly_chart(gauge, use_container_width=True)
        styled_dataframe(pd.DataFrame([parts]), title="Title Score Breakdown")
    with c2:
        gauge2 = plotly_gauge_chart(desc_score, "Description Score", max_val=100)
        st.plotly_chart(gauge2, use_container_width=True)
        styled_dataframe(pd.DataFrame([desc_parts]), title="Description Score Breakdown")

    if tips:
        st.markdown("**Title suggestions**")
        for t in tips:
            st.markdown(f"- {t}")
    if desc_tips:
        st.markdown("**Description suggestions**")
        for t in desc_tips:
            st.markdown(f"- {t}")


def _render_competitor_benchmark() -> None:
    section_header("Competitor Benchmark", icon="📊")
    handles = st.text_area(
        "Competitor handles (comma separated)",
        value="@3blue1brown,@veritasium,@smartereveryday",
        height=90,
    )

    run = st.button("Run Competitor Benchmark", use_container_width=True)
    if not run:
        st.caption("Enter competitor handles and run benchmark.")
        return

    if get_provider_key_count("youtube") <= 0:
        st.error("No YouTube API keys are configured for competitor benchmarking.")
        return

    competitors = [h.strip() for h in handles.split(",") if h.strip()]
    rows = []

    with st.spinner("Loading competitor channels..."):
        for handle in competitors:
            try:
                cdf, source, cid, title = _fetch_or_get_cached_channel(
                    handle,
                    force_refresh=False,
                )
                cdf = _ensure_numeric_and_dates(cdf)
                rows.append(
                    {
                        "handle": handle,
                        "channel_title": title,
                        "channel_id": cid,
                        "source": source,
                        "videos_1y": len(cdf),
                        "total_views": int(cdf["views"].fillna(0).sum()) if not cdf.empty else 0,
                        "avg_views": int(cdf["views"].fillna(0).mean()) if not cdf.empty else 0,
                        "median_engagement": float(cdf["engagement_rate"].median()) if not cdf.empty else 0.0,
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "handle": handle,
                        "channel_title": "ERROR",
                        "channel_id": "",
                        "source": "error",
                        "videos_1y": 0,
                        "total_views": 0,
                        "avg_views": 0,
                        "median_engagement": 0.0,
                        "error": str(exc),
                    }
                )

    if not rows:
        st.warning("No competitor data produced.")
        return

    bdf = pd.DataFrame(rows).sort_values("total_views", ascending=False)
    styled_dataframe(bdf, title=None, precision=1)

    if not bdf.empty:
        radar_series = {
            row["channel_title"]: [
                row["videos_1y"],
                row["total_views"],
                row["avg_views"],
                row["median_engagement"],
            ]
            for _, row in bdf.iterrows()
        }
        cats = ["Videos", "Total Views", "Avg Views", "Median Engagement"]
        radar_fig = plotly_radar_chart(cats, radar_series, "Competitor Shape")
        st.plotly_chart(radar_fig, use_container_width=True)

        bar_fig = plotly_bar_chart(
            bdf.head(10),
            x="channel_title",
            y="total_views",
            title="Total Views by Competitor",
            horizontal=True,
        )
        st.plotly_chart(bar_fig, use_container_width=True)


def _render_trend_radar(channel_df: pd.DataFrame) -> None:
    section_header("Trend Radar", icon="📡")
    now = datetime.now(timezone.utc)
    recent_60 = channel_df[channel_df["video_publishedAt"] >= (now - timedelta(days=60))]
    prev_60 = channel_df[
        (channel_df["video_publishedAt"] < (now - timedelta(days=60)))
        & (channel_df["video_publishedAt"] >= (now - timedelta(days=120)))
    ]

    def keyword_counter(frame: pd.DataFrame) -> Counter:
        c = Counter()
        for title in frame["video_title"].fillna("").astype(str):
            c.update(set(_tokenize(title)))
        return c

    c_recent = keyword_counter(recent_60)
    c_prev = keyword_counter(prev_60)

    rows = []
    for kw, recent_count in c_recent.items():
        prev_count = c_prev.get(kw, 0)
        growth = recent_count - prev_count
        rows.append(
            {
                "keyword": kw,
                "recent_mentions": recent_count,
                "previous_mentions": prev_count,
                "momentum_delta": growth,
            }
        )

    tdf = pd.DataFrame(rows)
    if tdf.empty:
        st.info("Not enough recent data for trend radar.")
        return

    tdf = tdf.sort_values(
        ["momentum_delta", "recent_mentions"], ascending=[False, False]
    ).head(25)
    styled_dataframe(tdf, title=None, precision=1)

    rising = tdf[tdf["momentum_delta"] > 0].copy()
    falling = tdf[tdf["momentum_delta"] <= 0].copy()

    if not rising.empty:
        rising_fig = plotly_bar_chart(
            rising.sort_values("momentum_delta", ascending=True),
            x="keyword",
            y="momentum_delta",
            title="🔥 Rising Keywords",
            horizontal=True,
        )
        st.plotly_chart(rising_fig, use_container_width=True)

    if not falling.empty:
        falling_fig = plotly_bar_chart(
            falling.sort_values("momentum_delta", ascending=True),
            x="keyword",
            y="momentum_delta",
            title="❄️ Falling Keywords",
            horizontal=True,
        )
        st.plotly_chart(falling_fig, use_container_width=True)


def _render_content_planner(channel_df: pd.DataFrame) -> None:
    section_header("Content Planner", icon="🗓️")

    day_perf = (
        channel_df.groupby("publish_day", dropna=False)
        .agg(avg_views=("views", "mean"), median_engagement=("engagement_rate", "median"), videos=("video_id", "count"))
        .reset_index()
        .sort_values("avg_views", ascending=False)
    )

    hour_perf = (
        channel_df.groupby("publish_hour", dropna=False)
        .agg(avg_views=("views", "mean"), median_engagement=("engagement_rate", "median"), videos=("video_id", "count"))
        .reset_index()
        .sort_values("avg_views", ascending=False)
    )

    best_day = day_perf.iloc[0]["publish_day"] if not day_perf.empty else "Wednesday"
    best_hour = int(hour_perf.iloc[0]["publish_hour"]) if not hour_perf.empty else 15

    kpi_row(
        [
            {"label": "Best Publishing Day", "value": str(best_day), "icon": "📅"},
            {
                "label": "Best Publishing Hour (UTC)",
                "value": f"{best_hour:02d}:00",
                "icon": "⏰",
            },
        ]
    )

    st.markdown("**Day Performance**")
    day_melt = day_perf.melt(
        id_vars="publish_day",
        value_vars=["avg_views", "median_engagement", "videos"],
        var_name="metric",
        value_name="value",
    )
    fig_day = plotly_heatmap(
        day_melt, x="publish_day", y="metric", z="value", title="Performance by Day"
    )
    st.plotly_chart(fig_day, use_container_width=True)

    st.markdown("**Hour Performance (UTC)**")
    fig_hour = plotly_bar_chart(
        hour_perf.head(24),
        x="publish_hour",
        y="avg_views",
        title="Views by Hour (UTC)",
    )
    st.plotly_chart(fig_hour, use_container_width=True)

    top_topics = _top_keywords(channel_df, top_n=12)
    if top_topics:
        st.markdown("**Suggested next content angles**")
        styled_keyword_chips(top_topics[:8])

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday_map = {d: i for i, d in enumerate(weekday_order)}
    target_weekday = weekday_map.get(best_day, 2)

    start = datetime.now(timezone.utc)
    plan_rows = []
    cursor = start
    for i in range(1, 5):
        while cursor.weekday() != target_weekday:
            cursor += timedelta(days=1)
        plan_rows.append(
            {
                "week": f"Week {i}",
                "publish_date_utc": cursor.date().isoformat(),
                "publish_time_utc": f"{best_hour:02d}:00",
                "topic_hint": top_topics[(i - 1) % max(len(top_topics), 1)] if top_topics else "core topic",
            }
        )
        cursor += timedelta(days=7)

    st.markdown("**4-Week Suggested Calendar**")
    calendar_df = pd.DataFrame(plan_rows)
    cols = st.columns(4)
    for idx, row in calendar_df.iterrows():
        col = cols[idx % 4]
        with col:
            st.markdown(
                f"""
                <div class="yt-card" style="padding:0.6rem 0.75rem;margin-bottom:0.6rem;">
                    <div style="font-size:11px;color:#B0B0B0;">{row['week']}</div>
                    <div style="font-size:16px;font-weight:600;color:#FFFFFF;">{row['publish_date_utc']}</div>
                    <div style="font-size:12px;color:#B0B0B0;margin-bottom:0.15rem;">{row['publish_time_utc']} UTC</div>
                    <div style="font-size:12px;color:#FFFFFF;">
                        <span class="keyword-chip">{row['topic_hint']}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_ai_studio(
    channel_df: pd.DataFrame,
    channel_title: str,
    channel_id: str,
    keyword_hints: List[str],
) -> None:
    section_header("AI Studio", icon="🤖")
    st.markdown('<div class="yt-card">', unsafe_allow_html=True)

    gemini_count = get_provider_key_count("gemini")
    openai_count = get_provider_key_count("openai")
    available_text_providers = [
        provider for provider in ["gemini", "openai"] if get_provider_key_count(provider) > 0
    ]
    available_image_providers = available_text_providers[:]

    st.caption(
        f"Provider pools: Gemini `{gemini_count}` key(s) • OpenAI `{openai_count}` key(s). "
        "Generation uses the configured secret pools automatically."
    )

    if not available_text_providers and not available_image_providers:
        st.info("Add `GEMINI_API_KEYS` and/or `OPENAI_API_KEYS` in secrets to unlock AI Studio.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if "ytuber_ai_task" not in st.session_state or st.session_state["ytuber_ai_task"] not in AI_STUDIO_TASKS:
        st.session_state["ytuber_ai_task"] = AI_STUDIO_TASKS[0]

    default_text_provider = "gemini" if "gemini" in available_text_providers else available_text_providers[0]
    default_image_provider = "gemini" if "gemini" in available_image_providers else available_image_providers[0]
    if "ytuber_text_provider" not in st.session_state or st.session_state["ytuber_text_provider"] not in available_text_providers:
        st.session_state["ytuber_text_provider"] = default_text_provider
    if "ytuber_image_provider" not in st.session_state or st.session_state["ytuber_image_provider"] not in available_image_providers:
        st.session_state["ytuber_image_provider"] = default_image_provider

    control_col1, control_col2 = st.columns(2)
    with control_col1:
        text_provider = st.selectbox(
            "Text provider",
            available_text_providers,
            key="ytuber_text_provider",
            format_func=lambda value: PROVIDER_LABELS.get(value, value.title()),
        )
        text_model_options = [item["id"] for item in TEXT_MODEL_CATALOG[text_provider]]
        if (
            "ytuber_text_model_selection" not in st.session_state
            or st.session_state["ytuber_text_model_selection"] not in text_model_options
        ):
            st.session_state["ytuber_text_model_selection"] = text_model_options[0]
        text_model = st.selectbox(
            "Text model",
            text_model_options,
            key="ytuber_text_model_selection",
            format_func=lambda value: _format_text_model_option(text_provider, value),
        )
        text_model_meta = _catalog_map(TEXT_MODEL_CATALOG[text_provider])[text_model]
        st.caption(
            f"{text_model_meta['summary']}  •  "
            f"${text_model_meta['input_per_million']}/1M input tokens  •  "
            f"${text_model_meta['output_per_million']}/1M output tokens"
        )

    with control_col2:
        image_provider = st.selectbox(
            "Image provider",
            available_image_providers,
            key="ytuber_image_provider",
            format_func=lambda value: PROVIDER_LABELS.get(value, value.title()),
        )
        image_model_options = [item["id"] for item in IMAGE_MODEL_CATALOG[image_provider]]
        if (
            "ytuber_image_model_selection" not in st.session_state
            or st.session_state["ytuber_image_model_selection"] not in image_model_options
        ):
            st.session_state["ytuber_image_model_selection"] = image_model_options[0]
        image_model = st.selectbox(
            "Thumbnail model",
            image_model_options,
            key="ytuber_image_model_selection",
            format_func=lambda value: _format_image_model_option(image_provider, value),
        )
        image_model_meta = _catalog_map(IMAGE_MODEL_CATALOG[image_provider])[image_model]
        st.caption(image_model_meta["summary"])

    if (
        "ytuber_image_size" not in st.session_state
        or st.session_state["ytuber_image_size"] not in image_model_meta["size_options"]
    ):
        st.session_state["ytuber_image_size"] = image_model_meta["size_options"][0]
    if (
        "ytuber_image_quality" not in st.session_state
        or st.session_state["ytuber_image_quality"] not in image_model_meta["quality_options"]
    ):
        st.session_state["ytuber_image_quality"] = image_model_meta["quality_options"][0]

    image_tuning_col1, image_tuning_col2 = st.columns(2)
    with image_tuning_col1:
        image_size = st.selectbox(
            "Thumbnail size",
            image_model_meta["size_options"],
            key="ytuber_image_size",
            disabled=len(image_model_meta["size_options"]) == 1,
        )
    with image_tuning_col2:
        image_quality = st.selectbox(
            "Thumbnail quality",
            image_model_meta["quality_options"],
            key="ytuber_image_quality",
            disabled=len(image_model_meta["quality_options"]) == 1,
        )

    quantity_col1, quantity_col2, quantity_col3 = st.columns(3)
    with quantity_col1:
        idea_count = st.slider("Video ideas", min_value=1, max_value=12, value=5)
    with quantity_col2:
        script_count = st.slider("Scripts / outlines", min_value=1, max_value=6, value=2)
    with quantity_col3:
        thumbnail_count = st.slider("Thumbnail options", min_value=1, max_value=6, value=3)

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        audience_profile = st.selectbox("Audience level", AUDIENCE_OPTIONS, index=0)
        format_focus = st.selectbox("Format focus", FORMAT_OPTIONS, index=0)
    with filter_col2:
        strategy_filters = st.multiselect(
            "Strategy filters",
            STRATEGY_FILTERS,
            default=["Evergreen", "High CTR"],
        )
        exclude_topics = st.text_input(
            "Exclude / avoid",
            value="",
            placeholder="Overused themes, competitors, claims to avoid",
        )

    prompt_goal = _goal_from_prompt(st.session_state.get("ytuber_growth_prompt", ""))
    default_brief = (
        f"Goal: {prompt_goal}. Channel: {channel_title}. Build a sharp plan based on the current stats."
        if prompt_goal
        else f"Channel: {channel_title}. Create a high-performing next-month content plan grounded in the current stats."
    )
    creative_brief = st.text_area(
        "Creative brief",
        value=default_brief,
        key="ytuber_creative_brief",
        height=110,
    )

    output_type = st.selectbox(
        "Creative task",
        AI_STUDIO_TASKS,
        key="ytuber_ai_task",
    )

    input_tokens, output_tokens, estimated_text_cost = _estimate_text_cost(
        text_provider,
        text_model,
        output_type,
        idea_count,
        script_count,
        thumbnail_count,
    )
    image_unit_cost, estimated_image_cost = _estimate_image_cost(
        image_provider,
        image_model,
        thumbnail_count,
        image_size,
        image_quality,
    )

    estimate_col1, estimate_col2 = st.columns(2)
    with estimate_col1:
        st.markdown(
            f"""
            <div class="yt-card" style="padding:0.85rem 1rem;margin-bottom:0.75rem;">
                <div style="font-size:11px;color:#7D8AB1;letter-spacing:0.08em;text-transform:uppercase;">Estimated text spend</div>
                <div style="font-size:26px;font-weight:700;color:#FFFFFF;">${estimated_text_cost:.4f}</div>
                <div style="font-size:12px;color:#A8B0CC;margin-top:0.2rem;">~{input_tokens:,} input tokens and ~{output_tokens:,} output tokens for this task mix.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with estimate_col2:
        st.markdown(
            f"""
            <div class="yt-card" style="padding:0.85rem 1rem;margin-bottom:0.75rem;">
                <div style="font-size:11px;color:#7D8AB1;letter-spacing:0.08em;text-transform:uppercase;">Estimated thumbnail spend</div>
                <div style="font-size:26px;font-weight:700;color:#FFFFFF;">${estimated_image_cost:.4f}</div>
                <div style="font-size:12px;color:#A8B0CC;margin-top:0.2rem;">{thumbnail_count} image(s) at about ${image_unit_cost:.4f} each using {image_model_meta['label']}.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    col_a, col_b = st.columns(2)
    gen_text = col_a.button("Generate AI Content", use_container_width=True)
    gen_thumb = col_b.button("Generate Thumbnail Images", use_container_width=True)

    total_videos = len(channel_df)
    total_views = int(channel_df["views"].fillna(0).sum())
    avg_views = int(channel_df["views"].fillna(0).mean())
    med_eng = float(channel_df["engagement_rate"].median() * 100)

    if gen_text:
        count_instruction = ""
        if output_type == "Full Pack (titles + descriptions + scripts + thumbnail concepts)":
            count_instruction = (
                f"Generate exactly {idea_count} video ideas, {script_count} scripts/outlines, "
                f"and {thumbnail_count} thumbnail concepts."
            )
        elif output_type == "Video Ideas":
            count_instruction = f"Generate exactly {idea_count} video ideas."
        elif output_type == "Niche Expansion":
            count_instruction = f"Generate exactly {idea_count} niche opportunities with positioning notes."
        elif output_type == "Titles Only":
            count_instruction = f"Generate exactly {idea_count} title options."
        elif output_type == "Descriptions Only":
            count_instruction = f"Generate exactly {idea_count} video descriptions."
        elif output_type == "Scripts Only":
            count_instruction = f"Generate exactly {script_count} script or outline drafts."
        elif output_type == "Hooks + CTAs":
            count_instruction = f"Generate exactly {idea_count} hook and CTA sets."
        elif output_type == "Shorts Ideas":
            count_instruction = f"Generate exactly {idea_count} short-form ideas."
        elif output_type == "Thumbnail Concepts":
            count_instruction = f"Generate exactly {thumbnail_count} thumbnail concepts."

        prompt = (
                "You are an advanced YouTube strategist. "
                "Produce concise, high-performing outputs grounded in these channel stats.\n\n"
                f"Channel: {channel_title} ({channel_id})\n"
                f"Videos(1y): {total_videos}, Total views: {total_views}, Avg views/video: {avg_views}, Median engagement: {med_eng:.2f}%\n"
                f"Priority keywords: {', '.join(keyword_hints[:15])}\n"
                f"Task: {output_type}\n"
                f"Requested output counts: ideas={idea_count}, scripts={script_count}, thumbnails={thumbnail_count}\n"
                f"Audience level: {audience_profile}\n"
                f"Format focus: {format_focus}\n"
                f"Strategy filters: {', '.join(strategy_filters) if strategy_filters else 'None'}\n"
                f"Avoid / exclude: {exclude_topics or 'None'}\n"
                f"Brief: {creative_brief}\n\n"
                f"{count_instruction}\n"
                "When relevant include:\n"
                "- strong hooks\n"
                "- clear structure\n"
                "- search intent alignment\n"
                "- simple CTA\n"
            )
        with st.spinner("Generating AI content..."):
            try:
                model_name = text_model.strip()
                output = _generate_text_with_provider_pool(text_provider, model_name, prompt)

                st.markdown(
                    f"""
                    <div class="yt-card" style="margin-top:0.8rem;">
                        <div style="font-size:13px;color:#B0B0B0;margin-bottom:0.35rem;">AI Output</div>
                        <pre style="white-space:pre-wrap;font-size:13px;color:#FFFFFF;background:rgba(5,5,15,0.95);padding:0.75rem;border-radius:10px;border:1px solid rgba(255,255,255,0.12);max-height:520px;overflow:auto;">{output}</pre>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            except RuntimeError:
                # Error already surfaced to user.
                pass
            except Exception as exc:
                st.error(f"AI generation failed: {exc}")

    if gen_thumb:
        base_title = (
            channel_df.sort_values("views", ascending=False)
            .head(1)["video_title"]
            .iloc[0]
        )

        with st.spinner("Generating thumbnails..."):
            try:
                images = _generate_images_with_provider_pool(
                    image_provider,
                    image_model.strip(),
                    title=f"Inspired by: {base_title}",
                    context=(
                        f"{creative_brief}\n"
                        f"Audience level: {audience_profile}. "
                        f"Format focus: {format_focus}. "
                        f"Filters: {', '.join(strategy_filters) if strategy_filters else 'None'}."
                    ),
                    style=(
                        "High contrast, one clear subject, bold science aesthetic, 16:9 composition"
                    ),
                    negative_prompt=(
                        f"{exclude_topics}, clutter, tiny text, low contrast"
                        if exclude_topics
                        else "clutter, tiny text, low contrast"
                    ),
                    count=thumbnail_count,
                    size=image_size,
                    quality=image_quality,
                )
                out_dir = os.path.join("outputs", "thumbnails")
                os.makedirs(out_dir, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

                st.markdown('<div class="thumb-grid">', unsafe_allow_html=True)
                for idx, generated in enumerate(images, start=1):
                    ext = "png" if "png" in generated.mime_type else "jpg"
                    filename = f"ytuber_{channel_id}_{ts}_{idx}.{ext}"
                    with open(os.path.join(out_dir, filename), "wb") as fp:
                        fp.write(generated.image_bytes)
                    with st.container():
                        st.markdown('<div class="thumb-card">', unsafe_allow_html=True)
                        st.image(generated.image_bytes, use_container_width=True)
                        st.download_button(
                            label="Download",
                            data=generated.image_bytes,
                            file_name=filename,
                            mime=generated.mime_type,
                            use_container_width=True,
                            key=f"ytuber_thumb_{idx}_{ts}",
                        )
                        st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            except Exception as exc:
                st.error(f"Thumbnail generation failed: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)


def render() -> None:
    if build is None:
        st.error("Missing dependency: google-api-python-client. Install with: python3 -m pip install google-api-python-client")
        return

    _inject_ytuber_css()

    if "ytuber_growth_prompt" not in st.session_state:
        st.session_state["ytuber_growth_prompt"] = "@veritasium"
    if "ytuber_module_selection" not in st.session_state or st.session_state["ytuber_module_selection"] not in WORKSPACE_MODULES:
        st.session_state["ytuber_module_selection"] = WORKSPACE_MODULES[0]
    provider_counts = {
        "youtube": get_provider_key_count("youtube"),
        "gemini": get_provider_key_count("gemini"),
        "openai": get_provider_key_count("openai"),
    }

    st.markdown(
        """
        <div class="ytuber-hero">
            <div class="ytuber-brand-row">
                <span class="ytuber-brand-badge">YouTube IP V3</span>
                <span class="ytuber-brand-badge soft">Creator Intelligence Suite</span>
            </div>
            <div class="ytuber-kicker">Live channel intelligence for teams and creators</div>
            <div class="ytuber-title">Audit channels, uncover keyword gaps, and ship better YouTube strategy faster.</div>
            <div class="ytuber-subtitle">
                Use one workspace for live channel audits, competitor benchmarking, content planning, and
                AI-assisted idea, script, and thumbnail generation while keeping the existing dark product theme.
            </div>
            <div class="ytuber-feature-row">
                <span class="ytuber-feature-pill">Live channel audit</span>
                <span class="ytuber-feature-pill">Keyword and niche intelligence</span>
                <span class="ytuber-feature-pill">Competitor benchmarking</span>
                <span class="ytuber-feature-pill">Publishing planner</span>
                <span class="ytuber-feature-pill">AI scripts and thumbnails</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="ytuber-command-card">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="ytuber-command-title">Start with a channel</div>
        <div class="ytuber-command-subtitle">
            Paste a handle, name, or channel ID, pick a quick action, and launch the live workspace.
        </div>
        """,
        unsafe_allow_html=True,
    )
    growth_prompt = st.text_input(
        "How can I help you grow?",
        key="ytuber_growth_prompt",
        placeholder="@veritasium or 'Audit @veritasium and find the next niche to own'",
        label_visibility="collapsed",
    )
    detected_channel = _extract_channel_query(growth_prompt)
    if detected_channel:
        st.markdown(
            f"<div class='ytuber-detected'>Detected channel target: <code>{escape(detected_channel)}</code></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='ytuber-detected'>Paste a channel handle, name, or channel ID to load the live workspace.</div>",
            unsafe_allow_html=True,
        )

    selected_action = st.pills(
        "Quick actions",
        QUICK_ACTIONS,
        key="ytuber_quick_action",
        label_visibility="collapsed",
        selection_mode="single",
    )
    last_action = st.session_state.get("ytuber_last_applied_action")
    if selected_action and selected_action != last_action:
        st.session_state["ytuber_module_selection"] = QUICK_ACTION_TO_MODULE.get(
            selected_action,
            WORKSPACE_MODULES[0],
        )
        mapped_task = QUICK_ACTION_TO_TASK.get(selected_action)
        if mapped_task:
            st.session_state["ytuber_ai_task"] = mapped_task
        st.session_state["ytuber_last_applied_action"] = selected_action
    elif not selected_action:
        st.session_state["ytuber_last_applied_action"] = None

    controls_left, controls_mid, controls_right = st.columns([1.1, 1.1, 1.5])
    with controls_left:
        force_refresh = st.toggle(
            "Force live refresh",
            key="ytuber_force_refresh",
            help="Bypass cached rows and pull the last year from the YouTube API again.",
        )
    with controls_mid:
        st.caption(
            f"YouTube pool: {provider_counts['youtube']} key(s) ready"
            if provider_counts["youtube"] > 0
            else "YouTube pool missing"
        )
    with controls_right:
        analyze = st.button(
            "Load Live Workspace",
            type="primary",
            use_container_width=True,
            disabled=provider_counts["youtube"] <= 0,
        )
    st.markdown("</div>", unsafe_allow_html=True)
    _render_connection_cards(provider_counts)

    if provider_counts["youtube"] <= 0:
        st.warning(
            "No YouTube API keys are configured. Add `YOUTUBE_API_KEYS` or `YOUTUBE_API_KEY` in Streamlit secrets to enable live channel loading."
        )

    if analyze:
        channel_query = _extract_channel_query(st.session_state.get("ytuber_growth_prompt", ""))
        if not channel_query:
            st.error("Enter a channel handle, channel name, or channel ID in the prompt box.")
            return

        with st.spinner("Loading channel data from cache/API..."):
            try:
                channel_df, source, channel_id, channel_title = _fetch_or_get_cached_channel(
                    channel_query=channel_query.strip(),
                    force_refresh=force_refresh,
                )
            except Exception as exc:
                st.error(f"Failed to load channel data: {exc}")
                return

        st.session_state["ytuber_channel_df"] = channel_df
        st.session_state["ytuber_channel_title"] = channel_title
        st.session_state["ytuber_channel_id"] = channel_id
        st.session_state["ytuber_source"] = source
        st.session_state.pop("ytuber_keyword_hints", None)
        st.session_state.pop("ytuber_creative_brief", None)

    if "ytuber_channel_df" not in st.session_state:
        st.info("Load a channel to unlock the full Ytuber suite.")
        return

    channel_df = st.session_state["ytuber_channel_df"]
    channel_title = st.session_state.get("ytuber_channel_title", "")
    channel_id = st.session_state.get("ytuber_channel_id", "")
    source = st.session_state.get("ytuber_source", "")

    if channel_df.empty:
        st.warning("No videos available for this channel in the last year.")
        return

    channel_df = _ensure_numeric_and_dates(channel_df)
    focus_text = selected_action or "Explore the workspace"
    st.markdown(
        f"""
        <div class="ytuber-banner">
            <div class="ytuber-banner-title">{escape(channel_title)}</div>
            <div class="ytuber-banner-meta">
                Loaded from <code>{escape(source)}</code> • Channel ID <code>{escape(channel_id)}</code> •
                {len(channel_df):,} videos in view • Focus: <strong>{escape(focus_text)}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_module = st.segmented_control(
        "Workspace modules",
        WORKSPACE_MODULES,
        key="ytuber_module_selection",
        selection_mode="single",
        label_visibility="collapsed",
    )

    if selected_module == "Overview":
        _render_overview(channel_df)
    elif selected_module == "Channel Audit":
        _render_channel_audit(channel_df)
    elif selected_module == "Keyword Intel":
        keyword_hints = _render_keyword_intel(channel_df)
        st.session_state["ytuber_keyword_hints"] = keyword_hints
    elif selected_module == "Title & SEO Lab":
        hints = st.session_state.get("ytuber_keyword_hints") or _top_keywords(channel_df, 20)
        _render_title_seo_lab(hints)
    elif selected_module == "Competitor Benchmark":
        _render_competitor_benchmark()
    elif selected_module == "Trend Radar":
        _render_trend_radar(channel_df)
    elif selected_module == "Content Planner":
        _render_content_planner(channel_df)
    elif selected_module == "AI Studio":
        hints = st.session_state.get("ytuber_keyword_hints") or _top_keywords(channel_df, 20)
        _render_ai_studio(channel_df, channel_title, channel_id, hints)
