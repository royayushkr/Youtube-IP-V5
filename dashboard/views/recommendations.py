import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from dashboard.components.visualizations import (
    kpi_row,
    section_header,
    styled_dataframe,
    styled_keyword_chips,
)
from src.llm_integration.thumbnail_generator import ThumbnailGenerator, get_api_key


if load_dotenv:
    load_dotenv()

BASE_DATA_DIR = os.path.join("data", "youtube api data")
CATEGORY_FILES = {
    "Research / Science": "research_science_channels_videos.csv",
    "Tech": "tech_channels_videos.csv",
    "Gaming": "gaming_channels_videos.csv",
    "Entertainment": "entertainment_channels_videos.csv",
}
ALL_LABEL = "All Categories"
STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "for", "with", "on", "and", "or", "at", "is", "are", "was", "were",
    "this", "that", "how", "why", "what", "when", "from", "your", "you", "my", "we", "our", "it",
}


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


def _load_recommendation_data_for_label(label: str) -> pd.DataFrame:
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
        (df["likes"].fillna(0) + df["comments"].fillna(0)) / df["views"].clip(lower=1)
    )
    df["title_length"] = df["video_title"].fillna("").astype(str).str.len()
    df["publish_day"] = df["video_publishedAt"].dt.day_name()
    return df


def _extract_keywords(titles: pd.Series, top_n: int = 8) -> list[str]:
    words: list[str] = []
    for title in titles.dropna().astype(str):
        tokens = re.findall(r"[A-Za-z]{3,}", title.lower())
        words.extend([tok for tok in tokens if tok not in STOPWORDS])
    return [w for w, _ in Counter(words).most_common(top_n)]


def _render_data_recommendations(df: pd.DataFrame, category_label: str) -> None:
    section_header("Data-Driven Content Recommendations", icon="🎯")

    if df.empty:
        st.info(
            f"No data available yet for `{category_label}`. Check that the CSV files exist."
        )
        return

    channels = sorted(df["channel_title"].dropna().unique().tolist())
    selected_channel = st.selectbox(
        "Benchmark channel", ["All channels"] + channels, index=0
    )
    working = (
        df if selected_channel == "All channels" else df[df["channel_title"] == selected_channel]
    )

    if working.empty:
        st.warning("No data available for selected channel.")
        return

    high_perf_threshold = working["views"].quantile(0.75)
    high_perf = working[working["views"] >= high_perf_threshold].copy()
    if high_perf.empty:
        high_perf = working.nlargest(50, "views")

    best_day = (
        high_perf.groupby("publish_day")["views"]
        .mean()
        .sort_values(ascending=False)
        .index[0]
        if high_perf["publish_day"].notna().any()
        else "N/A"
    )
    recommended_title_len = (
        int(high_perf["title_length"].median())
        if high_perf["title_length"].notna().any()
        else 60
    )
    top_keywords = _extract_keywords(high_perf["video_title"], top_n=10)

    kpi_row(
        [
            {
                "label": "Best Publish Day",
                "value": best_day,
                "icon": "📅",
            },
            {
                "label": "Target Title Length",
                "value": f"~{recommended_title_len} chars",
                "icon": "✏️",
            },
            {
                "label": "High-Perf Sample",
                "value": f"{len(high_perf):,} videos",
                "icon": "🎬",
            },
        ]
    )

    if top_keywords:
        st.markdown("**Suggested keyword angles**")
        styled_keyword_chips(top_keywords)

    top_refs = high_perf[
        [
            "channel_title",
            "video_title",
            "views",
            "likes",
            "comments",
            "engagement_rate",
            "video_publishedAt",
            "thumb_medium_url",
        ]
        if "thumb_medium_url" in high_perf.columns
        else [
            "channel_title",
            "video_title",
            "views",
            "likes",
            "comments",
            "engagement_rate",
            "video_publishedAt",
        ]
    ].sort_values("views", ascending=False).head(12)

    st.markdown("**Reference videos to model**")
    image_cols = ["thumb_medium_url"] if "thumb_medium_url" in top_refs.columns else None
    styled_dataframe(
        top_refs,
        title=None,
        precision=1,
        image_columns=image_cols,
    )


def render() -> None:
    st.title("Recommendations & Thumbnail Generator")
    st.write("Use analytics-backed recommendations, then generate thumbnail concepts.")

    categories = _available_categories()
    selected_category = st.selectbox("Dataset category", categories, index=0)

    rec_df = _load_recommendation_data_for_label(selected_category)
    _render_data_recommendations(rec_df, selected_category)
    st.markdown("---")

    st.markdown('<div class="yt-card">', unsafe_allow_html=True)
    section_header("AI Thumbnail Studio")

    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox("Provider", ["gemini", "openai"], index=0)
    with col2:
        if provider == "gemini":
            model = st.text_input(
                "Gemini image model",
                value="gemini-2.0-flash-exp-image-generation",
            )
        else:
            model = st.text_input("OpenAI image model", value="gpt-image-1")

    api_key_default = get_api_key(provider) or ""
    api_key = st.text_input(
        "API key",
        value=api_key_default,
        type="password",
        help="If blank, app reads from .env.",
    )

    title = st.text_input(
        "Video title", value="The Physics of Black Holes in 10 Minutes"
    )
    context = st.text_area(
        "Context",
        value=(
            "Audience: curious high-school and college students. "
            "Goal: simplify Hawking radiation and event horizon visuals."
        ),
        height=120,
    )
    style = st.text_area(
        "Style",
        value="Bold contrast, cinematic lighting, one main object, science aesthetic.",
        height=90,
    )
    negative_prompt = st.text_input(
        "Avoid",
        value="clutter, tiny text, low contrast, too many subjects",
    )

    col3, col4 = st.columns(2)
    with col3:
        count = st.slider("Number of options", min_value=1, max_value=4, value=2)
    with col4:
        size = st.selectbox(
            "Output size (OpenAI only)",
            ["1024x1024", "1536x1024", "1024x1536"],
            index=1,
        )

    run = st.button("Generate Thumbnails", type="primary", use_container_width=True)
    if not run:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if not api_key:
        st.error("Missing API key. Add it in the API key box or .env.")
        st.markdown("</div>", unsafe_allow_html=True)
        return
    if not title.strip() or not context.strip():
        st.error("Title and context are required.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    with st.spinner("Generating thumbnail concepts..."):
        try:
            generator = ThumbnailGenerator(
                provider=provider, api_key=api_key, model=model
            )
            images = generator.generate(
                title=title,
                context=context,
                style=style,
                negative_prompt=negative_prompt,
                count=count,
                size=size,
            )
        except Exception as exc:
            st.error(f"Generation failed: {exc}")
            st.markdown("</div>", unsafe_allow_html=True)
            return

    st.success(f"Generated {len(images)} image(s).")
    out_dir = os.path.join("outputs", "thumbnails")
    os.makedirs(out_dir, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    st.markdown('<div class="thumb-grid">', unsafe_allow_html=True)
    for idx, generated in enumerate(images, start=1):
        ext = "png" if "png" in generated.mime_type else "jpg"
        filename = f"thumbnail_{ts}_{idx}.{ext}"
        file_path = os.path.join(out_dir, filename)
        with open(file_path, "wb") as fp:
            fp.write(generated.image_bytes)

        with st.container():
            st.markdown('<div class="thumb-card">', unsafe_allow_html=True)
            st.image(generated.image_bytes, use_container_width=True)
            st.markdown(
                f"""
                <div class="thumb-card-footer">
                    <span>Option {idx}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.download_button(
                label="Download",
                data=generated.image_bytes,
                file_name=filename,
                mime=generated.mime_type,
                use_container_width=True,
                key=f"download_{idx}_{ts}",
            )
            st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
