# YouTube IP V3

YouTube IP V3 is a Streamlit application for YouTube research, benchmarking, live channel analysis, outlier discovery, and AI-assisted planning. It combines bundled CSV datasets with live YouTube Data API requests and optional Gemini/OpenAI generation so one app can cover historical benchmarking, channel diagnostics, idea research, and creative asset prototyping.

Live app:

- https://youtube-ip-v3.streamlit.app/

This README documents the current deployed app as it exists in this repository, including:

- what the product does
- which files power each feature
- how the app is wired together
- what data sources and API keys it uses
- how to run it locally
- how to deploy it on Streamlit Community Cloud
- what parts of the repo are active versus legacy scaffolding
- how the retrieval-first assistant caches and reuses answers before calling AI

## Product Overview

The app currently exposes seven sidebar destinations:

| Page | Purpose | Main File |
| --- | --- | --- |
| `Channel Analysis` | Portfolio-level analytics across the bundled datasets | `dashboard/views/channel_analysis.py` |
| `Recommendations` | Dataset-backed publishing guidance and thumbnail generation | `dashboard/views/recommendations.py` |
| `Ytuber` | Live creator workspace for one channel at a time | `dashboard/views/ytuber.py` |
| `Channel Insights` | Persisted public-channel snapshots and creator intelligence over time | `dashboard/views/channel_insights.py` |
| `Outlier Finder` | Standalone niche research and outlier-video discovery | `dashboard/views/outlier_finder.py` |
| `Tools` | Standalone utility workspace for YouTube metadata and asset downloads | `dashboard/views/tools.py` |
| `Deployment` | Run/deploy notes shown inside the app | `dashboard/app.py` |

In addition to the sidebar pages, the app now includes a **global Assistant** in the sidebar. It is available across the product and is designed to answer product-help, troubleshooting, metric-interpretation, and creator-workflow questions with a retrieval-first stack before it escalates to Gemini or OpenAI.

At a high level, the app is designed for three use cases:

1. Analyze existing cross-channel datasets to understand benchmark patterns.
2. Pull live stats for a public channel and turn them into creator-focused diagnostics.
3. Persist public-channel snapshots and compare topic, format, and outlier patterns over time.
4. Generate strategy and creative suggestions with Gemini or OpenAI using the same public data.
5. Export public YouTube assets such as thumbnails, transcripts, audio, and video from one utility page.

## What The App Includes

### 1. Channel Analysis

`Channel Analysis` is the dataset-backed analytics view.

It can:

- load one category dataset or all committed datasets together
- filter by channel and published-date range
- show KPI summaries for videos, channels, views, average views, and median engagement
- surface top channels by total views
- chart monthly upload trends
- list best-performing videos
- compare publishing-day performance
- visualize views versus engagement

Code:

- `dashboard/views/channel_analysis.py`
- `dashboard/components/visualizations.py`

Data source:

- committed CSV files in `data/youtube api data/`

### 2. Recommendations

`Recommendations` turns the same bundled datasets into lightweight strategy guidance.

It can:

- benchmark a selected category or all categories
- compute a high-performing sample from the top quartile of videos
- suggest publish timing and title length targets
- extract keyword angles from strong titles
- show reference videos to model
- generate thumbnail concepts with Gemini or OpenAI

Code:

- `dashboard/views/recommendations.py`
- `src/llm_integration/thumbnail_generator.py`

### 3. Ytuber

`Ytuber` is the live creator workspace for one public channel.

It can:

- resolve a handle, channel name, or channel ID
- pull fresh channel and recent-video metadata from the YouTube Data API
- cache channel fetches in the local CSV-backed dataset
- compute a channel overview and audit
- generate keyword intelligence from recent uploads
- score titles and descriptions in `Title And SEO Lab`
- benchmark competitors and generate comparative recommendations
- plan content around day/hour performance patterns
- run `AI Studio` for titles, ideas, scripts, clips, and thumbnail generation
- hand off into the standalone `Outlier Finder`

Key modules inside the page:

- `AI Studio`
- `Overview`
- `Channel Audit`
- `Keyword Intel`
- `Outliers Finder` shortcut
- `Title And SEO Lab`
- `Competitor Benchmark`
- `Content Planner`

Code:

- `dashboard/views/ytuber.py`
- `src/utils/api_keys.py`
- `src/llm_integration/thumbnail_generator.py`

### 4. Channel Insights

`Channel Insights` is the new public-channel intelligence workflow for recurring creator analysis.

It can:

- add a public channel by URL, handle, or channel ID
- store tracked channels in a local SQLite database
- persist dated channel snapshots on refresh
- compare current public performance against prior snapshots
- surface rising and weak themes from recent public uploads
- compare Shorts versus long-form and duration buckets
- identify outliers and underperformers within the channel
- recommend what to double down on, what to avoid, and what to test next
- generate grounded video-direction suggestions from actual channel data

Code:

- `dashboard/views/channel_insights.py`
- `src/services/public_channel_service.py`
- `src/services/channel_snapshot_store.py`
- `src/services/channel_insights_service.py`
- `src/services/topic_analysis_service.py`
- `src/services/channel_idea_service.py`
- `src/utils/channel_parser.py`

Storage:

- `outputs/channel_insights/channel_insights.db`

### 5. Outlier Finder

`Outlier Finder` is a standalone niche-research page in the sidebar. It is designed to find videos that are overperforming relative to channel size, age, peers, or channel baseline within the scanned cohort returned by the official YouTube API.

It supports:

- niche / keyword search
- timeframe filters
- region and language filters
- language strictness
- duration preference
- minimum views
- subscriber bucket and explicit min/max subscriber filters
- include/exclude hidden subscriber counts
- exact-phrase versus broad matching
- exclude keywords
- bounded search depth and baseline-enrichment settings

Its results-first workflow is:

1. `Top Outliers In This Scan`
2. `Breakout Snapshot`
3. `AI Research`
4. `How This Works`

The page also includes:

- sortable outlier results
- explanation strings for why each video is an outlier
- score and scan summary cards
- breakout charts for age, duration, title pattern, and language quality
- structured AI report cards via Gemini/OpenAI
- an inline methodology section explaining metrics and caveats

Code:

- `dashboard/views/outlier_finder.py`
- `src/services/outliers_finder.py`
- `src/services/outlier_ai.py`

### 6. Tools

`Tools` is a standalone utility page for public YouTube asset retrieval.

It supports:

- single-video metadata preview
- batch URL processing
- public playlist preview with selected-item operations
- thumbnail preview and export
- transcript language discovery and `.txt` export
- audio download
- video download
- quality/format selection for single videos
- profile-based audio/video choices for batch and playlist workflows

The page is designed around three modes:

- `Single`
- `Batch`
- `Playlist`

Code:

- `dashboard/views/tools.py`
- `src/services/youtube_tools.py`
- `src/services/transcript_service.py`
- `src/utils/file_utils.py`

### 7. Assistant

The sidebar `Assistant` is a retrieval-first help and creator-support layer.

It can:

- answer product usage questions
- explain metrics and caveats
- suggest creator workflows
- help troubleshoot missing results, failed exports, or unavailable AI features
- reuse prior high-confidence answers before making any paid AI call
- fall back to Gemini or OpenAI only when retrieval is insufficient

Core implementation:

- `dashboard/components/assistant_panel.py`
- `src/services/assistant_service.py`
- `src/services/retrieval_service.py`
- `src/services/cache_service.py`
- `src/services/assistant_knowledge.py`
- `src/utils/text_normalization.py`

Knowledge and storage:

- `data/assistant/*.json`
- `outputs/assistant/assistant_cache.db`

## Current Runtime Architecture

### App Entrypoints

There are two Streamlit entrypoints:

- `streamlit_app.py`
  - root deployment entrypoint used by Streamlit Cloud
  - simply imports `dashboard.app`
- `dashboard/app.py`
  - real application shell
  - configures Streamlit page settings
  - injects the shared theme
  - renders the sidebar
  - routes to each page

### Shared UI Layer

- `dashboard/components/sidebar.py`
  - branded sidebar navigation using `streamlit-option-menu`
- `dashboard/components/theme.py`
  - shared app theme, CSS tokens, page widths, button styling, and general chrome
- `dashboard/components/visualizations.py`
  - reusable Plotly chart helpers, dataframe styling, keyword chips, KPI rows, and section headers
- `dashboard/components/assistant_panel.py`
  - sidebar assistant UI, starter prompts, answer cards, and feedback controls

### Active Service Layer

The current active backend logic is concentrated in a small number of files:

- `src/utils/api_keys.py`
  - reads API keys from environment variables and Streamlit secrets
  - supports single-key and pooled-key modes
  - rotates keys per provider in session state
  - retries operations across configured keys

- `src/services/outliers_finder.py`
  - core outlier-search request and scoring engine
  - YouTube API orchestration for search, videos, channels, and baseline fetches
  - language confidence heuristics
  - duration and age bucketing
  - peer percentile and baseline-based scoring
  - cache wrappers for niche scans and channel baselines

- `src/services/outlier_ai.py`
  - converts outlier results into structured AI research cards
  - calls Gemini or OpenAI
  - expects JSON output and falls back gracefully if parsing fails

- `src/services/public_channel_service.py`
  - shared public-channel fetch layer reused by `Ytuber` and `Channel Insights`
  - resolves handles / channel IDs
  - reuses the local CSV-backed cache plus live YouTube Data API refreshes

- `src/services/channel_snapshot_store.py`
  - SQLite-backed persistence for tracked channels and dated channel snapshots

- `src/services/channel_insights_service.py`
  - channel refresh orchestration
  - baseline computation
  - topic/format/outlier insight payload generation

- `src/services/topic_analysis_service.py`
  - title-pattern classification
  - heuristic topic clustering
  - duration and timing aggregations

- `src/services/channel_idea_service.py`
  - grounded “double down / avoid / test next” suggestions
  - optional AI explanation layer on top of structured metrics

- `src/services/assistant_service.py`
  - top-level assistant orchestration
  - intent detection
  - page-context snapshots
  - exact-cache -> semantic-retrieval -> knowledge -> hybrid -> LLM routing

- `src/services/retrieval_service.py`
  - local TF-IDF retrieval over curated knowledge and cached historical answers

- `src/services/cache_service.py`
  - SQLite-backed answer cache and feedback storage

- `src/services/assistant_knowledge.py`
  - JSON knowledge loading for FAQs, metric definitions, troubleshooting, and workflow guidance

- `src/llm_integration/thumbnail_generator.py`
  - Gemini and OpenAI image-generation wrapper
  - used by the Recommendations page and `Ytuber -> AI Studio`

### Data Flow

There are two main data flows in the app:

#### A. Dataset-backed analytics

```text
Bundled CSV datasets
-> pandas loading/cleaning in page views
-> dashboard/components/visualizations.py
-> Channel Analysis / Recommendations UI
```

#### B. Live API-backed creator workflows

```text
Streamlit secrets / env vars
-> src/utils/api_keys.py
-> YouTube API or Gemini/OpenAI calls
-> page-specific transformations in Ytuber / Outlier Finder
-> charts, result cards, and AI panels in the Streamlit UI
```

#### C. Retrieval-first assistant workflow

```text
User question
-> query normalization
-> exact cache lookup (SQLite)
-> semantic similarity search (TF-IDF over cached answers)
-> structured knowledge retrieval (JSON knowledge base)
-> hybrid deterministic response when possible
-> Gemini/OpenAI only when retrieval is insufficient
-> cache new answer + collect helpful / not-helpful feedback
```

## Repository Map

This is the practical repository layout, not just the nominal one:

```text
.
├── dashboard/
│   ├── app.py                       # Main Streamlit router
│   ├── components/
│   │   ├── sidebar.py               # Sidebar navigation
│   │   ├── theme.py                 # Shared dark/purple theme
│   │   └── visualizations.py        # Plotly + dataframe helpers
│   └── views/
│       ├── channel_analysis.py      # Dataset analytics page
│       ├── channel_insights.py      # Persisted public-channel insights page
│       ├── recommendations.py       # Recommendations + thumbnail studio
│       ├── ytuber.py                # Live creator workspace
│       ├── outlier_finder.py        # Standalone niche research page
│       └── tools.py                 # Standalone YouTube tools page
├── data/
│   └── youtube api data/            # Bundled CSV datasets used by the app
├── data/assistant/                  # Curated assistant knowledge records
├── docs/
│   ├── ARCHITECTURE.md              # Original architecture note
│   └── PROJECT_BRIEF.md             # Original project brief
├── outputs/
│   └── thumbnails/                  # Generated image outputs
│   └── assistant/                   # SQLite cache for assistant answers/feedback
├── scripts/
│   ├── yt_api_smoketest.py          # Rich YouTube API smoke test
│   ├── build_*_dataset.py           # Dataset builder scripts
│   └── available_data_constraints.md
├── src/
│   ├── services/                    # Active outlier, tools, and AI service layer
│   ├── utils/                       # API-key management, file helpers, and shared utilities
│   ├── llm_integration/             # Thumbnail generation wrapper
│   ├── data_collection/             # Mostly legacy / empty scaffolding
│   ├── data_processing/             # Partial older scaffolding
│   └── modeling/                    # Partial older scaffolding
├── tests/
│   ├── integration/                 # Integration tests
│   └── unit/                        # Unit tests
├── streamlit_app.py                 # Root Streamlit Cloud entrypoint
├── requirements.txt                 # Python dependencies
└── .streamlit/config.toml           # Theme config
```

## What Is Active Versus Historical Scaffolding

This repo has evolved over time. The currently deployed app does **not** use every folder equally.

### Actively used by the app today

- `dashboard/`
- `src/services/`
- `src/services/public_channel_service.py`
- `src/services/channel_snapshot_store.py`
- `src/services/channel_insights_service.py`
- `src/services/topic_analysis_service.py`
- `src/services/channel_idea_service.py`
- `src/utils/api_keys.py`
- `src/utils/channel_parser.py`
- `src/utils/file_utils.py`
- `src/llm_integration/thumbnail_generator.py`
- `dashboard/components/assistant_panel.py`
- `src/services/assistant_service.py`
- `src/services/retrieval_service.py`
- `src/services/cache_service.py`
- `src/services/assistant_knowledge.py`
- `src/utils/text_normalization.py`
- `data/youtube api data/`
- `data/assistant/`
- `outputs/channel_insights/`
- `tests/unit/test_outliers_finder.py`
- `tests/unit/test_outlier_ai.py`
- `tests/integration/test_pipeline.py`
- `tests/unit/test_text_normalization.py`
- `tests/unit/test_cache_service.py`
- `tests/unit/test_retrieval_service.py`
- `tests/unit/test_assistant_service.py`
- `tests/integration/test_assistant_flow.py`

## Assistant Retrieval And Caching Flow

The Assistant is intentionally retrieval-first to reduce token cost and improve speed.

### Layer order

1. **Exact cache lookup**
   - normalized question + page scope + context mode
   - reuses answers younger than 30 days when confidence is strong and feedback is not negative
2. **Semantic cache lookup**
   - local TF-IDF cosine similarity across prior resolved answers
   - allows near-duplicate reuse without paying for embeddings
3. **Structured knowledge retrieval**
   - uses curated JSON knowledge files for product help, metrics, troubleshooting, and workflows
4. **Hybrid deterministic answer**
   - combines cached answers and knowledge into a structured response without calling an LLM
5. **LLM fallback**
   - Gemini first, OpenAI fallback
   - used only when retrieval is insufficient, especially for creator strategy or contextual interpretation

### Storage

- Cache DB: `outputs/assistant/assistant_cache.db`
- Knowledge files: `data/assistant/*.json`

### What gets stored

- original query
- normalized query
- page scope
- context mode
- answer text
- answer source type (`exact_cache`, `semantic_cache`, `knowledge`, `hybrid`, `llm`)
- confidence
- source references
- related questions
- page-context snapshot
- model/provider metadata when generation occurs
- helpful / not-helpful feedback counts

### Current limitations

- SQLite persistence is local and may not survive all Streamlit Cloud redeploys
- TF-IDF retrieval is deliberately lightweight and cheaper than embeddings, but it is weaker on heavy paraphrases
- the strongest context support today is on `Outlier Finder`, `Ytuber`, and `Tools`
- creator-strategy answers may still require AI fallback when product knowledge is not enough
- Channel Insights uses public channel data only, so it does not include private owner metrics like impressions, CTR, watch time, or retention

### Present in the repo but only partially used or currently inactive

- `src/data_collection/`
- `src/modeling/`
- `src/llm_integration/content_generator.py`
- `src/llm_integration/gpt4_client.py`
- parts of `src/data_processing/`

Several of these files are empty or legacy placeholders from the original research-project structure. The README reflects the code that powers the live app today, not every historical idea in the repo.

## Bundled Data Assets

The repository currently ships with four CSV datasets under `data/youtube api data/`.

| Dataset | Rows | Columns |
| --- | ---: | ---: |
| `entertainment_channels_videos.csv` | 101,554 | 54 |
| `gaming_channels_videos.csv` | 95,534 | 54 |
| `research_science_channels_videos.csv` | 221,325 | 54 |
| `tech_channels_videos.csv` | 125,693 | 54 |

Total bundled rows: **544,106**

These datasets power:

- `Channel Analysis`
- the dataset-backed parts of `Recommendations`
- parts of the `Ytuber` page when appending live fetches into the working CSV-backed flow

## Secrets, Environment Variables, And API-Key Pools

The app supports both single keys and pooled keys.

Supported provider groups:

- `youtube`
- `gemini`
- `openai`

### Preferred pooled-key format

Environment variables:

```bash
YOUTUBE_API_KEYS=key_1,key_2
GEMINI_API_KEYS=key_1,key_2
OPENAI_API_KEYS=key_1,key_2
```

Streamlit secrets:

```toml
YOUTUBE_API_KEYS = ["key_1", "key_2"]
GEMINI_API_KEYS = ["key_1", "key_2"]
OPENAI_API_KEYS = ["key_1", "key_2"]
```

### Supported single-key fallbacks

- `YOUTUBE_API_KEY`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`

### How key rotation works

`src/utils/api_keys.py` does the following:

- reads values from Streamlit secrets first, then environment variables
- accepts JSON-style lists, comma-separated strings, line-delimited strings, or indexed secret names
- deduplicates the final list
- stores a session-level cursor for each provider
- retries operations across all configured keys when failures are retryable

This matters most for:

- live YouTube fetches in `Ytuber`
- outlier scans in `Outlier Finder`
- Gemini/OpenAI generation in `AI Studio`, `Recommendations`, and Outlier AI reports

## Local Development

### Prerequisites

- Python 3.10 or newer
- `ffmpeg` for merged video downloads and MP3 conversion in the `Tools` page
- valid YouTube Data API credentials for live features
- Gemini and/or OpenAI credentials for AI features

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you are running locally outside Streamlit Community Cloud, make sure `ffmpeg` is on your system path when you want:

- merged video downloads in `Tools`
- MP3 conversion in `Tools`

### Configure local secrets

Copy:

```bash
cp .env.example .env
```

Then populate:

- `YOUTUBE_API_KEYS`
- `GEMINI_API_KEYS`
- `OPENAI_API_KEYS`

Example:

```bash
YOUTUBE_API_KEYS=your_youtube_key_1,your_youtube_key_2
GEMINI_API_KEYS=your_gemini_key_1,your_gemini_key_2
OPENAI_API_KEYS=your_openai_key_1,your_openai_key_2
```

Local Streamlit-style secrets are also supported via `.streamlit/secrets.toml`.

Reference file:

- `.streamlit/secrets.toml.example`

### Run the app

Preferred:

```bash
streamlit run streamlit_app.py
```

Alternate:

```bash
streamlit run dashboard/app.py
```

## Streamlit Community Cloud Deployment

This repo is structured to deploy directly from GitHub to Streamlit Community Cloud.

Current deployed app:

- https://youtube-ip-v3.streamlit.app/

### Streamlit app settings

- Repo: `royayushkr/Youtube-IP-V3`
- Branch: `main`
- Main file path: `streamlit_app.py`

### Required secrets

```toml
YOUTUBE_API_KEYS = ["your_youtube_key_1", "your_youtube_key_2"]
GEMINI_API_KEYS = ["your_gemini_key_1", "your_gemini_key_2"]
OPENAI_API_KEYS = ["your_openai_key_1", "your_openai_key_2"]
```

Single-key fallbacks still work if needed.

### Theme

The live app theme is defined in `.streamlit/config.toml`:

- `primaryColor = "#8B5CF6"`
- `backgroundColor = "#090B14"`
- `secondaryBackgroundColor = "#141A31"`
- `textColor = "#F7F8FC"`

### Extra System Package For Tools

This repo now includes a `packages.txt` file with:

```text
ffmpeg
```

Streamlit Community Cloud uses that file to install the system dependency required for merged video downloads and audio conversion in the `Tools` page.

## Outlier Finder Methodology Summary

Outlier Finder is one of the most custom parts of the app, so it deserves a direct summary here.

### What it measures

The outlier score is a weighted mix of:

- channel-baseline lift
- peer percentile
- engagement percentile
- recency boost

### Key derived metrics

- `Views Per Day`
  - views divided by video age in days
- `Views Per Subscriber`
  - views normalized by channel subscriber count when public
- `Peer Percentile`
  - performance relative to the scanned cohort
- `Baseline Component`
  - how far the video is running above the channel's recent baseline
- `Language Confidence`
  - heuristic score based on metadata and title script

### Practical constraints

- results come from the scanned cohort returned by YouTube search, not the entire platform
- YouTube search is ranked and sampled
- subscriber counts may be hidden or rounded
- language filtering is heuristic, not guaranteed
- there is no access to impressions, CTR, watch time, or retention from the public API

### Current cache behavior

- niche query cache: 1 hour
- channel baseline cache: 6 hours

## AI Integrations

### Outlier AI Research

`src/services/outlier_ai.py` converts outlier results into structured research cards with:

- executive headline
- key takeaway
- confidence label and notes
- breakout themes
- title patterns
- repeatable angles
- notable anomalies
- next steps
- warnings

Provider support:

- Gemini
- OpenAI

### Thumbnail Generation

`src/llm_integration/thumbnail_generator.py` supports:

- Gemini image generation
- OpenAI image generation via the Images API

It exposes controls for:

- model
- count
- size
- quality
- background
- output format

Generated files are saved under `outputs/thumbnails/`.

## Tools Page Notes

The `Tools` page is intentionally scoped to public YouTube content and temporary downloads.

### Supported V1 modes

- `Single`
  - exact metadata preview
  - exact transcript-language selection
  - exact audio/video format selection where available
- `Batch`
  - newline-separated public URLs
  - per-item statuses
  - per-item downloads
- `Playlist`
  - public playlist preview
  - selected-item processing
  - per-item downloads

### Dependencies used by Tools

- `yt-dlp`
  - metadata extraction
  - format listing
  - audio/video downloads
  - playlist expansion
- `youtube-transcript-api`
  - transcript language discovery
  - transcript retrieval
  - transcript export
- `ffmpeg`
  - merged video downloads
  - MP3 conversion

### Important delivery constraint

`st.download_button` keeps file data in memory for the connected session. For that reason, the app blocks very large in-app downloads instead of trying to stream arbitrarily large files through Streamlit.

### Known Tools limitations

- public URLs only
- no auth/cookies in V1
- private, members-only, or region-restricted videos may fail
- batch and playlist downloads are sequential, not parallel
- batch and playlist modes use quality profiles instead of per-video exact format IDs
- transcript summarization is not included in V1

## Scripts

The `scripts/` directory includes the repo's operational utilities.

### `scripts/yt_api_smoketest.py`

A richer smoke test for the public YouTube Data API. It checks:

- channel discovery
- channel details
- uploads playlist traversal
- video details
- video categories
- sample comments

Use it when validating that a YouTube API key is working and returning the expected response shapes.

### `scripts/build_*_dataset.py`

These scripts build the CSV datasets for different categories:

- `build_category_dataset.py`
- `build_fitness_dataset.py`
- `build_research_dataset.py`

They are useful if you want to refresh or regenerate the bundled datasets outside the Streamlit app.

### `scripts/available_data_constraints.md`

Documents what the public YouTube API can and cannot provide, and how those limitations should influence product design and interpretation.

## Tests

The current test suite includes:

- `tests/unit/test_outliers_finder.py`
  - verifies scoring behavior, ordering, scan quality summaries, and presentational helpers
- `tests/unit/test_outlier_ai.py`
  - verifies JSON extraction, report mapping, and fallback behavior
- `tests/integration/test_pipeline.py`
  - verifies outlier search flow with mocked API responses and advanced filters
- `tests/unit/test_text_processing.py`
- `tests/unit/test_data_collection.py`
- `tests/unit/test_youtube_tools.py`
  - verifies URL validation, playlist shaping, format curation, and batch error handling
- `tests/unit/test_transcript_service.py`
  - verifies transcript option normalization and transcript file export
- `tests/unit/test_file_utils.py`
  - verifies temp-file helpers and filename sanitization
- `tests/integration/test_tools_flow.py`
  - verifies playlist and batch orchestration for the new Tools page

Run:

```bash
python3 -m pytest
```

## Known Limitations

This app is intentionally pragmatic, not a full YouTube intelligence platform with first-party creator analytics.

Important limitations:

- all live research is limited to public YouTube metadata
- all `Tools` exports are limited to public YouTube content and Streamlit-friendly in-memory delivery
- YouTube API search quota is expensive, especially `search.list`
- `yt-dlp` and transcript retrieval behavior can change when YouTube changes extraction behavior
- Outlier Finder is not an exhaustive rank tracker
- language, geography, and subscriber-based filters are best-effort
- some legacy folders in `src/` are still placeholders and do not reflect the live dashboard architecture

## Supporting Documentation

- `docs/ARCHITECTURE.md`
  - original high-level architecture note
- `docs/PROJECT_BRIEF.md`
  - original academic project brief
- `CONTRIBUTING.md`
  - contribution guidelines
- `SECURITY.md`
  - private reporting guidance for vulnerabilities
- `LICENSE`
  - MIT license

## Contribution And Maintenance Notes

If you change behavior or configuration:

- update the relevant view/service code
- update tests if the behavior is observable
- update this README if setup, deployment, or feature scope changed

For UI changes, include screenshots in pull requests as noted in `CONTRIBUTING.md`.

## License

MIT License. See `LICENSE`.
