"""Tests for core/taxually.py and core/taxually_delta.py."""
from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
from jtl2datev.core.models import PartyAddress, RawInvoice, RawInvoiceLine
from jtl2datev.core.taxually import (
    TAXUALLY_COLUMNS,
    _vat_reporting_country,
    format_taxually_xlsx,
)
from jtl2datev.core.taxually_delta import (
    compute_taxually_delta,
    write_taxually_delta_xlsx,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _addr(country: str) -> PartyAddress:
    return PartyAddress(country_iso=country)


def _line(
    gross: Decimal = Decimal("119.00"),
    net: Decimal = Decimal("100.00"),
    vat_amount: Decimal = Decimal("19.00"),
    vat_rate: Decimal = Decimal("19.00"),
) -> RawInvoiceLine:
    return RawInvoiceLine(
        line_no=1,
        quantity=Decimal("1"),
        gross=gross,
        net=net,
        vat_amount=vat_amount,
        vat_rate=vat_rate,
    )


def _invoice(
    invoice_no: str = "R-2026-001",
    gross: Decimal = Decimal("119.00"),
    net: Decimal = Decimal("100.00"),
    vat_amount: Decimal = Decimal("19.00"),
    vat_rate: Decimal = Decimal("19.00"),
    warehouse_country: str = "DE",
    ship_to_country: str = "FR",
    currency: str = "EUR",
    invoice_date: datetime.date = datetime.date(2026, 1, 15),
    is_credit_note: bool = False,
) -> RawInvoice:
    return RawInvoice(
        source="jtl_own",
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        currency=currency,
        currency_factor=Decimal("1"),
        warehouse_country=warehouse_country,
        ship_to=_addr(ship_to_country),
        bill_to=_addr(ship_to_country),
        is_credit_note=is_credit_note,
        lines=(
            _line(
                gross=gross,
                net=net,
                vat_amount=vat_amount,
                vat_rate=vat_rate,
            ),
        ),
    )


def _read_xlsx(path: Path) -> tuple[list[str], list[list]]:
    """Return (header_row, data_rows) from 'Your data' sheet."""
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    ws = wb["Your data"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    header = [str(c) if c is not None else "" for c in rows[0]]
    data = [list(r) for r in rows[1:]]
    return header, data


# ── Header tests ──────────────────────────────────────────────────────────────

def test_header_columns_count_and_order(tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    format_taxually_xlsx([_invoice()], out)
    header, _ = _read_xlsx(out)
    assert header == list(TAXUALLY_COLUMNS)
    assert len(header) == 20


# ── Transaction type ──────────────────────────────────────────────────────────

def test_sale_transaction_type(tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    format_taxually_xlsx([_invoice(gross=Decimal("119.00"))], out)
    _, rows = _read_xlsx(out)
    assert rows[0][0] == "SALE"


def test_refund_transaction_type(tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    inv = _invoice(
        gross=Decimal("-119.00"),
        net=Decimal("-100.00"),
        vat_amount=Decimal("-19.00"),
        is_credit_note=True,
    )
    format_taxually_xlsx([inv], out)
    _, rows = _read_xlsx(out)
    assert rows[0][0] == "REFUND"
    assert rows[0][9] < 0  # Gross amount is negative


# ── VAT reporting country rules ───────────────────────────────────────────────

def test_vat_reporting_country_rate_positive() -> None:
    # rate > 0 → customer country
    assert _vat_reporting_country("FR", "DE", 19.0) == "FR"


def test_vat_reporting_country_zero_rate_gb() -> None:
    # rate == 0, customer is GB → GB
    assert _vat_reporting_country("GB", "DE", 0.0) == "GB"


def test_vat_reporting_country_zero_rate_other() -> None:
    # rate == 0, customer not GB → dispatch country
    assert _vat_reporting_country("US", "DE", 0.0) == "DE"


def test_vat_reporting_country_in_xlsx_row_positive(tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    # FR customer, DE warehouse, 19% VAT → vatc = FR
    inv = _invoice(warehouse_country="DE", ship_to_country="FR", vat_rate=Decimal("19.00"))
    format_taxually_xlsx([inv], out)
    _, rows = _read_xlsx(out)
    vatc_col = TAXUALLY_COLUMNS.index("VAT reporting country")
    assert rows[0][vatc_col] == "FR"


def test_vat_reporting_country_in_xlsx_row_zero_dispatch(tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    # US customer, DE warehouse, 0% → vatc = DE
    inv = _invoice(
        warehouse_country="DE",
        ship_to_country="US",
        vat_rate=Decimal("0"),
        vat_amount=Decimal("0"),
        gross=Decimal("100.00"),
        net=Decimal("100.00"),
    )
    format_taxually_xlsx([inv], out)
    _, rows = _read_xlsx(out)
    vatc_col = TAXUALLY_COLUMNS.index("VAT reporting country")
    assert rows[0][vatc_col] == "DE"


# ── VAT rate as float fraction ────────────────────────────────────────────────

def test_vat_rate_is_fraction(tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    format_taxually_xlsx([_invoice(vat_rate=Decimal("19.00"))], out)
    _, rows = _read_xlsx(out)
    rate_col = TAXUALLY_COLUMNS.index("VAT Rate")
    assert abs(rows[0][rate_col] - 0.19) < 1e-9


def test_vat_rate_23_percent(tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    inv = _invoice(vat_rate=Decimal("23.00"), warehouse_country="DE", ship_to_country="PL")
    format_taxually_xlsx([inv], out)
    _, rows = _read_xlsx(out)
    rate_col = TAXUALLY_COLUMNS.index("VAT Rate")
    assert abs(rows[0][rate_col] - 0.23) < 1e-9


# ── Foreign currency invoice ──────────────────────────────────────────────────

def test_foreign_currency_pln(tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    inv = _invoice(
        currency="PLN",
        warehouse_country="DE",
        ship_to_country="PL",
        vat_rate=Decimal("23.00"),
        gross=Decimal("246.00"),
        net=Decimal("200.00"),
        vat_amount=Decimal("46.00"),
    )
    format_taxually_xlsx([inv], out)
    _, rows = _read_xlsx(out)
    row = rows[0]

    currency_col = TAXUALLY_COLUMNS.index("Currency")
    gross_col = TAXUALLY_COLUMNS.index("Gross amount")
    vatc_col = TAXUALLY_COLUMNS.index("VAT reporting country")
    rate_col = TAXUALLY_COLUMNS.index("VAT Rate")

    assert row[currency_col] == "PLN"
    # openpyxl may return int for whole numbers; check numeric value
    assert isinstance(row[gross_col], (int, float))
    assert abs(row[gross_col] - 246.0) < 1e-6
    assert row[vatc_col] == "PL"
    assert abs(row[rate_col] - 0.23) < 1e-9


# ── Null columns are empty ────────────────────────────────────────────────────

def test_null_columns_empty(tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    format_taxually_xlsx([_invoice()], out)
    _, rows = _read_xlsx(out)
    row = rows[0]
    for col_name in ("Net amount", "VAT amount", "Invoice date", "Local currency",
                     "Exchange rate", "Gross amount_local", "Net amount_local", "VAT amount_local"):
        idx = TAXUALLY_COLUMNS.index(col_name)
        assert row[idx] is None, f"{col_name} should be None, got {row[idx]!r}"


# ── Delta tests ───────────────────────────────────────────────────────────────

def _write_archive(invoices: list[RawInvoice], path: Path) -> None:
    format_taxually_xlsx(invoices, path)


def test_delta_new_invoices_only(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.xlsx"
    inv_old = _invoice(invoice_no="R-2026-001")
    inv_new = _invoice(invoice_no="R-2026-002")
    _write_archive([inv_old], archive_path)

    delta = compute_taxually_delta([inv_old, inv_new], archive_path)
    assert len(delta) == 1
    assert delta[0].invoice_no == "R-2026-002"


def test_delta_no_new_invoices(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.xlsx"
    inv = _invoice(invoice_no="R-2026-001")
    _write_archive([inv], archive_path)

    delta = compute_taxually_delta([inv], archive_path)
    assert delta == []


def test_delta_all_new_when_archive_empty(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.xlsx"
    # Write an empty archive (header only)
    format_taxually_xlsx([], archive_path)

    invoices = [_invoice("R-001"), _invoice("R-002")]
    delta = compute_taxually_delta(invoices, archive_path)
    assert len(delta) == 2


# ── Date-shift in delta ───────────────────────────────────────────────────────

def test_date_shift_overrides_transaction_date(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.xlsx"
    format_taxually_xlsx([], archive_path)

    inv = _invoice(invoice_no="R-2026-001", invoice_date=datetime.date(2026, 1, 15))
    out = tmp_path / "delta.xlsx"
    shift_date = datetime.date(2026, 2, 1)
    write_taxually_delta_xlsx([inv], out, shift_to=shift_date)

    _, rows = _read_xlsx(out)
    tx_date_col = TAXUALLY_COLUMNS.index("Transaction date")
    val = rows[0][tx_date_col]
    # openpyxl returns datetime.datetime or datetime.date for date cells
    if isinstance(val, datetime.datetime):
        val = val.date()
    assert val == datetime.date(2026, 2, 1)
