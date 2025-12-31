from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_code: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    fee: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    sender: Mapped[Optional[str]] = mapped_column(String(255))
    recipient: Mapped[Optional[str]] = mapped_column(String(255))
    balance: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    raw_message: Mapped[Optional[str]] = mapped_column(Text)

    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("transaction_code", name="uq_transactions_code"),
        Index("ix_transactions_occurred_at", "occurred_at"),
        Index("ix_transactions_type_date", "transaction_type", "occurred_at"),
    )


class TxDaily(Base):
    __tablename__ = "tx_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    tx_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_fees: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)


class TxTypeDaily(Base):
    __tablename__ = "tx_type_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    transaction_type: Mapped[str] = mapped_column(String(32), primary_key=True)

    tx_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_fees: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    __table_args__ = (
        Index("ix_tx_type_daily_day", "day"),
        Index("ix_tx_type_daily_type", "transaction_type"),
    )