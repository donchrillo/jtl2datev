"""Tests for verbringung_parser encoding detection (W-12)."""
from pathlib import Path

import pytest

from jtl2datev.core.verbringung_parser import _read_amazon_report, parse_amazon_report

# Minimal TSV header + one FC_TRANSFER row
_TSV_HEADER = (
    "TRANSACTION_TYPE\tTRANSACTION_EVENT_ID\tACTIVITY_TRANSACTION_ID\t"
    "TRANSACTION_DEPART_DATE\tTRANSACTION_ARRIVAL_DATE\tTRANSACTION_COMPLETE_DATE\t"
    "SELLER_SKU\tASIN\tITEM_DESCRIPTION\tQTY\tITEM_WEIGHT\t"
    "DEPARTURE_COUNTRY\tARRIVAL_COUNTRY\tARRIVAL_POST_CODE\t"
    "TRANSACTION_CURRENCY_CODE\tSELLER_DEPART_COUNTRY_VAT_NUMBER\t"
    "SELLER_ARRIVAL_COUNTRY_VAT_NUMBER\n"
)
_TSV_ROW = (
    "FC_TRANSFER\tEVT-001\tACT-001\t"
    "01-01-2026\t03-01-2026\t03-01-2026\t"
    "SKU-A\tB001\tTestprodukt\t1\t0.5\t"
    "DE\tPL\t00-001\t"
    "EUR\tDE123\tPL456\n"
)
_TSV_CONTENT = _TSV_HEADER + _TSV_ROW


class TestReadAmazonReportEncoding:
    def test_reads_utf8(self, tmp_path: Path) -> None:
        f = tmp_path / "report.txt"
        f.write_bytes(_TSV_CONTENT.encode("utf-8"))
        result = _read_amazon_report(f)
        assert "FC_TRANSFER" in result

    def test_reads_utf8_bom(self, tmp_path: Path) -> None:
        f = tmp_path / "report.txt"
        f.write_bytes(_TSV_CONTENT.encode("utf-8-sig"))
        result = _read_amazon_report(f)
        assert "FC_TRANSFER" in result

    def test_reads_cp1252(self, tmp_path: Path) -> None:
        f = tmp_path / "report.txt"
        f.write_bytes(_TSV_CONTENT.encode("cp1252"))
        result = _read_amazon_report(f)
        assert "FC_TRANSFER" in result

    def test_reads_nonempty_content(self, tmp_path: Path) -> None:
        """Any non-empty file is decoded without raising."""
        f = tmp_path / "report.txt"
        f.write_bytes(_TSV_CONTENT.encode("cp1252"))
        result = _read_amazon_report(f)
        assert len(result) > 0


class TestParseAmazonReportCp1252:
    def test_parses_cp1252_tsv(self, tmp_path: Path) -> None:
        f = tmp_path / "report.txt"
        f.write_bytes(_TSV_CONTENT.encode("cp1252"))
        rows = parse_amazon_report(f)
        assert len(rows) == 1
        assert rows[0].seller_sku == "SKU-A"
        assert rows[0].departure_country == "DE"
        assert rows[0].arrival_country == "PL"
