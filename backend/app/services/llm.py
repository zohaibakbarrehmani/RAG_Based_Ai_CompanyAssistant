from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — direct, concise, policy-expert persona
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are a corporate policy expert assistant. Your sole job is to answer employee \
questions using ONLY the company document context provided below.

Rules you MUST follow:
1. Open with a direct, one-sentence answer to the question.
2. Follow up with specific details in concise bullet points (numbers, dates, \
conditions, procedures).
3. Never use filler phrases like "Based on the company documents…", \
"According to the provided context…", or "As per…". Just answer directly.
4. If the answer requires steps or a process, use a numbered list.
5. If the context does NOT contain enough information to answer, reply with \
exactly: "I couldn't find this in the company documents."
6. Do NOT invent, infer, or assume anything not explicitly stated in the context.
7. Keep the answer well-structured Markdown — use **bold** for key terms/values.

Output format — return a JSON object with exactly two fields:
  "answer": "<your Markdown answer>",
  "used_chunk_ids": ["C1", "C2", ...]  — list only context IDs you directly cited.\
"""

FOLLOW_UP_CUES = (
    "what about",
    "how about",
    "and ",
    "what if",
    "does that",
    "is that",
    "those",
    "they",
    "it ",
    "there ",
    "can i",
    "can we",
    "is there",
    "are there",
    "how long",
    "how many",
    "when do",
    "when can",
)

# Model priority lists — fastest first, overloaded/heaviest as last resort
_ANSWER_MODELS = [
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.8-flash",
]

_FAST_MODELS = [
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.8-flash",
]


def _client() -> genai.Client:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY must be configured before calling Gemini.")
    return genai.Client(api_key=settings.gemini_api_key)


def _is_overload_error(exc: Exception) -> bool:
    """Return True for transient 503/429 errors worth retrying."""
    msg = str(exc)
    return "503" in msg or "UNAVAILABLE" in msg or "429" in msg or "rate" in msg.lower()


def _generate_with_retry(
    client: genai.Client,
    model: str,
    contents: str,
    config: types.GenerateContentConfig,
    max_retries: int = 2,
) -> Any:
    """Call generate_content with exponential back-off on transient errors."""
    for attempt in range(max_retries + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            if _is_overload_error(exc) and attempt < max_retries:
                wait = 1.5 ** attempt
                logger.warning(
                    "Model %s transient error (attempt %d/%d), retrying in %.1fs: %s",
                    model, attempt + 1, max_retries + 1, wait, exc,
                )
                time.sleep(wait)
            else:
                raise


def is_follow_up(question: str, history: Sequence[dict[str, str]]) -> bool:
    if not history:
        return False
    normalized = question.strip().lower()
    return (
        len(normalized.split()) <= 8
        or any(normalized.startswith(cue) for cue in FOLLOW_UP_CUES)
    )


def rewrite_follow_up(
    question: str,
    history: Sequence[dict[str, str]],
) -> str:
    if not settings.gemini_fast_model:
        return question

    recent_history = list(history[-4:])
    history_text = "\n".join(
        f"{message['role']}: {message['content']}" for message in recent_history
    )

    # Build model list: configured fast model first, then fallbacks
    models_to_try = list(
        dict.fromkeys([settings.gemini_fast_model] + _FAST_MODELS)
    )

    for model_name in models_to_try:
        if not model_name:
            continue
        try:
            client = _client()
            response = _generate_with_retry(
                client,
                model_name,
                (
                    "Rewrite the follow-up below as a single, self-contained question "
                    "about company policies or internal documentation. "
                    "Return only the rewritten question, no explanation.\n\n"
                    f"Conversation:\n{history_text}\n\n"
                    f"Follow-up: {question}"
                ),
                types.GenerateContentConfig(
                    max_output_tokens=80,
                    temperature=0.0,
                ),
            )
            text = getattr(response, "text", "")
            if text and text.strip():
                return text.strip().strip('"\'')
        except Exception as exc:
            logger.warning("Rewrite with model %s failed: %s", model_name, exc)

    return question


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    # 1. Direct JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Markdown fenced JSON ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. First '{' to last '}'
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            data = json.loads(text[first_brace : last_brace + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def _build_prompt(question: str, contexts: Sequence[tuple[str, str]]) -> str:
    context_text = "\n\n".join(
        f"[{label}]\n{text}" for label, text in contexts
    )
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "---\n"
        f"QUESTION: {question}\n\n"
        f"CONTEXT:\n{context_text}\n"
        "---\n\n"
        'Return ONLY valid JSON: {"answer": "...", "used_chunk_ids": ["C1"]}'
    )


def generate_answer(
    question: str,
    contexts: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    if not contexts:
        return {
            "answer": "I couldn't find this in the company documents.",
            "used_chunk_ids": [],
        }

    prompt = _build_prompt(question, contexts)
    valid_labels = {label for label, _ in contexts}

    # Build model list: configured answer model first, then fallbacks
    models_to_try = list(
        dict.fromkeys([settings.gemini_answer_model] + _ANSWER_MODELS)
    )

    client = _client()

    for model_name in models_to_try:
        if not model_name:
            continue
        try:
            response = _generate_with_retry(
                client,
                model_name,
                prompt,
                types.GenerateContentConfig(
                    max_output_tokens=settings.max_output_tokens or 900,
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            raw_text = getattr(response, "text", "")
            if not raw_text:
                logger.warning("Empty response from model %s", model_name)
                continue

            payload = _extract_json_payload(raw_text)
            if payload and "answer" in payload:
                # Unwrap nested answer dicts
                ans_val = payload["answer"]
                while isinstance(ans_val, dict) and "answer" in ans_val:
                    ans_val = ans_val["answer"]
                if isinstance(ans_val, str) and ans_val.strip().startswith("{") and "answer" in ans_val:
                    nested_p = _extract_json_payload(ans_val)
                    if nested_p and "answer" in nested_p:
                        ans_val = nested_p["answer"]

                answer = str(ans_val).strip()
                raw_chunks = payload.get("used_chunk_ids", [])
                if isinstance(raw_chunks, list):
                    used_chunks = [str(c) for c in raw_chunks if str(c) in valid_labels]
                else:
                    used_chunks = list(valid_labels)

                logger.info(
                    "Answer generated by %s | chunks cited: %s",
                    model_name,
                    used_chunks,
                )

                # If model cited nothing but didn't say not-found, cite top chunks
                not_found = "couldn't find" in answer.lower()
                if not used_chunks and not not_found:
                    used_chunks = sorted(valid_labels)[:2]

                return {
                    "answer": answer,
                    "used_chunk_ids": used_chunks,
                }

            # Fallback: plain text returned (no JSON wrapper)
            if raw_text.strip():
                clean_ans = raw_text.strip()
                logger.warning("Model %s returned plain text instead of JSON", model_name)
                return {
                    "answer": clean_ans,
                    "used_chunk_ids": list(valid_labels) if "couldn't find" not in clean_ans.lower() else [],
                }

        except Exception as exc:
            logger.warning("Generation with model %s failed: %s", model_name, exc)

    # All models exhausted — return top snippet as fallback
    logger.error("All answer models failed; returning raw snippet fallback.")
    top_snippet = contexts[0][1][:600]
    return {
        "answer": f"{top_snippet}",
        "used_chunk_ids": [contexts[0][0]],
    }
