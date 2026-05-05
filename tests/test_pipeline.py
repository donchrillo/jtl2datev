from datetime import date
from decimal import Decimal

import pytest

from jtl2datev.core.models import PartyAddress, RawInvoice, RawInvoiceLine, TaxTreatment
from jtl2datev.core.pipeline import ReconcileReport, run_reconcile

OWN_VAT = frozenset({"DE", "FR", "IT", "ES", "PL", "CZ", "GB"})


def _line(
    line_no: int,
    vat_rate: Decimal = Decimal("19.00"),
    vat_amount: Decimal = Decimal("19.00"),
) -> RawInvoiceLine:
    return RawInvoiceLine(
        line_no=line_no,
        quantity=Decimal("1"),
        net=Decimal("100"),
        gross=Decimal("100") + vat_amount,
        vat_amount=vat_amount,
        vat_rate=vat_rate,
    )


def _invoice(
    invoice_no: str,
    warehouse: str,
    dest: str,
    source: str = "jtl_own",
    vat_id: str | None = None,
    platform_name: str | None = None,
    lines: tuple[RawInvoiceLine, ...] | None = None,
    is_credit_note: bool = False,
) -> RawInvoice:
    if lines is None:
        lines = (_line(1),)
    return RawInvoice(
        source=source,  # type: ignore[arg-type]
        invoice_no=invoice_no,
        invoice_date=date(2026, 1, 15),
        currency="EUR",
        currency_factor=Decimal("1"),
        warehouse_country=warehouse,
        ship_to=PartyAddress(country_iso=dest, vat_id=vat_id),
        bill_to=PartyAddress(country_iso=dest),
        is_credit_note=is_credit_note,
        lines=lines,
        platform_name=platform_name,
    )


def test_empty_iterator_returns_zero_report() -> None:
    report = run_reconcile(iter([]), own_vat_countries=OWN_VAT)
    assert report.invoices_total == 0
    assert report.lines_total == 0
    assert report.invoices_with_any_mismatch == 0
    assert len(report.sample_mismatches) == 0


def test_single_domestic_no_mismatch() -> None:
    inv = _invoice("R-001", "DE", "DE")
    report = run_reconcile([inv], own_vat_countries=OWN_VAT)
    assert report.invoices_total == 1
    assert report.lines_total == 1
    assert report.treatments[TaxTreatment.DOMESTIC] == 1
    assert report.invoices_with_any_mismatch == 0
    assert len(report.sample_mismatches) == 0


def test_third_country_with_nonzero_vat_produces_mismatch() -> None:
    # DE→US: engine says THIRD_COUNTRY (0% VAT), but JTL stored 19% rate + vat_amount
    bad_line = _line(1, vat_rate=Decimal("19.00"), vat_amount=Decimal("19.00"))
    inv = _invoice("R-002", "DE", "US", lines=(bad_line,))
    report = run_reconcile([inv], own_vat_countries=OWN_VAT)
    assert report.invoices_with_any_mismatch == 1
    assert sum(report.mismatches_by_severity.values()) > 0
    assert report.mismatches_by_source["jtl_own"] > 0
    assert report.mismatches_by_warehouse["DE"] > 0


def test_multiple_invoices_aggregate_correctly() -> None:
    invoices = [
        _invoice("R-001", "DE", "DE"),  # domestic, no mismatch
        _invoice("R-002", "DE", "FR"),  # OSS B2C, no mismatch (same vat_rate retained)
        _invoice(  # DE→US with wrong VAT → mismatch
            "R-003",
            "DE",
            "US",
            lines=(_line(1, vat_rate=Decimal("19.00"), vat_amount=Decimal("19.00")),),
        ),
    ]
    report = run_reconcile(invoices, own_vat_countries=OWN_VAT)
    assert report.invoices_total == 3
    assert report.lines_total == 3
    assert report.invoices_with_any_mismatch == 1
    assert report.treatments[TaxTreatment.DOMESTIC] == 1
    assert report.treatments[TaxTreatment.OSS_B2C] == 1
    assert report.treatments[TaxTreatment.THIRD_COUNTRY] == 1


def test_sample_limit_respected() -> None:
    # 5 invoices each with a mismatch, but sample_limit=2
    bad_line = _line(1, vat_rate=Decimal("19.00"), vat_amount=Decimal("19.00"))
    invoices = [
        _invoice(f"R-{i:03}", "DE", "US", lines=(bad_line,)) for i in range(5)
    ]
    report = run_reconcile(invoices, own_vat_countries=OWN_VAT, sample_limit=2)
    assert report.invoices_with_any_mismatch == 5
    assert len(report.sample_mismatches) == 2


def test_oss_b2c_vat_rate_no_mismatch_when_matching() -> None:
    # DE→FR OSS: engine keeps the vat_rate from the line (B2C, no change)
    line = _line(1, vat_rate=Decimal("20.00"), vat_amount=Decimal("20.00"))
    inv = _invoice("R-001", "DE", "FR", lines=(line,))
    report = run_reconcile([inv], own_vat_countries=OWN_VAT)
    assert report.invoices_with_any_mismatch == 0


def test_igl_b2b_with_vat_amount_produces_error_mismatch() -> None:
    # DE→FR B2B (has VAT-ID): engine expects 0% + 0 vat_amount
    bad_line = _line(1, vat_rate=Decimal("0.00"), vat_amount=Decimal("19.00"))
    inv = _invoice("R-001", "DE", "FR", vat_id="FR12345678901", lines=(bad_line,))
    report = run_reconcile([inv], own_vat_countries=OWN_VAT)
    assert report.invoices_with_any_mismatch == 1
    error_mms = [mm for mm in report.sample_mismatches if mm.severity == "error"]
    assert len(error_mms) >= 1
    assert error_mms[0].field == "vat_amount"


def test_credit_note_source_tracked_in_mismatches() -> None:
    bad_line = _line(1, vat_rate=Decimal("19.00"), vat_amount=Decimal("19.00"))
    inv = _invoice(
        "GS-001", "DE", "US", source="jtl_credit_note",
        is_credit_note=True, lines=(bad_line,)
    )
    report = run_reconcile([inv], own_vat_countries=OWN_VAT)
    assert report.mismatches_by_source.get("jtl_credit_note", 0) > 0


def test_report_is_dataclass_instance() -> None:
    report = run_reconcile(iter([]), own_vat_countries=OWN_VAT)
    assert isinstance(report, ReconcileReport)


@pytest.mark.integration
def test_integration_q1_2026() -> None:
    """Requires live JTL DB. Run with: pytest -m integration"""
    from datetime import date

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine

    settings = Settings()
    engine = make_engine(settings)
    repo = JtlInvoiceRepository(engine)
    invoices = repo.fetch_invoices(date_from=date(2026, 1, 1), date_to=date(2026, 4, 1))
    report = run_reconcile(invoices, own_vat_countries=settings.own_vat_countries)
    assert report.invoices_total > 1000
