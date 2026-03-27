# YouTube IP V5 Architecture

## Sidebar Navigation

1. `Channel Analysis`
2. `Channel Insights`
3. `Thumbnails`
4. `Outlier Finder`
5. `Ytuber`
6. `Tools`
7. `Deployment`

V5 removes the sidebar `Assistant` and removes Google OAuth from `Channel Insights`.

## Full Runtime And Data Pipeline

```mermaid
flowchart TD
    A["GitHub committed CSVs<br/>data/youtube api data/*.csv"] --> B["streamlit_app.py"]
    U["User actions"] --> B
    B --> C["dashboard/app.py"]
    C --> D["dashboard/components/sidebar.py"]
    D --> E["Page views"]

    S["Streamlit secrets / env"] --> F["src/utils/api_keys.py"]
    F --> G["YouTube Data API v3"]
    F --> H["Gemini / OpenAI"]

    A --> J["Channel Analysis / Thumbnails"]
    G --> K["Ytuber / Channel Insights / Outlier Finder / Tools"]
    H --> L["Thumbnails / Ytuber / Outlier Finder"]

    J --> N["pandas transforms + service payloads"]
    K --> N
    L --> N

    N --> P["dashboard/components/visualizations.py"]
    P --> Q["Charts, cards, tables, downloads, AI outputs"]
```

## Page Problem Map

| Page | Problem Solved | Main Services / Inputs | Main UI Outputs | Interlinks |
| --- | --- | --- | --- | --- |
| `Channel Analysis` | benchmark bundled datasets | CSVs, pandas, visualization helpers | KPI cards, trend charts, ranked tables | shares benchmark context with `Thumbnails` |
| `Channel Insights` | analyze one tracked public channel over time | `public_channel_service`, `channel_snapshot_store`, `channel_insights_service`, optional BERTopic | topic trends, format analysis, outliers, next-topic ideas | can inform `Outlier Finder` themes |
| `Thumbnails` | generate or export thumbnails without mixing broader strategy UI | `thumbnail_generator.py`, `thumbnail_hub_service.py`, public thumbnail URLs | generated thumbnails, preview cards, downloadable images | lighter replacement for the old recommendations surface |
| `Outlier Finder` | find niche winners | `outliers_finder.py`, `outlier_ai.py`, YouTube API | scored outlier tables, breakout snapshot, AI research | receives handoff from `Ytuber` and `Channel Insights` |
| `Ytuber` | run a live creator AI workspace | YouTube API, pooled API keys, thumbnail generator | AI Studio, audit views, keyword and planner outputs | can hand off into `Outlier Finder` |
| `Tools` | export public YouTube assets | `youtube_tools.py`, `transcript_service.py`, `yt-dlp`, `ffmpeg` | metadata previews, transcript/audio/video/thumbnail downloads | standalone utility surface |
| `Deployment` | explain setup and deployment | static instructions in app shell | repo, branch, secrets, deploy notes | operational reference only |

## Live API Extraction Flow

```mermaid
flowchart LR
    A["User enters channel, keyword, or URL"] --> B["Page view"]
    B --> C["src/utils/api_keys.py"]
    C --> D["Selected provider key"]
    D --> E["YouTube Data API request"]
    E --> F["Service-layer normalization"]
    F --> G["pandas dataframes / scored payloads"]
    G --> H["dashboard/components/visualizations.py"]
    H --> I["Rendered Streamlit UI"]
```

In V5, `Channel Insights` is public-only. It does not use Google OAuth and it does not merge owner-only YouTube Analytics metrics.

## Model-Backed Topic Flow

```mermaid
flowchart LR
    A["Streamlit secrets"] --> B["MODEL_ARTIFACTS_ENABLED"]
    A --> C["MODEL_ARTIFACTS_MANIFEST_URL"]
    C --> D["src/services/model_artifact_service.py"]
    D --> E["Manifest JSON"]
    E --> F["artifact_url + sha256 + bundle_version"]
    F --> G["Download on explicit beta refresh only"]
    G --> H["outputs/models/runtime/<bundle_version>/"]
    H --> I["src/services/topic_model_runtime.py"]
    I --> J["src/services/channel_insights_service.py"]
    J --> K["dashboard/views/channel_insights.py"]
    D --> L["Fallback to heuristic topics"]
    L --> J
```

Topic modes:

- `Heuristic Topics` uses built-in keyword and rule grouping
- `Model-Backed Topics` uses optional BERTopic semantic grouping

## Branch Notes

- V5 removes the global `Assistant`
- V5 removes Google OAuth and owner-only analytics overlays
- V5 renames page 3 to `Thumbnails`
- BERTopic is optional and never required at app boot
