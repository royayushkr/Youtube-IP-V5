from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List

import pandas as pd


STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "you",
    "your",
    "this",
    "that",
    "from",
    "into",
    "about",
    "what",
    "when",
    "why",
    "how",
    "best",
    "video",
    "videos",
    "channel",
    "shorts",
}


def normalize_topic_token(token: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "", str(token or "").lower())
    if len(text) <= 2 or text in STOPWORDS:
        return ""
    if text.endswith("ies") and len(text) > 4:
        return text[:-3] + "y"
    if text.endswith("s") and len(text) > 4 and not text.endswith("ss"):
        return text[:-1]
    return text


def tokenize_topic_text(text: str) -> List[str]:
    return [token for token in (normalize_topic_token(match) for match in re.findall(r"[A-Za-z0-9]+", str(text or ""))) if token]


def classify_title_pattern(title: str) -> str:
    lower = str(title or "").lower().strip()
    if not lower:
        return "Other"
    if lower.startswith("how to ") or lower.startswith("how "):
        return "How-To"
    if re.match(r"^\d+", lower):
        return "Numbered"
    if " vs " in lower or "versus" in lower:
        return "Versus"
    if "?" in lower:
        return "Question"
    if any(token in lower for token in ("react", "reaction", "responds to")):
        return "Reaction"
    if any(token in lower for token in ("update", "news", "latest", "breaking")):
        return "Update"
    if any(token in lower for token in ("review", "test", "tried")):
        return "Review/Test"
    if any(token in lower for token in ("explained", "explain", "guide", "breakdown")):
        return "Explainer"
    return "Other"


def duration_bucket(seconds: float) -> str:
    if seconds <= 60:
        return "Shorts"
    if seconds <= 240:
        return "1-4 Minutes"
    if seconds <= 480:
        return "4-8 Minutes"
    if seconds <= 900:
        return "8-15 Minutes"
    if seconds <= 1800:
        return "15-30 Minutes"
    return "30+ Minutes"


def add_channel_video_features(channel_df: pd.DataFrame) -> pd.DataFrame:
    if channel_df.empty:
        return channel_df.copy()

    df = channel_df.copy()
    now = datetime.now(timezone.utc)
    df["video_publishedAt"] = pd.to_datetime(df["video_publishedAt"], errors="coerce", utc=True)
    df["views"] = pd.to_numeric(df["views"], errors="coerce").fillna(0)
    if "likes" not in df.columns:
        df["likes"] = 0
    if "comments" not in df.columns:
        df["comments"] = 0
    if "duration_seconds" not in df.columns:
        df["duration_seconds"] = 0
    df["likes"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0)
    df["comments"] = pd.to_numeric(df["comments"], errors="coerce").fillna(0)
    df["duration_seconds"] = pd.to_numeric(df["duration_seconds"], errors="coerce").fillna(0)
    df["engagement_rate"] = ((df["likes"] + df["comments"]) / df["views"].clip(lower=1)).fillna(0)
    df["age_days"] = df["video_publishedAt"].apply(
        lambda value: max((now - value.to_pydatetime()).total_seconds() / 86400.0, 0.5) if pd.notna(value) else 0.5
    )
    df["views_per_day"] = (df["views"] / df["age_days"].clip(lower=0.5)).fillna(0)
    df["publish_day"] = df["video_publishedAt"].dt.day_name()
    df["publish_hour"] = df["video_publishedAt"].dt.hour
    df["is_short"] = df["duration_seconds"] <= 60
    df["duration_bucket"] = df["duration_seconds"].map(duration_bucket)
    df["title_pattern"] = df["video_title"].fillna("").astype(str).map(classify_title_pattern)
    return df


def assign_topic_labels(channel_df: pd.DataFrame, *, max_topic_pool: int = 30) -> pd.DataFrame:
    if channel_df.empty:
        return channel_df.copy()

    df = channel_df.copy()
    token_counter: Counter[str] = Counter()
    video_tokens: Dict[str, List[str]] = {}

    for _, row in df.iterrows():
        combined_text = " ".join(
            [
                str(row.get("video_title", "")),
                str(row.get("video_tags", "")).replace("|", " "),
                str(row.get("video_description", ""))[:180],
            ]
        )
        tokens = list(dict.fromkeys(tokenize_topic_text(combined_text)))
        video_tokens[str(row.get("video_id", ""))] = tokens
        weighted_score = math.log1p(float(row.get("views_per_day", 0) or 0) + 1)
        for token in tokens:
            token_counter[token] += max(1, int(round(weighted_score)))

    top_tokens = [token for token, _ in token_counter.most_common(max_topic_pool)]
    top_token_set = set(top_tokens)

    topic_labels: List[List[str]] = []
    primary_topics: List[str] = []
    for _, row in df.iterrows():
        tokens = [token for token in video_tokens.get(str(row.get("video_id", "")), []) if token in top_token_set]
        labels = tokens[:2] if tokens else []
        if not labels:
            labels = ["misc"]
        topic_labels.append(labels)
        primary_topics.append(labels[0])

    df["topic_labels"] = topic_labels
    df["primary_topic"] = primary_topics
    return df


def build_topic_metrics(channel_df: pd.DataFrame) -> pd.DataFrame:
    if channel_df.empty or "primary_topic" not in channel_df.columns:
        return pd.DataFrame()

    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=90)
    previous_cutoff = now - timedelta(days=180)

    rows: List[Dict[str, Any]] = []
    for topic, topic_df in channel_df.groupby("primary_topic"):
        recent_df = topic_df[topic_df["video_publishedAt"] >= recent_cutoff]
        previous_df = topic_df[
            (topic_df["video_publishedAt"] < recent_cutoff)
            & (topic_df["video_publishedAt"] >= previous_cutoff)
        ]

        recent_median = float(recent_df["views_per_day"].median()) if not recent_df.empty else 0.0
        previous_median = float(previous_df["views_per_day"].median()) if not previous_df.empty else 0.0
        if previous_median > 0:
            trend_score = (recent_median - previous_median) / previous_median
        else:
            trend_score = recent_median / max(float(topic_df["views_per_day"].median()), 1.0)

        rows.append(
            {
                "topic_label": str(topic).replace("_", " ").title(),
                "topic_key": topic,
                "video_count": int(len(topic_df)),
                "median_views_per_day": float(topic_df["views_per_day"].median()),
                "median_views": float(topic_df["views"].median()),
                "avg_engagement": float(topic_df["engagement_rate"].mean()),
                "outlier_count": int((topic_df["performance_score"] >= 75).sum()) if "performance_score" in topic_df.columns else 0,
                "trend_score": float(trend_score),
                "recent_video_count": int(len(recent_df)),
            }
        )

    topic_metrics = pd.DataFrame(rows)
    if topic_metrics.empty:
        return topic_metrics
    return topic_metrics.sort_values(["trend_score", "median_views_per_day"], ascending=[False, False]).reset_index(drop=True)


def build_title_pattern_metrics(channel_df: pd.DataFrame) -> pd.DataFrame:
    if channel_df.empty:
        return pd.DataFrame()
    return (
        channel_df.groupby("title_pattern", dropna=False)
        .agg(
            videos=("video_id", "count"),
            median_views_per_day=("views_per_day", "median"),
            avg_engagement=("engagement_rate", "mean"),
        )
        .reset_index()
        .sort_values(["median_views_per_day", "videos"], ascending=[False, False])
    )


def build_duration_metrics(channel_df: pd.DataFrame) -> pd.DataFrame:
    if channel_df.empty:
        return pd.DataFrame()
    return (
        channel_df.groupby("duration_bucket", dropna=False)
        .agg(
            videos=("video_id", "count"),
            median_views_per_day=("views_per_day", "median"),
            avg_engagement=("engagement_rate", "mean"),
        )
        .reset_index()
        .sort_values(["median_views_per_day", "videos"], ascending=[False, False])
    )


def build_publish_day_metrics(channel_df: pd.DataFrame) -> pd.DataFrame:
    if channel_df.empty:
        return pd.DataFrame()
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    metrics = (
        channel_df.groupby("publish_day", dropna=False)
        .agg(
            videos=("video_id", "count"),
            median_views_per_day=("views_per_day", "median"),
        )
        .reindex(weekday_order)
        .reset_index()
        .rename(columns={"index": "publish_day"})
    )
    return metrics.dropna(subset=["publish_day"], how="all")


def build_publish_hour_metrics(channel_df: pd.DataFrame) -> pd.DataFrame:
    if channel_df.empty:
        return pd.DataFrame()
    return (
        channel_df.groupby("publish_hour", dropna=False)
        .agg(
            videos=("video_id", "count"),
            median_views_per_day=("views_per_day", "median"),
        )
        .reset_index()
        .sort_values("publish_hour")
    )
