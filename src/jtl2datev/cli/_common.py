"""Geteilte Helfer für alle CLI-Commands: Datums-Parsing, Range-Validierung."""
from __future__ import annotations

import datetime as dt
import re

import click

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _parse_month(month_str: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' and return (year, month). Raises SystemExit on bad input."""
    if not _MONTH_RE.fullmatch(month_str):
        click.echo(f"Ungültiges Monatsformat: {month_str!r}. Erwartet: YYYY-MM (z.B. 2026-04)")
        raise SystemExit(1)
    year_s, month_s = month_str.split("-")
    return int(year_s), int(month_s)


def _month_date_range(year: int, month: int) -> tuple[dt.date, dt.date]:
    date_from = dt.date(year, month, 1)
    if month == 12:
        date_to_excl = dt.date(year + 1, 1, 1)
    else:
        date_to_excl = dt.date(year, month + 1, 1)
    return date_from, date_to_excl - dt.timedelta(days=1)


def _resolve_date_range(
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    month_str: str | None,
) -> tuple[dt.date, dt.date]:
    """Validate and resolve date input. Exactly one of (--from + --to) or
    --month must be provided. Returns (date_from, date_to_inclusive)."""
    has_range = date_from is not None and date_to is not None
    has_partial_range = (date_from is None) ^ (date_to is None)
    has_month = month_str is not None

    if has_partial_range:
        raise click.BadParameter("--from und --to müssen zusammen angegeben werden.")
    if has_month and has_range:
        raise click.BadParameter("Entweder --month oder --from/--to, nicht beides.")
    if not has_month and not has_range:
        raise click.BadParameter("Bitte entweder --month YYYY-MM oder --from/--to angeben.")
    if has_month:
        year, month = _parse_month(month_str)  # type: ignore[arg-type]
        return _month_date_range(year, month)
    assert date_from is not None and date_to is not None
    return date_from.date(), date_to.date()
