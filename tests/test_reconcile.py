from datetime import date
from decimal import Decimal

from jtl2datev.core.models import (
    LineDecision,
    PartyAddress,
    RawInvoice,
    RawInvoiceLine,
    TaxDecision,
    TaxTreatment,
)
from jtl2datev.core.reconcile import compare

_ADDR_DE = PartyAddress(country_iso="DE")

_BASE_INVOICE = RawInvoice(
    source="jtl_own",
    invoice_no="R-001",
    invoice_date=date(2026, 1, 15),
    currency="EUR",
    currency_factor=Decimal("1"),
    warehouse_country="DE",
    ship_to=_ADDR_DE,
    bill_to=_ADDR_DE,
    is_credit_note=False,
    lines=(),
)


def _line(line_no: int, vat_rate: Decimal, vat_amount: Decimal) -> RawInvoiceLine:
    return RawInvoiceLine(
        line_no=line_no,
        quantity=Decimal("1"),
        net=Decimal("100"),
        gross=Decimal("100") + vat_amount,
        vat_amount=vat_amount,
        vat_rate=vat_rate,
    )


def test_no_mismatches_for_matching_domestic() -> None:
    line = _line(1, Decimal("19.00"), Decimal("19.00"))
    decision = TaxDecision(
        treatment=TaxTreatment.DOMESTIC,
        expected_vat_rate=Decimal("19.00"),
        tax_country="DE",
    )
    ld = LineDecision(line=line, decision=decision)
    result = compare(_BASE_INVOICE, [ld])
    assert result == []


def test_igl_b2b_with_nonzero_vat_amount_is_error() -> None:
    line = _line(1, Decimal("0.00"), Decimal("19.00"))
    decision = TaxDecision(
        treatment=TaxTreatment.IGL_B2B,
        expected_vat_rate=Decimal("0"),
        tax_country="DE",
    )
    ld = LineDecision(line=line, decision=decision)
    result = compare(_BASE_INVOICE, [ld])

    error_mismatches = [m for m in result if m.severity == "error" and m.field == "vat_amount"]
    assert len(error_mismatches) == 1
    assert error_mismatches[0].invoice_no == "R-001"
    assert error_mismatches[0].line_no == 1
