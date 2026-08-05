from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional, Sequence

from src.crm.columns import COLUMNS, DEFAULT_STATUS, MANUAL_COLUMNS
from src.crm.sync import build_sqlite_rows, merge_rows, sync_manual_to_sqlite
from src.crm.workbook import (
    create_workbook,
    normalise_row,
    openpyxl_available,
    read_workbook,
    validate_row,
    write_workbook,
)
from src.settings import CRM_WORKBOOK_PATH

logger = logging.getLogger("lead.crm.service")

# Public CRM facade. SQLite is the technical store; the .xlsx workbook is the
# editable CRM layer. Everything is best-effort: sync/load/save never raise and
# degrade to empty rows / clear issues so the dashboard stays usable.


class CrmService:
    """Local Excel CRM: sync, merge, save and reload a ``lead_crm.xlsx`` file."""

    def __init__(
        self,
        db_path: Path,
        workbook_path: Optional[Path] = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._workbook_path = Path(workbook_path or CRM_WORKBOOK_PATH)

    # -- public API ----------------------------------------------------------

    def columns(self) -> Sequence[str]:
        return COLUMNS

    def manual_columns(self) -> Sequence[str]:
        return MANUAL_COLUMNS

    def auto_columns(self) -> Sequence[str]:
        return [column for column in COLUMNS if column not in MANUAL_COLUMNS]

    def default_status(self) -> str:
        return DEFAULT_STATUS

    def workbook_path(self) -> Path:
        return self._workbook_path

    def openpyxl_available(self) -> bool:
        return openpyxl_available()

    def sync(self) -> list[dict[str, Any]]:
        """Refresh the workbook from SQLite (manual edits preserved) and reload."""
        connection = self._connect()
        try:
            auto_rows = build_sqlite_rows(connection)
            manual_rows = read_workbook(self._workbook_path) or []
            merged = merge_rows(auto_rows, manual_rows)
            if self._workbook_path.exists():
                write_workbook(self._workbook_path, merged)
            else:
                create_workbook(self._workbook_path, merged)
            return merged
        finally:
            connection.close()

    def load(self) -> list[dict[str, Any]]:
        """Load the latest workbook rows (creating + syncing it when missing)."""
        if not self._workbook_path.exists():
            return self.sync()
        rows = read_workbook(self._workbook_path)
        if rows is None:
            return self.sync()
        return rows

    def save(self, rows: Sequence[dict[str, Any]]) -> tuple[bool, list[str]]:
        """Validate + persist the edited rows: workbook first, then SQLite.

        Returns ``(ok, issues)``. Invalid cells are normalised away (issues
        explain what happened) but never crash the app.
        """
        if not rows:
            write_workbook(self._workbook_path, [])
            return True, []

        known = frozenset(self._known_lead_ids())
        issues: list[str] = []
        valid_rows: list[dict[str, Any]] = []
        for row in rows:
            try:
                lead_id = int(row.get("lead_id"))
            except (TypeError, ValueError):
                issues.append("A row was skipped: missing or invalid lead_id.")
                continue
            if lead_id not in known:
                issues.append(f"lead {lead_id}: unknown, row skipped.")
                continue
            ok, row_issues = validate_row(row, known_lead_ids=known)
            if not ok:
                issues.extend(row_issues)
            valid_rows.append(normalise_row(row))
        if not valid_rows:
            return False, issues or ["No valid rows to save."]

        write_workbook(self._workbook_path, valid_rows)
        connection = self._connect()
        try:
            sync_manual_to_sqlite(connection, valid_rows)
        finally:
            connection.close()
        return True, issues

    def reload(self) -> list[dict[str, Any]]:
        """Re-read the workbook from disk (reflects external edits)."""
        return self.load()

    def rebuild(self) -> list[dict[str, Any]]:
        """Explicit full rebuild: regenerate every row from SQLite.

        Discards manual workbook edits — callers must confirm first.
        """
        connection = self._connect()
        try:
            auto_rows = build_sqlite_rows(connection)
            if self._workbook_path.exists():
                write_workbook(self._workbook_path, auto_rows)
            else:
                create_workbook(self._workbook_path, auto_rows)
            return auto_rows
        finally:
            connection.close()

    def statistics(self, rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
        """Small summary counts for the dashboard header."""
        statuses: dict[str, int] = {}
        for row in rows:
            status = str(row.get("status") or "").strip() or DEFAULT_STATUS
            statuses[status] = statuses.get(status, 0) + 1
        return {"total": len(rows), "by_status": statuses}

    # -- internals -----------------------------------------------------------

    def _known_lead_ids(self) -> set[int]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT id FROM leads").fetchall()
            return {int(row["id"]) for row in rows}
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._db_path))
        connection.row_factory = sqlite3.Row
        return connection