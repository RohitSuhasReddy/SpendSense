from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

import pdfplumber
from dateutil import parser as date_parser

from app.services.normalize import clean_description, detect_bank, normalize_merchant

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}-[A-Za-z]{3}-\d{2,4})\b"),
]
AMOUNT_RE = re.compile(r"(?:INR|Rs\.?|₹)?\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})|[0-9]+\.[0-9]{1,2})")
CREDIT_HINT = re.compile(r"\b(cr|credit|refund|cashback|interest.?rev|payment received)\b", re.I)
DEBIT_HINT = re.compile(r"\b(dr|debit|purchase|spent|withdrawal)\b", re.I)
UPI_HINT = re.compile(r"\b(upi|vpa|@oksbi|@okhdfc|@okicici|@ybl|@apl|@paytm|phonepe|google pay|gpay)\b", re.I)


def parse_statement_pdf(content: bytes, source_type: str) -> dict[str, Any]:
    pages_text: list[str] = []
    table_rows: list[list[str]] = []

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
            tables = page.extract_tables() or []
            for table in tables:
                for row in table:
                    cells = [str(cell).strip() if cell else "" for cell in row]
                    if any(cells):
                        table_rows.append(cells)

    full_text = "\n".join(pages_text)
    bank_hint = detect_bank(full_text)
    inferred_source = source_type
    if source_type == "auto":
        inferred_source = "upi" if UPI_HINT.search(full_text) else "credit_card"

    parsed = _from_tables(table_rows, inferred_source)
    if len(parsed) < 3:
        parsed = _from_lines(pages_text, inferred_source)

    return {
        "bank_hint": bank_hint,
        "source_type": inferred_source,
        "transactions": parsed,
        "raw_preview": full_text[:2000],
    }


def _from_tables(rows: list[list[str]], source_type: str) -> list[dict[str, Any]]:
    if not rows:
        return []

    header_idx = _find_header_row(rows)
    body = rows[header_idx + 1 :] if header_idx is not None else rows
    results: list[dict[str, Any]] = []
    for row in body:
        txn = _row_to_txn(row, source_type)
        if txn:
            results.append(txn)
    return _dedupe(results)


def _find_header_row(rows: list[list[str]]) -> int | None:
    keywords = ("date", "description", "particular", "merchant", "amount", "debit", "credit")
    for i, row in enumerate(rows[:12]):
        joined = " ".join(row).lower()
        hits = sum(1 for key in keywords if key in joined)
        if hits >= 2:
            return i
    return None


def _row_to_txn(row: list[str], source_type: str) -> dict[str, Any] | None:
    joined = " ".join(row)
    txn_date = _extract_date(joined)
    if not txn_date:
        return None

    amounts = _extract_amounts(row)
    if not amounts:
        return None

    direction, amount = _direction_and_amount(row, amounts)
    description = _best_description(row)
    if not description or len(description) < 3:
        return None
    if _looks_like_header(description):
        return None

    return {
        "txn_date": txn_date,
        "amount": amount,
        "direction": direction,
        "raw_description": description,
        "cleaned_description": clean_description(description),
        "merchant": normalize_merchant(description),
        "source": source_type,
    }


def _from_lines(pages_text: list[str], source_type: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for page in pages_text:
        for raw_line in page.splitlines():
            line = " ".join(raw_line.split())
            txn_date = _extract_date(line)
            amounts = _extract_amounts([line])
            if not txn_date or not amounts:
                continue
            direction, amount = _direction_and_amount([line], amounts)
            description = DATE_PATTERNS[0].sub(" ", line)
            description = AMOUNT_RE.sub(" ", description)
            description = clean_description(description)
            if len(description) < 3 or _looks_like_header(description):
                continue
            results.append(
                {
                    "txn_date": txn_date,
                    "amount": amount,
                    "direction": direction,
                    "raw_description": line[:400],
                    "cleaned_description": description,
                    "merchant": normalize_merchant(description),
                    "source": source_type,
                }
            )
    return _dedupe(results)


def _extract_date(text: str) -> datetime | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text or "")
        if not match:
            continue
        try:
            parsed = date_parser.parse(match.group(1), dayfirst=True, fuzzy=True)
            if 2000 <= parsed.year <= 2100:
                return parsed
        except (ValueError, OverflowError, TypeError):
            continue
    return None


def _extract_amounts(cells: list[str]) -> list[float]:
    found: list[float] = []
    for cell in cells:
        for match in AMOUNT_RE.finditer(cell.replace(" ", "")):
            try:
                value = float(match.group(1).replace(",", ""))
            except ValueError:
                continue
            if 0 < value < 10_000_000:
                found.append(value)
    return found


def _direction_and_amount(cells: list[str], amounts: list[float]) -> tuple[str, float]:
    joined = " ".join(cells)
    if CREDIT_HINT.search(joined) and not DEBIT_HINT.search(joined):
        return "credit", amounts[-1]
    lowered = [c.lower() for c in cells]
    for i, cell in enumerate(lowered):
        if "credit" in cell and i + 1 < len(amounts):
            return "credit", amounts[-1]
    # Typical CC statements: last amount is transaction amount
    return "debit", amounts[-1]


def _best_description(row: list[str]) -> str:
    candidates = sorted(row, key=len, reverse=True)
    for cell in candidates:
        if _extract_date(cell) and len(cell) < 16:
            continue
        if AMOUNT_RE.fullmatch(cell.replace(" ", "").replace("₹", "").replace("Rs", "")):
            continue
        if len(cell) >= 3:
            return cell
    return " ".join(row)


def _looks_like_header(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in ("statement", "opening balance", "closing balance", "page no", "gstin")
    )


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row["txn_date"].date().isoformat(),
            round(row["amount"], 2),
            row["raw_description"][:80],
            row["direction"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique
