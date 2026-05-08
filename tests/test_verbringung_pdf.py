"""Tests for verbringung_pdf.generate_proforma_pdfs."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from jtl2datev.core.verbringung_parser import MovementRow
from jtl2datev.core.verbringung_pricing import PricingResult
from jtl2datev.core.verbringung_pdf import generate_proforma_pdfs


def _make_movement(
    transaction_type: str = "FC_TRANSFER",
    seller_sku: str = "SKU-001",
    departure_country: str = "DE",
    arrival_country: str = "PL",
    depart_date: date | None = date(2026, 1, 15),
    complete_date: date | None = date(2026, 1, 31),
    qty: int = 2,
) -> MovementRow:
    return MovementRow(
        transaction_type=transaction_type,  # type: ignore[arg-type]
        transaction_event_id="EVT-001",
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


class TestSmoke:
    def test_single_route_creates_one_pdf(self, tmp_path: Path) -> None:
        movements = [
            _make_movement(seller_sku="SKU-001", qty=3),
            _make_movement(seller_sku="SKU-002", qty=1),
        ]
        pricing = {
            "SKU-001": _make_pricing("SKU-001"),
            "SKU-002": _make_pricing("SKU-002"),
        }
        paths = generate_proforma_pdfs(
            movements, pricing, "2026-01", tmp_path,
            own_vat_ids={"DE": "DE123456789", "PL": "PL123456789"},
        )
        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].stat().st_size > 0

    def test_empty_movements_creates_no_pdfs(self, tmp_path: Path) -> None:
        paths = generate_proforma_pdfs([], {}, "2026-01", tmp_path)
        assert paths == []


class TestFileNaming:
    def test_pfr_naming_convention(self, tmp_path: Path) -> None:
        movements = [_make_movement(departure_country="DE", arrival_country="PL")]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        paths = generate_proforma_pdfs(
            movements, pricing, "2026-01", tmp_path,
            own_vat_ids={"DE": "DE123", "PL": "PL456"},
        )
        assert len(paths) == 1
        assert paths[0].name == "PFR26-01-0001.pdf"

    def test_starting_pfr_number_respected(self, tmp_path: Path) -> None:
        movements = [_make_movement(departure_country="DE", arrival_country="PL")]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        paths = generate_proforma_pdfs(
            movements, pricing, "2026-02", tmp_path,
            starting_pfr_number=5,
            own_vat_ids={"DE": "DE123", "PL": "PL456"},
        )
        assert paths[0].name == "PFR26-02-0005.pdf"

    def test_different_months(self, tmp_path: Path) -> None:
        movements = [_make_movement()]
        pricing = {"SKU-001": _make_pricing("SKU-001")}
        paths = generate_proforma_pdfs(
            movements, pricing, "2026-03", tmp_path,
            own_vat_ids={"DE": "DE123", "PL": "PL456"},
        )
        assert "PFR26-03-" in paths[0].name


class TestRouteGrouping:
    def test_two_routes_create_two_pdfs(self, tmp_path: Path) -> None:
        movements = [
            _make_movement(departure_country="DE", arrival_country="PL", seller_sku="SKU-001"),
            _make_movement(departure_country="PL", arrival_country="CZ", seller_sku="SKU-002"),
        ]
        pricing = {
            "SKU-001": _make_pricing("SKU-001"),
            "SKU-002": _make_pricing("SKU-002"),
        }
        paths = generate_proforma_pdfs(
            movements, pricing, "2026-01", tmp_path,
            own_vat_ids={"DE": "DE123", "PL": "PL456", "CZ": "CZ789"},
        )
        assert len(paths) == 2

    def test_three_movements_two_routes(self, tmp_path: Path) -> None:
        movements = [
            _make_movement(departure_country="DE", arrival_country="PL", seller_sku="SKU-001"),
            _make_movement(departure_country="DE", arrival_country="PL", seller_sku="SKU-002"),
            _make_movement(departure_country="PL", arrival_country="CZ", seller_sku="SKU-003"),
        ]
        pricing = {k: _make_pricing(k) for k in ["SKU-001", "SKU-002", "SKU-003"]}
        paths = generate_proforma_pdfs(
            movements, pricing, "2026-01", tmp_path,
            own_vat_ids={"DE": "DE123", "PL": "PL456", "CZ": "CZ789"},
        )
        assert len(paths) == 2

    def test_routes_sorted_alphabetically(self, tmp_path: Path) -> None:
        movements = [
            _make_movement(departure_country="PL", arrival_country="CZ", seller_sku="SKU-002"),
            _make_movement(departure_country="DE", arrival_country="PL", seller_sku="SKU-001"),
        ]
        pricing = {k: _make_pricing(k) for k in ["SKU-001", "SKU-002"]}
        paths = generate_proforma_pdfs(
            movements, pricing, "2026-01", tmp_path,
            own_vat_ids={"DE": "DE123", "PL": "PL456", "CZ": "CZ789"},
        )
        # Alphabetical: DE->PL < PL->CZ
        assert paths[0].name == "PFR26-01-0001.pdf"
        assert paths[1].name == "PFR26-01-0002.pdf"
        # Both should exist
        for p in paths:
            assert p.exists()

    def test_all_pdfs_are_non_empty(self, tmp_path: Path) -> None:
        movements = [
            _make_movement(departure_country="DE", arrival_country="ES", seller_sku="SKU-A", qty=10),
            _make_movement(departure_country="CZ", arrival_country="DE", seller_sku="SKU-B", qty=5),
        ]
        pricing = {k: _make_pricing(k) for k in ["SKU-A", "SKU-B"]}
        paths = generate_proforma_pdfs(
            movements, pricing, "2026-01", tmp_path,
            own_vat_ids={"DE": "DE123", "ES": "ES456", "CZ": "CZ789"},
        )
        for p in paths:
            assert p.stat().st_size > 1000  # must be a real PDF, not empty


class TestContentSmoke:
    def test_pdf_is_readable_by_pdfplumber(self, tmp_path: Path) -> None:
        """Smoke test: generated PDF must be parseable and contain key strings."""
        import pdfplumber

        movements = [_make_movement(departure_country="DE", arrival_country="PL")]
        pricing = {"SKU-001": _make_pricing("SKU-001", ek_netto=Decimal("3.50"))}
        paths = generate_proforma_pdfs(
            movements, pricing, "2026-01", tmp_path,
            own_vat_ids={"DE": "DE249030238", "PL": "PL5263144779"},
        )
        assert len(paths) == 1

        with pdfplumber.open(str(paths[0])) as pdf:
            all_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        assert "Pro-Forma Rechnung" in all_text
        assert "PFR26-01-0001" in all_text
        assert "ToCi Vertrieb OHG" in all_text
        assert "Deutschland" in all_text
        assert "Polen" in all_text
        assert "DE249030238" in all_text
        assert "PL5263144779" in all_text
