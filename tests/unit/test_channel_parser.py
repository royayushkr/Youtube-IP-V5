from src.utils.channel_parser import extract_channel_query, normalize_channel_input


def test_extract_channel_query_from_handle_url() -> None:
    assert extract_channel_query("https://www.youtube.com/@veritasium") == "@veritasium"


def test_extract_channel_query_from_channel_id_url() -> None:
    channel_id = "UC12345678901234567890"
    assert extract_channel_query(f"https://www.youtube.com/channel/{channel_id}") == channel_id


def test_normalize_channel_input_for_handle() -> None:
    parsed = normalize_channel_input("@veritasium")
    assert parsed.input_kind == "handle"
    assert parsed.lookup_value == "@veritasium"
    assert parsed.canonical_url.endswith("/@veritasium")


def test_normalize_channel_input_for_channel_id() -> None:
    channel_id = "UC12345678901234567890"
    parsed = normalize_channel_input(channel_id)
    assert parsed.input_kind == "channel_id"
    assert parsed.channel_id == channel_id
