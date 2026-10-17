from types import SimpleNamespace

from app.config import settings
from app.services import llm


def test_generate_answer_requests_json_and_filters_unknown_chunk_ids(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                text='{"answer":"Grounded answer.","used_chunk_ids":["C1","C99"]}',
                usage_metadata=SimpleNamespace(
                    prompt_token_count=20,
                    candidates_token_count=8,
                    total_token_count=28,
                ),
            )

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(llm, "_client", lambda: FakeClient())
    monkeypatch.setattr(settings, "gemini_answer_model", "configured-answer-model")
    monkeypatch.setattr(settings, "max_output_tokens", 77)

    result = llm.generate_answer("What is the policy?", [("C1", "The policy is documented.")])

    assert result == {"answer": "Grounded answer.", "used_chunk_ids": ["C1"]}
    assert captured["model"] == "configured-answer-model"
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].max_output_tokens == 77
    assert "[C1]" in captured["contents"]
