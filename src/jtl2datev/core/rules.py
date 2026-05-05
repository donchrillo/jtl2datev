from __future__ import annotations

import logging
from dataclasses import dataclass

from jtl2datev.core.models import RawInvoice, RawInvoiceLine, TaxDecision, TaxTreatment

logger = logging.getLogger(__name__)

# EU member states (excluding DE) used in warehouse classification
_EU_NON_DE: frozenset[str] = frozenset(
    {
        "AT", "BE", "BG", "CY", "CZ", "DK", "EE", "ES", "FI",
        "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
        "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    }
)

_EU_ALL: frozenset[str] = _EU_NON_DE | frozenset({"DE"})

# Helgoland is customs-free, treated like third-country for VAT purposes
_HELGOLAND = "HLG"

# Debitor account by payment method — case-insensitive, stripped
_DEBITOR_BY_PAYMENT: dict[str, int] = {
    "bar": 10001000,
    "bar bei selbstabholung": 10001000,
    "überweisung": 10002000,
    "vorkasse": 10002000,
    "rechnung manuell": 10002000,
    "paypal": 10004000,
    "paypal-express": 10004000,
    "amazonpayments": 10005000,
    "amazon payments": 10005000,
    "amazon_payments": 10005000,
    "ebay rechnungskauf": 10006000,
    "ebay managed payments": 10006000,
    "gewährleistung": 10007000,
    "real": 10008000,
    "kaufland": 10008000,
    "kaufland.de": 10008000,
    "rechnung_mit_klarna": 10009000,
    "sofortbezahlen klarna": 10009000,
    "shopify_payments": 10010000,
    "otto": 10011000,
    "otto.de": 10011000,
    "temu": 10012000,
}


@dataclass(frozen=True)
class DatevAccount:
    account: str  # 7-digit, e.g. "4400000"
    bu_key: str = ""  # e.g. "240", "241", "285", or empty
    note: str = ""  # explanation for special/fallback cases


def map_to_debitor_account(
    invoice: RawInvoice,
    *,
    payment_method: str | None,
    default: int,
) -> str:
    """Return 8-digit debitor account number based on payment method."""
    if payment_method:
        key = payment_method.strip().lower()
        account_no = _DEBITOR_BY_PAYMENT.get(key)
        if account_no is not None:
            return str(account_no)
    return str(default)


def map_to_datev_account(
    invoice: RawInvoice,
    line: RawInvoiceLine,
    decision: TaxDecision,
) -> DatevAccount:
    """
    Map a line's tax decision to a DATEV Sachkonto (7-digit) + BU key.

    Implements the lookup algorithm from docs/datev-format.md.
    """
    wh = invoice.warehouse_country
    dest = invoice.ship_to.country_iso
    treatment = decision.treatment
    has_vat_id = decision.cleaned_vat_id is not None
    line_vat_rate = line.vat_rate

    # 1. Helgoland (customs-free zone, like third-country)
    if dest == _HELGOLAND:
        return DatevAccount(account="4120000")

    # 2. Third-country destinations (outside EU + GB + CH)
    if dest not in _EU_ALL and dest not in ("GB", "CH", _HELGOLAND):
        if wh == "DE":
            return DatevAccount(account="4120000")
        # EU warehouse or GB warehouse → third-country export
        return DatevAccount(account="4121000")

    # 3. GB destination (post-Brexit, Marketplace-Facilitator or Export-Local-VAT)
    if dest == "GB":
        if treatment == TaxTreatment.MARKETPLACE_FACILITATOR:
            return DatevAccount(account="4328000")
        if treatment == TaxTreatment.EXPORT_LOCAL_VAT:
            return DatevAccount(account="4325000")
        # Fallback: if line shows 0% VAT and engine gave THIRD_COUNTRY → MF
        if line_vat_rate == 0 and treatment == TaxTreatment.THIRD_COUNTRY:
            return DatevAccount(account="4328000")
        # Non-zero VAT to GB: export with local VAT
        return DatevAccount(account="4325000")

    # 4. MARKETPLACE_FACILITATOR or EXPORT_LOCAL_VAT (generic — e.g. CH)
    if treatment == TaxTreatment.MARKETPLACE_FACILITATOR:
        return DatevAccount(account="4328000")
    if treatment == TaxTreatment.EXPORT_LOCAL_VAT:
        return DatevAccount(account="4325000")

    # 5. DOMESTIC (warehouse == destination)
    if treatment == TaxTreatment.DOMESTIC:
        # National reverse-charge: domestic B2B with 0% VAT + valid UStID
        if line_vat_rate == 0 and has_vat_id:
            if wh in _EU_NON_DE:
                return DatevAccount(account="4126000", note="national reverse-charge EU warehouse")
            # DE domestic reverse-charge is rare but map to 4001000 if it occurs
            return DatevAccount(account="4001000", bu_key="285", note="national reverse-charge DE")
        _DOMESTIC_MAP: dict[str, str] = {
            "DE": "4400000",
            "FR": "4324000",
            "IT": "4326000",
            "ES": "4323000",
            "PL": "4327000",
            "CZ": "4322000",
            "GB": "4325000",
        }
        account = _DOMESTIC_MAP.get(wh)
        if account:
            return DatevAccount(account=account)
        return DatevAccount(
            account="0000000",
            note=f"DOMESTIC: no account mapping for warehouse {wh!r}",
        )

    # 6. IGL_B2B (cross-border EU with customer VAT ID)
    if treatment == TaxTreatment.IGL_B2B:
        if wh == "DE":
            if dest == "DE":
                # Shouldn't happen (domestic would catch it), but guard
                return DatevAccount(account="4001000", bu_key="285", note="DE→DE B2B anomaly")
            # DE → EU B2B: intracommunity supply
            return DatevAccount(account="4125000")
        # EU non-DE warehouse
        if dest == "DE":
            # EU warehouse → DE B2B customer: intracommunity acquisition from seller's POV
            # We book as 4001000 BU 285 (Jera sample confirms this pattern)
            return DatevAccount(account="4001000", bu_key="285")
        # EU warehouse → other EU country B2B
        return DatevAccount(account="4126000")

    # 7. OSS_B2C (cross-border EU, B2C)
    if treatment == TaxTreatment.OSS_B2C:
        if wh == "DE":
            return DatevAccount(account="4320000", bu_key="240")
        # EU warehouse → DE customer: special "EU → Eigene Land Std. Steuer" booking
        # (Jera SachkontenZuordnung row: USt=19, Lager=EU, Ziel=DE → 4001000 BU 285)
        if dest == "DE":
            return DatevAccount(account="4001000", bu_key="285")
        # Non-DE EU warehouse → other EU country
        return DatevAccount(account="4320000", bu_key="241")

    # 8. THIRD_COUNTRY treatment with EU destination: shouldn't normally happen
    if treatment == TaxTreatment.THIRD_COUNTRY:
        if wh == "DE":
            return DatevAccount(account="4120000", note="THIRD_COUNTRY to EU dest — verify")
        return DatevAccount(account="4121000", note="THIRD_COUNTRY to EU dest — verify")

    # Fallback for UNKNOWN or unhandled
    logger.warning(
        "No DATEV account rule matched for invoice=%s line=%d treatment=%s wh=%s dest=%s",
        invoice.invoice_no,
        line.line_no,
        treatment,
        wh,
        dest,
    )
    return DatevAccount(
        account="0000000",
        note=f"unmatched: treatment={treatment} wh={wh} dest={dest}",
    )
