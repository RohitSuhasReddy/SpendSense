import re

UPI_NOISE = re.compile(
    r"\b(upi|imps|neft|rtgs|ach|nwd|pos|atm|ref|txn|utr|vpa|paytm|gpay|phonepe|bhim)\b",
    re.I,
)
ID_NOISE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\b|\b\d{6,}\b", re.I)
MULTI_SPACE = re.compile(r"\s+")


def clean_description(raw: str) -> str:
    text = (raw or "").replace("\n", " ").strip()
    text = re.sub(r"[*_=/\\|]+", " ", text)
    text = ID_NOISE.sub(" ", text)
    text = MULTI_SPACE.sub(" ", text).strip(" -.,")
    return text[:255]


def normalize_merchant(raw: str) -> str:
    text = clean_description(raw).lower()
    text = UPI_NOISE.sub(" ", text)
    text = re.sub(r"[^a-z0-9 &]+", " ", text)
    text = MULTI_SPACE.sub(" ", text).strip()
    return text[:120] or "unknown"


def detect_bank(text: str) -> str | None:
    blob = (text or "").lower()
    banks = [
        ("hdfc", "HDFC"),
        ("icici", "ICICI"),
        ("axis bank", "Axis"),
        ("kotak", "Kotak"),
        ("state bank of india", "SBI"),
        ("sbi card", "SBI Card"),
        ("american express", "Amex"),
        ("amex", "Amex"),
        ("yes bank", "Yes Bank"),
        ("idfc", "IDFC"),
        ("hsbc", "HSBC"),
        ("standard chartered", "Standard Chartered"),
        ("phonepe", "PhonePe"),
        ("google pay", "Google Pay"),
        ("gpay", "Google Pay"),
    ]
    for needle, label in banks:
        if needle in blob:
            return label
    return None
