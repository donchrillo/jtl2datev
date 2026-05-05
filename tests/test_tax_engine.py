from datetime import date
from decimal import Decimal

from jtl2datev.core.models import PartyAddress, RawInvoice, RawInvoiceLine, TaxTreatment
from jtl2datev.core.tax_engine import decide

OWN_VAT = frozenset({"DE", "FR", "IT", "ES", "PL", "CZ", "GB"})

_BASE_LINE = RawInvoiceLine(
    line_no=1,
    quantity=Decimal("1"),
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
    inv = _invoice("DE", "FR", vat_id="FR12345678901")
    d = decide(inv, _BASE_LINE, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.IGL_B2B
    assert d.expected_vat_rate == Decimal("0")


def test_third_country_de_to_us() -> None:
    inv = _invoice("DE", "US")
    d = decide(inv, _BASE_LINE, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.THIRD_COUNTRY
    assert d.expected_vat_rate == Decimal("0")


def test_marketplace_facilitator_pl_to_gb_amazon() -> None:
    inv = _invoice("PL", "GB", platform_name="Amazon")
    d = decide(inv, _BASE_LINE, own_vat_countries=OWN_VAT)
    assert d.treatment == TaxTreatment.MARKETPLACE_FACILITATOR
    assert d.expected_vat_rate == Decimal("0")


def test_unknown_warehouse_warns() -> None:
    inv = _invoice("SE", "SE")
    d = decide(inv, _BASE_LINE, own_vat_countries=OWN_VAT)
    assert any("own_vat_countries" in n for n in d.notes)
