from decimal import Decimal

from jtl2datev.core.models import RawInvoice, RawInvoiceLine, TaxDecision, TaxTreatment

EU_COUNTRIES: frozenset[str] = frozenset(
    {
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
        "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
        "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    }
)

# Country-prefixes accepted as plausible VAT-IDs. EU + GB/NI/CH variants.
_VAT_ID_PREFIXES: frozenset[str] = EU_COUNTRIES | frozenset({"GB", "XI", "CH"})

_AMAZON_PLATFORM_PREFIX = "amazon"  # matches Amazon.de, Amazon.co.uk, Amazon.fr, …

# Marketplace-Facilitator destinations: Amazon collects local VAT itself
# (UK post-Brexit, Switzerland) — no VAT in our DATEV booking.
MARKETPLACE_FACILITATOR_DESTINATIONS: frozenset[str] = frozenset({"GB", "CH"})

# Standard VAT rates per country (2026). Reduced rates not modelled —
# Plausi mismatches there end up as warn, never error.
STANDARD_VAT_RATE: dict[str, Decimal] = {
    "AT": Decimal("20"),
    "BE": Decimal("21"),
    "BG": Decimal("20"),
    "CY": Decimal("19"),
    "CZ": Decimal("21"),
    "DE": Decimal("19"),
    "DK": Decimal("25"),
    "EE": Decimal("22"),
    "ES": Decimal("21"),
    "FI": Decimal("25.5"),
    "FR": Decimal("20"),
    "GR": Decimal("24"),
    "HR": Decimal("25"),
    "HU": Decimal("27"),
    "IE": Decimal("23"),
    "IT": Decimal("22"),
    "LT": Decimal("21"),
    "LU": Decimal("17"),
    "LV": Decimal("21"),
    "MT": Decimal("18"),
    "NL": Decimal("21"),
    "PL": Decimal("23"),
    "PT": Decimal("23"),
    "RO": Decimal("21"),
    "SE": Decimal("25"),
    "SI": Decimal("22"),
    "SK": Decimal("23"),
    "GB": Decimal("20"),
    "CH": Decimal("8.1"),
}

_ZERO = Decimal("0")


def looks_like_valid_vat_id(vat_id: str | None) -> bool:
    """Format-only plausibility check (no VIES call): EU/UK/CH prefix + alphanumeric body."""
    if not vat_id:
        return False
    cleaned = vat_id.strip().upper().replace(" ", "").replace("-", "")
    if len(cleaned) < 4:
        return False
    if cleaned[:2] not in _VAT_ID_PREFIXES:
        return False
    return cleaned[2:].isalnum()


def normalise_vat_id(vat_id: str | None, customer_country: str | None) -> str | None:
    """Return the UStId suitable for DATEV/VIES.

    - If empty: None.
    - If already starts with a known EU/UK/CH prefix: cleaned (uppercase, no spaces/dashes).
    - If body looks alphanumeric and customer_country is an EU prefix: prepend it.
      (Marketplaces sometimes drop the leading 'IT'/'ES'.)
    - Otherwise: return cleaned value as-is — the downstream tax tool will reject it
      if invalid; we don't second-guess.
    """
    if not vat_id:
        return None
    cleaned = vat_id.strip().upper().replace(" ", "").replace("-", "")
    if not cleaned:
        return None
    if len(cleaned) >= 2 and cleaned[:2] in _VAT_ID_PREFIXES:
        return cleaned
    cc = (customer_country or "").strip().upper()
    if cc in _VAT_ID_PREFIXES and cleaned.isalnum():
        return cc + cleaned
    return cleaned


def decide(
    invoice: RawInvoice,
    line: RawInvoiceLine,
    *,
    own_vat_countries: frozenset[str],
) -> TaxDecision:
    """Classify a line based on what the marketplace already decided.

    Strategy (per user direction): the marketplace's stored VAT rate is the
    primary signal whether the order was treated as B2C or B2B. We mirror
    that decision and only validate the destination country's rate as a
    plausibility check — without overriding it.
    """
    notes: list[str] = []
    wh = invoice.warehouse_country
    dest = invoice.ship_to.country_iso
    bill_country = invoice.bill_to.country_iso
    raw_vat_id = invoice.bill_to.vat_id or invoice.ship_to.vat_id
    cleaned_vat_id = normalise_vat_id(raw_vat_id, bill_country)
    vat_charged = line.vat_rate > _ZERO

    if wh not in own_vat_countries:
        notes.append(
            f"warehouse_country '{wh}' not in own_vat_countries — verify registration"
        )

    # 1) Domestic: warehouse == destination.
    if wh == dest:
        # Domestic B2B reverse-charge: marketplace booked 0% on a customer with
        # a vat_id (e.g. Italian / Spanish national reverse charge). Mirror that
        # decision instead of demanding the standard rate.
        if line.vat_rate == _ZERO and cleaned_vat_id is not None:
            return TaxDecision(
                treatment=TaxTreatment.DOMESTIC,
                expected_vat_rate=_ZERO,
                tax_country=wh,
                cleaned_vat_id=cleaned_vat_id,
                notes=tuple(notes),
            )
        return TaxDecision(
            treatment=TaxTreatment.DOMESTIC,
            expected_vat_rate=STANDARD_VAT_RATE.get(wh, line.vat_rate),
            tax_country=wh,
            cleaned_vat_id=cleaned_vat_id,
            notes=tuple(notes),
        )

    # 2) Third-country destination
    if dest not in EU_COUNTRIES:
        platform = (invoice.platform_name or "").lower()
        is_marketplace_facilitator = (
            dest in MARKETPLACE_FACILITATOR_DESTINATIONS
            and platform.startswith(_AMAZON_PLATFORM_PREFIX)
        )
        if is_marketplace_facilitator:
            return TaxDecision(
                treatment=TaxTreatment.MARKETPLACE_FACILITATOR,
                expected_vat_rate=_ZERO,
                tax_country=dest,
                cleaned_vat_id=cleaned_vat_id,
                notes=tuple(notes),
            )
        return TaxDecision(
            treatment=TaxTreatment.THIRD_COUNTRY,
            expected_vat_rate=_ZERO,
            tax_country=dest,
            cleaned_vat_id=cleaned_vat_id,
            notes=tuple(notes),
        )

    # 3) Cross-border EU (wh != dest, both in EU)
    if vat_charged:
        # Marketplace charged VAT → B2C (OSS), regardless of whether a vat_id was given.
        # Plausi: the rate should match the destination country's standard rate.
        return TaxDecision(
            treatment=TaxTreatment.OSS_B2C,
            expected_vat_rate=STANDARD_VAT_RATE.get(dest, line.vat_rate),
            tax_country=dest,
            cleaned_vat_id=cleaned_vat_id,
            notes=tuple(notes),
        )

    # vat_rate == 0 → either B2B/Reverse-Charge or a data anomaly.
    if cleaned_vat_id:
        return TaxDecision(
            treatment=TaxTreatment.IGL_B2B,
            expected_vat_rate=_ZERO,
            tax_country=wh,
            cleaned_vat_id=cleaned_vat_id,
            notes=tuple(notes),
        )

    notes.append("zero VAT, no customer vat_id — manual review required")
    return TaxDecision(
        treatment=TaxTreatment.UNKNOWN,
        expected_vat_rate=line.vat_rate,
        tax_country=dest,
        cleaned_vat_id=None,
        notes=tuple(notes),
    )
