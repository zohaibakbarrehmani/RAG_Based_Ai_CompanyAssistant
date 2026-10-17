from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from google import genai
from google.genai import types

from app.config import settings
from app.services.embeddings import _call_with_rate_limit_retry

logger = logging.getLogger(__name__)
BUCKETS = ("hr", "engineering", "product", "sop", "faq", "general")
KEYWORD_RULES = {
    "hr": {
        "leave", "leaves", "salary", "holiday", "holidays", "payroll", "benefit", "benefits",
        "employee", "employees", "vacation", "vacations", "maternity", "paternity",
        "insurance", "bonus", "compensation", "resignation", "notice", "attendance", "probation",
    },
    "engineering": {
        "deploy", "deployment", "pipeline", "api", "code", "database",
        "server", "architecture", "infrastructure", "build", "bug", "git", "ci", "cd",
    },
    "product": {
        "refund", "pricing", "price", "plan", "subscription", "feature",
        "customer", "product", "billing", "tier",
    },
    "sop": {"procedure", "process", "workflow", "standard", "checklist", "guideline", "protocol"},
    "faq": {"faq", "frequently", "question", "answer", "help"},
}


@dataclass(frozen=True)
class BucketRoute:
    buckets: list[str]
    source: str


def _rule_route(question: str) -> BucketRoute | None:
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    scores = {
        bucket: len(words.intersection(keywords))
        for bucket, keywords in KEYWORD_RULES.items()
    }
    highest_score = max(scores.values(), default=0)
    if highest_score == 0:
        return None

    winners = [
        bucket for bucket, score in scores.items() if score == highest_score
    ]
    if len(winners) == 1:
        return BucketRoute(buckets=winners, source="keyword")
    return None


def _parse_bucket(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower().strip("`'\".,:; ")
    return cleaned if cleaned in BUCKETS else None


def route_bucket(question: str) -> BucketRoute:
    if not question.strip():
        raise ValueError("Question must not be empty.")

    keyword_route = _rule_route(question)
    if keyword_route is not None:
        return keyword_route

    if not settings.gemini_api_key or not settings.gemini_fast_model:
        return BucketRoute(buckets=list(BUCKETS), source="fallback_all")

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = _call_with_rate_limit_retry(
            lambda: client.models.generate_content(
                model=settings.gemini_fast_model,
                contents=(
                    "Choose exactly one document category for this question: "
                    "hr, engineering, product, sop, faq, or general. "
                    f"Question: {question}"
                ),
                config=types.GenerateContentConfig(
                    max_output_tokens=10,
                    temperature=0,
                ),
            )
        )
        usage = getattr(response, "usage_metadata", None)
        logger.info(
            "Gemini bucket routing token usage: prompt=%s candidates=%s total=%s.",
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
            getattr(usage, "total_token_count", None),
        )
        bucket = _parse_bucket(response.text)
        if bucket is not None:
            return BucketRoute(buckets=[bucket], source="gemini")
    except Exception as exc:
        logger.warning("Bucket classifier error (%s); falling back to all buckets.", exc)

    return BucketRoute(buckets=list(BUCKETS), source="fallback_all")
