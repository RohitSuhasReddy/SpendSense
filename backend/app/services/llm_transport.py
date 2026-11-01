from __future__ import annotations

import json
import re

import httpx

from app.config import settings
from app.models import CATEGORIES

_LAST_LLM_ERROR = ""
_AMOUNT_RE = re.compile(r"amount=₹([0-9,]+(?:\.[0-9]{1,2})?)", re.I)
_TIME_RE = re.compile(r"time=(\d{2}):(\d{2})", re.I)


def get_last_llm_error() -> str:
    return _LAST_LLM_ERROR


def _set_last_error(message: str) -> None:
    global _LAST_LLM_ERROR
    _LAST_LLM_ERROR = (message or "")[:500]
    if _LAST_LLM_ERROR:
        print(f"[SpendSense LLM] {_LAST_LLM_ERROR}")


def _looks_like_person_name(merchant: str) -> bool:
    lowered = merchant.lower().strip()
    commercial_terms = (
        "shop", "store", "foods", "food", "hotel", "cafe", "restaurant", "pvt", "ltd",
        "pharmacy", "medical", "mart", "market", "salon", "barber", "services", "enterprises",
        "technologies", "digital", "retail", "bakery", "supermarket", "agency", "travels",
    )
    if any(term in lowered for term in commercial_terms):
        return False
    words = re.findall(r"[A-Za-z]+", merchant)
    return 1 <= len(words) <= 4 and not re.search(r"\d", merchant)


def _personal_upi_guess(merchant: str, description: str) -> str | None:
    lowered = description.lower()
    if "source=upi" not in lowered or "paid to" not in lowered:
        return None
    if not _looks_like_person_name(merchant):
        return None

    amount_match = _AMOUNT_RE.search(description)
    if not amount_match:
        return None
    try:
        amount = float(amount_match.group(1).replace(",", ""))
    except ValueError:
        return None

    time_match = _TIME_RE.search(description)
    minutes = None
    if time_match:
        minutes = int(time_match.group(1)) * 60 + int(time_match.group(2))

    lunch = minutes is not None and 11 * 60 + 30 <= minutes <= 14 * 60 + 30
    dinner = minutes is not None and 18 * 60 + 30 <= minutes <= 22 * 60 + 30

    # COD food deliveries often appear only as the rider's personal UPI name.
    if 120 <= amount <= 1000 and (lunch or dinner):
        return "Food & Dining"

    # User's dominant ambiguous-person UPI pattern is local cab/auto/driver payments.
    if amount <= 800:
        return "Travel"

    return None


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
    """Use Gemini first, then a conservative personal-UPI travel/food fallback."""
    if not pending:
        return {}

    from app.services import classifier

    result = classifier._classify_llm_chunk(pending)
    for key, (merchant, description) in pending:
        if result.get(key) in {None, "Others"}:
            guess = _personal_upi_guess(merchant, description)
            if guess:
                result[key] = guess
    return result


def _contextual_batch_prompt(rows: list[dict[str, str]]) -> str:
    categories = ", ".join(CATEGORIES)
    return (
        "Classify Indian personal-finance transactions. Context can include merchant/payee, amount, "
        "payment source and time. Use real-world merchant knowledge and parent-company knowledge. "
        "Travel includes cab, taxi, auto-rickshaw, driver and ride payments. Food & Dining includes "
        "restaurants and food-delivery/COD rider payments when the context supports it. Salon & Personal Care "
        "includes salons, barbers, haircuts, grooming and beauty services. For a plain person's name with weak "
        "evidence, use amount/time only as weak clues and do not invent a merchant identity. "
        f"Choose exactly one category for every row from: {categories}. "
        "Return ONLY a JSON array. Each element must be "
        '{"id":"the exact short input id","category":"one allowed category"}. '
        f"Rows: {json.dumps(rows, ensure_ascii=False)}"
    )


def _install_category_rules() -> None:
    from app.services import classifier

    normalized_rules: list[tuple[str, tuple[str, ...]]] = []
    for category, keywords in classifier.RULES:
        if category == "Travel & Transport":
            category = "Travel"
        normalized_rules.append((category, keywords))

    normalized_rules.insert(
        0,
        (
            "Salon & Personal Care",
            (
                "salon",
                "saloon",
                "barber",
                "haircut",
                "hair cut",
                "grooming",
                "beauty parlour",
                "beauty parlor",
                "naturals salon",
                "green trends",
                "jawed habib",
                "toni and guy",
                "toni & guy",
                "lakme salon",
                "bounce salon",
            ),
        ),
    )
    normalized_rules.insert(
        1,
        (
            "Travel",
            (
                "namma yatri",
                "nammayatri",
                "cab driver",
                "auto driver",
                "taxi driver",
                "driver payment",
                "auto rickshaw",
                "rickshaw",
                "taxi",
                "cab",
                "rapido captain",
            ),
        ),
    )
    classifier.RULES = normalized_rules


def _cache_key_v3(merchant: str, description: str) -> str:
    return f"v3|{merchant}|{description[:80]}"[:255]


def install_resilient_llm_transport() -> None:
    """Install SpendSense category rules and the fast Gemini transport."""
    from app.services import classifier

    _install_category_rules()
    classifier._batch_prompt = _contextual_batch_prompt
    classifier._cache_key = _cache_key_v3
    classifier._gemini_classify_batch = _gemini_classify_batch_fast
    classifier._from_llm_batch = _from_llm_batch_fast
