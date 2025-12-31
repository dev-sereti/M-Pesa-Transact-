from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Transaction:
    transaction_code: str
    amount: float
    date: datetime
    fee: float
    transaction_type: str
    recipient: Optional[str] = None
    sender: Optional[str] = None
    balance: Optional[float] = None
    message: Optional[str] = None