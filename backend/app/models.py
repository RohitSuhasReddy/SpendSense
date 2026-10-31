from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


CATEGORIES = [
    "Food & Dining",
    "Groceries",
    "Travel & Transport",
    "Shopping",
    "Entertainment",
    "Utilities & Bills",
    "Rent / Housing",
    "Health",
    "Education",
    "Transfers (Self / Family)",
    "Income",
    "Others",
]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120), default="Rohit")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="user")
    mappings = relationship("MerchantMapping", back_populates="user")
    uploads = relationship("UploadedFile", back_populates="user")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(40))  # credit_card | upi
    bank_hint: Mapped[str | None] = mapped_column(String(80), nullable=True)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="uploads")
    transactions = relationship("Transaction", back_populates="upload")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id"), nullable=True)
    txn_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    amount: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(16), default="debit")  # debit | credit
    raw_description: Mapped[str] = mapped_column(Text)
    cleaned_description: Mapped[str] = mapped_column(Text, default="")
    merchant: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(80), default="Others", index=True)
    source: Mapped[str] = mapped_column(String(40), default="unknown")
    classification_method: Mapped[str] = mapped_column(String(40), default="unclassified")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")
    upload = relationship("UploadedFile", back_populates="transactions")


class MerchantMapping(Base):
    __tablename__ = "merchant_mappings"
    __table_args__ = (UniqueConstraint("user_id", "normalized_name", name="uq_user_merchant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    raw_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="mappings")


class LlmCache(Base):
    __tablename__ = "llm_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
