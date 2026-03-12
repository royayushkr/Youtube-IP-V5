import os

import pandas as pd
import streamlit as st

from dashboard.components.visualizations import (
    kpi_row,
    plotly_bar_chart,
    plotly_donut_chart,
    plotly_heatmap,
    plotly_line_chart,
    plotly_scatter,
    section_header,
    styled_dataframe,
)


BASE_DATA_DIR = os.path.join("data", "youtube api data")
CATEGORY_FILES = {
    "Research / Science": "research_science_channels_videos.csv",
    "Tech": "tech_channels_videos.csv",
    "Gaming": "gaming_channels_videos.csv",
    "Entertainment": "entertainment_channels_videos.csv",
}
ALL_LABEL = "All Categories"


def _dataset_path_for_label(label: str) -> str:
    filename = CATEGORY_FILES.get(label) or CATEGORY_FILES.get("Research / Science")
    return os.path.join(BASE_DATA_DIR, filename)


def _available_categories() -> list[str]:
    labels: list[str] = []
    for label, filename in CATEGORY_FILES.items():
        path = os.path.join(BASE_DATA_DIR, filename)
        if os.path.exists(path):
            labels.append(label)
    if labels:
        return [ALL_LABEL] + labels
    return list(CATEGORY_FILES.keys())


def _load_data_for_label(label: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    if label == ALL_LABEL:
        for filename in CATEGORY_FILES.values():
            path = os.path.join(BASE_DATA_DIR, filename)
            if os.path.exists(path):
                frames.append(pd.read_csv(path))
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
    else:
        dataset_path = _dataset_path_for_label(label)
        if not os.path.exists(dataset_path):
            return pd.DataFrame()
        df = pd.read_csv(dataset_path)

    for col in ["views", "likes", "comments"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["video_publishedAt"] = pd.to_datetime(
        df["video_publishedAt"], errors="coerce", utc=True
    )
    df["engagement_rate"] = (
        (df["likes"].fillna(0) + df["comments"].fillna(0))
        / df["views"].clip(lower=1)
    )
    df["publish_month"] = df["video_publishedAt"].dt.to_period("M").astype(str)
    df["publish_day"] = df["video_publishedAt"].dt.day_name()
    return df


def render() -> None:
    section_header("Channel Analysis", icon="📊")

    categories = _available_categories()
    selected_category = st.selectbox("Dataset category", categories, index=0)

    st.caption(f"Analytics for `{selected_category}` YouTube channels and videos.")

    df = _load_data_for_label(selected_category)
    if df.empty:
        st.warning(
            "No data available for the selected category. Check that the CSV files exist."
        )
        return

    channels = sorted(df["channel_title"].dropna().unique().tolist())
    selected_channels = st.multiselect(
        "Filter channels", channels, default=channels[:8]
    )

    min_date = df["video_publishedAt"].min().date()
    max_date = df["video_publishedAt"].max().date()
    date_range = st.date_input(
        "Published date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    filtered = df.copy()
    if selected_channels:
        filtered = filtered[filtered["channel_title"].isin(selected_channels)]

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        filtered = filtered[
            (filtered["video_publishedAt"].dt.date >= start_date)
            & (filtered["video_publishedAt"].dt.date <= end_date)
        ]

    if filtered.empty:
        st.warning("No data after filters. Broaden your channel/date filters.")
        return

    # KPI row
    metrics = [
        {
            "label": "Videos",
            "value": f"{len(filtered):,}",
            "icon": "🎬",
            "color": "#A855F7",
        },
        {
            "label": "Channels",
            "value": f"{filtered['channel_id'].nunique():,}",
            "icon": "📺",
            "color": "#C4B5FD",
        },
        {
            "label": "Total Views",
            "value": f"{int(filtered['views'].fillna(0).sum()):,}",
            "icon": "👁️",
        },
        {
            "label": "Avg Views / Video",
            "value": f"{int(filtered['views'].fillna(0).mean()):,}",
            "icon": "📈",
        },
        {
            "label": "Median Engagement",
            "value": f"{filtered['engagement_rate'].median() * 100:.2f} %",
            "icon": "💡",
        },
    ]
    kpi_row(metrics)

    left, right = st.columns(2)

    with left:
        section_header("Top Channels by Views", icon="🏆")
        channel_summary = (
            filtered.groupby("channel_title", dropna=False)
            .agg(
                videos=("video_id", "count"),
                total_views=("views", "sum"),
                avg_views=("views", "mean"),
                engagement=("engagement_rate", "median"),
            )
            .sort_values("total_views", ascending=False)
            .head(15)
            .reset_index()
        )
        fig = plotly_bar_chart(
            channel_summary, x="channel_title", y="total_views", title="Top 15 Channels"
        )
        st.plotly_chart(fig, use_container_width=True)
        styled_dataframe(channel_summary, title="Channel Summary")

    with right:
        section_header("Monthly Upload Trend", icon="📆")
        trend = (
            filtered.groupby("publish_month", dropna=False)
            .agg(videos=("video_id", "count"), views=("views", "sum"))
            .reset_index()
            .sort_values("publish_month")
        )
        fig = plotly_line_chart(
            trend,
            x="publish_month",
            y_cols=["videos", "views"],
            title="Videos & Views Over Time",
            secondary_y=["views"],
        )
        st.plotly_chart(fig, use_container_width=True)

    section_header("Best Performing Videos", icon="⭐")
    top_videos = filtered[
        [
            "channel_title",
            "video_title",
            "views",
            "likes",
            "comments",
            "engagement_rate",
            "video_publishedAt",
        ]
    ].sort_values("views", ascending=False)
    styled_dataframe(
        top_videos.head(50),
        title="Top Videos by Views",
        precision=2,
    )

    section_header("Publishing Day Performance", icon="🗓️")
    day_perf = (
        filtered.groupby("publish_day", dropna=False)
        .agg(
            videos=("video_id", "count"),
            avg_views=("views", "mean"),
            median_engagement=("engagement_rate", "median"),
        )
        .reindex(
            [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
        )
        .dropna(how="all")
        .reset_index()
    )

    col_day1, col_day2 = st.columns(2)
    with col_day1:
        fig_views = plotly_bar_chart(
            day_perf,
            x="publish_day",
            y="avg_views",
            title="Average Views by Day",
        )
        st.plotly_chart(fig_views, use_container_width=True)
    with col_day2:
        fig_eng = plotly_bar_chart(
            day_perf,
            x="publish_day",
            y="median_engagement",
            title="Median Engagement Rate by Day",
        )
        st.plotly_chart(fig_eng, use_container_width=True)

    section_header("Views vs Engagement", icon="📉")
    scatter_df = filtered.copy()
    fig_scatter = plotly_scatter(
        scatter_df,
        x="views",
        y="engagement_rate",
        size=None,
        color="channel_title",
        title="Views vs Engagement Rate",
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    section_header("Engagement Distribution", icon="🥧")
    bins = []
    for val in filtered["engagement_rate"]:
        if pd.isna(val):
            continue
        pct = val * 100
        if pct < 2:
            bins.append("Low (<2%)")
        elif pct < 8:
            bins.append("Medium (2–8%)")
        else:
            bins.append("High (8%+)")
    if bins:
        counts = pd.Series(bins, name="bucket").value_counts().reset_index()
        counts.columns = ["bucket", "count"]
        dist_df = counts
        fig_donut = plotly_donut_chart(
            dist_df,
            names="bucket",
            values="count",
            title="Engagement Rate Buckets",
        )
        st.plotly_chart(fig_donut, use_container_width=True)
