from __future__ import annotations

import mimetypes
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path


_INVALID_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_filename(text: str, fallback: str = "download") -> str:
    """Return a filesystem-safe filename stem.

    The goal is not perfect transliteration; it is to create a stable,
    readable filename that behaves well across common filesystems.
    """
    normalized = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    normalized = _INVALID_FILENAME_CHARS.sub("", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip(" ._-")
    if not normalized:
        normalized = fallback
    return normalized[:160]


def safe_temp_dir(prefix: str) -> Path:
    """Create and return a dedicated temporary directory."""
    return Path(tempfile.mkdtemp(prefix=prefix))


def cleanup_temp_dirs(paths: list[str]) -> None:
    """Best-effort cleanup for temporary directories."""
    for path in paths:
        if not path:
            continue
        target = Path(path)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)


def guess_mime_type(path: str | Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"
