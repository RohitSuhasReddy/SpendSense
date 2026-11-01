from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Iterable

import httpx
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CATEGORIES, LlmCache, MerchantMapping, Transaction

# Deterministic rules handle merchants we can recognize confidently.
# LLM is reserved for genuinely unclear UPI names that remain.
RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Food & Dining",
        (
            "swiggy", "zomato", "razzomato", "eatclub", "dominos", "domino's",
            "jubilant foodworks", "jubilantfoodworks", "bundl technologies",
            "spices n chefs", "spices and chefs", "vendx", "vending machine",
            "hotel sri akshaya", "restaurant", "cafe", "coffee", "bakery",
            "pizza", "burger", "kfc", "mcdonald", "biryani", "eatsure",
            "box8", "faasos", "behrouz", "ovenstory", "mojo pizza", "starbucks",
        ),
    ),
    (
        "Groceries",
        (
            "amazon pay groceries", "groceries", "grocery", "blinkit", "zepto",
            "instamart", "bigbasket", "dmart", "jiomart", "supermarket",
            "super market", "vijetha", "kirana", "general stores", "food store",
            "meat shop", "chicken and fish", "chicken & fish", "reliance fresh",
            "more supermarket", "nature's basket",
        ),
    ),
    (
        "Travel & Transport",
        (
            "uber", "ola", "rapido", "irctc", "indigo", "air india", "vistara",
            "makemytrip", "goibibo", "redbus", "fastag", "metro", "petrol",
            "indian oil", "bpcl", "hpcl", "fuel", "parking",
        ),
    ),
    (
        "Amazon",
        (
            "amazon seller services", "amazon.in", "amazon seller", "asspl",
            "amzn", "amazon pay", "amazon",
        ),
    ),
    (
        "Shopping",
        (
            "flipkart", "myntra", "ajio", "meesho", "nykaa", "croma", "ikea",
            "decathlon", "tata cliq", "snapdeal", "shopclues", "lifestyle",
            "westside", "pantaloons", "reliance digital",
        ),
    ),
    (
        "Entertainment",
        (
            "netflix", "spotify", "prime video", "hotstar", "disney", "bookmyshow",
            "book my show", "pvr", "inox", "youtube premium", "gaana", "wynk",
            "apple music", "sonyliv", "zee5", "movie", "cinema", "fancode",
        ),
    ),
    (
        "Utilities & Bills",
        (
            "airtel", "jio", "vi ", "bsnl", "electricity", "bescom", "tata power",
            "act fibernet", "hathway", "gas bill", "broadband", "recharge",
            "billdesk", "bbps", "water bill", "municipal",
        ),
    ),
    (
        "Rent / Housing",
        ("rent", "landlord", "housing", "nobroker", "society maintenance", "maintenance"),
    ),
    (
        "Health",
        (
            "pharmacy", "apollo", "1mg", "pharmeasy", "netmeds", "hospital",
            "clinic", "practo", "medplus", "wellness",
        ),
    ),
    (
        "Education",
        ("udemy", "coursera", "unacademy", "byju", "school", "college", "tuition", "exam fee"),
    ),
    (
        "Credit Card / EMI",
        (
            "emi", "interest on emi", "fp emi", "credit card payment", "cc payment",
            "payment received", "infinity payment", "card payment", "min amount due",
            "total amount due", "outstanding", "finance charge",
        ),
    ),
    (
        "Transfers (Self / Family)",
        ("self transfer", "own account", "family", "credited to", "to self"),
    ),
    (
        "Income",
        ("salary", "payroll", "stipend", "cashback credited", "interest credited"),
    ),
]


def classify_transaction(
    db: Session, user_id: int, merchant: str, description: str
) -> tuple[str, str, float]:
    """Classify one transaction. Batch classification is preferred for imports."""
    return classify_transactions(
        db,
        user_id,
        [{"merchant": merchant, "description": description}],
    )[0]


def classify_transactions(
    db: Session,
    user_id: int,
    rows: Iterable[dict[str, str]],
) -> list[tuple[str, str, float]]:
    """
    Hybrid classification:
      1) personal mappings
      2) deterministic rules
      3) cached LLM result
      4) one batched LLM request for unresolved merchants
      5) fallback to Others

    The batched LLM step avoids dozens of serial API calls for a GPay statement.
    """
    items = [
        {
            "merchant": (row.get("merchant") or "unknown").strip(),
            "description": (row.get("description") or "").strip(),
        }
        for row in rows
    ]
    mappings = db.query(MerchantMapping).filter(MerchantMapping.user_id == user_id).all()

    results: list[tuple[str, str, float] | None] = [None] * len(items)
    unresolved: list[tuple[int, str, str, str]] = []
    cached_categories: dict[str, str] = {}

    cache_keys = {_cache_key(item["merchant"], item["description"]) for item in items}
    if cache_keys:
        cached = db.query(LlmCache).filter(LlmCache.cache_key.in_(cache_keys)).all()
        cached_categories = {row.cache_key: row.category for row in cached}

    for index, item in enumerate(items):
        merchant = item["merchant"]
        description = item["description"]

        mapped = _from_mapping_list(mappings, merchant)
        if mapped:
            results[index] = (mapped, "mapping", 0.99)
            continue

        ruled = _from_rules(merchant, description)
        if ruled:
            results[index] = (ruled, "rules", 0.95)
            continue

        key = _cache_key(merchant, description)
        cached_category = cached_categories.get(key)
        if cached_category in CATEGORIES:
            results[index] = (cached_category, "llm-cache", 0.82)
            continue

        unresolved.append((index, key, merchant, description))

    if unresolved:
        unique_pending: dict[str, tuple[str, str]] = {}
        for _, key, merchant, description in unresolved:
            unique_pending.setdefault(key, (merchant, description))

        llm_categories = _from_llm_batch(list(unique_pending.items()))

        for index, key, _, _ in unresolved:
            category = llm_categories.get(key)
            if category in CATEGORIES:
                results[index] = (category, "llm", 0.82)
                if key not in cached_categories:
                    db.add(LlmCache(cache_key=key, category=category, confidence=0.82))
                    cached_categories[key] = category
            else:
                results[index] = ("Others", "fallback", 0.3)

        if llm_categories:
            db.flush()

    return [result or ("Others", "fallback", 0.3) for result in results]


def active_llm_provider() -> str | None:
    """Return the provider/model that will be attempted first, if any key is configured."""
    preferred = (settings.llm_provider or "").strip().lower()
    if preferred == "openai" and settings.openai_api_key:
        return f"OpenAI · {settings.openai_model}"
    if preferred == "gemini" and settings.gemini_api_key:
        return f"Gemini · {settings.gemini_model}"
    if settings.gemini_api_key:
        return f"Gemini · {settings.gemini_model}"
    if settings.openai_api_key:
        return f"OpenAI · {settings.openai_model}"
    return None


def learn_mapping(db: Session, user_id: int, raw_name: str, merchant: str, category: str) -> None:
    existing = (
        db.query(MerchantMapping)
        .filter(MerchantMapping.user_id == user_id, MerchantMapping.normalized_name == merchant)
        .one_or_none()
    )
    if existing:
        existing.category = category
        existing.raw_name = raw_name
    else:
        db.add(
            MerchantMapping(
                user_id=user_id,
                raw_name=raw_name,
                normalized_name=merchant,
                category=category,
            )
        )


def mark_recurring(db: Session, user_id: int) -> int:
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id, Transaction.direction == "debit")
        .all()
    )
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for txn in txns:
        groups[txn.merchant].append(txn)

    flagged = 0
    for merchant, items in groups.items():
        if merchant in {"", "unknown"} or len(items) < 3:
            continue
        months = {item.txn_date.strftime("%Y-%m") for item in items}
        amounts = [round(item.amount, 0) for item in items]
        similar_amount = max(amounts.count(a) for a in set(amounts)) >= 2
        if len(months) >= 2 and similar_amount:
            for item in items:
                if not item.is_recurring:
                    item.is_recurring = True
                    flagged += 1
    return flagged


def _from_mapping_list(mappings: list[MerchantMapping], merchant: str) -> str | None:
    for mapping in mappings:
        if mapping.normalized_name == merchant:
            return mapping.category

    best_score = 0
    best_category = None
    for mapping in mappings:
        score = fuzz.token_set_ratio(merchant, mapping.normalized_name)
        if score > best_score:
            best_score = score
            best_category = mapping.category
    return best_category if best_score >= 88 else None


def _from_rules(merchant: str, description: str) -> str | None:
    haystack = f"{merchant} {description}".lower()
    for category, keywords in RULES:
        if any(keyword in haystack for keyword in keywords):
            return category
    if re.search(r"\bupi\b", haystack) and re.search(r"\b(mom|dad|papa|amma|family)\b", haystack):
        return "Transfers (Self / Family)"
    return None


def _cache_key(merchant: str, description: str) -> str:
    return f"{merchant}|{description[:80]}"[:255]


def _from_llm_batch(
    pending: list[tuple[str, tuple[str, str]]],
) -> dict[str, str]:
    if not pending:
        return {}

    preferred = (settings.llm_provider or "").strip().lower()
    providers: list[str] = []
    if preferred in {"gemini", "openai"}:
        providers.append(preferred)
    for provider in ("gemini", "openai"):
        if provider not in providers:
            providers.append(provider)

    for provider in providers:
        if provider == "gemini" and settings.gemini_api_key:
            result = _gemini_classify_batch(pending)
            if result:
                return result
        if provider == "openai" and settings.openai_api_key:
            result = _openai_classify_batch(pending)
            if result:
                return result
    return {}


def _batch_prompt(pending: list[tuple[str, tuple[str, str]]]) -> str:
    cats = ", ".join(CATEGORIES)
    rows = [
        {
            "id": key,
            "merchant": merchant,
            "description": description,
        }
        for key, (merchant, description) in pending
    ]
    return (
        "You classify Indian personal-finance transactions from UPI and credit-card statements. "
        "Use real-world merchant knowledge when helpful (brand names, parent companies, restaurant chains, "
        "vending operators, pharmacies, supermarkets, travel services, subscriptions). "
        "Do not guess a specific spending category for an ordinary person's name with no commercial clue; "
        "use Others unless the text clearly indicates a transfer. "
        f"Choose exactly one category for every row from: {cats}. "
        "Return ONLY a JSON array. Each element must be "
        '{"id":"the exact input id","category":"one allowed category"}. '
        f"Rows: {json.dumps(rows, ensure_ascii=False)}"
    )


def _parse_batch_categories(text: str, valid_keys: set[str]) -> dict[str, str]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}

    if not isinstance(data, list):
        return {}

    parsed: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id", ""))
        category = item.get("category")
        if key in valid_keys and category in CATEGORIES:
            parsed[key] = category
    return parsed


def _gemini_classify_batch(
    pending: list[tuple[str, tuple[str, str]]],
) -> dict[str, str]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": _batch_prompt(pending)}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    try:
        response = httpx.post(url, json=payload, timeout=30)
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_batch_categories(text, {key for key, _ in pending})
    except Exception:
        return {}


def _openai_classify_batch(
    pending: list[tuple[str, tuple[str, str]]],
) -> dict[str, str]:
    try:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_model,
                "input": _batch_prompt(pending),
                "temperature": 0,
                "max_output_tokens": 5000,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        chunks: list[str] = []
        for output in payload.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(content["text"])
        return _parse_batch_categories("\n".join(chunks), {key for key, _ in pending})
    except Exception:
        return {}
