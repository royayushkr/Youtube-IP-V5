from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


DEFAULT_CHANNEL_INSIGHTS_DB = Path("outputs") / "channel_insights" / "channel_insights.db"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _connect(db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_channel_snapshot_store(db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracked_channels (
                channel_id TEXT PRIMARY KEY,
                input_value TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                channel_title TEXT NOT NULL,
                channel_handle TEXT DEFAULT '',
                source TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                added_at TEXT NOT NULL,
                last_refresh_at TEXT
            );

            CREATE TABLE IF NOT EXISTS channel_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                snapshot_at TEXT NOT NULL,
                source TEXT DEFAULT '',
                video_count INTEGER DEFAULT 0,
                summary_json TEXT NOT NULL,
                UNIQUE(channel_id, snapshot_at)
            );

            CREATE TABLE IF NOT EXISTS video_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                snapshot_at TEXT NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT,
                views REAL DEFAULT 0,
                likes REAL DEFAULT 0,
                comments REAL DEFAULT 0,
                duration_seconds INTEGER DEFAULT 0,
                is_short INTEGER DEFAULT 0,
                duration_bucket TEXT DEFAULT '',
                views_per_day REAL DEFAULT 0,
                engagement_rate REAL DEFAULT 0,
                topic_labels TEXT DEFAULT '',
                title_pattern TEXT DEFAULT '',
                row_json TEXT NOT NULL,
                UNIQUE(channel_id, snapshot_at, video_id)
            );

            CREATE TABLE IF NOT EXISTS topic_snapshot_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                snapshot_at TEXT NOT NULL,
                topic_label TEXT NOT NULL,
                video_count INTEGER DEFAULT 0,
                median_views_per_day REAL DEFAULT 0,
                median_views REAL DEFAULT 0,
                outlier_count INTEGER DEFAULT 0,
                trend_score REAL DEFAULT 0,
                avg_engagement REAL DEFAULT 0,
                UNIQUE(channel_id, snapshot_at, topic_label)
            );

            CREATE TABLE IF NOT EXISTS insight_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                snapshot_at TEXT NOT NULL,
                insight_type TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )


def upsert_tracked_channel(
    *,
    channel_id: str,
    input_value: str,
    canonical_url: str,
    channel_title: str,
    channel_handle: str,
    source: str,
    added_at: str,
    last_refresh_at: str,
    notes: str = "",
    db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB,
) -> None:
    initialize_channel_snapshot_store(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tracked_channels (
                channel_id, input_value, canonical_url, channel_title, channel_handle, source, notes, added_at, last_refresh_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                input_value=excluded.input_value,
                canonical_url=excluded.canonical_url,
                channel_title=excluded.channel_title,
                channel_handle=excluded.channel_handle,
                source=excluded.source,
                notes=excluded.notes,
                last_refresh_at=excluded.last_refresh_at
            """,
            (
                channel_id,
                input_value,
                canonical_url,
                channel_title,
                channel_handle,
                source,
                notes,
                added_at,
                last_refresh_at,
            ),
        )


def list_tracked_channels(db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB) -> List[Dict[str, Any]]:
    initialize_channel_snapshot_store(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT channel_id, input_value, canonical_url, channel_title, channel_handle, source, added_at, last_refresh_at
            FROM tracked_channels
            ORDER BY COALESCE(last_refresh_at, added_at) DESC, channel_title ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_tracked_channel(channel_id: str, db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB) -> Optional[Dict[str, Any]]:
    initialize_channel_snapshot_store(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT channel_id, input_value, canonical_url, channel_title, channel_handle, source, added_at, last_refresh_at
            FROM tracked_channels
            WHERE channel_id = ?
            """,
            (channel_id,),
        ).fetchone()
    return dict(row) if row else None


def store_channel_snapshot(
    *,
    channel_id: str,
    snapshot_at: str,
    source: str,
    summary: Dict[str, Any],
    videos_df: pd.DataFrame,
    topic_metrics_df: pd.DataFrame,
    insights_payload: Dict[str, Any],
    db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB,
) -> None:
    initialize_channel_snapshot_store(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO channel_snapshots (channel_id, snapshot_at, source, video_count, summary_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                channel_id,
                snapshot_at,
                source,
                int(len(videos_df)),
                _json_dumps(summary),
            ),
        )

        conn.execute(
            "DELETE FROM video_snapshots WHERE channel_id = ? AND snapshot_at = ?",
            (channel_id, snapshot_at),
        )
        conn.execute(
            "DELETE FROM topic_snapshot_metrics WHERE channel_id = ? AND snapshot_at = ?",
            (channel_id, snapshot_at),
        )
        conn.execute(
            "DELETE FROM insight_snapshots WHERE channel_id = ? AND snapshot_at = ?",
            (channel_id, snapshot_at),
        )

        video_rows: List[tuple[Any, ...]] = []
        for row in videos_df.to_dict(orient="records"):
            video_rows.append(
                (
                    channel_id,
                    snapshot_at,
                    str(row.get("video_id", "")),
                    str(row.get("video_title", "")),
                    str(row.get("video_publishedAt", "")),
                    float(row.get("views", 0) or 0),
                    float(row.get("likes", 0) or 0),
                    float(row.get("comments", 0) or 0),
                    int(row.get("duration_seconds", 0) or 0),
                    1 if bool(row.get("is_short")) else 0,
                    str(row.get("duration_bucket", "")),
                    float(row.get("views_per_day", 0) or 0),
                    float(row.get("engagement_rate", 0) or 0),
                    "|".join(row.get("topic_labels", [])) if isinstance(row.get("topic_labels"), list) else str(row.get("topic_labels", "")),
                    str(row.get("title_pattern", "")),
                    _json_dumps(row),
                )
            )
        conn.executemany(
            """
            INSERT OR REPLACE INTO video_snapshots (
                channel_id, snapshot_at, video_id, title, published_at, views, likes, comments,
                duration_seconds, is_short, duration_bucket, views_per_day, engagement_rate,
                topic_labels, title_pattern, row_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            video_rows,
        )

        topic_rows = [
            (
                channel_id,
                snapshot_at,
                str(row.get("topic_label", "")),
                int(row.get("video_count", 0) or 0),
                float(row.get("median_views_per_day", 0) or 0),
                float(row.get("median_views", 0) or 0),
                int(row.get("outlier_count", 0) or 0),
                float(row.get("trend_score", 0) or 0),
                float(row.get("avg_engagement", 0) or 0),
            )
            for row in topic_metrics_df.to_dict(orient="records")
        ]
        conn.executemany(
            """
            INSERT OR REPLACE INTO topic_snapshot_metrics (
                channel_id, snapshot_at, topic_label, video_count, median_views_per_day, median_views,
                outlier_count, trend_score, avg_engagement
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            topic_rows,
        )

        conn.execute(
            """
            INSERT INTO insight_snapshots (channel_id, snapshot_at, insight_type, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                channel_id,
                snapshot_at,
                "channel_insights_v1",
                _json_dumps(insights_payload),
            ),
        )


def list_channel_snapshot_history(channel_id: str, db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB) -> pd.DataFrame:
    initialize_channel_snapshot_store(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT snapshot_at, source, video_count, summary_json
            FROM channel_snapshots
            WHERE channel_id = ?
            ORDER BY snapshot_at DESC
            """,
            (channel_id,),
        ).fetchall()

    if not rows:
        return pd.DataFrame()

    records = []
    for row in rows:
        summary = _json_loads(row["summary_json"], {})
        records.append(
            {
                "snapshot_at": row["snapshot_at"],
                "source": row["source"],
                "video_count": row["video_count"],
                "median_views_per_day": summary.get("median_views_per_day", 0),
                "recent_outlier_count": summary.get("recent_outlier_count", 0),
                "strongest_theme": summary.get("strongest_theme", ""),
                "weakest_theme": summary.get("weakest_theme", ""),
                "upload_gap_days": summary.get("avg_upload_gap_days", 0),
            }
        )
    return pd.DataFrame(records)


def load_latest_channel_snapshot(channel_id: str, db_path: Path = DEFAULT_CHANNEL_INSIGHTS_DB) -> Optional[Dict[str, Any]]:
    initialize_channel_snapshot_store(db_path)
    with _connect(db_path) as conn:
        snapshot_row = conn.execute(
            """
            SELECT snapshot_at, source, video_count, summary_json
            FROM channel_snapshots
            WHERE channel_id = ?
            ORDER BY snapshot_at DESC
            LIMIT 1
            """,
            (channel_id,),
        ).fetchone()
        if not snapshot_row:
            return None

        topic_rows = conn.execute(
            """
            SELECT topic_label, video_count, median_views_per_day, median_views, outlier_count, trend_score, avg_engagement
            FROM topic_snapshot_metrics
            WHERE channel_id = ? AND snapshot_at = ?
            ORDER BY trend_score DESC, median_views_per_day DESC
            """,
            (channel_id, snapshot_row["snapshot_at"]),
        ).fetchall()
        video_rows = conn.execute(
            """
            SELECT row_json
            FROM video_snapshots
            WHERE channel_id = ? AND snapshot_at = ?
            ORDER BY views_per_day DESC, views DESC
            """,
            (channel_id, snapshot_row["snapshot_at"]),
        ).fetchall()
        insight_row = conn.execute(
            """
            SELECT payload_json
            FROM insight_snapshots
            WHERE channel_id = ? AND snapshot_at = ? AND insight_type = 'channel_insights_v1'
            ORDER BY id DESC
            LIMIT 1
            """,
            (channel_id, snapshot_row["snapshot_at"]),
        ).fetchone()

    videos = [_json_loads(row["row_json"], {}) for row in video_rows]
    topic_metrics = [dict(row) for row in topic_rows]
    summary = _json_loads(snapshot_row["summary_json"], {})
    insight_payload = _json_loads(insight_row["payload_json"] if insight_row else "", {})
    return {
        "snapshot_at": snapshot_row["snapshot_at"],
        "source": snapshot_row["source"],
        "video_count": snapshot_row["video_count"],
        "summary": summary,
        "videos": videos,
        "topic_metrics": topic_metrics,
        "insights": insight_payload,
    }
