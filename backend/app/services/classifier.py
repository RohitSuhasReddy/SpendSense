from __future__ import annotations

import json
import re
from collections import defaultdict

import httpx
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CATEGORIES, LlmCache, MerchantMapping, Transaction

RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Food & Dining", ("swiggy", "zomato", "eatclub", "dominos", "pizza", "burger", "starbucks", "cafe", "restaurant", "kfc", "mcdonald", "biryani", "eatsure", "box8")),
    ("Groceries", ("blinkit", "zepto", "instamart", "bigbasket", "dmart", "jiomart", "grocery", "supermarket", "more supermarket", "reliance fresh")),
    ("Travel & Transport", ("uber", "ola", "rapido", "irctc", "indigo", "air india", "vistara", "makemytrip", "goibibo", "redbus", "fastag", "metro", "petrol", "indian oil", "bpcl", "hpcl")),
    ("Shopping", ("amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa", "croma", "ikea", "decathlon")),
    ("Entertainment", ("netflix", "spotify", "prime video", "hotstar", "disney", "bookmyshow", "pvr", "inox", "youtube premium")),
    ("Utilities & Bills", ("airtel", "jio", "vi ", "bsnl", "electricity", "bescom", "tata power", "act fibernet", "hathway", "gas", "broadband", "recharge")),
    ("Rent / Housing", ("rent", "landlord", "housing", "nobroker", "society maintenance")),
    ("Health", ("pharmacy", "apollo", "1mg", "pharmeasy", "netmeds", "hospital", "clinic", "practo")),
    ("Education", ("udemy", "coursera", "unacademy", "byju", "school", "college", "tuition", "exam fee")),
    ("Transfers (Self / Family)", ("self transfer", "own account", "family", "credited to")),
    ("Income", ("salary", "payroll", "stipend", "refund", "cashback credited")),
]


def classify_transaction(db: Session, user_id: int, merchant: str, description: str) -> tuple[str, str, float]:
    mapped = _from_mapping(db, user_id, merchant)
    if mapped:
        return mapped, "mapping", 0.99

    ruled = _from_rules(merchant, description)
    if ruled:
        return ruled, "rules", 0.9

    llm = _from_llm(db, merchant, description)
    if llm:
        return llm, "llm", 0.75

    return "Others", "fallback", 0.3


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


def _from_mapping(db: Session, user_id: int, merchant: str) -> str | None:
    mappings = db.query(MerchantMapping).filter(MerchantMapping.user_id == user_id).all()
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
    if best_score >= 88:
        return best_category
    return None


def _from_rules(merchant: str, description: str) -> str | None:
    haystack = f"{merchant} {description}".lower()
    for category, keywords in RULES:
        if any(keyword in haystack for keyword in keywords):
            return category
    if re.search(r"\bupi\b", haystack) and re.search(r"\b(mom|dad|papa|amma|family)\b", haystack):
        return "Transfers (Self / Family)"
    return None


def _from_llm(db: Session, merchant: str, description: str) -> str | None:
    cache_key = f"{merchant}|{description[:80]}"
    cached = db.query(LlmCache).filter(LlmCache.cache_key == cache_key).one_or_none()
    if cached:
        return cached.category

    category = None
    if settings.llm_provider == "openai" and settings.openai_api_key:
        category = _openai_classify(merchant, description)
    elif settings.gemini_api_key:
        category = _gemini_classify(merchant, description)

    if category in CATEGORIES:
        db.add(LlmCache(cache_key=cache_key, category=category, confidence=0.75))
        db.flush()
        return category
    return None


def _prompt(merchant: str, description: str) -> str:
    cats = ", ".join(CATEGORIES)
    return (
        "You classify Indian personal finance transactions. "
        f"Pick exactly one category from: {cats}. "
        "Reply with JSON only: {\"category\": \"...\"}. "
        f"Merchant: {merchant}. Description: {description}."
    )


def _parse_category(text: str) -> str | None:
    try:
        data = json.loads(text)
        category = data.get("category")
        if category in CATEGORIES:
            return category
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    for category in CATEGORIES:
        if category.lower() in (text or "").lower():
            return category
    return None


def _gemini_classify(merchant: str, description: str) -> str | None:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={settings.gemini_api_key}"
    )
    payload = {"contents": [{"parts": [{"text": _prompt(merchant, description)}]}]}
    try:
        response = httpx.post(url, json=payload, timeout=20)
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_category(text)
    except Exception:
        return None


def _openai_classify(merchant: str, description: str) -> str | None:
    try:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": _prompt(merchant, description)}],
                "temperature": 0,
            },
            timeout=20,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        return _parse_category(text)
    except Exception:
        return None
