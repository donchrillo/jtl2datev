"""Delta computation for CSV exports keyed by DocumentID.

Works on any semicolon-delimited CSV where one column is the document key.
Intended for DutyPay; generic enough to reuse for Taxually/DATEV later.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MONTH_ABBR: tuple[str, ...] = (
    "", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)

# Fields overwritten in the delta output when --shift-to-period is active.
# User has manually done this for years — enables direct upload as subsequent-month supplement.
_SHIFT_DATE_FIELDS = ("DepartureDate", "ArrivalDate", "DocumentDate")
_SHIFT_PERIOD_FIELD = "ReportingPeriod"
# PostingDateInvoice is intentionally NOT shifted (internal reference to original document).


class NoBaselineError(Exception):
    """Raised when no baseline CSV can be found for the requested period."""


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        return list(reader)


def _group_by_doc(rows: list[dict[str, str]], key_col: str) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        doc_id = row.get(key_col, "")
        groups.setdefault(doc_id, []).append(row)
    return groups


def _rows_equal(a: list[dict[str, str]], b: list[dict[str, str]]) -> bool:
    """Compare two groups of rows ignoring Positions-Nr. (renumbered on write)."""
    if len(a) != len(b):
        return False
    skip = {"Positions-Nr."}
    for ra, rb in zip(a, b):
        if {k: v for k, v in ra.items() if k not in skip} != {k: v for k, v in rb.items() if k not in skip}:
            return False
    return True


def _shift_row(row: dict[str, str], target_year: int, target_month: int) -> dict[str, str]:
    month_abbr = _MONTH_ABBR[target_month]
    new_date = f"01.{target_month:02d}.{target_year}"
    new_period = f"{target_year}-{month_abbr}"

    shifted = dict(row)
    shifted[_SHIFT_PERIOD_FIELD] = new_period
    for field in _SHIFT_DATE_FIELDS:
        if field in shifted:
            shifted[field] = new_date
    return shifted


def compute_delta(
    *,
    current_rows: list[dict[str, str]],
    baseline_rows: list[dict[str, str]],
    key_col: str = "DocumentID",
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    """Return (delta_rows, new_doc_ids, changed_doc_ids).

    delta_rows: rows for new + changed documents (original Positions-Nr. preserved).
    new_doc_ids: DocumentIDs not in baseline.
    changed_doc_ids: DocumentIDs present in both but with differing rows.
    """
    current_groups = _group_by_doc(current_rows, key_col)
    baseline_groups = _group_by_doc(baseline_rows, key_col)

    new_doc_ids: list[str] = []
    changed_doc_ids: list[str] = []
    delta_rows: list[dict[str, str]] = []

    for doc_id, rows in current_groups.items():
        if doc_id not in baseline_groups:
            new_doc_ids.append(doc_id)
            delta_rows.extend(rows)
        elif not _rows_equal(rows, baseline_groups[doc_id]):
            changed_doc_ids.append(doc_id)
            logger.info("Changed document detected: %s", doc_id)
            delta_rows.extend(rows)

    return delta_rows, new_doc_ids, changed_doc_ids


def write_delta_csv(
    delta_rows: list[dict[str, str]],
    *,
    out_path: Path,
    fieldnames: list[str],
    shift_to_period: tuple[int, int] | None = None,
) -> None:
    """Write delta rows to *out_path*, renumbering Positions-Nr. from 1.

    If *shift_to_period* is given as (year, month), date-related fields are
    overwritten in the output CSV (not in the archived full export).
    """
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=";",
                                quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        writer.writeheader()

        for pos_nr, row in enumerate(delta_rows, start=1):
            out_row = dict(row)
            out_row["Positions-Nr."] = str(pos_nr)

            if shift_to_period is not None:
                year, month = shift_to_period
                out_row = _shift_row(out_row, year, month)

            writer.writerow(out_row)

    logger.info("Delta CSV written: %d rows → %s", len(delta_rows), out_path)


def load_baseline(baseline_path: Path) -> list[dict[str, str]]:
    return _load_csv(baseline_path)
