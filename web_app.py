from __future__ import annotations

import os
import secrets
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from scr.database.db_manager import DatabaseManager
from scr.excel.excel_handler import ExcelHandler
from scr.parsers.mpesa_parser import MPesaParser

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="M-Pesa Transaction Manager")

# Serve frontend assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

parser = MPesaParser()
db = DatabaseManager("mpesa_transactions.db")

DOWNLOAD_TTL_SECONDS = 30 * 60  # 30 minutes


@dataclass
class DownloadItem:
    path: str
    filename: str
    created_at: float


DOWNLOADS: Dict[str, DownloadItem] = {}


def split_messages(text: str) -> List[str]:
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    return blocks if blocks else ([text.strip()] if text.strip() else [])


def safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def cleanup_expired_downloads() -> None:
    now = time.time()
    expired = [token for token, item in DOWNLOADS.items() if (now - item.created_at) > DOWNLOAD_TTL_SECONDS]
    for token in expired:
        item = DOWNLOADS.pop(token, None)
        if item:
            safe_remove(item.path)


@app.get("/")
def index():
    # Serve the static HTML file from disk
    return FileResponse(str(WEB_DIR / "index.html"), media_type="text/html")


@app.get("/health")
def health():
    cleanup_expired_downloads()
    return {"status": "ok"}


@app.get("/stats")
def stats():
    return db.get_statistics()


@app.post("/api/process")
async def api_process(
    messages: str = Form(...),
    workbook: UploadFile = File(...),
    update_existing: Optional[str] = Form(None),
):
    cleanup_expired_downloads()

    filename = (workbook.filename or "").lower()
    if not filename.endswith(".xlsx"):
        return JSONResponse({"ok": False, "error": "Please upload a .xlsx file."}, status_code=400)

    msg_list = split_messages(messages)
    transactions = parser.parse_multiple_messages(msg_list)
    if not transactions:
        return JSONResponse({"ok": False, "error": "No valid transactions parsed. Check message format."}, status_code=400)

    inserted, duplicates = db.insert_multiple_transactions(transactions)

    # Save upload to a temp file
    data = await workbook.read()
    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    with open(tmp_path, "wb") as f:
        f.write(data)

    # Update only the Transaction sheet
    try:
        handler = ExcelHandler(tmp_path, sheet_name="Transaction")
        handler.append_transactions(transactions, update_existing=bool(update_existing))
    except Exception as e:
        safe_remove(tmp_path)
        return JSONResponse({"ok": False, "error": f"Excel update failed: {e}"}, status_code=500)

    token = secrets.token_urlsafe(16)
    base_name = (workbook.filename or "Expenditure_Tracker.xlsx").rsplit(".", 1)[0]
    out_name = f"{base_name}_updated.xlsx"

    DOWNLOADS[token] = DownloadItem(
        path=tmp_path,
        filename=out_name,
        created_at=time.time(),
    )

    total_amount = sum(float(t.amount) for t in transactions)
    total_fees = sum(float(t.fee) for t in transactions)

    return {
        "ok": True,
        "download_token": token,
        "parsed": len(transactions),
        "inserted": inserted,
        "duplicates": duplicates,
        "total_amount": total_amount,
        "total_fees": total_fees,
        "ttl_seconds": DOWNLOAD_TTL_SECONDS,
    }


@app.get("/download/{token}")
def download(token: str):
    cleanup_expired_downloads()

    item = DOWNLOADS.pop(token, None)
    if not item:
        return FileResponse(
            str(WEB_DIR / "expired.html") if (WEB_DIR / "expired.html").exists() else str(WEB_DIR / "index.html"),
            media_type="text/html",
        )

    return FileResponse(
        path=item.path,
        filename=item.filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(safe_remove, item.path),
    )