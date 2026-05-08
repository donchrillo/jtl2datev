"""Exchange-rate storage and BMF-CSV importer.

Storage: data/exchange_rates.json in repo root.
Schema: {period: {currency: {value: str, source: "BMF"|"manual"}}}
Semantics: 1 EUR = value currency.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_RATES_PATH = Path(__file__).resolve().parents[3] / "data" / "exchange_rates.json"

# Month-index → "YYYY-MM" suffix (zero-based slot, first is 0 = January)
_BMF_MONTH_NAMES = [
    "januar", "februar", "märz", "marz", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "dezember",
]
_BMF_URL_TEMPLATE = (
    "https://www.bundesfinanzministerium.de/Datenportal/Daten/offene-daten/"
    "steuern-zoelle/umsatzsteuer-umrechnungskurse/datensaetze/"
    "uu-kurse-{year}-csv.csv?__blob=publicationFile"
)


# ---------------------------------------------------------------------------
# Storage API
# ---------------------------------------------------------------------------


def load_rates(path: Path = DEFAULT_RATES_PATH) -> dict[str, dict[str, dict[str, str]]]:
    """Returns the full rates dict (period → currency → {value, source}).

    Returns empty dict if file does not exist.
    """
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def get_rate(period: str, currency: str, path: Path = DEFAULT_RATES_PATH) -> Decimal | None:
    """Returns 1 EUR = X currency for the given period, or None if missing."""
    data = load_rates(path)
    entry = data.get(period, {}).get(currency.upper())
    if entry is None:
        return None
    return Decimal(entry["value"])


def set_rate(
    period: str,
    currency: str,
    value: Decimal | str,
    source: str = "manual",
    path: Path = DEFAULT_RATES_PATH,
) -> None:
    """Stores a rate. Creates file and parent directories as needed.

    Atomic write (tmp + os.replace).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_rates(path)

    period_data = data.setdefault(period, {})
    period_data[currency.upper()] = {"value": str(value), "source": source}

    _atomic_write(path, data)


def get_rates_for_period(period: str, path: Path = DEFAULT_RATES_PATH) -> dict[str, Decimal]:
    """Returns {currency: Decimal} for the period (only filled entries)."""
    data = load_rates(path)
    return {
        currency: Decimal(entry["value"])
        for currency, entry in data.get(period, {}).items()
    }


def _atomic_write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp_str = str(tmp)
    with open(tmp_str, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_str, str(path))


# ---------------------------------------------------------------------------
# BMF CSV Importer
# ---------------------------------------------------------------------------


def fetch_bmf_csv(year: int, timeout: int = 30) -> bytes:
    """Downloads CSV from BMF datensaetze URL. Raises on HTTP error."""
    url = _BMF_URL_TEMPLATE.format(year=year)
    logger.info("Downloading BMF exchange rates from %s", url)
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def parse_bmf_csv(content: bytes) -> dict[str, dict[str, str]]:
    """Parses BMF CSV bytes.

    Returns {period: {currency: value_str}} for all non-empty cells.
    Period format: 'YYYY-MM' (year extracted from title line, month from header).
    """
    text = content.decode("iso-8859-1")
    lines = [line.rstrip("\r") for line in text.split("\n")]

    # First non-empty line: title — extract year
    title_line = next((l for l in lines if l.strip()), "")
    year_match = re.search(r"\b(20\d{2})\b", title_line)
    if not year_match:
        raise ValueError(f"Cannot extract year from BMF CSV title: {title_line!r}")
    year = int(year_match.group(1))

    # Second non-empty line: header row
    header_line = ""
    header_idx = -1
    for i, line in enumerate(lines):
        if line.strip() and line != title_line:
            header_line = line
            header_idx = i
            break

    if not header_line:
        raise ValueError("Cannot find header row in BMF CSV")

    columns = [c.strip() for c in header_line.split(";")]
    # columns[0] = "Land", columns[1] = "Währung"
    # columns[2..] = month names like "Januar[1]", "Februar [2]", ...

    month_indices: list[int] = []  # maps column index → 1-based month number
    for col_i, col_name in enumerate(columns):
        if col_i < 2:
            month_indices.append(0)
            continue
        normalized = col_name.lower().split("[")[0].strip()
        # Remove trailing space / digits
        # Try to match a known month name
        month_num = _parse_month_name(normalized)
        month_indices.append(month_num)

    result: dict[str, dict[str, str]] = {}

    for line in lines[header_idx + 1 :]:
        if not line.strip():
            continue
        cells = [c.strip() for c in line.split(";")]
        if len(cells) < 3:
            continue
        # cells[0] = country, cells[1] = "1 Euro" (skip), cells[2..] = values
        for col_i in range(2, len(cells)):
            if col_i >= len(month_indices):
                break
            month_num = month_indices[col_i]
            if month_num == 0:
                continue
            cell = cells[col_i].strip()
            if not cell:
                continue
            parsed = _parse_bmf_cell(cell)
            if parsed is None:
                continue
            value_str, currency = parsed
            period = f"{year}-{month_num:02d}"
            result.setdefault(period, {})[currency] = value_str

    return result


def _parse_month_name(name: str) -> int:
    """Returns 1-based month number, 0 if not recognized."""
    # Normalize German umlauts that may survive after iso-8859-1 decode
    normalized = name.lower().replace("ä", "a").replace("ö", "o").replace("ü", "u")
    table = {
        "januar": 1, "februar": 2, "marz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    }
    return table.get(normalized, 0)


def _parse_bmf_cell(cell: str) -> tuple[str, str] | None:
    """Parses a BMF value cell like '4,2127 PLN' or '19.757,02 IDR'.

    Returns (value_str_with_dot, currency_code) or None.
    """
    parts = cell.rsplit(" ", 1)
    if len(parts) != 2:
        return None
    raw_num, currency = parts[0].strip(), parts[1].strip()
    if not currency or len(currency) > 4:
        return None
    # Remove thousands separator (.) then replace decimal comma with dot
    raw_num = raw_num.replace(".", "").replace(",", ".")
    try:
        # Validate it's a real number
        Decimal(raw_num)
    except Exception:
        return None
    return raw_num, currency.upper()


def import_bmf_rates(
    year: int,
    path: Path = DEFAULT_RATES_PATH,
    content: bytes | None = None,
) -> dict[str, list[str]]:
    """Imports BMF rates for the given year.

    If content is None, downloads from URL.
    Returns {period: [list of imported currencies]} for logging.

    Behaviour:
    - For each (period, currency) in BMF data:
      - If existing rate has source != 'BMF' (manual): SKIP, log warning.
      - Otherwise: write with source='BMF' (overwrites previous BMF value).
    - Atomic write at the end.
    """
    if content is None:
        content = fetch_bmf_csv(year)

    bmf_data = parse_bmf_csv(content)

    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_rates(path)

    imported: dict[str, list[str]] = {}

    for period, currencies in sorted(bmf_data.items()):
        for currency, value_str in sorted(currencies.items()):
            existing_entry = existing.get(period, {}).get(currency)
            if existing_entry is not None and existing_entry.get("source") != "BMF":
                logger.warning(
                    "Skipping %s %s: manual rate exists (%s), not overwriting",
                    period, currency, existing_entry["value"],
                )
                continue
            existing.setdefault(period, {})[currency] = {
                "value": value_str,
                "source": "BMF",
            }
            imported.setdefault(period, []).append(currency)
            logger.debug("Imported %s %s = %s EUR", period, currency, value_str)

    _atomic_write(path, existing)

    total = sum(len(v) for v in imported.values())
    logger.info("BMF import %d: %d rates across %d periods", year, total, len(imported))
    return imported
