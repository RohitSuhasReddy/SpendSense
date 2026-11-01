from __future__ import annotations

import time

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


def _gemini_classify_batch_resilient(
    pending: list[tuple[str, tuple[str, str]]],
) -> dict[str, str]:
    """Gemini classifier with lower thinking, longer timeouts and transient retries."""
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
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
        "X-Server-Timeout": "110",
    }

    # Try direct networking first. If a machine-level proxy is interfering,
    # trust_env=False avoids it; the second pass permits env proxy settings.
    last_error = ""
    for trust_env in (False, True):
        for attempt in range(2):
            try:
                timeout = httpx.Timeout(120.0, connect=15.0)
                with httpx.Client(timeout=timeout, trust_env=trust_env) as client:
                    response = client.post(url, headers=headers, json=payload)

                if response.status_code in {408, 429, 500, 502, 503, 504}:
                    last_error = f"Gemini HTTP {response.status_code}: {response.text[:300]}"
                    if attempt == 0:
                        time.sleep(1.5)
                        continue

                response.raise_for_status()
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = classifier._parse_batch_categories(text, id_to_key)
                if parsed:
                    _set_last_error("")
                    return parsed
                last_error = f"Gemini returned no usable categories. Raw response: {text[:300]}"
                break
            except httpx.ReadTimeout:
                last_error = (
                    f"Gemini timed out after 120s (trust_env={trust_env}, attempt={attempt + 1})."
                )
            except httpx.ConnectError as exc:
                last_error = f"Gemini connection error: {exc}"
                break
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:300] if exc.response is not None else ""
                last_error = f"Gemini HTTP error: {exc}; {body}"
                # 4xx errors other than 408/429 are not transient.
                if exc.response is not None and 400 <= exc.response.status_code < 500:
                    _set_last_error(last_error)
                    return {}
                break
            except Exception as exc:
                last_error = f"Gemini error: {type(exc).__name__}: {exc}"
                break

    _set_last_error(last_error or "Gemini request failed without a response.")
    return {}


def _from_llm_batch_resilient(
    pending: list[tuple[str, tuple[str, str]]],
) -> dict[str, str]:
    """Use smaller chunks so simple merchant classification stays fast."""
    if not pending:
        return {}

    from app.services import classifier

    results: dict[str, str] = {}
    for start in range(0, len(pending), 8):
        chunk = pending[start : start + 8]
        results.update(classifier._classify_llm_chunk(chunk))
    return results


def install_resilient_llm_transport() -> None:
    """Patch the classifier's internal transport without changing public APIs."""
    from app.services import classifier

    classifier._gemini_classify_batch = _gemini_classify_batch_resilient
    classifier._from_llm_batch = _from_llm_batch_resilient
