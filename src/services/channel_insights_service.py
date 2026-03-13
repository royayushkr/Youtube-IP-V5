from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.services.channel_idea_service import build_grounded_idea_bundle, maybe_generate_ai_overlay
from src.services.channel_snapshot_store import (
    DEFAULT_CHANNEL_INSIGHTS_DB,
    get_tracked_channel,
    list_channel_snapshot_history,
    list_tracked_channels,
    load_latest_channel_snapshot,
    store_channel_snapshot,
    upsert_tracked_channel,
)
from src.services.public_channel_service import PublicChannelWorkspace, ensure_public_channel_frame, load_public_channel_workspace
from src.services.topic_analysis_service import (
    add_channel_video_features,
    assign_topic_labels,
    build_duration_metrics,
    build_publish_day_metrics,
    build_publish_hour_metrics,
    build_title_pattern_metrics,
    build_topic_metrics,
)
from src.utils.channel_parser import normalize_channel_input


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_upload_gap_days(df: pd.DataFrame) -> float:
    ordered = df.sort_values("video_publishedAt").copy()
    if len(ordered) < 2:
        return 0.0
    gaps = ordered["video_publishedAt"].diff().dt.total_seconds().dropna() / 86400
    return float(gaps.mean()) if not gaps.empty else 0.0


def _score_videos(channel_df: pd.DataFrame) -> pd.DataFrame:
    if channel_df.empty:
        return channel_df.copy()
    df = channel_df.copy()
    views_rank = df["views_per_day"].rank(method="average", pct=True).fillna(0)
    engagement_rank = df["engagement_rate"].rank(method="average", pct=True).fillna(0)
    recency_raw = 1 / df["age_days"].clip(lower=0.5)
    recency_rank = recency_raw.rank(method="average", pct=True).fillna(0)
    df["performance_score"] = (views_rank * 60 + engagement_rank * 25 + recency_rank * 15).clip(0, 100)
    return df


def _outlier_and_underperformer_tables(channel_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if channel_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    ranked = channel_df.sort_values(["performance_score", "views_per_day"], ascending=[False, False]).copy()
    outliers = ranked[ranked["performance_score"] >= 75].head(12).copy()
    underperformers = ranked.sort_values(["performance_score", "views_per_day"], ascending=[True, True]).head(12).copy()

    outliers["why_it_worked"] = outliers.apply(
        lambda row: f"{row['primary_topic'].replace('_', ' ').title()} is outperforming the channel median with {row['views_per_day']:.0f} views/day.",
        axis=1,
    )
    underperformers["why_it_lagged"] = underperformers.apply(
        lambda row: f"{row['primary_topic'].replace('_', ' ').title()} is lagging the channel baseline and the packaging may need a new angle.",
        axis=1,
    )
    return outliers, underperformers


def _format_metrics(topic_metrics: pd.DataFrame, duration_metrics: pd.DataFrame, title_pattern_metrics: pd.DataFrame) -> Dict[str, Any]:
    strongest_theme = topic_metrics.iloc[0]["topic_label"] if not topic_metrics.empty else "No Theme Yet"
    weakest_theme = topic_metrics.sort_values("median_views_per_day", ascending=True).iloc[0]["topic_label"] if not topic_metrics.empty else "No Theme Yet"
    best_duration = duration_metrics.iloc[0]["duration_bucket"] if not duration_metrics.empty else "No Pattern Yet"
    best_title_pattern = title_pattern_metrics.iloc[0]["title_pattern"] if not title_pattern_metrics.empty else "No Pattern Yet"
    return {
        "strongest_theme": strongest_theme,
        "weakest_theme": weakest_theme,
        "best_duration_bucket": best_duration,
        "best_title_pattern": best_title_pattern,
    }


def _recommended_actions(
    channel_df: pd.DataFrame,
    topic_metrics: pd.DataFrame,
    duration_metrics: pd.DataFrame,
    outliers: pd.DataFrame,
) -> List[str]:
    actions: List[str] = []
    upload_gap = _compute_upload_gap_days(channel_df)

    if not topic_metrics.empty:
        strongest = topic_metrics.iloc[0]["topic_label"]
        actions.append(f"Double Down On {strongest} because it currently leads your channel on median views per day.")
        weakest = topic_metrics.sort_values("median_views_per_day", ascending=True).iloc[0]["topic_label"]
        if weakest != strongest:
            actions.append(f"Reduce volume on {weakest} unless you can repackage it with a stronger promise or format.")

    if not duration_metrics.empty:
        best_duration = duration_metrics.iloc[0]["duration_bucket"]
        actions.append(f"Test more uploads in the {best_duration} bucket because it is your current strongest duration pattern.")

    if upload_gap > 0:
        actions.append(f"Your average upload gap is {upload_gap:.1f} days. Tighten the cadence if you want the trend signals to compound faster.")

    if len(outliers) > 0:
        actions.append("Study the top outlier titles and reuse the same promise structure before trying a completely new topic.")

    unique_actions = []
    for action in actions:
        if action not in unique_actions:
            unique_actions.append(action)
    return unique_actions[:4]


def _history_delta(history_df: pd.DataFrame) -> Dict[str, float]:
    if history_df.empty or len(history_df) < 2:
        return {}
    latest = history_df.iloc[0]
    previous = history_df.iloc[1]
    return {
        "median_views_per_day_delta": float(latest.get("median_views_per_day", 0) - previous.get("median_views_per_day", 0)),
        "outlier_count_delta": float(latest.get("recent_outlier_count", 0) - previous.get("recent_outlier_count", 0)),
        "upload_gap_delta": float(latest.get("upload_gap_days", 0) - previous.get("upload_gap_days", 0)),
    }


def _build_summary(
    workspace: PublicChannelWorkspace,
    channel_df: pd.DataFrame,
    topic_metrics: pd.DataFrame,
    duration_metrics: pd.DataFrame,
    title_pattern_metrics: pd.DataFrame,
    outliers: pd.DataFrame,
) -> Dict[str, Any]:
    metrics = _format_metrics(topic_metrics, duration_metrics, title_pattern_metrics)
    return {
        "channel_id": workspace.channel_id,
        "channel_title": workspace.channel_title,
        "canonical_url": workspace.canonical_url,
        "snapshot_at": _iso_now(),
        "video_count": int(len(channel_df)),
        "median_views_per_day": float(channel_df["views_per_day"].median()) if not channel_df.empty else 0.0,
        "median_engagement": float(channel_df["engagement_rate"].median()) if not channel_df.empty else 0.0,
        "avg_upload_gap_days": _compute_upload_gap_days(channel_df),
        "shorts_ratio": float(channel_df["is_short"].mean()) if not channel_df.empty else 0.0,
        "recent_outlier_count": int(len(outliers)),
        **metrics,
    }


def _insight_payload(
    *,
    channel_df: pd.DataFrame,
    topic_metrics: pd.DataFrame,
    duration_metrics: pd.DataFrame,
    title_pattern_metrics: pd.DataFrame,
    publish_day_metrics: pd.DataFrame,
    publish_hour_metrics: pd.DataFrame,
    outliers: pd.DataFrame,
    underperformers: pd.DataFrame,
    summary: Dict[str, Any],
    recommendations: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "summary": summary,
        "topic_metrics": topic_metrics.to_dict(orient="records"),
        "duration_metrics": duration_metrics.to_dict(orient="records"),
        "title_pattern_metrics": title_pattern_metrics.to_dict(orient="records"),
        "publish_day_metrics": publish_day_metrics.to_dict(orient="records"),
        "publish_hour_metrics": publish_hour_metrics.to_dict(orient="records"),
        "outliers": outliers.to_dict(orient="records"),
        "underperformers": underperformers.to_dict(orient="records"),
        "recommendations": recommendations,
    }


def refresh_channel_insights(
    channel_input: str,
    *,
    force_refresh: bool = False,
    db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB,
) -> Dict[str, Any]:
    parsed_input = normalize_channel_input(channel_input)
    workspace = load_public_channel_workspace(parsed_input.lookup_value, force_refresh=force_refresh)
    channel_df = ensure_public_channel_frame(workspace.channel_df)
    channel_df = add_channel_video_features(channel_df)
    channel_df = assign_topic_labels(channel_df)
    channel_df = _score_videos(channel_df)

    topic_metrics = build_topic_metrics(channel_df)
    duration_metrics = build_duration_metrics(channel_df)
    title_pattern_metrics = build_title_pattern_metrics(channel_df)
    publish_day_metrics = build_publish_day_metrics(channel_df)
    publish_hour_metrics = build_publish_hour_metrics(channel_df)
    outliers, underperformers = _outlier_and_underperformer_tables(channel_df)

    summary = _build_summary(
        workspace=workspace,
        channel_df=channel_df,
        topic_metrics=topic_metrics,
        duration_metrics=duration_metrics,
        title_pattern_metrics=title_pattern_metrics,
        outliers=outliers,
    )

    idea_bundle = build_grounded_idea_bundle(
        workspace.channel_title,
        topic_metrics.to_dict(orient="records"),
        outliers.to_dict(orient="records"),
        underperformers.to_dict(orient="records"),
    )
    recommendations = {
        "summary": idea_bundle.summary,
        "double_down": [item.__dict__ for item in idea_bundle.double_down],
        "avoid": [item.__dict__ for item in idea_bundle.avoid],
        "test_next": [item.__dict__ for item in idea_bundle.test_next],
        "video_ideas": [item.__dict__ for item in idea_bundle.video_ideas],
    }
    recommendations["actions"] = _recommended_actions(channel_df, topic_metrics, duration_metrics, outliers)
    try:
        recommendations["ai_overlay"] = maybe_generate_ai_overlay(
            workspace.channel_title,
            summary,
            topic_metrics.to_dict(orient="records"),
        )
    except Exception:
        recommendations["ai_overlay"] = ""

    snapshot_at = summary["snapshot_at"]
    channel_handle = parsed_input.handle or (parsed_input.lookup_value if parsed_input.lookup_value.startswith("@") else "")
    upsert_tracked_channel(
        channel_id=workspace.channel_id,
        input_value=parsed_input.lookup_value,
        canonical_url=workspace.canonical_url,
        channel_title=workspace.channel_title,
        channel_handle=channel_handle,
        source=workspace.source,
        added_at=snapshot_at,
        last_refresh_at=snapshot_at,
        db_path=db_path,
    )
    store_channel_snapshot(
        channel_id=workspace.channel_id,
        snapshot_at=snapshot_at,
        source=workspace.source,
        summary=summary,
        videos_df=channel_df,
        topic_metrics_df=topic_metrics,
        insights_payload=_insight_payload(
            channel_df=channel_df,
            topic_metrics=topic_metrics,
            duration_metrics=duration_metrics,
            title_pattern_metrics=title_pattern_metrics,
            publish_day_metrics=publish_day_metrics,
            publish_hour_metrics=publish_hour_metrics,
            outliers=outliers,
            underperformers=underperformers,
            summary=summary,
            recommendations=recommendations,
        ),
        db_path=db_path,
    )
    return load_channel_insights(workspace.channel_id, db_path=db_path) or {}


def list_connected_channels(db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB) -> List[Dict[str, Any]]:
    return list_tracked_channels(db_path=db_path)


def load_channel_insights(channel_id: str, *, db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB) -> Optional[Dict[str, Any]]:
    tracked = get_tracked_channel(channel_id, db_path=db_path)
    snapshot = load_latest_channel_snapshot(channel_id, db_path=db_path)
    if not tracked or not snapshot:
        return None

    history_df = list_channel_snapshot_history(channel_id, db_path=db_path)
    insights = snapshot.get("insights", {})
    videos_df = pd.DataFrame(snapshot.get("videos", []))
    topic_metrics_df = pd.DataFrame(snapshot.get("topic_metrics", []))
    summary = snapshot.get("summary", {})
    history_delta = _history_delta(history_df)

    if videos_df.empty and "outliers" in insights:
        videos_df = pd.DataFrame(insights.get("outliers", []))

    return {
        "channel": tracked,
        "snapshot_at": snapshot["snapshot_at"],
        "source": snapshot["source"],
        "summary": summary,
        "history_delta": history_delta,
        "videos_df": videos_df,
        "topic_metrics_df": topic_metrics_df,
        "duration_metrics_df": pd.DataFrame(insights.get("duration_metrics", [])),
        "title_pattern_metrics_df": pd.DataFrame(insights.get("title_pattern_metrics", [])),
        "publish_day_metrics_df": pd.DataFrame(insights.get("publish_day_metrics", [])),
        "publish_hour_metrics_df": pd.DataFrame(insights.get("publish_hour_metrics", [])),
        "outliers_df": pd.DataFrame(insights.get("outliers", [])),
        "underperformers_df": pd.DataFrame(insights.get("underperformers", [])),
        "recommendations": insights.get("recommendations", {}),
        "history_df": history_df,
    }
