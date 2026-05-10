from datetime import date
from decimal import Decimal

from jtl2datev.core.models import PartyAddress, RawInvoice, RawInvoiceLine, TaxTreatment
from jtl2datev.core.tax_engine import decide

OWN_VAT = frozenset({"DE", "FR", "IT", "ES", "PL", "CZ", "GB"})

_BASE_LINE = RawInvoiceLine(
    line_no=1,
    net=Decimal("100.00"),
    gross=Decimal("119.00"),
    vat_amount=Decimal("19.00"),
    vat_rate=Decimal("19.00"),
)


def _invoice(
    warehouse: str,
    dest: str,
    vat_id: str | None = None,
    platform_name: str | None = None,
) -> RawInvoice:
    return RawInvoice(
        source="jtl_own",
        invoice_no="R-001",
        invoice_date=date(2026, 1, 15),
        currency="EUR",
        currency_factor=Decimal("1"),
        warehouse_country=warehouse,
        ship_to=PartyAddress(country_iso=dest, vat_id=vat_id),
        bill_to=PartyAddress(country_iso=dest),
        is_credit_note=False,
        lines=(_BASE_LINE,),
        platform_name=platform_name,
    )


def test_domestic_de_to_de() -> None:
    inv = _invoice("DE", "DE")
    d = decide(inv, _BASE_LINE, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.DOMESTIC
    assert d.expected_vat_rate == Decimal("19.00")
    assert d.tax_country == "DE"


def test_oss_b2c_de_to_fr() -> None:
    inv = _invoice("DE", "FR")
    d = decide(inv, _BASE_LINE, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.OSS_B2C
    assert d.tax_country == "FR"


def test_igl_b2b_de_to_fr_with_vat_id() -> None:
    """Marketplace charged 0% AND customer has VAT-ID → B2B."""
    line = RawInvoiceLine(
        line_no=1, net=Decimal("100"),
        gross=Decimal("100"), vat_amount=Decimal("0"), vat_rate=Decimal("0"),
    )
    inv = _invoice("DE", "FR", vat_id="FR12345678901")
    inv = inv.model_copy(update={"lines": (line,)})
    d = decide(inv, line, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.IGL_B2B
    assert d.expected_vat_rate == Decimal("0")
    assert d.cleaned_vat_id == "FR12345678901"


def test_b2c_when_marketplace_charged_vat_despite_vat_id() -> None:
    """User rule: if marketplace charged VAT, treat as B2C even when a vat_id is set."""
    inv = _invoice("DE", "FR", vat_id="FR12345678901")
    d = decide(inv, _BASE_LINE, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.OSS_B2C
    # FR standard rate is 20% — Plausi will flag the JTL 19% rate
    assert d.expected_vat_rate == Decimal("20")


def test_third_country_de_to_us() -> None:
    inv = _invoice("DE", "US")
    d = decide(inv, _BASE_LINE, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.THIRD_COUNTRY
    assert d.expected_vat_rate == Decimal("0")


def test_marketplace_facilitator_when_gross_equals_net() -> None:
    """Amazon withheld VAT → gross == net → MARKETPLACE_FACILITATOR."""
    line = RawInvoiceLine(
        line_no=0, net=Decimal("100"),
        gross=Decimal("100"), vat_amount=Decimal("0"), vat_rate=Decimal("0"),
    )
    inv = _invoice("PL", "GB", platform_name="Amazon.co.uk")
    inv = inv.model_copy(update={"lines": (line,)})
    d = decide(inv, line, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.MARKETPLACE_FACILITATOR
    assert d.expected_vat_rate == Decimal("0")


def test_export_local_vat_when_amazon_uk_didnt_withhold() -> None:
    """Edge case: Amazon UK didn't withhold (gross != net) → we owe UK VAT."""
    line = RawInvoiceLine(
        line_no=0, net=Decimal("20.64"),
        gross=Decimal("24.77"), vat_amount=Decimal("4.13"), vat_rate=Decimal("20"),
    )
    inv = _invoice("ES", "GB", platform_name="Amazon.co.uk")
    inv = inv.model_copy(update={"lines": (line,)})
    d = decide(inv, line, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.EXPORT_LOCAL_VAT
    assert d.expected_vat_rate == Decimal("20")


def test_unknown_warehouse_warns() -> None:
    inv = _invoice("SE", "SE")
    d = decide(inv, _BASE_LINE, own_vat_countries=OWN_VAT)
    assert any("own_vat_countries" in n for n in d.notes)


def test_b2c_when_marketplace_charged_vat_with_junk_vat_id() -> None:
    """Spanish CIF 'B06800015' in vat_id field; marketplace charged VAT → B2C."""
    line = RawInvoiceLine(
        line_no=0, net=Decimal("22"),
        gross=Decimal("26.64"), vat_amount=Decimal("4.62"), vat_rate=Decimal("21"),
    )
    inv = RawInvoice(
        source="jtl_own", invoice_no="X", invoice_date=date(2026, 3, 9),
        currency="EUR", currency_factor=Decimal("1"),
        warehouse_country="IT",
        ship_to=PartyAddress(country_iso="ES"),
        bill_to=PartyAddress(country_iso="ES", vat_id="B06800015"),
        is_credit_note=False, lines=(line,),
    )
    d = decide(inv, line, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.OSS_B2C
    assert d.expected_vat_rate == Decimal("21")  # ES standard rate
    # Junk gets prefixed with bill_to country → "ESB06800015"
    assert d.cleaned_vat_id == "ESB06800015"


def test_ch_treated_as_third_country() -> None:
    """CH wird als regulärer Drittlandsexport behandelt (4121000), nicht als
    Marketplace-Facilitator — auch wenn Amazon die Schweizer MWSt einbehält.
    Klärung mit Steuerberater offen, ob CH später wie GB behandelt werden soll."""
    line = RawInvoiceLine(
        line_no=1, net=Decimal("100"),
        gross=Decimal("100"), vat_amount=Decimal("0"), vat_rate=Decimal("0"),
    )
    inv = _invoice("DE", "CH", platform_name="Amazon.de")
    inv = inv.model_copy(update={"lines": (line,)})
    d = decide(inv, line, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.THIRD_COUNTRY
    assert d.expected_vat_rate == Decimal("0")
    assert d.tax_country == "CH"


def test_de_domestic_zero_vat_with_vat_id_not_rc() -> None:
    """DE→DE + vat_id + 0% must NOT be treated as RC; expected_rate=19 with note."""
    line = RawInvoiceLine(
        line_no=1, net=Decimal("100"),
        gross=Decimal("100"), vat_amount=Decimal("0"), vat_rate=Decimal("0"),
    )
    inv = _invoice("DE", "DE", vat_id="DE123456789")
    inv = inv.model_copy(update={"lines": (line,)})
    d = decide(inv, line, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.DOMESTIC
    assert d.expected_vat_rate == Decimal("19")
    assert any("§13b" in n for n in d.notes)


def test_normalise_vat_id_adds_missing_prefix() -> None:
    """Marketplaces sometimes drop the leading IT/ES prefix."""
    from jtl2datev.core.tax_engine import normalise_vat_id

    assert normalise_vat_id("12345678901", "IT") == "IT12345678901"
    assert normalise_vat_id("IT12345678901", "IT") == "IT12345678901"
    assert normalise_vat_id("  it 1234 5678 ", "IT") == "IT12345678"
    assert normalise_vat_id(None, "IT") is None
    assert normalise_vat_id("", "IT") is None
    # No customer country and no prefix: best-effort cleaned value
    assert normalise_vat_id("99999", None) == "99999"
