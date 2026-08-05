from __future__ import annotations

"""Local Excel CRM workbook (Phase 18).

A lightweight, fully-local CRM layer: one ``data/lead_crm.xlsx`` workbook with
a single "Leads" sheet, auto-filled from the project's SQLite data. Manual
fields (status, notes, follow-ups, assignment, best contact method) are
user-owned and always win on merge; SQLite stays the technical store and the
workbook is the editable, user-facing CRM file.
"""

from src.crm.columns import (
    AUTO_COLUMNS,
    COLUMNS,
    DEFAULT_STATUS,
    MANUAL_COLUMNS,
)
from src.crm.service import CrmService
from src.crm.sync import build_sqlite_rows, merge_rows, sync_manual_to_sqlite
from src.crm.workbook import (
    create_workbook,
    normalise_row,
    openpyxl_available,
    read_workbook,
    validate_row,
    write_workbook,
)