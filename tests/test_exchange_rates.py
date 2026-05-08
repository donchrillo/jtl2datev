"""Tests for core/exchange_rates.py."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from jtl2datev.core.exchange_rates import (
    get_rate,
    get_rates_for_period,
    import_bmf_rates,
    load_rates,
    parse_bmf_csv,
    set_rate,
)


# ---------------------------------------------------------------------------
# Sample BMF CSV for tests (ISO-8859-1 encoded bytes, minimal)
# ---------------------------------------------------------------------------

_SAMPLE_CSV = (
    "Monatlich fortgeschriebene Übersicht der Umsatzsteuer-Umrechnungskurse 2026\r\n"
    "Land;Währung;Januar[1];Februar [2];März [3];April [4];Mai [5]\r\n"
    "Polen;1 Euro;4,2127 PLN;4,2184 PLN;4,2715 PLN;;;\r\n"
    "Tschechien;1 Euro;24,278 CZK;24,260 CZK;;;;\r\n"
    "Indonesien;1 Euro;19.757,02 IDR;20.001,50 IDR;;;;\r\n"
    "Großbritannien;1 Euro;0,86828 GBP;;;;;\r\n"
)
_SAMPLE_CSV_BYTES = _SAMPLE_CSV.encode("iso-8859-1")


class TestParseBmfCsv:
    def test_parses_known_currencies(self) -> None:
        result = parse_bmf_csv(_SAMPLE_CSV_BYTES)
        assert "2026-01" in result
        assert result["2026-01"]["PLN"] == "4.2127"
        assert result["2026-01"]["CZK"] == "24.278"
        assert result["2026-01"]["GBP"] == "0.86828"

    def test_parses_multiple_periods(self) -> None:
        result = parse_bmf_csv(_SAMPLE_CSV_BYTES)
        assert result["2026-02"]["PLN"] == "4.2184"
        assert result["2026-02"]["CZK"] == "24.260"
        assert result["2026-03"]["PLN"] == "4.2715"

    def test_thousands_separator_removed(self) -> None:
        result = parse_bmf_csv(_SAMPLE_CSV_BYTES)
        # 19.757,02 IDR → "19757.02"
        assert result["2026-01"]["IDR"] == "19757.02"
        assert result["2026-02"]["IDR"] == "20001.50"

    def test_empty_cells_are_skipped(self) -> None:
        result = parse_bmf_csv(_SAMPLE_CSV_BYTES)
        # April and beyond are empty for PLN/CZK/GBP
        assert "2026-04" not in result or "PLN" not in result.get("2026-04", {})

    def test_year_extracted_from_title(self) -> None:
        result = parse_bmf_csv(_SAMPLE_CSV_BYTES)
        # All periods should be 2026-xx
        for period in result:
            assert period.startswith("2026-")

    def test_raises_on_missing_year(self) -> None:
        bad_csv = b"No year here\r\nLand;Wahrung;Januar[1]\r\n"
        with pytest.raises(ValueError, match="Cannot extract year"):
            parse_bmf_csv(bad_csv)

    def test_umlaut_month_names_parsed(self) -> None:
        """März (with umlaut) must map to month 3."""
        result = parse_bmf_csv(_SAMPLE_CSV_BYTES)
        assert "2026-03" in result

    def test_decimal_precision_preserved(self) -> None:
        result = parse_bmf_csv(_SAMPLE_CSV_BYTES)
        # 4.2127 must survive as exact string
        assert result["2026-01"]["PLN"] == "4.2127"
        d = Decimal(result["2026-01"]["PLN"])
        assert d == Decimal("4.2127")


class TestSetRateGetRate:
    def test_round_trip(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", Decimal("4.2127"), source="BMF", path=p)
        assert get_rate("2026-01", "PLN", path=p) == Decimal("4.2127")

    def test_creates_file_and_parents(self, tmp_path: Path) -> None:
        p = tmp_path / "sub" / "dir" / "rates.json"
        set_rate("2026-01", "CZK", "24.278", path=p)
        assert p.exists()

    def test_get_rate_missing_period(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        assert get_rate("2026-01", "PLN", path=p) is None

    def test_get_rate_missing_currency(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", "4.2127", path=p)
        assert get_rate("2026-01", "USD", path=p) is None

    def test_get_rate_missing_file_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "nonexistent.json"
        assert get_rate("2026-01", "PLN", path=p) is None

    def test_source_stored(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", "4.21", source="manual", path=p)
        data = load_rates(path=p)
        assert data["2026-01"]["PLN"]["source"] == "manual"

    def test_overwrite_existing(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", "4.00", path=p)
        set_rate("2026-01", "PLN", "4.21", path=p)
        assert get_rate("2026-01", "PLN", path=p) == Decimal("4.21")

    def test_uppercase_currency_key(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "pln", "4.2127", path=p)
        assert get_rate("2026-01", "PLN", path=p) == Decimal("4.2127")

    def test_atomic_write_file_is_valid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", "4.21", path=p)
        with p.open() as fh:
            data = json.load(fh)
        assert "2026-01" in data

    def test_decimal_precision_round_trip(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", Decimal("4.2127"), path=p)
        retrieved = get_rate("2026-01", "PLN", path=p)
        assert retrieved == Decimal("4.2127")


class TestGetRatesForPeriod:
    def test_returns_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", "4.2127", path=p)
        set_rate("2026-01", "CZK", "24.278", path=p)
        rates = get_rates_for_period("2026-01", path=p)
        assert rates["PLN"] == Decimal("4.2127")
        assert rates["CZK"] == Decimal("24.278")

    def test_missing_period_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        assert get_rates_for_period("2099-01", path=p) == {}

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "nonexistent.json"
        assert get_rates_for_period("2026-01", path=p) == {}


class TestImportBmfRates:
    def test_import_writes_rates(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        imported = import_bmf_rates(2026, path=p, content=_SAMPLE_CSV_BYTES)
        assert "PLN" in imported.get("2026-01", [])
        assert "CZK" in imported.get("2026-01", [])

    def test_import_does_not_overwrite_manual(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", "4.9999", source="manual", path=p)
        import_bmf_rates(2026, path=p, content=_SAMPLE_CSV_BYTES)
        # manual rate must survive
        assert get_rate("2026-01", "PLN", path=p) == Decimal("4.9999")

    def test_import_overwrites_bmf(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", "4.0000", source="BMF", path=p)
        import_bmf_rates(2026, path=p, content=_SAMPLE_CSV_BYTES)
        assert get_rate("2026-01", "PLN", path=p) == Decimal("4.2127")

    def test_returns_imported_map(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        imported = import_bmf_rates(2026, path=p, content=_SAMPLE_CSV_BYTES)
        # PLN appears in 2026-01, 2026-02, 2026-03
        assert "2026-01" in imported
        assert "2026-02" in imported

    def test_creates_file(self, tmp_path: Path) -> None:
        p = tmp_path / "newdir" / "rates.json"
        import_bmf_rates(2026, path=p, content=_SAMPLE_CSV_BYTES)
        assert p.exists()

    def test_import_result_is_json_decodable(self, tmp_path: Path) -> None:
        p = tmp_path / "rates.json"
        import_bmf_rates(2026, path=p, content=_SAMPLE_CSV_BYTES)
        with p.open() as fh:
            data = json.load(fh)
        assert isinstance(data, dict)

    def test_manual_rate_skipped_message(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        p = tmp_path / "rates.json"
        set_rate("2026-01", "PLN", "4.9999", source="manual", path=p)
        with caplog.at_level(logging.WARNING, logger="jtl2datev.core.exchange_rates"):
            import_bmf_rates(2026, path=p, content=_SAMPLE_CSV_BYTES)
        assert any("manual" in r.message.lower() for r in caplog.records)
