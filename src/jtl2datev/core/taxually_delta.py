"""Delta computation for Taxually XLSX exports.

Compares the current invoice set against a previous XLSX archive run.
Key column: "Invoice number" (column 6, index 5).
"""
from __future__ import annotations

import datetime
import logging
import shutil
from pathlib import Path

import openpyxl

from jtl2datev.core.models import RawInvoice
from jtl2datev.core.taxually import TAXUALLY_COLUMNS, format_taxually_xlsx

logger = logging.getLogger(__name__)

_KEY_COLUMN = "Invoice number"
_KEY_COL_IDX = TAXUALLY_COLUMNS.index(_KEY_COLUMN)  # 0-based

# Date columns that get shifted (0-based indices in TAXUALLY_COLUMNS)
_SHIFT_COL_INDICES = {
    TAXUALLY_COLUMNS.index("Transaction date"),
}


class NoBaselineError(Exception):
    """Raised when no baseline XLSX can be found for the requested period."""


def _load_xlsx_invoice_numbers(path: Path) -> set[str]:
    """Read all invoice numbers from the 'Your data' sheet of an XLSX archive."""
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    ws = wb["Your data"]

    invoice_numbers: set[str] = set()
    header_skipped = False
    for row in ws.iter_rows(values_only=True):
        if not header_skipped:
            header_skipped = True
            continue
        key = row[_KEY_COL_IDX]
        if key is not None:
            invoice_numbers.add(str(key))

    wb.close()
    return invoice_numbers


def compute_taxually_delta(
    current: list[RawInvoice],
    previous_archive: Path,
) -> list[RawInvoice]:
    """Return invoices from *current* whose invoice_no is not in *previous_archive*."""
    archived_keys = _load_xlsx_invoice_numbers(previous_archive)
    delta = [inv for inv in current if inv.invoice_no not in archived_keys]
    logger.info(
        "Taxually delta: %d new invoices out of %d (archive had %d keys)",
        len(delta),
        len(current),
        len(archived_keys),
    )
    return delta


def write_taxually_delta_xlsx(
    invoices: list[RawInvoice],
    path: Path,
    shift_to: datetime.date | None = None,
) -> None:
    """Write delta invoices as XLSX.

    If *shift_to* is given, overrides the Transaction date of every row to
    the first day of *shift_to*'s month (used for subsequent-month supplements).
    """
    if shift_to is None:
        format_taxually_xlsx(invoices, path)
        return

    # Date-shift: replace invoice_date so format_taxually_xlsx picks it up.
    # We do this by creating temporary wrapper objects with patched invoice_date.
    first_of_month = datetime.date(shift_to.year, shift_to.month, 1)

    shifted: list[RawInvoice] = [
        inv.model_copy(update={"invoice_date": first_of_month})
        for inv in invoices
    ]
    format_taxually_xlsx(shifted, path)
    logger.info("Taxually delta date-shifted to %s: %d invoices", first_of_month, len(invoices))


# ── Archive helpers (XLSX-aware, mirrors archive.archive_export logic) ────────

def archive_taxually_export(
    source: Path,
    *,
    archive_root: Path,
    period: str,
    now: datetime.datetime | None = None,
) -> Path:
    """Copy *source* XLSX into the taxually archive tree; return destination path."""
    ts = (now or datetime.datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    dest_dir = archive_root / "taxually" / period
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{ts}.xlsx"
    shutil.copy2(source, dest)
    logger.info("Archived Taxually XLSX %s → %s", source, dest)
    return dest


def archive_taxually_delta(
    source: Path,
    *,
    archive_root: Path,
    period: str,
    now: datetime.datetime | None = None,
) -> Path:
    """Copy *source* delta XLSX into the taxually deltas archive; return destination."""
    ts = (now or datetime.datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    dest_dir = archive_root / "taxually" / period / "deltas"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{ts}.xlsx"
    shutil.copy2(source, dest)
    logger.info("Archived Taxually delta XLSX %s → %s", source, dest)
    return dest


def latest_taxually_archive(
    archive_root: Path,
    *,
    period: str,
) -> Path | None:
    """Return the lexicographically last XLSX archive for *period*, or None."""
    period_dir = archive_root / "taxually" / period
    if not period_dir.is_dir():
        return None
    candidates = sorted(period_dir.glob("*.xlsx"))
    if not candidates:
        return None
    return candidates[-1]
