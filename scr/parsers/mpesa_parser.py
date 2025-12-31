from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from scr.models.transaction import Transaction


class MPesaParser:
    PATTERNS = {
        "sent": {
            "code": r"([A-Z0-9]{10})\s+confirmed",
            "amount": r"Ksh([\d,]+\.?\d*)",
            "date": r"on\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM)?)",
            "fee": r"Transaction cost[,:]?\s*Ksh([\d,]+\.?\d*)",
            "recipient": r"sent to\s+(.+?)\s+(?:on|\d)",
        },
        "received": {
            "code": r"([A-Z0-9]{10})\s+confirmed",
            "amount": r"Ksh([\d,]+\.?\d*)",
            "date": r"on\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM)?)",
            "sender": r"from\s+(.+?)\s+(?:on|\d)",
            "fee": r"0\.00",
        },
        "withdrawn": {
            "code": r"([A-Z0-9]{10})\s+confirmed",
            "amount": r"Ksh([\d,]+\.?\d*)",
            "date": r"on\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM)?)",
            "fee": r"Transaction cost[,:]?\s*Ksh([\d,]+\.?\d*)",
        },
        "paybill": {
            "code": r"([A-Z0-9]{10})\s+confirmed",
            "amount": r"Ksh([\d,]+\.?\d*)",
            "date": r"on\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM)?)",
            "fee": r"Transaction cost[,:]?\s*Ksh([\d,]+\.?\d*)",
            "recipient": r"paid to\s+(.+?)(?:\.|on)",
        },
        "airtime": {
            "code": r"([A-Z0-9]{10})\s+confirmed",
            "amount": r"Ksh([\d,]+\.?\d*)",
            "date": r"on\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM)?)",
            "fee": r"0\.00",
        },
    }

    @staticmethod
    def detect_transaction_type(message: str) -> Optional[str]:
        m = message.lower()
        if "sent to" in m:
            return "sent"
        if "received" in m and "from" in m:
            return "received"
        if "withdraw" in m:
            return "withdrawn"
        if "paid to" in m or "paybill" in m:
            return "paybill"
        if "airtime" in m or "bought" in m:
            return "airtime"
        return None

    @staticmethod
    def clean_amount(amount_str: str) -> float:
        return float(amount_str.replace(",", ""))

    @staticmethod
    def parse_date(date_str: str, time_str: str) -> datetime:
        fmts = [
            "%d/%m/%y %I:%M %p",
            "%d/%m/%Y %I:%M %p",
            "%d/%m/%y %H:%M",
            "%d/%m/%Y %H:%M",
        ]
        dt_str = f"{date_str} {time_str}".strip()
        for fmt in fmts:
            try:
                return datetime.strptime(dt_str, fmt)
            except ValueError:
                pass
        raise ValueError(f"Unparseable date/time: {dt_str}")

    def _extract(self, message: str, pattern: str) -> Optional[str]:
        if not pattern:
            return None
        match = re.search(pattern, message, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def parse_message(self, message: str) -> Optional[Transaction]:
        try:
            tx_type = self.detect_transaction_type(message)
            if not tx_type or tx_type not in self.PATTERNS:
                return None

            p = self.PATTERNS[tx_type]

            code = self._extract(message, p["code"])
            amount_str = self._extract(message, p["amount"])
            if not code or not amount_str:
                return None

            date_match = re.search(p["date"], message, re.IGNORECASE)
            if not date_match:
                return None

            tx_date = self.parse_date(date_match.group(1), date_match.group(2))
            fee_str = self._extract(message, p.get("fee", ""))
            fee = self.clean_amount(fee_str) if fee_str else 0.0

            recipient = self._extract(message, p.get("recipient", ""))
            sender = self._extract(message, p.get("sender", ""))

            bal_match = re.search(r"balance.*?Ksh([\d,]+\.?\d*)", message, re.IGNORECASE)
            balance = self.clean_amount(bal_match.group(1)) if bal_match else None

            return Transaction(
                transaction_code=code,
                amount=self.clean_amount(amount_str),
                date=tx_date,
                fee=fee,
                transaction_type=tx_type,
                recipient=recipient,
                sender=sender,
                balance=balance,
                message=message,
            )
        except Exception:
            return None

    def parse_multiple_messages(self, messages: List[str]) -> List[Transaction]:
        out: List[Transaction] = []
        for msg in messages:
            tx = self.parse_message(msg.strip())
            if tx:
                out.append(tx)
        return out