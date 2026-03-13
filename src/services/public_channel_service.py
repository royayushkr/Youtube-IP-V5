from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:  # pragma: no cover - import guard for environments without the dependency
    build = None
    HttpError = Exception

from src.utils.api_keys import run_with_provider_keys
from src.utils.channel_parser import extract_channel_query, normalize_channel_input


DATASET_PATH_DEFAULT = Path("data") / "youtube api data" / "research_science_channels_videos.csv"
DEFAULT_CATEGORY = "research_science"
THUMB_KEYS = ["default", "medium", "high", "standard", "maxres"]


@dataclass(frozen=True)
class PublicChannelWorkspace:
    channel_df: pd.DataFrame
    source: str
    channel_id: str
    channel_title: str
    canonical_url: str
    query_used: str


def _safe_get(data: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    current: Any = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _join_list(items: Optional[List[str]]) -> str:
    if not items:
        return ""
    return "|".join(str(item) for item in items)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _api_call_with_backoff(fn, max_retries: int = 7):
    delay = 1.0
    last_exc: Optional[Exception] = None
    for _ in range(max_retries):
        try:
            return fn()
        except HttpError as exc:
            last_exc = exc
            status = getattr(exc.resp, "status", None)
            if status in (403, 429, 500, 503):
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
        except Exception as exc:
            last_exc = exc
            time.sleep(delay)
            delay = min(delay * 2, 60)
    raise RuntimeError(f"YouTube API call failed after retries: {last_exc}")


def _yt_client(api_key: str):
    if build is None:
        raise RuntimeError(
            "Missing dependency: google-api-python-client. Install with: python3 -m pip install google-api-python-client"
        )
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _resolve_channel_id(youtube, lookup_value: str) -> str:
    query = lookup_value.strip()
    if query.startswith("UC") and len(query) >= 20:
        return query

    request = youtube.search().list(part="snippet", q=query, type="channel", maxResults=1)
    response = _api_call_with_backoff(request.execute)
    items = response.get("items", [])

    if not items and query.startswith("@"):
        fallback_query = query[1:]
        fallback_request = youtube.search().list(part="snippet", q=fallback_query, type="channel", maxResults=1)
        fallback_response = _api_call_with_backoff(fallback_request.execute)
        items = fallback_response.get("items", [])

    if not items:
        raise RuntimeError(f"No channel found for: {lookup_value}")

    channel_id = _safe_get(items[0], ["snippet", "channelId"])
    if not channel_id:
        raise RuntimeError(f"Search returned an item without channelId for: {lookup_value}")
    return channel_id


def _fetch_channel_details(youtube, channel_id: str) -> Dict[str, Any]:
    request = youtube.channels().list(
        part="snippet,contentDetails,statistics,brandingSettings,status,topicDetails",
        id=channel_id,
        maxResults=1,
    )
    response = _api_call_with_backoff(request.execute)
    items = response.get("items", [])
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
        request = youtube.playlistItems().list(
            part="contentDetails,snippet",
            playlistId=uploads_playlist_id,
            maxResults=min(50, max_videos - len(video_ids)),
            pageToken=page_token,
        )
        response = _api_call_with_backoff(request.execute)

        for item in response.get("items", []):
            video_id = _safe_get(item, ["contentDetails", "videoId"])
            published_at = _safe_get(item, ["snippet", "publishedAt"])
            if not video_id or not published_at:
                continue
            published_dt = pd.to_datetime(published_at, errors="coerce", utc=True)
            if pd.isna(published_dt):
                continue
            if published_dt.to_pydatetime() < published_after_utc:
                stop = True
                break
            video_ids.append(video_id)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def _fetch_videos_details(youtube, video_ids: List[str]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for index in range(0, len(video_ids), 50):
        chunk = video_ids[index : index + 50]
        if not chunk:
            continue
        request = youtube.videos().list(
            part="snippet,contentDetails,statistics,status,topicDetails",
            id=",".join(chunk),
            maxResults=50,
        )
        response = _api_call_with_backoff(request.execute)
        payload.extend(response.get("items", []))
    return payload


def _extract_thumbnails(thumbnails: Dict[str, Any]) -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    if not isinstance(thumbnails, dict):
        thumbnails = {}

    for thumb_key in THUMB_KEYS:
        thumb_data = thumbnails.get(thumb_key, {}) if isinstance(thumbnails.get(thumb_key, {}), dict) else {}
        output[f"thumb_{thumb_key}_url"] = thumb_data.get("url", "")
        output[f"thumb_{thumb_key}_width"] = thumb_data.get("width", "")
        output[f"thumb_{thumb_key}_height"] = thumb_data.get("height", "")
    return output


def _channel_fields(channel: Dict[str, Any], handle: str) -> Dict[str, Any]:
    snippet = channel.get("snippet", {}) or {}
    stats = channel.get("statistics", {}) or {}
    branding = _safe_get(channel, ["brandingSettings", "channel"], {}) or {}
    status = channel.get("status", {}) or {}
    topic = channel.get("topicDetails", {}) or {}

    uploads_playlist_id = _safe_get(channel, ["contentDetails", "relatedPlaylists", "uploads"], "")

    return {
        "snapshot_utc": _iso_now(),
        "category_name": DEFAULT_CATEGORY,
        "channel_handle_used": handle,
        "channel_id": channel.get("id", ""),
        "channel_title": snippet.get("title", ""),
        "channel_description": snippet.get("description", ""),
        "channel_publishedAt": snippet.get("publishedAt", ""),
        "uploads_playlist_id": uploads_playlist_id,
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


def _video_row(video: Dict[str, Any], channel_fields: Dict[str, Any]) -> Dict[str, Any]:
    snippet = video.get("snippet", {}) or {}
    content_details = video.get("contentDetails", {}) or {}
    statistics = video.get("statistics", {}) or {}
    status = video.get("status", {}) or {}
    topic_details = video.get("topicDetails", {}) or {}

    return {
        **channel_fields,
        "video_id": video.get("id", ""),
        "video_title": snippet.get("title", ""),
        "video_description": snippet.get("description", ""),
        "video_publishedAt": snippet.get("publishedAt", ""),
        "video_channelId": snippet.get("channelId", ""),
        "video_categoryId": snippet.get("categoryId", ""),
        "video_tags": _join_list(snippet.get("tags")),
        "video_defaultLanguage": snippet.get("defaultLanguage", ""),
        "video_defaultAudioLanguage": snippet.get("defaultAudioLanguage", ""),
        **_extract_thumbnails(snippet.get("thumbnails", {}) or {}),
        "views": statistics.get("viewCount", ""),
        "likes": statistics.get("likeCount", ""),
        "comments": statistics.get("commentCount", ""),
        "duration": content_details.get("duration", ""),
        "caption": content_details.get("caption", ""),
        "licensedContent": content_details.get("licensedContent", ""),
        "definition": content_details.get("definition", ""),
        "projection": content_details.get("projection", ""),
        "madeForKids": status.get("madeForKids", ""),
        "embeddable": status.get("embeddable", ""),
        "video_topicCategories": _join_list(topic_details.get("topicCategories")),
        "video_topicIds": _join_list(topic_details.get("topicIds")),
    }


def _load_dataset(dataset_path: Path = DATASET_PATH_DEFAULT) -> pd.DataFrame:
    if not dataset_path.exists():
        return pd.DataFrame()
    return pd.read_csv(dataset_path)


def _append_rows_to_dataset(new_rows: pd.DataFrame, existing_df: pd.DataFrame, dataset_path: Path = DATASET_PATH_DEFAULT) -> None:
    if new_rows.empty:
        return

    if existing_df.empty:
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        new_rows.to_csv(dataset_path, index=False)
        return

    existing_cols = existing_df.columns.tolist()
    aligned_new_rows = new_rows.copy()
    aligned_existing = existing_df.copy()

    for column in existing_cols:
        if column not in aligned_new_rows.columns:
            aligned_new_rows[column] = ""

    for column in aligned_new_rows.columns:
        if column not in existing_cols:
            aligned_existing[column] = ""
            existing_cols.append(column)

    aligned_new_rows = aligned_new_rows[existing_cols]
    aligned_new_rows.to_csv(dataset_path, mode="a", header=False, index=False)


def parse_iso_duration_seconds(duration: str) -> int:
    if not isinstance(duration, str):
        return 0
    hours = minutes = seconds = 0
    duration = duration.strip()
    if not duration.startswith("PT"):
        return 0
    current = duration[2:]
    hour_match = current.split("H")
    if len(hour_match) == 2:
        hours = int(hour_match[0] or 0)
        current = hour_match[1]
    minute_match = current.split("M")
    if len(minute_match) == 2:
        minutes = int(minute_match[0] or 0)
        current = minute_match[1]
    second_match = current.split("S")
    if len(second_match) >= 2 and second_match[0]:
        seconds = int(second_match[0] or 0)
    return hours * 3600 + minutes * 60 + seconds


def ensure_public_channel_frame(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in ("views", "likes", "comments", "channel_subscriberCount"):
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce")
        else:
            output[column] = 0

    if "video_publishedAt" in output.columns:
        output["video_publishedAt"] = pd.to_datetime(output["video_publishedAt"], errors="coerce", utc=True)
    else:
        output["video_publishedAt"] = pd.NaT

    output["likes"] = output["likes"].fillna(0)
    output["comments"] = output["comments"].fillna(0)
    output["views"] = output["views"].fillna(0)
    output["engagement_rate"] = (output["likes"] + output["comments"]) / output["views"].clip(lower=1)
    output["publish_month"] = output["video_publishedAt"].dt.strftime("%Y-%m")
    output["publish_day"] = output["video_publishedAt"].dt.day_name()
    output["publish_hour"] = output["video_publishedAt"].dt.hour
    if "duration" not in output.columns:
        output["duration"] = ""
    output["duration_seconds"] = output["duration"].fillna("").astype(str).map(parse_iso_duration_seconds)
    output["is_short"] = output["duration_seconds"] <= 60
    now = datetime.now(timezone.utc)
    output["age_days"] = output["video_publishedAt"].apply(
        lambda value: max((now - value.to_pydatetime()).total_seconds() / 86400.0, 0.5) if pd.notna(value) else 0.5
    )
    output["views_per_day"] = output["views"] / output["age_days"].clip(lower=0.5)
    return output


def _canonical_channel_url(channel: Dict[str, Any], channel_id: str, normalized_query: str) -> str:
    custom_url = _safe_get(channel, ["snippet", "customUrl"], "")
    if custom_url:
        if str(custom_url).startswith("@"):
            return f"https://www.youtube.com/{custom_url}"
        return f"https://www.youtube.com/@{custom_url.lstrip('@')}"

    if normalized_query.startswith("@"):
        return f"https://www.youtube.com/{normalized_query}"
    return f"https://www.youtube.com/channel/{channel_id}"


def load_public_channel_workspace(
    channel_query: str,
    force_refresh: bool,
    youtube_api_key: Optional[str] = None,
    dataset_path: Path = DATASET_PATH_DEFAULT,
    lookback_days: int = 365,
    max_videos: int = 600,
) -> PublicChannelWorkspace:
    existing_df = _load_dataset(dataset_path=dataset_path)
    existing_df = ensure_public_channel_frame(existing_df) if not existing_df.empty else existing_df
    normalized_input = normalize_channel_input(channel_query)
    lookup_value = normalized_input.lookup_value
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    def _load_with_key(api_key: str) -> PublicChannelWorkspace:
        youtube = _yt_client(api_key)
        channel_id = _resolve_channel_id(youtube, lookup_value)

        cached = pd.DataFrame()
        if not existing_df.empty and "channel_id" in existing_df.columns:
            cached = existing_df[existing_df["channel_id"].astype(str) == str(channel_id)].copy()

        if not cached.empty and not force_refresh:
            cached_recent = cached[cached["video_publishedAt"] >= pd.Timestamp(cutoff)]
            if not cached_recent.empty:
                title = cached_recent["channel_title"].dropna().iloc[0] if "channel_title" in cached_recent.columns else channel_id
                canonical_url = normalized_input.canonical_url or f"https://www.youtube.com/channel/{channel_id}"
                return PublicChannelWorkspace(
                    channel_df=cached_recent,
                    source="dataset_cache",
                    channel_id=channel_id,
                    channel_title=str(title),
                    canonical_url=canonical_url,
                    query_used=lookup_value,
                )

        channel = _fetch_channel_details(youtube, channel_id)
        uploads_playlist_id = _safe_get(channel, ["contentDetails", "relatedPlaylists", "uploads"], "")
        if not uploads_playlist_id:
            raise RuntimeError("Channel uploads playlist not found.")

        video_ids = _fetch_recent_video_ids(youtube, uploads_playlist_id, cutoff, max_videos=max_videos)
        if not video_ids:
            if not cached.empty:
                title = cached["channel_title"].dropna().iloc[0] if "channel_title" in cached.columns else channel_id
                canonical_url = _canonical_channel_url(channel, channel_id, lookup_value)
                return PublicChannelWorkspace(
                    channel_df=cached,
                    source="dataset_cache",
                    channel_id=channel_id,
                    channel_title=str(title),
                    canonical_url=canonical_url,
                    query_used=lookup_value,
                )
            raise RuntimeError(f"No public videos found in the last {lookback_days} days for this channel.")

        videos = _fetch_videos_details(youtube, video_ids)
        channel_data = _channel_fields(channel, lookup_value)
        rows = []
        for video in videos:
            video_id = str(video.get("id", "")).strip()
            if not video_id:
                continue
            rows.append(_video_row(video, channel_data))

        new_df = pd.DataFrame(rows)
        if new_df.empty:
            raise RuntimeError("YouTube returned no usable video rows for this channel.")

        if not existing_df.empty and "video_id" in existing_df.columns:
            existing_ids = set(existing_df["video_id"].dropna().astype(str).tolist())
            new_df = new_df[~new_df["video_id"].astype(str).isin(existing_ids)]

        _append_rows_to_dataset(new_df, _load_dataset(dataset_path=dataset_path), dataset_path=dataset_path)

        full_df = ensure_public_channel_frame(_load_dataset(dataset_path=dataset_path))
        channel_df = full_df[full_df["channel_id"].astype(str) == str(channel_id)].copy()
        recent_df = channel_df[channel_df["video_publishedAt"] >= pd.Timestamp(cutoff)]
        title = _safe_get(channel, ["snippet", "title"], channel_id)
        canonical_url = _canonical_channel_url(channel, channel_id, lookup_value)

        return PublicChannelWorkspace(
            channel_df=recent_df if not recent_df.empty else channel_df,
            source="youtube_api",
            channel_id=channel_id,
            channel_title=str(title),
            canonical_url=canonical_url,
            query_used=lookup_value,
        )

    if youtube_api_key and youtube_api_key.strip():
        return _load_with_key(youtube_api_key.strip())

    return run_with_provider_keys(
        "youtube",
        _load_with_key,
        retryable_error=_is_youtube_retryable_error,
    )


__all__ = [
    "DATASET_PATH_DEFAULT",
    "PublicChannelWorkspace",
    "ensure_public_channel_frame",
    "extract_channel_query",
    "load_public_channel_workspace",
    "parse_iso_duration_seconds",
]
