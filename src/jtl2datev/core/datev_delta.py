"""Delta computation for DATEV EXTF Buchungsstapel exports.

Match strategy: the first whitespace-separated token of the ``Buchungstext``
column is used as the match key ("Belegnr"). This equals the JTL invoice /
credit-note number (e.g. ``R-DE-249030238-2026-322``) and is unique per
DATEV booking line, because the engine writes exactly one Buchungstext per
invoice and groups lines by (Konto, BU-Schlüssel).

``Belegfeld 1`` is *not* used as the primary key because multiple DATEV rows
for the same invoice can share the same ``Belegfeld 1`` value (Storno +
original; or multiple account groups per invoice).

EXTF file format:
  - Encoding: cp1252
  - Line terminator: CRLF
  - Row 1: EXTF metadata header (semicolon-delimited, 124 fields)
  - Row 2: column names
  - Rows 3+: data
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_BUCHUNGSTEXT_COL = "Buchungstext"


class NoBaselineError(Exception):
    """Raised when no baseline DATEV archive can be found for the requested period."""


def _match_key(row: dict[str, str]) -> str:
    """Extract Belegnr (first whitespace token) from Buchungstext."""
    buchungstext = row.get(_BUCHUNGSTEXT_COL, "")
    return buchungstext.split(" ", 1)[0].strip()


def read_extf_csv(path: Path) -> tuple[str, str, list[dict[str, str]]]:
    """Read a DATEV EXTF CSV file.

    Returns (extf_header_line, column_header_line, rows) where rows is a list
    of dicts keyed by the column names from line 2.
    """
    with path.open(encoding="cp1252", newline="") as fh:
        lines = fh.read().splitlines()

    if len(lines) < 2:
        raise ValueError(f"EXTF file too short (expected ≥2 lines): {path}")

    extf_header_line = lines[0]
    column_header_line = lines[1]

    fieldnames = column_header_line.split(";")

    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        if not line.strip():
            continue
        values = list(csv.reader([line], delimiter=";"))[0]
        # Pad or trim to match fieldnames length
        while len(values) < len(fieldnames):
            values.append("")
        row = dict(zip(fieldnames, values))
        rows.append(row)

    return extf_header_line, column_header_line, rows


def _group_by_key(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = _match_key(row)
        groups.setdefault(key, []).append(row)
    return groups


def _rows_equal(a: list[dict[str, str]], b: list[dict[str, str]]) -> bool:
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        if ra != rb:
            return False
    return True


def compute_delta(
    *,
    current_rows: list[dict[str, str]],
    baseline_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    """Return (delta_rows, new_keys, changed_keys).

    delta_rows: rows for new + changed Belegnr entries.
    new_keys: Belegnr values not present in baseline.
    changed_keys: Belegnr values present in both but with differing rows.
    """
    current_groups = _group_by_key(current_rows)
    baseline_groups = _group_by_key(baseline_rows)

    new_keys: list[str] = []
    changed_keys: list[str] = []
    delta_rows: list[dict[str, str]] = []

    for key, rows in current_groups.items():
        if key not in baseline_groups:
            new_keys.append(key)
            delta_rows.extend(rows)
        elif not _rows_equal(rows, baseline_groups[key]):
            changed_keys.append(key)
            logger.info("Changed DATEV document detected: %s", key)
            delta_rows.extend(rows)

    return delta_rows, new_keys, changed_keys


def write_delta_extf(
    delta_rows: list[dict[str, str]],
    *,
    out_path: Path,
    extf_header_line: str,
    column_header_line: str,
) -> None:
    """Write delta rows as a valid DATEV EXTF file.

    Row 1 is the EXTF metadata header (unchanged from the fresh full export).
    Row 2 is the column header. Rows 3+ are the delta data rows.
    Encoding: cp1252, line terminator: CRLF.
    """
    fieldnames = column_header_line.split(";")

    with out_path.open("w", encoding="cp1252", newline="") as fh:
        fh.write(extf_header_line)
        fh.write("\r\n")
        fh.write(column_header_line)
        fh.write("\r\n")

        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        for row in delta_rows:
            writer.writerow([row.get(col, "") for col in fieldnames])

    logger.info("DATEV delta CSV written: %d rows → %s", len(delta_rows), out_path)


def load_baseline(baseline_path: Path) -> tuple[str, str, list[dict[str, str]]]:
    """Load a DATEV EXTF baseline file. Returns (extf_header, col_header, rows)."""
    return read_extf_csv(baseline_path)
