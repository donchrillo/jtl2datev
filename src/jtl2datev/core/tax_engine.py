from decimal import Decimal

from jtl2datev.core.models import RawInvoice, RawInvoiceLine, TaxDecision, TaxTreatment

EU_COUNTRIES: frozenset[str] = frozenset(
    {
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
        "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
        "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    }
)

# Country-prefixes accepted as plausible VAT-IDs. Includes EU + GB/NI/CH/XI variants.
_VAT_ID_PREFIXES: frozenset[str] = EU_COUNTRIES | frozenset({"GB", "XI", "CH"})

AMAZON_PLATFORM_NAMES: frozenset[str] = frozenset({"amazon"})

_ZERO = Decimal("0")


def looks_like_valid_vat_id(vat_id: str | None) -> bool:
    """Format-only plausibility check (no VIES call).

    Real validation requires VIES. Until that's wired up, we reject obviously
    non-VAT strings like local tax/CIF numbers (e.g. Spanish 'B06800015') by
    requiring the first two characters to be a known EU/UK/CH country code,
    followed by at least two alphanumerics. Marketplaces sometimes pass
    customer-supplied junk into this field; treating it blindly as B2B caused
    Reverse-Charge misclassifications in production.
    """
    if not vat_id:
        return False
    cleaned = vat_id.strip().upper().replace(" ", "").replace("-", "")
    if len(cleaned) < 4:
        return False
    prefix = cleaned[:2]
    if prefix not in _VAT_ID_PREFIXES:
        return False
    return cleaned[2:].isalnum()


def decide(
    invoice: RawInvoice,
    line: RawInvoiceLine,
    *,
    own_vat_countries: frozenset[str],
) -> TaxDecision:
    notes: list[str] = []
    wh = invoice.warehouse_country
    dest = invoice.ship_to.country_iso
    vat_id = invoice.ship_to.vat_id or invoice.bill_to.vat_id

    if wh not in own_vat_countries:
        notes.append(
            f"warehouse_country '{wh}' not in own_vat_countries — verify registration"
        )

    # UK / CH via Amazon → Marketplace Facilitator
    platform = (invoice.platform_name or "").lower()
    if dest not in EU_COUNTRIES and platform in AMAZON_PLATFORM_NAMES:
        return TaxDecision(
            treatment=TaxTreatment.MARKETPLACE_FACILITATOR,
            expected_vat_rate=_ZERO,
            tax_country=dest,
            notes=tuple(notes),
        )

    # Domestic: warehouse == destination
    if wh == dest:
        return TaxDecision(
            treatment=TaxTreatment.DOMESTIC,
            expected_vat_rate=line.vat_rate,
            tax_country=wh,
            notes=tuple(notes),
        )

    # Third country (non-EU destination, not caught by Marketplace Facilitator above)
    if dest not in EU_COUNTRIES:
        return TaxDecision(
            treatment=TaxTreatment.THIRD_COUNTRY,
            expected_vat_rate=_ZERO,
            tax_country=dest,
            notes=tuple(notes),
        )

    # Cross-border EU
    if wh in EU_COUNTRIES and dest in EU_COUNTRIES:
        if looks_like_valid_vat_id(vat_id):
            # B2B intra-community supply → Reverse Charge
            return TaxDecision(
                treatment=TaxTreatment.IGL_B2B,
                expected_vat_rate=_ZERO,
                tax_country=wh,
                notes=tuple(notes),
            )
        if vat_id:
            notes.append(
                f"customer vat_id '{vat_id}' has no recognised EU prefix — treating as B2C"
            )
        # B2C → OSS
        return TaxDecision(
            treatment=TaxTreatment.OSS_B2C,
            expected_vat_rate=line.vat_rate,
            tax_country=dest,
            notes=tuple(notes),
        )

    return TaxDecision(
        treatment=TaxTreatment.UNKNOWN,
        expected_vat_rate=line.vat_rate,
        tax_country=dest,
        notes=tuple([*notes, "No rule matched — manual review required"]),
    )
