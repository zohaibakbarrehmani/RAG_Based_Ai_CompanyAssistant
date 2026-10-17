from app.services.embeddings import _call_with_rate_limit_retry


def test_embedding_retry_uses_exponential_backoff() -> None:
    class RateLimitError(Exception):
        code = 429

    attempts = 0
    delays: list[float] = []

    def request() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError("rate limited")
        return "completed"

    result = _call_with_rate_limit_retry(request, sleep=delays.append)

    assert result == "completed"
    assert attempts == 2
    assert delays == [1]
