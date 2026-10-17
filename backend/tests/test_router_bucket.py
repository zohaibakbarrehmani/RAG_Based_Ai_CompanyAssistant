from types import SimpleNamespace

from app.config import settings
from app.services import router_bucket


def test_keyword_rules_choose_bucket_without_gemini(monkeypatch) -> None:
    def unexpected_client(**_kwargs):
        raise AssertionError("Keyword routing should not call Gemini.")

    monkeypatch.setattr(router_bucket.genai, "Client", unexpected_client)

    route = router_bucket.route_bucket("How many annual leaves do employees get?")

    assert route.buckets == ["hr"]
    assert route.source == "keyword"


def test_uncertain_question_uses_fast_model_with_output_cap(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="product")

    class FakeClient:
        def __init__(self, **_kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(router_bucket.genai, "Client", FakeClient)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_fast_model", "configured-fast-model")

    route = router_bucket.route_bucket("What does this document say?")

    assert route.buckets == ["product"]
    assert route.source == "gemini"
    assert captured["model"] == "configured-fast-model"
    assert captured["config"].max_output_tokens == 10
