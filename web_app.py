from __future__ import annotations

import os
import tempfile
from typing import List, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from scr.database.db_manager import DatabaseManager
from scr.excel.excel_handler import ExcelHandler
from scr.parsers.mpesa_parser import MPesaParser

app = FastAPI()

parser = MPesaParser()
db = DatabaseManager("mpesa_transactions.db")


def split_messages(text: str) -> List[str]:
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    return blocks if blocks else ([text.strip()] if text.strip() else [])


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
    <html>
      <head>
        <title>M-Pesa Transaction Manager</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body style="font-family: Arial, sans-serif; max-width: 900px; margin: 20px auto;">
        <h2>M-Pesa Transaction Manager</h2>

        <form action="/process" method="post" enctype="multipart/form-data">
          <label for="messages">Paste M-Pesa messages:</label><br/>
          <textarea id="messages" name="messages" rows="12" style="width: 100%;" required></textarea><br/><br/>

          <label for="workbook">Upload Expenditure Tracker workbook (.xlsx):</label><br/>
          <input id="workbook" type="file" name="workbook" accept=".xlsx" required /><br/><br/>

          <label>
            <input type="checkbox" name="update_existing" value="1" />
            Update existing rows (match by Transaction Code)
          </label><br/><br/>

          <button type="submit">Parse, Save, and Download Updated File</button>
        </form>

        <hr/>
        <p><a href="/stats" target="_blank">View stats (JSON)</a></p>
        <p><a href="/health" target="_blank">Health</a></p>
      </body>
    </html>
    """


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def stats():
    return db.get_statistics()


@app.post("/process")
async def process(
    messages: str = Form(...),
    workbook: UploadFile = File(...),
    update_existing: Optional[str] = Form(None),
):
    # Basic validation
    filename = (workbook.filename or "").lower()
    if not filename.endswith(".xlsx"):
        return HTMLResponse("Please upload a .xlsx file.", status_code=400)

    # Parse
    msg_list = split_messages(messages)
    transactions = parser.parse_multiple_messages(msg_list)
    if not transactions:
        return HTMLResponse("No valid transactions parsed. Check message format.", status_code=400)

    # Save to DB
    db.insert_multiple_transactions(transactions)

    # Write upload to a temp file, update only Transaction sheet, return updated file
    data = await workbook.read()

    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    with open(tmp_path, "wb") as f:
        f.write(data)

    try:
        handler = ExcelHandler(tmp_path, sheet_name="Transaction")
        handler.append_transactions(transactions, update_existing=bool(update_existing))
    except Exception as e:
        _safe_remove(tmp_path)
        return HTMLResponse(f"Excel update failed: {e}", status_code=500)

    return FileResponse(
        path=tmp_path,
        filename="Expenditure_Tracker_Updated.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(_safe_remove, tmp_path),
    )