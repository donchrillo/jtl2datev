"""Tests for core/rules.py — DATEV account mapping."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from jtl2datev.core.models import (
    PartyAddress,
    RawInvoice,
    RawInvoiceLine,
    TaxDecision,
    TaxTreatment,
)
from jtl2datev.core.rules import map_to_datev_account, map_to_debitor_account

_ZERO = Decimal("0")


def _invoice(wh: str, dest: str, vat_id: str | None = None, platform_name: str | None = None) -> RawInvoice:
    return RawInvoice(
        source="jtl_external",
        invoice_no="TEST-001",
        invoice_date=date(2026, 3, 15),
        currency="EUR",
        currency_factor=Decimal("1"),
        warehouse_country=wh,
        ship_to=PartyAddress(country_iso=dest),
        bill_to=PartyAddress(country_iso=dest, vat_id=vat_id),
        is_credit_note=False,
        lines=(),
        platform_name=platform_name,
    )


def _line(vat_rate: Decimal, gross: Decimal = Decimal("100"), net: Decimal = Decimal("84")) -> RawInvoiceLine:
    return RawInvoiceLine(
        line_no=1,
        net=net,
        gross=gross,
        vat_amount=gross - net,
        vat_rate=vat_rate,
    )


def _decision(
    treatment: TaxTreatment,
    vat_id: str | None = None,
    expected_vat: Decimal = _ZERO,
    tax_country: str = "DE",
) -> TaxDecision:
    return TaxDecision(
        treatment=treatment,
        expected_vat_rate=expected_vat,
        tax_country=tax_country,
        cleaned_vat_id=vat_id,
    )


class TestDomestic:
    def test_de_to_de(self) -> None:
        inv = _invoice("DE", "DE")
        line = _line(Decimal("19"))
        dec = _decision(TaxTreatment.DOMESTIC, expected_vat=Decimal("19"), tax_country="DE")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4400000"
        assert result.bu_key == ""

    def test_fr_to_fr(self) -> None:
        inv = _invoice("FR", "FR")
        line = _line(Decimal("20"))
        dec = _decision(TaxTreatment.DOMESTIC, expected_vat=Decimal("20"), tax_country="FR")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4324000"

    def test_it_to_it_vat_zero_with_vat_id_national_reverse_charge(self) -> None:
        inv = _invoice("IT", "IT", vat_id="IT05041920967")
        line = _line(Decimal("0"), gross=Decimal("100"), net=Decimal("100"))
        dec = _decision(TaxTreatment.DOMESTIC, vat_id="IT05041920967", expected_vat=_ZERO, tax_country="IT")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4126000"

    def test_pl_to_pl(self) -> None:
        inv = _invoice("PL", "PL")
        line = _line(Decimal("23"))
        dec = _decision(TaxTreatment.DOMESTIC, expected_vat=Decimal("23"), tax_country="PL")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4327000"

    def test_cz_to_cz(self) -> None:
        inv = _invoice("CZ", "CZ")
        line = _line(Decimal("21"))
        dec = _decision(TaxTreatment.DOMESTIC, expected_vat=Decimal("21"), tax_country="CZ")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4322000"

    def test_es_to_es(self) -> None:
        inv = _invoice("ES", "ES")
        line = _line(Decimal("21"))
        dec = _decision(TaxTreatment.DOMESTIC, expected_vat=Decimal("21"), tax_country="ES")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4323000"


class TestOSS:
    def test_de_to_it_b2c_oss_bu240(self) -> None:
        inv = _invoice("DE", "IT")
        line = _line(Decimal("22"))
        dec = _decision(TaxTreatment.OSS_B2C, expected_vat=Decimal("22"), tax_country="IT")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4320000"
        assert result.bu_key == "240"

    def test_fr_to_it_b2c_oss_bu241(self) -> None:
        inv = _invoice("FR", "IT")
        line = _line(Decimal("22"))
        dec = _decision(TaxTreatment.OSS_B2C, expected_vat=Decimal("22"), tax_country="IT")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4320000"
        assert result.bu_key == "241"


class TestIGL:
    """Per Jera convention: all IGL bookings go to 4126000 regardless of warehouse."""

    def test_de_to_fr_b2b_igl_4126000(self) -> None:
        inv = _invoice("DE", "FR", vat_id="FR12345678901")
        line = _line(_ZERO, gross=Decimal("100"), net=Decimal("100"))
        dec = _decision(TaxTreatment.IGL_B2B, vat_id="FR12345678901", tax_country="DE")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4126000"
        assert result.bu_key == ""

    def test_fr_to_de_b2b_igl_4126000(self) -> None:
        inv = _invoice("FR", "DE", vat_id="DE123456789")
        line = _line(_ZERO, gross=Decimal("100"), net=Decimal("100"))
        dec = _decision(TaxTreatment.IGL_B2B, vat_id="DE123456789", tax_country="FR")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4126000"
        assert result.bu_key == ""

    def test_eu_to_eu_b2b_igl_4126000(self) -> None:
        inv = _invoice("IT", "ES", vat_id="ESA12345678")
        line = _line(_ZERO, gross=Decimal("100"), net=Decimal("100"))
        dec = _decision(TaxTreatment.IGL_B2B, vat_id="ESA12345678", tax_country="IT")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4126000"


class TestThirdCountry:
    """Per Jera convention: all third-country exports go to 4121000 regardless of warehouse."""

    def test_de_to_us_third_country_4121000(self) -> None:
        inv = _invoice("DE", "US")
        line = _line(_ZERO, gross=Decimal("100"), net=Decimal("100"))
        dec = _decision(TaxTreatment.THIRD_COUNTRY, tax_country="US")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4121000"

    def test_gb_to_us_third_country_4121000(self) -> None:
        inv = _invoice("GB", "US")
        line = _line(_ZERO, gross=Decimal("100"), net=Decimal("100"))
        dec = _decision(TaxTreatment.THIRD_COUNTRY, tax_country="US")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4121000"

    def test_pl_to_us_third_country_4121000(self) -> None:
        inv = _invoice("PL", "US")
        line = _line(_ZERO, gross=Decimal("100"), net=Decimal("100"))
        dec = _decision(TaxTreatment.THIRD_COUNTRY, tax_country="US")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4121000"


class TestMarketplace:
    def test_pl_to_gb_amazon_mf_gross_eq_net(self) -> None:
        """PL-Lager → UK Amazon MF (gross == net → Amazon collected VAT)."""
        inv = _invoice("PL", "GB", platform_name="Amazon.co.uk")
        line = _line(_ZERO, gross=Decimal("100"), net=Decimal("100"))
        dec = _decision(TaxTreatment.MARKETPLACE_FACILITATOR, tax_country="GB")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4328000"

    def test_es_to_gb_amazon_export_local_vat(self) -> None:
        """ES-Lager → UK Amazon but gross != net → Export Local VAT."""
        inv = _invoice("ES", "GB", platform_name="Amazon.co.uk")
        line = _line(Decimal("20"), gross=Decimal("120"), net=Decimal("100"))
        dec = _decision(TaxTreatment.EXPORT_LOCAL_VAT, expected_vat=Decimal("20"), tax_country="GB")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4325000"

    def test_de_to_gb_amazon_mf(self) -> None:
        inv = _invoice("DE", "GB", platform_name="Amazon.co.uk")
        line = _line(_ZERO, gross=Decimal("50"), net=Decimal("50"))
        dec = _decision(TaxTreatment.MARKETPLACE_FACILITATOR, tax_country="GB")
        result = map_to_datev_account(inv, line, dec)
        assert result.account == "4328000"


class TestDebitorMapping:
    def _dummy_invoice(self) -> RawInvoice:
        return _invoice("DE", "DE")

    def test_amazon_payments(self) -> None:
        inv = self._dummy_invoice()
        result = map_to_debitor_account(inv, payment_method="AmazonPayments", default=10000000)
        assert result == "10005000"

    def test_amazon_payments_case_insensitive(self) -> None:
        inv = self._dummy_invoice()
        result = map_to_debitor_account(inv, payment_method="amazonpayments", default=10000000)
        assert result == "10005000"

    def test_paypal(self) -> None:
        inv = self._dummy_invoice()
        result = map_to_debitor_account(inv, payment_method="PayPal", default=10000000)
        assert result == "10004000"

    def test_otto(self) -> None:
        inv = self._dummy_invoice()
        result = map_to_debitor_account(inv, payment_method="Otto.de", default=10000000)
        assert result == "10011000"

    def test_unknown_falls_back_to_default(self) -> None:
        inv = self._dummy_invoice()
        result = map_to_debitor_account(inv, payment_method="SomeUnknownMethod", default=10000000)
        assert result == "10000000"

    def test_none_falls_back_to_default(self) -> None:
        inv = self._dummy_invoice()
        result = map_to_debitor_account(inv, payment_method=None, default=10000000)
        assert result == "10000000"

    def test_kaufland(self) -> None:
        inv = self._dummy_invoice()
        result = map_to_debitor_account(inv, payment_method="Kaufland.de", default=10000000)
        assert result == "10008000"
