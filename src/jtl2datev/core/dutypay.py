"""DutyPay OSS export — one CSV row per invoice document.

Format spec: docs/dutypay-format.md
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from jtl2datev.core.models import RawInvoice
from jtl2datev.core.tax_engine import EU_COUNTRIES, STANDARD_VAT_RATE

logger = logging.getLogger(__name__)

# ── Column header (98 columns, semicolon-joined) ─────────────────────────────

DUTYPAY_COLUMNS: tuple[str, ...] = (
    "Positions-Nr.",
    "KindOfBusiness",
    "TransactionID",
    "DocumentID",
    "ReportingPeriod",
    "DepartureDate",
    "ArrivalDate",
    "DocumentDate",
    "VatZone",
    "VATRate",
    "VATAmount",
    "SourceZone",
    "SourceZoneZip",
    "SourceZoneVatID",
    "SourceZoneVatRate",
    "SourceZoneCurrencyCode",
    "SourceZoneGross",
    "SourceZoneNet",
    "TargetZone",
    "TargetZoneZip",
    "TargetZoneVatID",
    "TargetZoneVatRate",
    "TargetZoneCurrencyCode",
    "TargetZoneGross",
    "TargetZoneNet",
    "MarketZone",
    "MarketZoneCurrencyCode",
    "MarketZoneGross",
    "MarketZoneNet",
    "ItemID",
    "ItemName",
    "ItemDescription",
    "CommodityCode",
    "ItemQuantity",
    "ItemUnit",
    "ItemSalesPrice",
    "ItemPurchasePrice",
    "ItemCurrencyCode",
    "ItemWeight",
    "TransportCode",
    "ItemManufacturer",
    "ItemManufacturerZone",
    "MPN",
    "Brand",
    "GTIN",
    "ASIN",
    "ISBN",
    "UPC",
    "JAN",
    "TPCompanyName",
    "PostingDateInvoice",
    "TransactionPartner Form Of Address",
    "TransactionPartner First Name",
    "TransactionPartner Placeholder 1",
    "TransactionPartner Family Name",
    "TransactionPartner Placeholder 2",
    "TransactionPartner Tax-ID",
    "TransactionPartner Street",
    "TransactionPartner House Number",
    "TransactionPartner Additional Address",
    "TransactionPartner ZIP",
    "TransactionPartner City",
    "TransactionPartner Region",
    "TransactionPartner Country IsoCode",
    "BillingAddress Company Name",
    "BillingAddress Form Of Address",
    "BillingAddress First Name",
    "BillingAddress Placeholder 1",
    "BillingAddress Family Name",
    "BillingAddress Placeholder 2",
    "BillingAddress Placeholder 3",
    "BillingAddress Street",
    "BillingAddress House Number",
    "BillingAddress Additional Address",
    "BillingAddress ZIP",
    "BillingAddress City",
    "BillingAddress Region",
    "BillingAddress Country ISOCode",
    "Incoterms",
    "TAX_REPORTING_SCHEME",
    "TAX_COLLECTION_RESPONSIBILITY",
    "Placeholder 4",
    "Placeholder 5",
    "Placeholder 6",
    "Placeholder 7",
    "Placeholder 8",
    "Placeholder 9",
    "Placeholder 10",
    "Placeholder 11",
    "Placeholder 12",
    "Placeholder 13",
    "Placeholder 14",
    "Placeholder 15",
    "Placeholder 16",
    "Placeholder 17",
    "Placeholder 18",
    "Placeholder 19",
    "Placeholder 20",
)

assert len(DUTYPAY_COLUMNS) == 98, f"Expected 98 columns, got {len(DUTYPAY_COLUMNS)}"

_MONTH_ABBR: tuple[str, ...] = (
    "", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)

_EU_ALL = EU_COUNTRIES

# ISO-2 country → ISO-4217 currency for all countries we handle.
# EUR-zone members share one entry; non-EUR EU and third countries listed individually.
_COUNTRY_CURRENCY: dict[str, str] = {
    # EUR-zone (including HR since 2023)
    **{c: "EUR" for c in (
        "DE", "AT", "BE", "CY", "EE", "ES", "FI", "FR", "GR", "HR",
        "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK",
    )},
    # Non-EUR EU members
    "CZ": "CZK",
    "DK": "DKK",
    "HU": "HUF",
    "PL": "PLN",
    "RO": "RON",
    "SE": "SEK",
    "BG": "BGN",
    # Non-EU third countries
    "GB": "GBP",
    "CH": "CHF",
    "NO": "NOK",
    "US": "USD",
}


def _warehouse_currency(country_iso: str, fallback: str) -> str:
    """Return the ISO-4217 currency for a given warehouse country.

    Falls back to *fallback* (typically the invoice currency) when the country
    is not in the mapping table, and logs a warning so unknown countries surface.
    """
    if country_iso in _COUNTRY_CURRENCY:
        return _COUNTRY_CURRENCY[country_iso]
    logger.warning(
        "DutyPay: unknown warehouse country %r — using fallback currency %r for SourceZoneCurrencyCode",
        country_iso,
        fallback,
    )
    return fallback


def _is_third_country(iso: str) -> bool:
    """True for any destination outside the EU — GB, CH, TR, US, etc. are all EXPORT."""
    return iso not in _EU_ALL


class KindOfBusiness(StrEnum):
    SALE = "SALE"
    REFUND = "REFUND"
    B2B = "B2B"
    EXPORT = "EXPORT"
    B2B_REFUND = "B2B-REFUND"
    EXPORT_REFUND = "EXPORT-REFUND"


def determine_kind_of_business(invoice: RawInvoice) -> KindOfBusiness:
    """Classify an invoice into the DutyPay KindOfBusiness bucket.

    Decision order matches the spec's KindOfBusiness table:
    1. is_credit_note → REFUND / B2B-REFUND / EXPORT-REFUND variants
    2. third-country destination → EXPORT
    3. B2B (cross-border EU with valid customer VAT ID) → B2B
    4. Everything else → SALE (domestic or cross-border B2C)
    """
    wh = invoice.warehouse_country
    dest = invoice.ship_to.country_iso
    is_refund = invoice.is_credit_note
    has_vat_id = bool(invoice.bill_to.vat_id or invoice.ship_to.vat_id)
    cross_border = wh != dest
    third_country = _is_third_country(dest)

    if is_refund:
        if third_country:
            return KindOfBusiness.EXPORT_REFUND
        if cross_border and has_vat_id:
            return KindOfBusiness.B2B_REFUND
        return KindOfBusiness.REFUND

    if third_country:
        return KindOfBusiness.EXPORT

    if cross_border and has_vat_id:
        return KindOfBusiness.B2B

    return KindOfBusiness.SALE


def _market_zone(invoice: RawInvoice, kind: KindOfBusiness) -> str:
    """MarketZone = Marketplace country from invoice.marketplace_country.

    Fallback when no Marketplace is known: SALE/REFUND → target country,
    all other kinds → warehouse country.
    """
    if invoice.marketplace_country:
        return invoice.marketplace_country
    if kind in (KindOfBusiness.SALE, KindOfBusiness.REFUND):
        return invoice.ship_to.country_iso
    return invoice.warehouse_country


def _incoterms(kind: KindOfBusiness) -> str:
    if kind in (
        KindOfBusiness.B2B,
        KindOfBusiness.EXPORT,
        KindOfBusiness.B2B_REFUND,
        KindOfBusiness.EXPORT_REFUND,
    ):
        return "DDP"
    return ""


def _tax_reporting_scheme(kind: KindOfBusiness, target_zone: str) -> str:
    if kind in (KindOfBusiness.EXPORT, KindOfBusiness.EXPORT_REFUND) and target_zone == "GB":
        return "UK_VOEC-IMPORT"
    return ""


def _tax_collection_responsibility(kind: KindOfBusiness, invoice: RawInvoice) -> str:
    if kind not in (KindOfBusiness.EXPORT, KindOfBusiness.EXPORT_REFUND):
        return ""
    # Marketplace detection: external order ID present (set by JTL for Amazon/eBay/etc.)
    # TransactionID prefix 'E' or 'ER' also signals external, but external_order_no is
    # the cleaner signal because it's directly stored by the JTL import.
    if invoice.jtl_external_order_no:
        return "MARKETPLACE"
    return ""


def _format_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _format_decimal(val: Decimal) -> str:
    """German decimal: comma separator, 2 decimal places."""
    return f"{val:.2f}".replace(".", ",")


def _reporting_period(d: date) -> str:
    return f"{d.year}-{_MONTH_ABBR[d.month]}"


def _vat_rate_str(rate: Decimal | None) -> str:
    if rate is None:
        return ""
    # Drop trailing zeros without scientific notation: 19.00 → "19", 8.10 → "8,1".
    # Decimal.normalize() returns "2E+1" for whole tens, so format as fixed-point first.
    s = format(rate, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _safe(val: str | None) -> str:
    if not val:
        return ""
    return val.replace(";", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ").strip()


def _build_invoice_row(
    *,
    pos_nr: int,
    invoice: RawInvoice,
    kind: KindOfBusiness,
    own_vat_ids: dict[str, str],
) -> list[str]:
    source_zone = invoice.warehouse_country
    target_zone = invoice.ship_to.country_iso
    market_zone = _market_zone(invoice, kind)
    doc_date = invoice.invoice_date
    currency = invoice.currency
    target_currency = _warehouse_currency(target_zone, currency)
    market_currency = _warehouse_currency(market_zone, currency)

    # Aggregate gross/net across all lines, then apply Refund sign.
    # abs() prevents double-negation when JTL already stores credit note
    # amounts as negative in the DB.
    is_refund_kind = kind in (
        KindOfBusiness.REFUND,
        KindOfBusiness.B2B_REFUND,
        KindOfBusiness.EXPORT_REFUND,
    )
    total_gross = sum((abs(line.gross) for line in invoice.lines), Decimal("0"))
    total_net = sum((abs(line.net) for line in invoice.lines), Decimal("0"))
    mz_gross = -total_gross if is_refund_kind else total_gross
    mz_net = -total_net if is_refund_kind else total_net

    # VatZone: the country where VAT applies.
    # - SALE/REFUND: target (destination) country.
    # - EXPORT to GB via Marketplace-Facilitator (Amazon/eBay collect & remit
    #   UK VAT directly): VatZone = GB, because the VAT is settled in the UK.
    # - All other B2B/EXPORT: source (warehouse).
    if kind in (KindOfBusiness.SALE, KindOfBusiness.REFUND):
        vat_zone = target_zone
    elif (
        kind in (KindOfBusiness.EXPORT, KindOfBusiness.EXPORT_REFUND)
        and target_zone == "GB"
        and invoice.jtl_external_order_no  # Marketplace-Facilitator-Indikator
    ):
        vat_zone = "GB"
    else:
        vat_zone = source_zone

    # VATRate: only for B2C (SALE/REFUND). Empty for reverse-charge / export.
    vat_rate_for_zone: Decimal | None = STANDARD_VAT_RATE.get(vat_zone) if kind in (
        KindOfBusiness.SALE, KindOfBusiness.REFUND
    ) else None

    # TargetZoneVatRate: filled for B2C/SALE; empty for B2B (0% reverse-charge)
    target_vat_rate: Decimal | None = STANDARD_VAT_RATE.get(target_zone) if kind in (
        KindOfBusiness.SALE, KindOfBusiness.REFUND
    ) else None

    # SourceZoneVatID: our own VAT-ID for that warehouse (used for B2B / cross-border)
    source_vat_id = own_vat_ids.get(source_zone, "") if kind not in (
        KindOfBusiness.SALE, KindOfBusiness.REFUND
    ) else ""

    # SourceZoneVatRate: standard rate of the warehouse country
    source_vat_rate: Decimal | None = STANDARD_VAT_RATE.get(source_zone)

    # TargetZoneVatID: customer VAT ID (only for B2B)
    target_vat_id = ""
    if kind in (KindOfBusiness.B2B, KindOfBusiness.B2B_REFUND):
        target_vat_id = _safe(invoice.bill_to.vat_id or invoice.ship_to.vat_id or "")

    # TransactionID: externe Auftragsnummer (Marketplace-Order-ID), Fallback auf
    # interne JTL-Wawi-Auftragsnummer — beide bereits im DB-Layer in
    # invoice.jtl_external_order_no zusammengeführt. Ermöglicht Suche im
    # JTL-Frontend und Join mit DATEV-Export (gleiche Order-ID dort in Belegfeld 1).
    # Falls weder externe noch interne Auftrnr existiert, fällt die Logik auf die
    # Jera-PK-Konvention {R/SR/G/SRK/ER/EG}{kPK} zurück, damit die Spalte nie leer ist.
    transaction_id = _safe(invoice.jtl_external_order_no or "")
    if not transaction_id:
        pk = invoice.jtl_primary_key
        no_upper = (invoice.invoice_no or "").upper()
        if pk is None:
            transaction_id = _safe(invoice.invoice_no)
        elif invoice.source == "jtl_own":
            transaction_id = f"SR{pk}" if no_upper.startswith("SR") else f"R{pk}"
        elif invoice.source == "jtl_external":
            transaction_id = f"EG{pk}" if invoice.is_credit_note else f"ER{pk}"
        elif invoice.source == "jtl_credit_note":
            transaction_id = f"SRK{pk}" if no_upper.startswith("SRK") else f"G{pk}"
        else:
            transaction_id = _safe(invoice.invoice_no)

    row: list[str] = [
        str(pos_nr),                                    # Positions-Nr.
        str(kind),                                      # KindOfBusiness
        transaction_id,                                 # TransactionID
        _safe(invoice.invoice_no),                      # DocumentID
        _reporting_period(doc_date),                    # ReportingPeriod
        _format_date(doc_date),                         # DepartureDate
        _format_date(doc_date),                         # ArrivalDate (= DepartureDate)
        _format_date(doc_date),                         # DocumentDate
        vat_zone,                                       # VatZone
        _vat_rate_str(vat_rate_for_zone),               # VATRate
        "",                                             # VATAmount (DutyPay calculates)
        source_zone,                                    # SourceZone
        "",                                             # SourceZoneZip (not available)
        source_vat_id,                                  # SourceZoneVatID
        _vat_rate_str(source_vat_rate),                 # SourceZoneVatRate
        _warehouse_currency(source_zone, currency),     # SourceZoneCurrencyCode
        "",                                             # SourceZoneGross (not filled per spec)
        "",                                             # SourceZoneNet (not filled per spec)
        target_zone,                                    # TargetZone
        "",                                             # TargetZoneZip (not filled — Profil 1)
        target_vat_id,                                  # TargetZoneVatID
        _vat_rate_str(target_vat_rate),                 # TargetZoneVatRate
        target_currency,                                # TargetZoneCurrencyCode
        "",                                             # TargetZoneGross (not filled per spec)
        "",                                             # TargetZoneNet (not filled per spec)
        market_zone,                                    # MarketZone
        market_currency,                                # MarketZoneCurrencyCode
        _format_decimal(mz_gross),                      # MarketZoneGross
        _format_decimal(mz_net),                        # MarketZoneNet
        "",                                             # ItemID (not required — Profil 1)
        "",                                             # ItemName
        "",                                             # ItemDescription
        "",                                             # CommodityCode
        "1",                                            # ItemQuantity (fixed per spec)
        "",                                             # ItemUnit
        "",                                             # ItemSalesPrice
        "",                                             # ItemPurchasePrice
        currency,                                       # ItemCurrencyCode
        "",                                             # ItemWeight
        "5",                                            # TransportCode (fixed default)
        "",                                             # ItemManufacturer
        "",                                             # ItemManufacturerZone
        "",                                             # MPN
        "",                                             # Brand
        "",                                             # GTIN
        "",                                             # ASIN
        "",                                             # ISBN
        "",                                             # UPC
        "",                                             # JAN
        "",                                             # TPCompanyName (not required — Profil 1)
        _format_date(doc_date),                         # PostingDateInvoice
        "",                                             # TransactionPartner Form Of Address
        "",                                             # TransactionPartner First Name
        "",                                             # TransactionPartner Placeholder 1
        "",                                             # TransactionPartner Family Name
        "",                                             # TransactionPartner Placeholder 2
        "",                                             # TransactionPartner Tax-ID
        "",                                             # TransactionPartner Street
        "",                                             # TransactionPartner House Number
        "",                                             # TransactionPartner Additional Address
        "",                                             # TransactionPartner ZIP
        "",                                             # TransactionPartner City
        "",                                             # TransactionPartner Region
        "",                                             # TransactionPartner Country IsoCode
        "",                                             # BillingAddress Company Name
        "",                                             # BillingAddress Form Of Address
        "",                                             # BillingAddress First Name
        "",                                             # BillingAddress Placeholder 1
        "",                                             # BillingAddress Family Name
        "",                                             # BillingAddress Placeholder 2
        "",                                             # BillingAddress Placeholder 3
        "",                                             # BillingAddress Street
        "",                                             # BillingAddress House Number
        "",                                             # BillingAddress Additional Address
        "",                                             # BillingAddress ZIP
        "",                                             # BillingAddress City
        "",                                             # BillingAddress Region
        "",                                             # BillingAddress Country ISOCode
        _incoterms(kind),                               # Incoterms
        _tax_reporting_scheme(kind, target_zone),       # TAX_REPORTING_SCHEME
        _tax_collection_responsibility(kind, invoice),  # TAX_COLLECTION_RESPONSIBILITY
        "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",  # Placeholders 4–20
    ]

    assert len(row) == 98, f"Row has {len(row)} columns, expected 98"
    return row


@dataclass
class DutyPayReport:
    rows_written: int = 0
    invoices_processed: int = 0
    skipped_no_lines: int = 0
    kind_counts: dict[str, int] = field(default_factory=dict)


def write_dutypay_csv(
    invoices: Iterable[RawInvoice],
    *,
    out_path: Path,
    own_vat_ids: dict[str, str],
) -> DutyPayReport:
    """Write DutyPay OSS CSV from an invoices iterator.

    UTF-8, semicolon-delimited, German decimal comma, DD.MM.YYYY dates.
    One row per invoice document (amounts aggregated across all line positions).
    """
    report = DutyPayReport()
    pos_nr = 0

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        writer.writerow(list(DUTYPAY_COLUMNS))

        for invoice in invoices:
            if not invoice.lines:
                report.skipped_no_lines += 1
                continue

            kind = determine_kind_of_business(invoice)
            report.kind_counts[str(kind)] = report.kind_counts.get(str(kind), 0) + 1

            pos_nr += 1
            row = _build_invoice_row(
                pos_nr=pos_nr,
                invoice=invoice,
                kind=kind,
                own_vat_ids=own_vat_ids,
            )
            writer.writerow(row)
            report.rows_written += 1
            report.invoices_processed += 1

    logger.info(
        "DutyPay export complete: %d rows written from %d invoices",
        report.rows_written,
        report.invoices_processed,
    )
    return report


def dutypay_filename(year: int, month: int) -> str:
    """Return the conventional DutyPay filename, e.g. DutyPay-SALE-2026-JAN.csv."""
    return f"DutyPay-SALE-{year}-{_MONTH_ABBR[month]}.csv"
