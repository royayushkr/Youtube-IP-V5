from dataclasses import dataclass

from src.services import transcript_service


@dataclass
class _FakeTranscript:
    language: str
    language_code: str
    is_generated: bool
    is_translatable: bool


@dataclass
class _FakeSnippet:
    text: str
    start: float = 0.0
    duration: float = 1.0


class _FakeFetchedTranscript:
    def __init__(self) -> None:
        self.language = "English"
        self.language_code = "en"
        self.is_generated = False
        self._snippets = [_FakeSnippet("First line"), _FakeSnippet("Second line")]

    def __iter__(self):
        return iter(self._snippets)


class _FakeApi:
    def list(self, video_id: str):
        return [
            _FakeTranscript("English", "en", False, True),
            _FakeTranscript("Spanish", "es", True, True),
        ]

    def fetch(self, video_id: str, languages, preserve_formatting: bool = False):
        assert list(languages)[0] in {"en", "es"}
        return _FakeFetchedTranscript()


def test_list_transcript_options_normalizes_api_output(monkeypatch) -> None:
    transcript_service.list_transcript_options.clear()
    monkeypatch.setattr(transcript_service, "_api", lambda: _FakeApi())

    options = transcript_service.list_transcript_options("video-1")

    assert [option.language_code for option in options] == ["en", "es"]
    assert options[0].language_label == "English"
    assert options[1].is_generated is True


def test_prepare_transcript_download_writes_text_file(monkeypatch) -> None:
    transcript_service.fetch_transcript_text.clear()
    monkeypatch.setattr(
        transcript_service,
        "fetch_transcript_text",
        lambda video_id, language_code, prefer_generated=None, prefer_any=False: "Language: English (en)\nType: Manual\n\nFirst line\nSecond line",
    )

    artifact = transcript_service.prepare_transcript_download(
        "video-1",
        "en",
        video_title="Example Video",
    )

    assert artifact.file_name.endswith(".txt")
    assert "Example Video-en.txt" == artifact.file_name
    with open(artifact.file_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    assert "First line" in content
