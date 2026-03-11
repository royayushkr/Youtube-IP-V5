# YouTube IP V3

YouTube IP V3 is a Streamlit application for channel benchmarking, content analysis, and AI-assisted planning. It combines prebuilt cross-channel datasets with live YouTube API pulls so you can analyze performance patterns, generate recommendations, and prototype creator assets in one interface.

## What The App Includes

- Channel Analysis for portfolio-level trends across the bundled datasets
- Recommendations for publish timing, title patterns, and keyword angles
- Ytuber Creator Suite for live channel audits, competitor benchmarking, SEO scoring, trend radar, content planning, and AI generation
- Gemini and OpenAI integrations for text and thumbnail workflows

## Repository Layout

```text
.
├── dashboard/                 # Streamlit UI and page views
├── data/youtube api data/     # Bundled CSV datasets used by the analytics views
├── docs/                      # Architecture and project brief
├── outputs/                   # Generated thumbnails and derived artifacts
├── scripts/                   # Dataset-building and API smoke-test scripts
├── src/                       # Partial package scaffolding
├── streamlit_app.py           # Root Streamlit Cloud entrypoint
└── requirements.txt           # Python dependencies
```

## Local Setup

### Prerequisites

- Python 3.10+
- `YOUTUBE_API_KEY` for live channel analysis
- `GEMINI_API_KEY` for Gemini generation
- `OPENAI_API_KEY` if you want OpenAI fallback text/image generation

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure Secrets For Local Development

```bash
cp .env.example .env
```

Populate `.env` with:

- `YOUTUBE_API_KEY`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`

`OPENAI_API_KEY` is optional if you only use Gemini-backed features.

### Run The App

```bash
streamlit run streamlit_app.py
```

The original module entrypoint also works:

```bash
streamlit run dashboard/app.py
```

## Dashboard Pages

### Channel Analysis

Located in `dashboard/views/channel_analysis.py`.

Uses the committed CSV datasets under `data/youtube api data/` to compare channels, inspect upload trends, review top-performing videos, and visualize engagement patterns.

### Recommendations

Located in `dashboard/views/recommendations.py`.

Uses dataset-backed performance patterns to suggest keyword angles, title length targets, publish timing, and reference videos. It also includes the thumbnail studio for Gemini/OpenAI image generation.

### Ytuber

Located in `dashboard/views/ytuber.py`.

Uses live YouTube API pulls for a single channel and exposes:

- Overview
- Channel Audit
- Keyword Intel
- Title and SEO Lab
- Competitor Benchmark
- Trend Radar
- Content Planner
- AI Studio

## Streamlit Deployment

This repo is ready to deploy from GitHub to Streamlit Community Cloud.

### Streamlit Cloud App Settings

- Repo: `royayushkr/Youtube-IP-V3`
- Branch: `main`
- Main file path: `streamlit_app.py`

### Required Secrets

Add these in the Streamlit app Secrets panel:

```toml
YOUTUBE_API_KEY = "your_youtube_key"
GEMINI_API_KEY = "your_gemini_key"
OPENAI_API_KEY = "your_openai_key"
```

You can also copy `.streamlit/secrets.toml.example` for local reference.

### Deployment Notes

- `streamlit_app.py` is the recommended root entrypoint for deployment.
- `dashboard/app.py` remains the main application module.
- Channel Analysis and Recommendations work from the committed datasets.
- The Ytuber page requires a valid `YOUTUBE_API_KEY` to pull live channel data.
- Thumbnail and text generation features require Gemini and/or OpenAI credentials.

## Supporting Files

- `.streamlit/config.toml` controls the app theme
- `.env.example` documents local environment variables
- `docs/ARCHITECTURE.md` describes the high-level data flow
- `scripts/` contains dataset builders and API smoke tests

## License

MIT License. See `LICENSE`.
