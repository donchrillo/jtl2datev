import csv
import io
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_DATE_FMT = "%d-%m-%Y"
_KEEP_TYPES: frozenset[str] = frozenset({"FC_TRANSFER", "INBOUND"})
_RETURN_POSTAL_CODE = "46569"


class MovementRow(BaseModel):
    transaction_type: Literal["FC_TRANSFER", "INBOUND"]
    transaction_event_id: str
    activity_transaction_id: str
    depart_date: date | None
    arrival_date: date | None
    complete_date: date | None
    seller_sku: str
    asin: str
    description: str
    qty: int
    item_weight: Decimal | None
    departure_country: str
    arrival_country: str
    arrival_postal_code: str
    is_return_to_user: bool
    currency: str
    raw_seller_depart_vat: str
    raw_seller_arrival_vat: str


def _parse_date(raw: str) -> date | None:
    stripped = raw.strip()
    if not stripped:
        return None
    return date.fromisoformat(
        f"{stripped[6:10]}-{stripped[3:5]}-{stripped[0:2]}"
    )


def _parse_decimal(raw: str) -> Decimal | None:
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return Decimal(stripped)
    except InvalidOperation:
        logger.warning("Could not parse decimal %r — treating as None", raw)
        return None


def _read_amazon_report(path: Path) -> str:
    """Detect encoding of an Amazon movement report TSV. Tries common encodings."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"Amazon-Report {path}: kein bekanntes Encoding (utf-8/utf-16/cp1252) passte"
    )


def parse_amazon_report(path: Path) -> list[MovementRow]:
    rows: list[MovementRow] = []
    skipped = 0

    text = _read_amazon_report(path)
    with io.StringIO(text) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for raw in reader:
            tt = raw.get("TRANSACTION_TYPE", "").strip()
            if tt not in _KEEP_TYPES:
                skipped += 1
                continue

            postal = raw.get("ARRIVAL_POST_CODE", "").strip()
            rows.append(
                MovementRow(
                    transaction_type=tt,  # type: ignore[arg-type]
                    transaction_event_id=raw.get("TRANSACTION_EVENT_ID", "").strip(),
                    activity_transaction_id=raw.get("ACTIVITY_TRANSACTION_ID", "").strip(),
                    depart_date=_parse_date(raw.get("TRANSACTION_DEPART_DATE", "")),
                    arrival_date=_parse_date(raw.get("TRANSACTION_ARRIVAL_DATE", "")),
                    complete_date=_parse_date(raw.get("TRANSACTION_COMPLETE_DATE", "")),
                    seller_sku=raw.get("SELLER_SKU", "").strip(),
                    asin=raw.get("ASIN", "").strip(),
                    description=raw.get("ITEM_DESCRIPTION", "").strip(),
                    qty=int(raw.get("QTY", "0").strip() or "0"),
                    item_weight=_parse_decimal(raw.get("ITEM_WEIGHT", "")),
                    departure_country=raw.get("DEPARTURE_COUNTRY", "").strip(),
                    arrival_country=raw.get("ARRIVAL_COUNTRY", "").strip(),
                    arrival_postal_code=postal,
                    is_return_to_user=(postal == _RETURN_POSTAL_CODE),
                    currency=raw.get("TRANSACTION_CURRENCY_CODE", "").strip(),
                    raw_seller_depart_vat=raw.get("SELLER_DEPART_COUNTRY_VAT_NUMBER", "").strip(),
                    raw_seller_arrival_vat=raw.get("SELLER_ARRIVAL_COUNTRY_VAT_NUMBER", "").strip(),
                )
            )

    logger.info(
        "parse_amazon_report(%s): %d rows kept, %d skipped",
        path.name,
        len(rows),
        skipped,
    )
    return rows
