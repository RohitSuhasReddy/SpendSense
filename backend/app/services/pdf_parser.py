from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

import pdfplumber
from dateutil import parser as date_parser

from app.services.normalize import clean_description, detect_bank, normalize_merchant

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3},?\s+\d{4})\b"),
    re.compile(r"\b(\d{1,2}[A-Za-z]{3},?\d{4})\b"),
    re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}-[A-Za-z]{3}-\d{2,4})\b"),
]
AMOUNT_RE = re.compile(
    r"(?:INR|Rs\.?|₹)\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"
)
CREDIT_HINT = re.compile(
    r"\b(cr|credit|refund|cashback|interest.?rev|payment received|received from)\b", re.I
)
DEBIT_HINT = re.compile(r"\b(dr|debit|purchase|spent|withdrawal|paid to)\b", re.I)
UPI_HINT = re.compile(
    r"\b(upi|vpa|@oksbi|@okhdfc|@okicici|@ybl|@apl|@paytm|phonepe|google pay|gpay)\b", re.I
)
GPAY_HINT = re.compile(r"google\s*pay|gpay|transaction\s*statement\s*period|powered\s*by\s*upi", re.I)

GPAY_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}[A-Za-z]{3},?\d{4})\s+"
    r"(?P<action>Paidto|Receivedfrom|Selftransferto|Top-?upto)"
    r"(?P<merchant>.*?)\s+₹\s*(?P<amount>[0-9,]+(?:\.[0-9]{1,2})?)$",
    re.I,
)
GPAY_SPACED_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}\s+[A-Za-z]{3},?\s+\d{4})\s+"
    r"(?P<action>Paid to|Received from|Self transfer to|Top-up to)\s+"
    r"(?P<merchant>.*?)\s+₹\s*(?P<amount>[0-9,]+(?:\.[0-9]{1,2})?)$",
    re.I,
)
GPAY_REFERENCE_RE = re.compile(r"(?:UPI)?TransactionID:(?P<ref>[A-Za-z0-9-]+)", re.I)

ICICI_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<serial>\d{6,})\s+"
    r"(?P<body>.+?)\s+"
    r"(?P<amount>[0-9][0-9,]*\.\d{2})(?:\s+(?P<marker>CR|DR))?$",
    re.I,
)

ACTION_LABELS = {
    "paidto": "Paid to",
    "receivedfrom": "Received from",
    "selftransferto": "Self transfer to",
    "top-upto": "Top-up to",
    "topupto": "Top-up to",
}


def parse_statement_pdf(content: bytes, source_type: str) -> dict[str, Any]:
    pages_text: list[str] = []
    table_rows: list[list[str]] = []

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
            for table in page.extract_tables() or []:
                for row in table:
                    cells = [str(cell).strip() if cell else "" for cell in row]
                    if any(cells):
                        table_rows.append(cells)

    full_text = "\n".join(pages_text)
    compact_text = re.sub(r"\s+", "", full_text).lower()
    bank_hint = detect_bank(full_text)
    inferred_source = source_type

    is_gpay = bool(
        GPAY_HINT.search(full_text)
        or "googlepay" in compact_text
        or "transactionstatementperiod" in compact_text
    )

    is_credit_card = bool(
        re.search(r"credit\s*card\s*statement|credit\s*summary|payment\s*due\s*date", full_text, re.I)
    )

    if source_type == "auto":
        if is_gpay:
            inferred_source = "upi"
            bank_hint = "Google Pay"
        elif is_credit_card:
            inferred_source = "credit_card"
        else:
            inferred_source = "upi" if UPI_HINT.search(full_text) else "credit_card"

    if is_gpay or bank_hint == "Google Pay":
        parsed = _from_gpay(pages_text)
        if parsed:
            return {
                "bank_hint": "Google Pay",
                "source_type": "upi",
                "transactions": parsed,
                "raw_preview": full_text[:2500],
            }

    if (bank_hint == "ICICI" or "credit card statement" in full_text.lower()) and inferred_source == "credit_card":
        parsed = _from_icici_credit_card(pages_text)
        if parsed:
            return {
                "bank_hint": bank_hint or "ICICI",
                "source_type": "credit_card",
                "transactions": parsed,
                "raw_preview": full_text[:2500],
            }

    parsed = _from_tables(table_rows, inferred_source)
    if len(parsed) < 3:
        parsed = _from_lines(pages_text, inferred_source)

    return {
        "bank_hint": bank_hint,
        "source_type": inferred_source,
        "transactions": parsed,
        "raw_preview": full_text[:2500],
    }


def _from_gpay(pages_text: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for page in pages_text:
        lines = [" ".join(line.split()) for line in page.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            match = GPAY_LINE_RE.match(line) or GPAY_SPACED_LINE_RE.match(line)
            if not match:
                continue

            try:
                txn_date = date_parser.parse(match.group("date"), dayfirst=True, fuzzy=True)
                amount = float(match.group("amount").replace(",", ""))
            except (ValueError, TypeError, OverflowError):
                continue

            action_key = re.sub(r"\s+", "", match.group("action")).lower()
            action = ACTION_LABELS.get(action_key, match.group("action").strip())
            merchant_raw = _prettify_compact_merchant(match.group("merchant").strip())

            # A UPI Lite top-up is funding the wallet, not a purchase. The subsequent
            # UPI Lite payments are already present in the same GPay statement.
            if action == "Top-up to":
                continue
            if amount <= 0 or len(merchant_raw) < 2:
                continue

            reference = None
            for look_ahead in lines[index + 1 : index + 3]:
                compact_look_ahead = look_ahead.replace(" ", "")
                time_match = re.match(r"(?P<time>\d{1,2}:\d{2}(?:AM|PM))", compact_look_ahead, re.I)
                if time_match:
                    try:
                        parsed_time = datetime.strptime(time_match.group("time").upper(), "%I:%M%p")
                        txn_date = txn_date.replace(hour=parsed_time.hour, minute=parsed_time.minute)
                    except ValueError:
                        pass
                ref_match = GPAY_REFERENCE_RE.search(compact_look_ahead)
                if ref_match:
                    reference = ref_match.group("ref")

            direction = "credit" if action == "Received from" else "debit"
            description = f"{action} {merchant_raw}".strip()
            raw_description = description
            if reference:
                raw_description = f"{description} | Transaction ID: {reference}"

            results.append(
                {
                    "txn_date": txn_date,
                    "amount": amount,
                    "direction": direction,
                    "raw_description": raw_description[:400],
                    "cleaned_description": clean_description(description),
                    "merchant": normalize_merchant(merchant_raw),
                    "source": "upi",
                }
            )

    return _dedupe(results)


def _from_icici_credit_card(pages_text: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for page in pages_text:
        for raw_line in page.splitlines():
            line = " ".join(raw_line.split())
            match = ICICI_LINE_RE.match(line)
            if not match:
                continue
            try:
                txn_date = datetime.strptime(match.group("date"), "%d/%m/%Y")
                amount = float(match.group("amount").replace(",", ""))
            except (ValueError, TypeError):
                continue

            body = match.group("body").strip()
            # The column immediately before Amount is reward points. pdfplumber
            # often collapses the table into one line, so remove that final integer.
            body = re.sub(r"\s+\d{1,5}$", "", body).strip()
            if len(body) < 2:
                continue

            marker = (match.group("marker") or "").upper()
            direction = "credit" if marker == "CR" or CREDIT_HINT.search(body) else "debit"
            serial = match.group("serial")
            raw_description = f"{body} | Ref: {serial}"

            results.append(
                {
                    "txn_date": txn_date,
                    "amount": amount,
                    "direction": direction,
                    "raw_description": raw_description[:400],
                    "cleaned_description": clean_description(body),
                    "merchant": normalize_merchant(body),
                    "source": "credit_card",
                }
            )
    return _dedupe(results)


def _prettify_compact_merchant(value: str) -> str:
    text = value.strip(" -,")
    # Google Pay's PDF text layer frequently removes spaces entirely. Camel-case
    # boundaries are still recoverable for many merchants (AmazonPayGroceries,
    # JuelAhmed, etc.). ALL-CAPS names remain intact rather than being guessed.
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Za-z])(?=\d{4}$)", " ", text)
    return " ".join(text.split())


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
    if not description or len(description) < 3 or _looks_like_header(description):
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
            description = line
            for pattern in DATE_PATTERNS:
                description = pattern.sub(" ", description)
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
        for token in (
            "statement", "opening balance", "closing balance", "page no", "gstin",
            "transaction statement", "date & time", "transaction details",
        )
    )


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row["txn_date"].date().isoformat(),
            round(row["amount"], 2),
            row["raw_description"][:160],
            row["direction"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique
