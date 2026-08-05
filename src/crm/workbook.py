from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from src.crm.columns import COLUMNS, DATE_COLUMNS, SHEET_NAME, URL_COLUMNS

# Low-level xlsx I/O (openpyxl, lazy import). The workbook is app-owned: we
# always rewrite our canonical column set, keep a local .bak before rewrites,
# and skip malformed rows instead of raising.

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def openpyxl_available() -> bool:
    try:  # pragma: no cover - environment probing
        import openpyxl  # noqa: F401

        return True
    except Exception:
        return False


def _is_url(value: Any) -> bool:
    return isinstance(value, str) and value.strip().startswith(("http://", "https://"))


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    text = str(value).strip()
    return text or None


def validate_row(row: Mapping[str, Any], *, known_lead_ids: frozenset[int]) -> tuple[bool, list[str]]:
    """Validate one workbook row. Returns ``(ok, issues)``; never raises."""
    issues: list[str] = []

    raw_id = row.get("lead_id")
    try:
        lead_id = int(raw_id)
    except (TypeError, ValueError):
        return False, ["lead_id is missing or not an integer."]
    if lead_id not in known_lead_ids:
        return False, [f"lead_id {lead_id} is not a known lead."]

    for column in COLUMNS:
        value = row.get(column)
        if column in URL_COLUMNS:
            if value is None or str(value).strip() == "":
                continue
            if not _is_url(value):
                issues.append(f"{column} is not a valid URL and was left blank.")
        if column in DATE_COLUMNS:
            text = _clean_text(value)
            if text and not _ISO_DATE_RE.match(text):
                issues.append(f"{column} is not a YYYY-MM-DD date and was left blank.")
    return (not issues, issues)


def normalise_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Best-effort normalisation: blanks stay empty, junk values become None."""
    outcome: dict[str, Any] = {}
    for column in COLUMNS:
        value = row.get(column)
        if column in URL_COLUMNS:
            if value is None or str(value).strip() == "":
                outcome[column] = None
            elif _is_url(value):
                outcome[column] = value.strip()
            else:
                outcome[column] = None
        elif column in DATE_COLUMNS or column in ("last_contacted", "next_follow_up"):
            text = _clean_text(value)
            outcome[column] = text if text and _ISO_DATE_RE.match(text) else None
        else:
            text = _clean_text(value)
            outcome[column] = text
    return outcome


def read_workbook(path: Path) -> Optional[list[dict[str, Any]]]:
    """Read the "Leads" sheet into row dicts (None when the file is missing).

    Blank rows and rows without a usable leading value are skipped safely.
    """
    if not Path(path).exists():
        return None
    import openpyxl

    rows: list[dict[str, Any]] = []
    workbook = openpyxl.load_workbook(Path(path), read_only=True, data_only=True)
    try:
        sheet = workbook[SHEET_NAME] if SHEET_NAME in workbook.sheetnames else workbook.worksheets[0]
    except IndexError:
        return rows
    header: list[str] = []
    for index, row in enumerate(sheet.iter_rows(values_only=True)):
        if not any(cell is not None for cell in row):
            continue
        if index == 0:
            header = [str(cell).strip() if cell is not None else "" for cell in row]
            continue
        if not row[0]:
            continue
        record = {name: value for name, value in zip(header, row) if name}
        if "lead_id" in record:
            rows.append(record)
    workbook.close()
    return rows


def _write_rows(workbook: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    sheet = workbook.active
    sheet.title = SHEET_NAME
    sheet.append(list(COLUMNS))
    for row in rows:
        sheet.append([row.get(column) for column in COLUMNS])


def create_workbook(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Create a brand-new workbook with the canonical headers + rows."""
    import openpyxl

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    workbook = openpyxl.Workbook()
    _write_rows(workbook, rows)
    workbook.save(path)
    workbook.close()


def write_workbook(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Rewrite an existing workbook, keeping a local .bak copy first."""
    import openpyxl

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_suffix(".bak.xlsx")
    if target.exists():
        shutil.copy2(target, backup)
    workbook = openpyxl.Workbook()
    _write_rows(workbook, rows)
    workbook.save(target)
    workbook.close()