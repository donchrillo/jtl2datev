from datetime import date
from pathlib import Path

import pytest

from jtl2datev.core.verbringung_parser import MovementRow, parse_amazon_report

_SAMPLES = Path(__file__).parent.parent / "samples" / "verbringungen"
_JAN = _SAMPLES / "3871700020495.txt"
_FEB = _SAMPLES / "3919876020521.txt"
_MAR = _SAMPLES / "3968288020550.txt"

pytestmark = pytest.mark.skipif(
    not _JAN.exists(),
    reason="Q1-Sample-Reports nicht im Repo (wurden entfernt nach Q1-Verifikation).",
)


@pytest.fixture(scope="module")
def jan_rows() -> list[MovementRow]:
    return parse_amazon_report(_JAN)


def test_jan_total_count(jan_rows: list[MovementRow]) -> None:
    assert len(jan_rows) == 1241


def test_jan_fc_transfer_count(jan_rows: list[MovementRow]) -> None:
    fc = [r for r in jan_rows if r.transaction_type == "FC_TRANSFER"]
    assert len(fc) == 1231


def test_jan_inbound_count(jan_rows: list[MovementRow]) -> None:
    inbound = [r for r in jan_rows if r.transaction_type == "INBOUND"]
    assert len(inbound) == 10


def test_no_filtered_types(jan_rows: list[MovementRow]) -> None:
    forbidden = {"SALE", "REFUND", "RETURN", "LIQUIDATION_SALE", "LIQUIDATION_REFUND", "DONATION"}
    types_in_result = {r.transaction_type for r in jan_rows}
    assert types_in_result.isdisjoint(forbidden)


def test_first_fc_transfer_spot_check(jan_rows: list[MovementRow]) -> None:
    first_fc = next(r for r in jan_rows if r.transaction_type == "FC_TRANSFER")
    assert first_fc.departure_country == "PL"
    assert first_fc.arrival_country == "CZ"
    assert first_fc.qty == 1
    assert "amzn.gr.ACA" in first_fc.seller_sku


def test_inbound_depart_country(jan_rows: list[MovementRow]) -> None:
    inbound_rows = [r for r in jan_rows if r.transaction_type == "INBOUND"]
    assert all(r.departure_country == "DE" for r in inbound_rows)


def test_inbound_arrival_country(jan_rows: list[MovementRow]) -> None:
    inbound_rows = [r for r in jan_rows if r.transaction_type == "INBOUND"]
    assert all(r.arrival_country == "PL" for r in inbound_rows)


def test_date_parsing(jan_rows: list[MovementRow]) -> None:
    first_fc = next(r for r in jan_rows if r.transaction_type == "FC_TRANSFER")
    assert first_fc.depart_date == date(2026, 1, 29)
    assert first_fc.arrival_date == date(2026, 1, 31)
    assert first_fc.complete_date == date(2026, 1, 31)


def test_weight_parsed_as_decimal(jan_rows: list[MovementRow]) -> None:
    from decimal import Decimal
    rows_with_weight = [r for r in jan_rows if r.item_weight is not None]
    assert len(rows_with_weight) > 0
    assert all(isinstance(r.item_weight, Decimal) for r in rows_with_weight)


def test_is_return_to_user_not_set_in_jan(jan_rows: list[MovementRow]) -> None:
    assert not any(r.is_return_to_user for r in jan_rows)


def test_all_three_files_parseable() -> None:
    for path in [_JAN, _FEB, _MAR]:
        rows = parse_amazon_report(path)
        assert len(rows) > 0
        assert all(r.transaction_type in {"FC_TRANSFER", "INBOUND"} for r in rows)
