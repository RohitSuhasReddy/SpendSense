from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = "Rohit"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TransactionOut(BaseModel):
    id: int
    txn_date: datetime
    amount: float
    direction: str
    raw_description: str
    cleaned_description: str
    merchant: str
    category: str
    source: str
    classification_method: str
    confidence: float
    is_corrected: bool
    is_recurring: bool

    model_config = {"from_attributes": True}


class TransactionUpdate(BaseModel):
    category: str


class UploadResult(BaseModel):
    upload_id: int
    filename: str
    source_type: str
    bank_hint: str | None
    imported: int
    skipped: int
    classified: dict[str, int]


class MonthlySummary(BaseModel):
    month: str
    total_debit: float
    total_credit: float
    by_category: dict[str, float]
    transaction_count: int
