from __future__ import annotations

import re
from dataclasses import dataclass


YOUTUBE_HOST_PATTERN = re.compile(r"^(?:https?://)?(?:www\.)?(?:m\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedChannelInput:
    raw_input: str
    lookup_value: str
    canonical_url: str
    input_kind: str
    channel_id: str = ""
    handle: str = ""


def extract_channel_query(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if YOUTUBE_HOST_PATTERN.match(text):
        text = text.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        handle_match = re.search(r"/(@[A-Za-z0-9._-]+)$", text)
        if handle_match:
            return handle_match.group(1)

        channel_match = re.search(r"/channel/(UC[\w-]{20,})$", text)
        if channel_match:
            return channel_match.group(1)

        custom_match = re.search(r"/(?:c|user)/([^/]+)$", text)
        if custom_match:
            return custom_match.group(1)

        last_segment = text.rsplit("/", 1)[-1].strip()
        return last_segment

    token_match = re.search(r"(UC[\w-]{20,}|@[A-Za-z0-9._-]+)", text)
    if token_match:
        return token_match.group(1)
    return text


def normalize_channel_input(value: str) -> ParsedChannelInput:
    query = extract_channel_query(value)
    if not query:
        raise ValueError("Enter a channel URL, handle, name, or channel ID.")

    if query.startswith("UC") and len(query) >= 20:
        return ParsedChannelInput(
            raw_input=value,
            lookup_value=query,
            canonical_url=f"https://www.youtube.com/channel/{query}",
            input_kind="channel_id",
            channel_id=query,
        )

    if query.startswith("@"):
        return ParsedChannelInput(
            raw_input=value,
            lookup_value=query,
            canonical_url=f"https://www.youtube.com/{query}",
            input_kind="handle",
            handle=query,
        )

    return ParsedChannelInput(
        raw_input=value,
        lookup_value=query,
        canonical_url="",
        input_kind="query",
    )

