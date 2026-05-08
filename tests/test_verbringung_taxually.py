"""Tests for verbringung_taxually.format_verbringung_xlsx."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from jtl2datev.core.taxually import TAXUALLY_COLUMNS
from jtl2datev.core.verbringung_parser import MovementRow
from jtl2datev.core.verbringung_pricing import PricingResult
from jtl2datev.core.verbringung_taxually import format_verbringung_xlsx


def _make_movement(
    transaction_type: str = "FC_TRANSFER",
    seller_sku: str = "SKU-001",
    departure_country: str = "DE",
    arrival_country: str = "PL",
    depart_date: date | None = date(2026, 1, 15),
    complete_date: date | None = date(2026, 1, 31),
    qty: int = 2,
    transaction_event_id: str = "ABCDEF1234567890ABCDEF1234567890",
) -> MovementRow:
    return MovementRow(
        transaction_type=transaction_type,  # type: ignore[arg-type]
        transaction_event_id=transaction_event_id,
        activity_transaction_id="ACT-001",
        depart_date=depart_date,
        arrival_date=date(2026, 1, 31),
        complete_date=complete_date,
        seller_sku=seller_sku,
        asin="B0001",
        description="Test product",
        qty=qty,
        item_weight=None,
        departure_country=departure_country,
        arrival_country=arrival_country,
        arrival_postal_code="00100",
        is_return_to_user=False,
        currency="EUR",
        raw_seller_depart_vat="",
        raw_seller_arrival_vat="",
    )


def _make_pricing(sku: str, ek_netto: Decimal | None = Decimal("5.00")) -> PricingResult:
    return PricingResult(
        seller_sku=sku,
        matched_jtl_artikel=sku,
        matched_via="direct",
        ek_netto=ek_netto,
        description="Test description",
    )


@pytest.fixture
def tmp_xlsx(tmp_path: Path) -> Path:
    return tmp_path / "out.xlsx"


def _load_ws(path: Path):  # type: ignore[no-untyped-def]
    wb = openpyxl.load_workbook(str(path))
    return wb.active


class TestHeaderOrder:
    def test_header_matches_taxually_columns(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement()]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        header = [cell.value for cell in list(ws.rows)[0]]
        assert header == list(TAXUALLY_COLUMNS)

    def test_sheet_name(self, tmp_xlsx: Path) -> None:
        format_verbringung_xlsx([], {}, tmp_xlsx)
        wb = openpyxl.load_workbook(str(tmp_xlsx))
        assert wb.active.title == "Your data"


class TestTransactionType:
    def test_fc_transfer_maps_to_inventory_transfer(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement(transaction_type="FC_TRANSFER")]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert row[0].value == "Inventory transfer"

    def test_inbound_maps_to_sales(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement(transaction_type="INBOUND")]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert row[0].value == "Sales"


class TestVatNumber:
    def test_vat_number_from_departure_country(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement(departure_country="DE")]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        own_vat_ids = {"DE": "DE123456789"}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx, own_vat_ids=own_vat_ids)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert row[3].value == "DE123456789"

    def test_vat_number_empty_for_unknown_country(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement(departure_country="SK")]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        own_vat_ids = {"DE": "DE123456789"}  # no SK entry
        format_verbringung_xlsx(movements, pricing, tmp_xlsx, own_vat_ids=own_vat_ids)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        # None or empty string — both acceptable
        assert not row[3].value


class TestGrossAmount:
    def test_gross_amount_equals_qty_times_ek(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement(qty=3)]
        pricing = {"SKU-001": _make_pricing("SKU-001", ek_netto=Decimal("7.50"))}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert abs(float(row[9].value) - 22.50) < 0.001

    def test_missing_ek_writes_zero(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement(seller_sku="NO-EK-SKU")]
        pricing = {"NO-EK-SKU": _make_pricing("NO-EK-SKU", ek_netto=None)}
        n = format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        assert n == 1  # row still written
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert float(row[9].value) == 0.0

    def test_missing_ek_row_still_written_even_when_not_in_pricing(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement(seller_sku="GHOST-SKU")]
        n = format_verbringung_xlsx(movements, {}, tmp_xlsx)
        assert n == 1
        ws = _load_ws(tmp_xlsx)
        assert len(list(ws.rows)) == 2  # header + 1 data row


class TestColumnsLayout:
    def test_subject_is_goods(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement()]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert row[1].value == "Goods"

    def test_currency_is_eur(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement()]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert row[8].value == "EUR"

    def test_columns_13_to_20_are_empty(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement()]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        # Columns index 10-19 (VAT reporting country through VAT amount_local)
        for col_idx in range(10, 20):
            assert row[col_idx].value is None, f"Column {col_idx} should be None"

    def test_sales_channel_is_empty(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement()]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert not row[2].value

    def test_departure_and_arrival_countries(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement(departure_country="CZ", arrival_country="PL")]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert row[6].value == "CZ"
        assert row[7].value == "PL"


class TestInvoiceNumber:
    def test_invoice_number_truncated_to_30_chars(self, tmp_xlsx: Path) -> None:
        long_id = "A" * 50
        movements = [_make_movement(transaction_event_id=long_id)]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert len(row[5].value) == 30

    def test_invoice_number_short_stays_intact(self, tmp_xlsx: Path) -> None:
        short_id = "FBA123"
        movements = [_make_movement(transaction_event_id=short_id)]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert row[5].value == short_id


class TestReturnValue:
    def test_returns_row_count(self, tmp_xlsx: Path) -> None:
        movements = [_make_movement(), _make_movement(seller_sku="SKU-002")]
        pricing = {
            "SKU-001": _make_pricing("SKU-001"),
            "SKU-002": _make_pricing("SKU-002"),
        }
        n = format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        assert n == 2

    def test_empty_movements_returns_zero(self, tmp_xlsx: Path) -> None:
        n = format_verbringung_xlsx([], {}, tmp_xlsx)
        assert n == 0


class TestDateLogic:
    def test_fc_transfer_uses_depart_date(self, tmp_xlsx: Path) -> None:
        movements = [
            _make_movement(
                transaction_type="FC_TRANSFER",
                depart_date=date(2026, 1, 10),
                complete_date=date(2026, 1, 31),
            )
        ]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert row[4].value == "10.01.2026"

    def test_inbound_uses_complete_date(self, tmp_xlsx: Path) -> None:
        movements = [
            _make_movement(
                transaction_type="INBOUND",
                depart_date=date(2026, 1, 5),
                complete_date=date(2026, 1, 30),
            )
        ]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        format_verbringung_xlsx(movements, pricing, tmp_xlsx)
        ws = _load_ws(tmp_xlsx)
        row = list(ws.rows)[1]
        assert row[4].value == "30.01.2026"
