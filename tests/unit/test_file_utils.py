from pathlib import Path

from src.utils.file_utils import cleanup_temp_dirs, sanitize_filename, safe_temp_dir


def test_sanitize_filename_keeps_readable_ascii() -> None:
    assert sanitize_filename("My / Fancy: Video? Title!!!") == "My Fancy Video Title"
    assert sanitize_filename("    ") == "download"


def test_safe_temp_dir_and_cleanup_remove_directory() -> None:
    temp_dir = safe_temp_dir("tools-test-")
    assert temp_dir.exists()
    file_path = Path(temp_dir) / "sample.txt"
    file_path.write_text("hello", encoding="utf-8")

    cleanup_temp_dirs([str(temp_dir)])

    assert not temp_dir.exists()
