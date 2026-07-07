from src.llm.openai_compatible_client import normalize_base_url


def test_normalize_base_url_accepts_mentor_style_base_url():
    assert normalize_base_url(base_url="http://10.67.43.7:12345/v1") == "http://10.67.43.7:12345/v1"


def test_normalize_base_url_accepts_legacy_chat_completions_endpoint():
    assert (
        normalize_base_url(endpoint="http://localhost:8850/v1/chat/completions")
        == "http://localhost:8850/v1"
    )
