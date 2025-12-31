from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Dict, List, Tuple

from scr.models.transaction import Transaction


class DatabaseManager:
    def __init__(self, db_path: str = "mpesa_transactions.db"):
        self.db_path = db_path
        self.create_tables()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=30,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_tables(self) -> None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_code TEXT UNIQUE NOT NULL,
                    amount REAL NOT NULL,
                    date TEXT NOT NULL,
                    fee REAL NOT NULL,
                    transaction_type TEXT NOT NULL,
                    recipient TEXT,
                    sender TEXT,
                    balance REAL,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transaction_code ON transactions(transaction_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_date ON transactions(date)")

    def insert_multiple_transactions(self, transactions: List[Transaction]) -> Tuple[int, int]:
        success = 0
        duplicates = 0
        with self.get_connection() as conn:
            cur = conn.cursor()
            for t in transactions:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO transactions
                    (transaction_code, amount, date, fee, transaction_type, recipient, sender, balance, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        t.transaction_code,
                        float(t.amount),
                        t.date.strftime("%Y-%m-%d %H:%M:%S"),
                        float(t.fee),
                        t.transaction_type,
                        t.recipient,
                        t.sender,
                        t.balance,
                        t.message,
                    ),
                )
                if cur.rowcount == 1:
                    success += 1
                else:
                    duplicates += 1
        return success, duplicates

    def get_all_transactions(self) -> List[Dict]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM transactions ORDER BY date DESC")
            return [dict(r) for r in cur.fetchall()]

    def get_statistics(self) -> Dict:
        with self.get_connection() as conn:
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) AS total FROM transactions")
            total = cur.fetchone()["total"]

            cur.execute("SELECT SUM(amount) AS total_amount FROM transactions")
            total_amount = cur.fetchone()["total_amount"] or 0

            cur.execute("SELECT SUM(fee) AS total_fees FROM transactions")
            total_fees = cur.fetchone()["total_fees"] or 0

            cur.execute(
                """
                SELECT transaction_type, COUNT(*) AS count, SUM(amount) AS total
                FROM transactions
                GROUP BY transaction_type
                """
            )
            by_type = [dict(r) for r in cur.fetchall()]

        return {
            "total_transactions": total,
            "total_amount": total_amount,
            "total_fees": total_fees,
            "by_type": by_type,
        }