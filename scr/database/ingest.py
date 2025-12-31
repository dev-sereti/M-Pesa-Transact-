from __future__ import annotations

from datetime import date
from typing import List, Tuple

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from scr.database.models import Transaction, TxDaily, TxTypeDaily
from scr.models.transaction import Transaction as ParsedTransaction


async def insert_transactions_and_update_stats(
    session: AsyncSession,
    txs: List[ParsedTransaction],
) -> Tuple[int, int]:
    """
    Inserts new transactions (dedupe by transaction_code) and updates rollup tables.
    Returns: (inserted_count, duplicate_count)
    """
    inserted = 0
    duplicates = 0

    # Insert one-by-one is simplest; you can batch later.
    # Keeping it explicit here for correctness and clarity.
    for t in txs:
        stmt = (
            insert(Transaction)
            .values(
                transaction_code=t.transaction_code,
                occurred_at=t.date,
                transaction_type=t.transaction_type,
                amount=t.amount,
                fee=t.fee,
                sender=t.sender,
                recipient=t.recipient,
                balance=t.balance,
                raw_message=t.message,
            )
            .on_conflict_do_nothing(index_elements=["transaction_code"])
            .returning(Transaction.id)
        )

        res = await session.execute(stmt)
        row = res.first()

        if row is None:
            duplicates += 1
            continue

        inserted += 1

        d: date = t.date.date()

        # Update tx_daily
        stmt_daily = (
            insert(TxDaily)
            .values(day=d, tx_count=1, total_amount=t.amount, total_fees=t.fee)
            .on_conflict_do_update(
                index_elements=["day"],
                set_={
                    "tx_count": TxDaily.tx_count + 1,
                    "total_amount": TxDaily.total_amount + t.amount,
                    "total_fees": TxDaily.total_fees + t.fee,
                },
            )
        )
        await session.execute(stmt_daily)

        # Update tx_type_daily
        stmt_type = (
            insert(TxTypeDaily)
            .values(day=d, transaction_type=t.transaction_type, tx_count=1, total_amount=t.amount, total_fees=t.fee)
            .on_conflict_do_update(
                index_elements=["day", "transaction_type"],
                set_={
                    "tx_count": TxTypeDaily.tx_count + 1,
                    "total_amount": TxTypeDaily.total_amount + t.amount,
                    "total_fees": TxTypeDaily.total_fees + t.fee,
                },
            )
        )
        await session.execute(stmt_type)

    return inserted, duplicates