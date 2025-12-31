from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union, cast

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.workbook import Workbook as OpenPyxlWorkbook
from openpyxl.worksheet.worksheet import Worksheet

from scr.models.transaction import Transaction


class ExcelHandler:
    """
    Updates only one worksheet (default: 'Transaction') in an existing workbook.

    Key behaviors:
    - Does not delete/overwrite other sheets in the workbook.
    - Does not clear the target sheet.
    - Writes only known columns (required headers). Any extra/custom columns remain intact.
    - Uses Transaction Code to detect duplicates.
      - update_existing=False: duplicates are skipped
      - update_existing=True: existing rows are updated (upsert) for known columns only
    """

    DEFAULT_HEADERS = [
        "Transaction Code",
        "Date",
        "Type",
        "Amount",
        "Fee",
        "Sender",
        "Recipient",
        "Balance",
    ]

    def __init__(self, excel_path: str, sheet_name: str = "Transaction"):
        self.excel_path = Path(excel_path)
        self.sheet_name = sheet_name

        self._ensure_workbook_exists()
        self._ensure_sheet_exists()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def append_transactions(self, transactions: List[Transaction], update_existing: bool = False) -> bool:
        """
        Append transactions into the configured sheet.

        If update_existing=True:
          - If Transaction Code exists, update known columns on that row.
          - Otherwise append a new row.

        If update_existing=False:
          - If Transaction Code exists, skip it.
          - Otherwise append a new row.
        """
        try:
            wb = load_workbook(self.excel_path)
            ws = self._get_or_create_sheet(wb)

            header_map = self._get_or_create_headers(ws)
            code_col = header_map["Transaction Code"]
            code_to_row = self._build_code_index(ws, code_col)

            for tx in transactions:
                record = self._tx_to_row_values(tx)
                tx_code = str(record.get("Transaction Code") or "").strip()
                if not tx_code:
                    continue

                existing_row = code_to_row.get(tx_code)
                if existing_row is not None:
                    if update_existing:
                        self._write_record_to_row(ws, header_map, existing_row, record)
                    continue

                new_row = ws.max_row + 1
                self._write_record_to_row(ws, header_map, new_row, record)
                code_to_row[tx_code] = new_row

            self._auto_fit_columns(ws, header_map)
            wb.save(self.excel_path)
            return True
        except Exception as e:
            print(f"Error updating Excel workbook: {e}")
            return False

    def upsert_from_database(self, db_rows: List[Dict[str, Any]], update_existing: bool = True) -> bool:
        """
        Ensures all DB transactions exist in the sheet.
        Default behavior updates existing rows and appends missing ones.

        This does not clear the sheet.
        """
        try:
            wb = load_workbook(self.excel_path)
            ws = self._get_or_create_sheet(wb)

            header_map = self._get_or_create_headers(ws)
            code_col = header_map["Transaction Code"]
            code_to_row = self._build_code_index(ws, code_col)

            for row in db_rows:
                record = self._db_dict_to_row_values(row)
                tx_code = str(record.get("Transaction Code") or "").strip()
                if not tx_code:
                    continue

                existing_row = code_to_row.get(tx_code)
                if existing_row is not None:
                    if update_existing:
                        self._write_record_to_row(ws, header_map, existing_row, record)
                    continue

                new_row = ws.max_row + 1
                self._write_record_to_row(ws, header_map, new_row, record)
                code_to_row[tx_code] = new_row

            self._auto_fit_columns(ws, header_map)
            wb.save(self.excel_path)
            return True
        except Exception as e:
            print(f"Error upserting DB rows to Excel: {e}")
            return False

    def export_from_database(self, db_manager) -> bool:
        """
        Backward-compatible method name for your GUI.
        Pulls all DB rows and upserts them into the configured sheet.
        """
        rows = db_manager.get_all_transactions()
        return self.upsert_from_database(rows, update_existing=True)

    # ---------------------------------------------------------------------
    # Workbook / Sheet helpers
    # ---------------------------------------------------------------------
    def _ensure_workbook_exists(self) -> None:
        """
        Create a new workbook only if it does not exist.
        If you pass an existing "Expenditure Tracker" workbook, this does nothing.
        """
        if self.excel_path.exists():
            return

        wb: OpenPyxlWorkbook = Workbook()

        # Some type stubs mark wb.active as Optional; guard for static type checkers.
        ws_opt = getattr(wb, "active", None)
        if ws_opt is None:
            ws: Worksheet = cast(Worksheet, wb.create_sheet(self.sheet_name))
        else:
            ws = cast(Worksheet, ws_opt)
            ws.title = self.sheet_name

        for col_idx, h in enumerate(self.DEFAULT_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)

        self._format_header(ws, len(self.DEFAULT_HEADERS))
        self._auto_fit_columns(ws, {h: i for i, h in enumerate(self.DEFAULT_HEADERS, start=1)})
        wb.save(self.excel_path)

    def _ensure_sheet_exists(self) -> None:
        wb = load_workbook(self.excel_path)
        _ = self._get_or_create_sheet(wb)
        wb.save(self.excel_path)

    def _get_or_create_sheet(self, wb: OpenPyxlWorkbook) -> Worksheet:
        """
        Get sheet by name (case-insensitive). If missing, create it.
        """
        target = self.sheet_name.strip().lower()
        for name in wb.sheetnames:
            if name.strip().lower() == target:
                return cast(Worksheet, wb[name])
        return cast(Worksheet, wb.create_sheet(self.sheet_name))

    def _get_or_create_headers(self, ws: Worksheet) -> Dict[str, int]:
        """
        Returns mapping: header name -> column index.
        If the sheet is missing required headers, it appends them to the end of row 1.
        It does not delete or reorder existing columns/headers.
        """
        max_col = ws.max_column if ws.max_column and ws.max_column > 0 else 0

        # If sheet is effectively empty, initialize with required headers.
        if ws.max_row < 1 or max_col == 0:
            for col_idx, h in enumerate(self.DEFAULT_HEADERS, start=1):
                ws.cell(row=1, column=col_idx, value=h)
            self._format_header(ws, len(self.DEFAULT_HEADERS))
            return {h: i for i, h in enumerate(self.DEFAULT_HEADERS, start=1)}

        # If header row is blank across current columns, initialize it.
        if all(ws.cell(1, c).value is None for c in range(1, max_col + 1)):
            for col_idx, h in enumerate(self.DEFAULT_HEADERS, start=1):
                ws.cell(row=1, column=col_idx, value=h)
            self._format_header(ws, len(self.DEFAULT_HEADERS))
            return {h: i for i, h in enumerate(self.DEFAULT_HEADERS, start=1)}

        # Read existing headers from row 1
        existing_headers: Dict[str, int] = {}
        scan_cols = max(max_col, len(self.DEFAULT_HEADERS))
        for col_idx in range(1, scan_cols + 1):
            v = ws.cell(1, col_idx).value
            if v is None:
                continue
            header = str(v).strip()
            if header:
                existing_headers[header] = col_idx

        # Append missing required headers to the end
        next_col = ws.max_column + 1
        changed = False
        for h in self.DEFAULT_HEADERS:
            if h not in existing_headers:
                ws.cell(row=1, column=next_col, value=h)
                existing_headers[h] = next_col
                next_col += 1
                changed = True

        if changed:
            self._format_header(ws, ws.max_column)

        # Ensure required headers exist
        for h in self.DEFAULT_HEADERS:
            if h not in existing_headers:
                raise ValueError(f"Failed to create required header: {h}")

        return existing_headers

    def _format_header(self, ws: Worksheet, header_col_count: int) -> None:
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center")

        for col_idx in range(1, header_col_count + 1):
            cell = ws.cell(row=1, column=col_idx)
            if cell.value is None:
                continue
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align

    def _build_code_index(self, ws: Worksheet, code_col: int) -> Dict[str, int]:
        """
        Builds an index mapping Transaction Code -> row number.
        """
        code_to_row: Dict[str, int] = {}
        if ws.max_row < 2:
            return code_to_row

        for r in range(2, ws.max_row + 1):
            v = ws.cell(r, code_col).value
            if v is None:
                continue
            code = str(v).strip()
            if code and code not in code_to_row:
                code_to_row[code] = r
        return code_to_row

    # ---------------------------------------------------------------------
    # Writing helpers
    # ---------------------------------------------------------------------
    def _write_record_to_row(self, ws: Worksheet, header_map: Dict[str, int], row_idx: int, record: Dict[str, Any]) -> None:
        """
        Writes only keys present in `record` into their corresponding columns.
        Any other columns on the row are left untouched.
        """
        for header, col_idx in header_map.items():
            if header not in record:
                continue

            value = record[header]
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            
            if (header_noticed := header == "Date"):
                cell.number_format = "yyyy-mm-dd hh:mm:ss"
            elif header in ("Amount", "Fee", "Balance"):
                cell.number_format = "#,##0.00"


            # if header noticed:= (header == "Date"):
            #     cell.number_format = "yyyy-mm-dd hh:mm:ss"
            # elif header in ("Amount", "Fee", "Balance"):
            #     cell.number_format = "#,##0.00"

    def _auto_fit_columns(self, ws: Worksheet, header_map: Dict[str, int]) -> None:
        """
        Best-effort column width adjustment for the target sheet only.
        """
        for header, col_idx in header_map.items():
            max_len = len(header)
            for r in range(2, min(ws.max_row, 5000) + 1):
                v = ws.cell(r, col_idx).value
                if v is None:
                    continue
                max_len = max(max_len, len(str(v)))
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 50)

    # ---------------------------------------------------------------------
    # Normalization helpers
    # ---------------------------------------------------------------------
    def _as_float(self, value: Any, default: float = 0.0) -> float:
        """
        Convert a value that may be None/number/string to float.
        Handles values like 'KSh 1,234.00', '1,234', '-', ''.
        """
        if value is None:
            return default

        if isinstance(value, (int, float)):
            return float(value)

        s = str(value).strip()
        if s == "" or s == "-":
            return default

        s = s.replace(",", "")
        s = s.replace("KSh", "").replace("ksh", "").strip()

        try:
            return float(s)
        except ValueError:
            return default

    def _tx_to_row_values(self, tx: Transaction) -> Dict[str, Any]:
        balance_value: Union[float, str] = "" if tx.balance is None else float(tx.balance)

        return {
            "Transaction Code": tx.transaction_code,
            "Date": tx.date,  # datetime preferred for Excel
            "Type": (tx.transaction_type or "").capitalize(),
            "Amount": float(tx.amount),
            "Fee": float(tx.fee),
            "Sender": tx.sender or "",
            "Recipient": tx.recipient or "",
            "Balance": balance_value,
        }

    def _db_dict_to_row_values(self, row: Dict[str, Any]) -> Dict[str, Any]:
        raw_date = row.get("date")
        dt_value: Any = raw_date
        if isinstance(raw_date, str):
            try:
                dt_value = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt_value = raw_date

        amount = self._as_float(row.get("amount"), default=0.0)
        fee = self._as_float(row.get("fee"), default=0.0)

        balance_raw = row.get("balance")
        balance_value: Union[float, str] = "" if balance_raw is None else self._as_float(balance_raw, default=0.0)

        return {
            "Transaction Code": str(row.get("transaction_code") or "").strip(),
            "Date": dt_value,
            "Type": str(row.get("transaction_type") or "").capitalize(),
            "Amount": amount,
            "Fee": fee,
            "Sender": str(row.get("sender") or ""),
            "Recipient": str(row.get("recipient") or ""),
            "Balance": balance_value,
        }