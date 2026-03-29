# V5 Deployment, Versions, And Model Flow

This document tracks the deployment story across all five released versions and explains how the current V5 runtime, secrets, and optional BERTopic path are deployed.

## Current V5 Branch And Repo Targets

| Item | Value |
| --- | --- |
| Original repo branch tag | `youtube-ip-v5` |
| Original repo | `matt-foor/purdue-youtube-ip` |
| Deploy repo | `royayushkr/Youtube-IP-V5` |
| Deploy branch | `main` |
| PR branch reference | [youtube-ip-v5](https://github.com/matt-foor/purdue-youtube-ip/tree/youtube-ip-v5) |
| Live V5 app | [youtube-ip-v5.streamlit.app](https://youtube-ip-v5.streamlit.app/) |

## All Deployed Versions

| Version | Live Link | Product Stage | Current Reading Of That Version |
| --- | --- | --- | --- |
| `V1` | [youtube-stats-ip.streamlit.app](https://youtube-stats-ip.streamlit.app/) | prototype | proof that public YouTube metadata and modeling could power creator strategy |
| `V2` | [youtube-stats-ip-v2.streamlit.app](https://youtube-stats-ip-v2.streamlit.app/) | expansion | larger creator operating system with more AI and workflow surface |
| `V3` | [youtube-ip-v3.streamlit.app](https://youtube-ip-v3.streamlit.app/) | productization | clearer multi-page app with a stronger runtime story |
| `V4` | [youtube-ip-v4.streamlit.app](https://youtube-ip-v4.streamlit.app/) | deep intelligence | most ambitious version with Assistant, Google OAuth, and BERTopic beta |
| `V5` | [youtube-ip-v5.streamlit.app](https://youtube-ip-v5.streamlit.app/) | simplification + presentation | current public-only streamlined shell with retained AI suite pages |

## Version Evolution Flow

```mermaid
flowchart LR
    V1["V1"] --> V2["V2"] --> V3["V3"] --> V4["V4"] --> V5["V5"]
    V1 --- A1["analytics prototype"]
    V2 --- A2["creator-suite expansion"]
    V3 --- A3["clear product shell"]
    V4 --- A4["Assistant + OAuth + Channel Insights + BERTopic beta"]
    V5 --- A5["public-only cleanup + consolidated documentation"]
```

## Version Comparison Matrix

| Area | V1 | V2 | V3 | V4 | V5 |
| --- | --- | --- | --- | --- | --- |
| Public dataset benchmarking | present | present | present | present | present |
| Live public-channel workspace | limited | expanded | present | present | present |
| Outlier research | early | present | strong standalone page | strong | strong |
| Thumbnail generation | present | expanded | present | present | present |
| Dedicated `Channel Insights` page | absent | absent | absent | present | present |
| Sidebar `Assistant` | absent | absent | absent | present | removed |
| Google OAuth / owner analytics | absent | absent | absent | present | removed |
| Optional BERTopic runtime in app | conceptual | conceptual | stack framing only | present | present |
| Current page 3 label | dataset/thumbnails mix | recommendations style | `Recommendations` | `Recommendations` | `Thumbnails` |

## Documented Navigation By Version

| Version | Clearly Documented Surface |
| --- | --- |
| `V1` | deployable dashboard with `Thumbnail Generator` and `Dataset Overview` |
| `V2` | creator-suite shell centered on `Ytuber`, `Recommendations`, and `Channel Analysis` |
| `V3` | `Channel Analysis`, `Recommendations`, `Ytuber`, `Outlier Finder`, `Deployment` |
| `V4` | `Channel Analysis`, `Channel Insights`, `Recommendations`, `Outlier Finder`, `Ytuber`, `Tools`, `Deployment`, plus sidebar `Assistant` |
| `V5` | `Channel Analysis`, `Channel Insights`, `Thumbnails`, `Outlier Finder`, `Ytuber`, `Tools`, `Deployment` |

## Deployment Summary By Version

| Version | Primary Delivery Idea | Deployment Complexity | Why It Changed |
| --- | --- | --- | --- |
| `V1` | prove the dashboard concept | low | needed broader creator workflows |
| `V2` | broaden the suite | medium | feature breadth grew faster than documentation clarity |
| `V3` | make the app structure understandable | medium | prepared the ground for deeper intelligence features |
| `V4` | add tracked-channel depth and owner overlays | high | richest feature set, but also the heaviest deployment and secrets burden |
| `V5` | keep high-value workflows while reducing deploy risk | medium | removed Assistant and OAuth, kept the AI suite and BERTopic beta optional |

## Secrets And Config Evolution

| Version | Core Secrets / Env | Why They Existed |
| --- | --- | --- |
| `V1` | `YOUTUBE_API_KEY`, later deployable `GEMINI_API_KEY`, optional `OPENAI_API_KEY` | public metadata plus the first dashboard and thumbnail-generation workflows |
| `V2` | `YOUTUBE_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, optional `NEWSAPI_KEY` | live creator workflows, AI generation, trend/news signals |
| `V3` | pooled or single-key `YOUTUBE`, `GEMINI`, `OPENAI` formats | stronger key rotation and Streamlit deploy support |
| `V4` | V3 keys plus `GOOGLE_OAUTH_*` and `MODEL_ARTIFACTS_*` | owner analytics overlays and optional BERTopic beta runtime |
| `V5` | pooled or single-key `YOUTUBE`, `GEMINI`, `OPENAI`, plus `MODEL_ARTIFACTS_*` | public-only runtime with optional BERTopic beta, no OAuth path |

## Current V5 Deployment Flow

```mermaid
flowchart TD
    A["GitHub repo branch<br/>youtube-ip-v5"] --> B["Streamlit app configuration"]
    B --> C["streamlit_app.py"]
    C --> D["dashboard/app.py"]
    D --> E["Sidebar navigation"]
    E --> F["Page views"]
    G["Streamlit secrets"] --> H["Runtime services"]
    H --> F
    F --> I["Charts, tables, cards, prompts, downloads"]
```

## Live API And Secrets Flow

```mermaid
flowchart LR
    A["Streamlit secrets"] --> B["YOUTUBE_API_KEYS or YOUTUBE_API_KEY"]
    A --> C["GEMINI_API_KEYS / OPENAI_API_KEYS"]
    A --> D["MODEL_ARTIFACTS_*"]

    B --> E["src/utils/api_keys.py"]
    C --> E
    E --> F["YouTube Data API / Gemini / OpenAI"]
    F --> G["Service-layer transforms"]
    G --> H["Rendered Streamlit UI"]
```

In V5, `Channel Insights` is public-only. It does not use Google OAuth and does not merge owner-only YouTube Analytics metrics.

## Model-Backed Topic Deployment

The deploy-time settings only enable the beta path. The normal `Channel Insights` workflow still starts from public channel data and branches inside `_apply_requested_topic_mode(...)`.

### Channel Insights Topic Pipeline

```mermaid
flowchart TD
    A["Channel Insights UI"] --> B["refresh_channel_insights(...)"]
    B --> C["load_public_channel_workspace(...)"]
    C --> D["ensure_public_channel_frame(...)"]
    D --> E["add_channel_video_features(...)"]
    E --> F["_apply_requested_topic_mode(...)"]
    F --> G["assign_topic_labels(...)"]
    F --> H["apply_optional_topic_model(...)"]
    H -->|failure| G
    G --> I["heuristic primary_topic + topic_labels + topic_source"]
    H --> J["model_topic_id + model_topic_label_raw + model_topic_label"]
    J --> K["model-backed primary_topic + topic_labels + topic_source"]
    I --> L["_score_videos(...)"]
    K --> L
    L --> M["topic / duration / title / timing metrics"]
    M --> N["outliers + recommendations + summary payload"]
    N --> O["store_channel_snapshot(...)"]
    O --> P["Overview / Topic Trends / Formats / Outliers / Next Topics / History"]
```

### Heuristic Vs Beta Topic Modes

| Mode | What It Uses | When It Runs | Failure Behavior |
| --- | --- | --- | --- |
| `Heuristic Topics` | title, tag, and description token rules | default and always available | no external dependency |
| `Model-Backed Topics (Beta)` | BERTopic semantic inference | only when explicitly requested and configured | falls back to heuristics |

### BERTopic Artifact Flow

```mermaid
flowchart LR
    A["MODEL_ARTIFACTS_ENABLED"] --> B["beta mode can be requested"]
    C["MODEL_ARTIFACTS_MANIFEST_URL"] --> D["model_artifact_service.py"]
    D --> E["Manifest JSON"]
    E --> F["artifact_url + sha256 + bundle_version"]
    F --> G["download only on explicit beta refresh"]
    G --> H["outputs/models/runtime/<bundle_version>/"]
    H --> I["topic_model_runtime.py"]
    I --> J["Channel Insights service path"]
    D --> K["fallback to heuristics if artifact is missing or invalid"]
```

## Recommended Current V5 Streamlit Secrets

```toml
YOUTUBE_API_KEYS = ["your_youtube_key_1", "your_youtube_key_2"]
GEMINI_API_KEYS = ["your_gemini_key_1", "your_gemini_key_2"]
OPENAI_API_KEYS = ["your_openai_key_1", "your_openai_key_2"]

MODEL_ARTIFACTS_ENABLED = true
MODEL_ARTIFACTS_MANIFEST_URL = "https://raw.githubusercontent.com/royayushkr/Youtube-IP-V5/main/data/model_manifests/bertopic_manifest_2026.03.27.json"
MODEL_ARTIFACTS_CACHE_DIR = "outputs/models/runtime"
MODEL_ARTIFACTS_DOWNLOAD_TIMEOUT_SECONDS = 300
MODEL_ARTIFACTS_MAX_SIZE_MB = 512
```

## What V5 Keeps And What It Leaves Behind

| Category | Kept In V5 | Left In Earlier Versions |
| --- | --- | --- |
| Benchmarking | dataset analytics, charts, rankings | none; this remains a through-line |
| Creator workspace | `Ytuber`, `Tools`, `Deployment`, `Thumbnails` | Assistant |
| Channel intelligence | public tracked-channel snapshots | owner-only OAuth branch |
| Modeling | heuristic topics and optional BERTopic beta | none removed here, only guarded more tightly |
| Deployment posture | Streamlit-first | heavier V4 auth and assistant overhead |
