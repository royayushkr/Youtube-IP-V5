from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

import requests

from src.utils.api_keys import get_provider_key_count, run_with_provider_keys


@dataclass(frozen=True)
class ThemeRecommendation:
    theme: str
    rationale: str
    action: str


@dataclass(frozen=True)
class IdeaSuggestion:
    title: str
    why_now: str


@dataclass(frozen=True)
class ChannelIdeaBundle:
    summary: str
    double_down: tuple[ThemeRecommendation, ...]
    avoid: tuple[ThemeRecommendation, ...]
    test_next: tuple[ThemeRecommendation, ...]
    video_ideas: tuple[IdeaSuggestion, ...]
    ai_overlay: str = ""


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _heuristic_theme_rows(topic_metrics: Sequence[Mapping[str, Any]]) -> tuple[List[ThemeRecommendation], List[ThemeRecommendation], List[ThemeRecommendation]]:
    sorted_topics = list(topic_metrics)
    if not sorted_topics:
        fallback = ThemeRecommendation("Build A Baseline First", "You need more recent uploads before theme scoring becomes stable.", "Refresh again after several uploads to compare reliable patterns.")
        return [fallback], [], [fallback]

    winners: List[ThemeRecommendation] = []
    weak: List[ThemeRecommendation] = []
    test_next: List[ThemeRecommendation] = []

    for row in sorted_topics[:3]:
        winners.append(
            ThemeRecommendation(
                theme=_safe_text(row.get("topic_label"), "Winning Theme"),
                rationale=f"Median views/day is {_safe_text(round(row.get('median_views_per_day', 0), 1))} with {int(row.get('video_count', 0) or 0)} tracked videos.",
                action="Double down with adjacent angles, stronger hooks, and clearer packaging around this theme.",
            )
        )

    for row in sorted(sorted_topics, key=lambda item: (item.get("median_views_per_day", 0), item.get("trend_score", 0)))[:2]:
        weak.append(
            ThemeRecommendation(
                theme=_safe_text(row.get("topic_label"), "Weak Theme"),
                rationale=f"This cluster is lagging with lower median views/day and only {int(row.get('outlier_count', 0) or 0)} breakout videos.",
                action="Reduce volume here unless you can repackage it with a stronger angle or format.",
            )
        )

    for row in sorted(sorted_topics, key=lambda item: (item.get("trend_score", 0), item.get("recent_video_count", 0)), reverse=True)[:3]:
        test_next.append(
            ThemeRecommendation(
                theme=_safe_text(row.get("topic_label"), "Next Theme"),
                rationale=f"Trend score is {row.get('trend_score', 0):.2f} with {int(row.get('recent_video_count', 0) or 0)} recent uploads.",
                action="Test a fresh angle here before the topic gets saturated on your channel.",
            )
        )

    return winners, weak, test_next


def _heuristic_ideas(channel_title: str, test_next: Sequence[ThemeRecommendation]) -> List[IdeaSuggestion]:
    ideas: List[IdeaSuggestion] = []
    for item in list(test_next)[:4]:
        ideas.append(
            IdeaSuggestion(
                title=f"{item.theme}: What Your Audience Still Hasn't Seen Yet",
                why_now=f"{channel_title} has signal that {item.theme.lower()} is rising, but the next angle should feel more specific and outcome-focused.",
            )
        )
    return ideas


def build_grounded_idea_bundle(
    channel_title: str,
    topic_metrics: Sequence[Mapping[str, Any]],
    outlier_rows: Sequence[Mapping[str, Any]],
    underperformer_rows: Sequence[Mapping[str, Any]],
) -> ChannelIdeaBundle:
    winners, weak, test_next = _heuristic_theme_rows(topic_metrics)
    ideas = _heuristic_ideas(channel_title, test_next)
    summary = (
        f"{channel_title} should lean into the strongest theme clusters, trim low-signal topics, and use the most recent breakout topics as the source for the next wave of ideas."
        if topic_metrics
        else f"{channel_title} needs a larger recent sample before the recommendation engine becomes highly confident."
    )
    return ChannelIdeaBundle(
        summary=summary,
        double_down=tuple(winners),
        avoid=tuple(weak),
        test_next=tuple(test_next),
        video_ideas=tuple(ideas),
    )


def _gemini_generate_text(api_key: str, model: str, prompt: str) -> str:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    response = requests.post(
        endpoint,
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=90,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini API error ({response.status_code}): {response.text[:400]}")
    body = response.json()
    return (
        body.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )


def _openai_generate_text(api_key: str, model: str, prompt: str) -> str:
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a concise YouTube strategy assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        },
        timeout=90,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI API error ({response.status_code}): {response.text[:400]}")
    body = response.json()
    return body.get("choices", [{}])[0].get("message", {}).get("content", "")


def maybe_generate_ai_overlay(
    channel_title: str,
    summary_payload: Mapping[str, Any],
    topic_metrics: Sequence[Mapping[str, Any]],
    provider_preference: str = "gemini",
) -> str:
    available = [provider for provider in ("gemini", "openai") if get_provider_key_count(provider) > 0]
    if not available:
        return ""

    provider = provider_preference if provider_preference in available else available[0]
    model = "gemini-2.5-flash" if provider == "gemini" else "gpt-4o-mini"
    prompt = (
        "You are helping a YouTube creator decide what to make next based on public channel performance data. "
        "Give a concise markdown answer with three short sections: Double Down, Stop Doing, Test Next. "
        "Use only the analytics below.\n\n"
        f"Channel: {channel_title}\n"
        f"Summary: {json.dumps(dict(summary_payload), ensure_ascii=True)}\n"
        f"Topic Metrics: {json.dumps(list(topic_metrics)[:8], ensure_ascii=True)}"
    )
    if provider == "gemini":
        return run_with_provider_keys("gemini", lambda key: _gemini_generate_text(key, model, prompt))
    return run_with_provider_keys("openai", lambda key: _openai_generate_text(key, model, prompt))

