from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scr.config import settings
from scr.database.ingest import insert_transactions_and_update_stats
from scr.database.models import TxDaily, TxTypeDaily
from scr.database.pg_db import get_session
from scr.excel.excel_handler import ExcelHandler
from scr.parsers.mpesa_parser import MPesaParser
from scr.realtime import StatsBroadcaster

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="static")

parser = MPesaParser()
broadcaster = StatsBroadcaster()


def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(str(WEB_DIR / "index.html"), media_type="text/html")


@app.websocket("/ws/stats")
async def ws_stats(ws: WebSocket):
    await broadcaster.connect(ws)
    try:
        while True:
            # Keep the socket open; client can ignore pings
            await ws.receive_text()
    except Exception:
        await broadcaster.disconnect(ws)


@app.get("/api/stats/summary", dependencies=[Depends(require_api_key)])
async def stats_summary(
    days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    start_day = date.today() - timedelta(days=days - 1)

    stmt = select(
        func.coalesce(func.sum(TxDaily.tx_count), 0),
        func.coalesce(func.sum(TxDaily.total_amount), 0),
        func.coalesce(func.sum(TxDaily.total_fees), 0),
    ).where(TxDaily.day >= start_day)

    res = await session.execute(stmt)
    tx_count, total_amount, total_fees = res.one()

    return {
        "days": days,
        "tx_count": int(tx_count),
        "total_amount": float(total_amount),
        "total_fees": float(total_fees),
    }


@app.get("/api/stats/by-day", dependencies=[Depends(require_api_key)])
async def stats_by_day(
    days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    start_day = date.today() - timedelta(days=days - 1)

    stmt = (
        select(TxDaily.day, TxDaily.tx_count, TxDaily.total_amount, TxDaily.total_fees)
        .where(TxDaily.day >= start_day)
        .order_by(TxDaily.day.asc())
    )

    res = await session.execute(stmt)
    rows = res.all()

    return [
        {
            "day": r.day.isoformat(),
            "tx_count": int(r.tx_count),
            "total_amount": float(r.total_amount),
            "total_fees": float(r.total_fees),
        }
        for r in rows
    ]


@app.get("/api/stats/by-type", dependencies=[Depends(require_api_key)])
async def stats_by_type(
    days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    start_day = date.today() - timedelta(days=days - 1)

    stmt = (
        select(
            TxTypeDaily.transaction_type,
            func.sum(TxTypeDaily.tx_count).label("tx_count"),
            func.sum(TxTypeDaily.total_amount).label("total_amount"),
            func.sum(TxTypeDaily.total_fees).label("total_fees"),
        )
        .where(TxTypeDaily.day >= start_day)
        .group_by(TxTypeDaily.transaction_type)
        .order_by(func.sum(TxTypeDaily.tx_count).desc())
    )

    res = await session.execute(stmt)
    rows = res.all()

    return [
        {
            "transaction_type": r.transaction_type,
            "tx_count": int(r.tx_count or 0),
            "total_amount": float(r.total_amount or 0),
            "total_fees": float(r.total_fees or 0),
        }
        for r in rows
    ]


@app.post("/api/process", dependencies=[Depends(require_api_key)])
async def process(
    messages: str = Form(...),
    workbook: UploadFile = File(...),
    update_existing: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
):
    # Parse
    msg_list = [m.strip() for m in messages.split("\n\n") if m.strip()]
    txs = parser.parse_multiple_messages(msg_list)
    if not txs:
        return JSONResponse({"ok": False, "error": "No valid transactions parsed."}, status_code=400)

    # Insert + update aggregates in one transaction
    async with session.begin():
        inserted, duplicates = await insert_transactions_and_update_stats(session, txs)

    # Update Excel (temp copy) and return token the same way you already do
    # (keep your existing token-based download implementation here)
    # After successful processing, notify dashboard clients:
    await broadcaster.broadcast({"type": "stats_updated"})

    return {"ok": True, "inserted": inserted, "duplicates": duplicates, "parsed": len(txs)}