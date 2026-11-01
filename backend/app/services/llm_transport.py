from __future__ import annotations

import httpx

from app.config import settings

_LAST_LLM_ERROR = ""


def get_last_llm_error() -> str:
    return _LAST_LLM_ERROR


def _set_last_error(message: str) -> None:
    global _LAST_LLM_ERROR
    _LAST_LLM_ERROR = (message or "")[:500]
    if _LAST_LLM_ERROR:
        print(f"[SpendSense LLM] {_LAST_LLM_ERROR}")


def _gemini_classify_batch_fast(
    pending: list[tuple[str, tuple[str, str]]],
) -> dict[str, str]:
    """Fast Gemini classification for lightweight merchant categorization."""
    from app.services import classifier

    rows, id_to_key = classifier._batch_payload(pending)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": classifier._batch_prompt(rows)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }

    try:
        timeout = httpx.Timeout(20.0, connect=10.0)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = classifier._parse_batch_categories(text, id_to_key)
        if parsed:
            _set_last_error("")
            return parsed
        _set_last_error(f"Gemini returned no usable categories. Raw response: {text[:300]}")
        return {}
    except httpx.ReadTimeout:
        _set_last_error("Gemini timed out after 20 seconds. Classification was skipped for this run.")
    except httpx.ConnectError as exc:
        _set_last_error(f"Gemini connection error: {exc}")
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300] if exc.response is not None else ""
        _set_last_error(f"Gemini HTTP error: {exc}; {body}")
    except Exception as exc:
        _set_last_error(f"Gemini error: {type(exc).__name__}: {exc}")
    return {}


def _from_llm_batch_fast(
    pending: list[tuple[str, tuple[str, str]]],
) -> dict[str, str]:
    """Classify all unresolved merchants in one compact request for low latency."""
    if not pending:
        return {}

    from app.services import classifier

    return classifier._classify_llm_chunk(pending)


def install_resilient_llm_transport() -> None:
    """Install the fast Gemini transport without changing the classifier's public API."""
    from app.services import classifier

    classifier._gemini_classify_batch = _gemini_classify_batch_fast
    classifier._from_llm_batch = _from_llm_batch_fast
