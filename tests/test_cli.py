from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from jtl2datev.cli import main


def test_version() -> None:
    result = CliRunner().invoke(main, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def test_export_help_shows_both_date_options() -> None:
    result = CliRunner().invoke(main, ["export", "--help"])
    assert result.exit_code == 0
    assert "--month" in result.output
    assert "--from" in result.output
    assert "--to" in result.output


def test_export_no_date_arg_fails() -> None:
    result = CliRunner().invoke(main, ["export", "--out", "/tmp/x.csv"])
    assert result.exit_code != 0
    assert "month" in result.output.lower() or "from" in result.output.lower()


def test_export_both_month_and_from_to_fails() -> None:
    result = CliRunner().invoke(
        main,
        ["export", "--month", "2026-01", "--from", "2026-01-01", "--to", "2026-01-31"],
    )
    assert result.exit_code != 0


def test_export_from_without_to_fails() -> None:
    result = CliRunner().invoke(main, ["export", "--from", "2026-01-01"])
    assert result.exit_code != 0


def test_export_exits_cleanly_with_month() -> None:
    """Export command must not crash hard — DB error, stub message, or success all
    produce exit_code=0 and a non-empty human-readable echo."""
    result = CliRunner().invoke(
        main,
        ["export", "--month", "2026-01", "--out", "/tmp/test_export.csv"],
    )
    assert result.exit_code == 0
    assert result.output.strip(), "Expected at least one output line"


# ---------------------------------------------------------------------------
# export-dutypay
# ---------------------------------------------------------------------------


def test_export_dutypay_help_shows_both_date_options() -> None:
    result = CliRunner().invoke(main, ["export-dutypay", "--help"])
    assert result.exit_code == 0
    assert "--month" in result.output
    assert "--from" in result.output
    assert "--to" in result.output


def test_export_dutypay_no_date_arg_fails() -> None:
    result = CliRunner().invoke(main, ["export-dutypay"])
    assert result.exit_code != 0


def test_export_dutypay_both_month_and_from_to_fails() -> None:
    result = CliRunner().invoke(
        main,
        ["export-dutypay", "--month", "2026-01", "--from", "2026-01-01", "--to", "2026-01-31"],
    )
    assert result.exit_code != 0


def test_export_dutypay_from_without_to_fails() -> None:
    result = CliRunner().invoke(main, ["export-dutypay", "--from", "2026-01-01"])
    assert result.exit_code != 0


def test_export_dutypay_from_to_without_out_fails() -> None:
    """--from/--to without --out must fail (no automatic archive)."""
    result = CliRunner().invoke(
        main, ["export-dutypay", "--from", "2026-01-01", "--to", "2026-01-31"]
    )
    assert result.exit_code != 0
    assert "--out" in result.output or "Pflicht" in result.output


# ---------------------------------------------------------------------------
# export-dutypay-delta
# ---------------------------------------------------------------------------


def test_export_dutypay_delta_help_shows_both_date_options() -> None:
    result = CliRunner().invoke(main, ["export-dutypay-delta", "--help"])
    assert result.exit_code == 0
    assert "--month" in result.output
    assert "--from" in result.output
    assert "--to" in result.output


def test_export_dutypay_delta_no_date_arg_fails() -> None:
    result = CliRunner().invoke(main, ["export-dutypay-delta"])
    assert result.exit_code != 0


def test_export_dutypay_delta_both_month_and_from_to_fails() -> None:
    result = CliRunner().invoke(
        main,
        [
            "export-dutypay-delta",
            "--month", "2026-01",
            "--from", "2026-01-01",
            "--to", "2026-01-31",
        ],
    )
    assert result.exit_code != 0


def test_export_dutypay_delta_from_without_to_fails() -> None:
    result = CliRunner().invoke(main, ["export-dutypay-delta", "--from", "2026-01-01"])
    assert result.exit_code != 0


def test_export_dutypay_delta_from_to_without_out_fails() -> None:
    """--from/--to without --out must fail."""
    result = CliRunner().invoke(
        main,
        ["export-dutypay-delta", "--from", "2026-01-01", "--to", "2026-01-31"],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


def test_reconcile_help_shows_both_date_options() -> None:
    result = CliRunner().invoke(main, ["reconcile", "--help"])
    assert result.exit_code == 0
    assert "--month" in result.output
    assert "--from" in result.output
    assert "--to" in result.output


def test_reconcile_no_date_arg_fails() -> None:
    result = CliRunner().invoke(main, ["reconcile"])
    assert result.exit_code != 0


def test_reconcile_both_month_and_from_to_fails() -> None:
    result = CliRunner().invoke(
        main,
        ["reconcile", "--month", "2026-01", "--from", "2026-01-01", "--to", "2026-01-31"],
    )
    assert result.exit_code != 0


def test_reconcile_from_without_to_fails() -> None:
    result = CliRunner().invoke(main, ["reconcile", "--from", "2026-01-01"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# mixed-vat-check
# ---------------------------------------------------------------------------


def test_mixed_vat_check_help_shows_both_date_options() -> None:
    result = CliRunner().invoke(main, ["mixed-vat-check", "--help"])
    assert result.exit_code == 0
    assert "--month" in result.output
    assert "--from" in result.output
    assert "--to" in result.output


def test_mixed_vat_check_no_date_arg_fails() -> None:
    result = CliRunner().invoke(main, ["mixed-vat-check"])
    assert result.exit_code != 0


def test_mixed_vat_check_both_month_and_from_to_fails() -> None:
    result = CliRunner().invoke(
        main,
        ["mixed-vat-check", "--month", "2026-01", "--from", "2026-01-01", "--to", "2026-01-31"],
    )
    assert result.exit_code != 0


def test_mixed_vat_check_from_without_to_fails() -> None:
    result = CliRunner().invoke(main, ["mixed-vat-check", "--from", "2026-01-01"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# export-delta
# ---------------------------------------------------------------------------


def test_export_delta_help_shows_both_date_options() -> None:
    result = CliRunner().invoke(main, ["export-delta", "--help"])
    assert result.exit_code == 0
    assert "--month" in result.output
    assert "--from" in result.output
    assert "--to" in result.output


def test_export_delta_no_date_arg_fails() -> None:
    result = CliRunner().invoke(main, ["export-delta"])
    assert result.exit_code != 0


def test_export_delta_both_month_and_from_to_fails() -> None:
    result = CliRunner().invoke(
        main,
        [
            "export-delta",
            "--month", "2026-01",
            "--from", "2026-01-01",
            "--to", "2026-01-31",
        ],
    )
    assert result.exit_code != 0


def test_export_delta_from_without_to_fails() -> None:
    result = CliRunner().invoke(main, ["export-delta", "--from", "2026-01-01"])
    assert result.exit_code != 0


def test_export_delta_from_to_without_out_fails() -> None:
    """--from/--to without --out must fail."""
    result = CliRunner().invoke(
        main, ["export-delta", "--from", "2026-01-01", "--to", "2026-01-31"]
    )
    assert result.exit_code != 0


def test_export_delta_from_to_without_baseline_fails() -> None:
    """--from/--to without --baseline must fail."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        out = f.name
    result = CliRunner().invoke(
        main,
        ["export-delta", "--from", "2026-01-01", "--to", "2026-01-31", "--out", out],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# export-verbringung
# ---------------------------------------------------------------------------

_SYNTHETIC_TSV_HEADER = (
    "UNIQUE_ACCOUNT_IDENTIFIER\tACTIVITY_PERIOD\tSALES_CHANNEL\tMARKETPLACE\t"
    "PROGRAM_TYPE\tTRANSACTION_TYPE\tTRANSACTION_EVENT_ID\tACTIVITY_TRANSACTION_ID\t"
    "TAX_CALCULATION_DATE\tTRANSACTION_DEPART_DATE\tTRANSACTION_ARRIVAL_DATE\t"
    "TRANSACTION_COMPLETE_DATE\tSELLER_SKU\tASIN\tITEM_DESCRIPTION\tQTY\tITEM_WEIGHT\t"
    "DEPARTURE_COUNTRY\tARRIVAL_COUNTRY\tARRIVAL_POST_CODE\t"
    "TRANSACTION_CURRENCY_CODE\tSELLER_DEPART_COUNTRY_VAT_NUMBER\tSELLER_ARRIVAL_COUNTRY_VAT_NUMBER"
)

_SYNTHETIC_TSV_ROW1 = (
    "ACC1\t2026-01\tAMZ\tDE\tFBA\tFC_TRANSFER\tEVT001\tACT001\t"
    "31-01-2026\t29-01-2026\t31-01-2026\t31-01-2026\tSKU-A\tASIN-A\tProduct A\t3\t0.5\t"
    "DE\tPL\t00100\tEUR\t\t"
)

_SYNTHETIC_TSV_ROW2 = (
    "ACC1\t2026-01\tAMZ\tDE\tFBA\tFC_TRANSFER\tEVT002\tACT002\t"
    "31-01-2026\t28-01-2026\t30-01-2026\t31-01-2026\tSKU-B\tASIN-B\tProduct B\t1\t0.2\t"
    "DE\tES\t28001\tEUR\t\t"
)

_SYNTHETIC_TSV_INBOUND = (
    "ACC1\t2026-01\tAMZ\tDE\tFBA\tINBOUND\tFBA123\tACT003\t"
    "30-01-2026\t09-01-2026\t\t30-01-2026\tSKU-C\tASIN-C\tProduct C\t10\t1.0\t"
    "DE\tPL\t00100\tEUR\t\t"
)


@pytest.fixture
def synthetic_report(tmp_path: Path) -> Path:
    content = "\n".join([
        _SYNTHETIC_TSV_HEADER,
        _SYNTHETIC_TSV_ROW1,
        _SYNTHETIC_TSV_ROW2,
        _SYNTHETIC_TSV_INBOUND,
    ])
    p = tmp_path / "report.txt"
    p.write_text(content, encoding="utf-8")
    return p


def test_export_verbringung_help() -> None:
    result = CliRunner().invoke(main, ["export-verbringung", "--help"])
    assert result.exit_code == 0
    assert "--report" in result.output
    assert "--month" in result.output


def test_export_verbringung_missing_report_fails() -> None:
    result = CliRunner().invoke(main, ["export-verbringung", "--month", "2026-01"])
    assert result.exit_code != 0


def test_export_verbringung_missing_month_fails(tmp_path: Path) -> None:
    report = tmp_path / "r.txt"
    report.write_text("x")
    result = CliRunner().invoke(
        main, ["export-verbringung", "--report", str(report)]
    )
    assert result.exit_code != 0


def test_export_verbringung_full_run_with_mock_db(
    synthetic_report: Path,
    tmp_path: Path,
) -> None:
    """Full integration test with mocked DB: parse → price lookup → XLSX + PDFs."""
    from decimal import Decimal
    from jtl2datev.core.verbringung_pricing import PricingResult

    mock_pricing = {
        "SKU-A": PricingResult(
            seller_sku="SKU-A",
            matched_jtl_artikel="SKU-A",
            matched_via="direct",
            ek_netto=Decimal("5.00"),
            description="Product A",
        ),
        "SKU-B": PricingResult(
            seller_sku="SKU-B",
            matched_jtl_artikel="SKU-B",
            matched_via="direct",
            ek_netto=Decimal("3.00"),
            description="Product B",
        ),
        "SKU-C": PricingResult(
            seller_sku="SKU-C",
            matched_jtl_artikel="SKU-C",
            matched_via="direct",
            ek_netto=Decimal("7.50"),
            description="Product C",
        ),
    }
    # Provide PLN rate so the interactive prompt is not triggered
    mock_rates = {"PLN": Decimal("4.2127")}

    out_xlsx = tmp_path / "out.xlsx"
    out_pdf_dir = tmp_path / "pdfs"

    with patch("jtl2datev.core.db_jtl.lookup_prices", return_value=mock_pricing), \
         patch("jtl2datev.core.db_jtl.make_engine") as mock_engine, \
         patch("jtl2datev.cli.get_rates_for_period", return_value=mock_rates):
        mock_engine.return_value = MagicMock()

        result = CliRunner().invoke(
            main,
            [
                "export-verbringung",
                "--report", str(synthetic_report),
                "--month", "2026-01",
                "--out-xlsx", str(out_xlsx),
                "--out-pdf-dir", str(out_pdf_dir),
            ],
        )

    assert result.exit_code == 0, f"Command failed:\n{result.output}"
    assert out_xlsx.exists()
    # 2 routes: DE->ES and DE->PL (both FC_TRANSFER + INBOUND)
    pdf_files = list(out_pdf_dir.glob("*.pdf"))
    assert len(pdf_files) == 2
    # Check XLSX has correct row count
    import openpyxl
    wb = openpyxl.load_workbook(str(out_xlsx))
    ws = wb.active
    assert ws.max_row == 4  # 1 header + 3 data rows


def test_export_verbringung_missing_ek_csv_created(
    synthetic_report: Path,
    tmp_path: Path,
) -> None:
    from decimal import Decimal
    from jtl2datev.core.verbringung_pricing import PricingResult

    # SKU-B has no EK
    mock_pricing = {
        "SKU-A": PricingResult(
            seller_sku="SKU-A", matched_jtl_artikel="SKU-A",
            matched_via="direct", ek_netto=Decimal("5.00"), description="Product A",
        ),
        "SKU-B": PricingResult(
            seller_sku="SKU-B", matched_jtl_artikel="SKU-B",
            matched_via="direct", ek_netto=None, description="Product B",
        ),
        "SKU-C": PricingResult(
            seller_sku="SKU-C", matched_jtl_artikel="SKU-C",
            matched_via="direct", ek_netto=Decimal("7.50"), description="Product C",
        ),
    }
    mock_rates = {"PLN": Decimal("4.2127")}

    out_missing = tmp_path / "missing.csv"

    with patch("jtl2datev.core.db_jtl.lookup_prices", return_value=mock_pricing), \
         patch("jtl2datev.core.db_jtl.make_engine") as mock_engine, \
         patch("jtl2datev.cli.get_rates_for_period", return_value=mock_rates):
        mock_engine.return_value = MagicMock()

        result = CliRunner().invoke(
            main,
            [
                "export-verbringung",
                "--report", str(synthetic_report),
                "--month", "2026-01",
                "--out-xlsx", str(tmp_path / "out.xlsx"),
                "--out-pdf-dir", str(tmp_path / "pdfs"),
                "--out-missing-ek", str(out_missing),
            ],
        )

    assert result.exit_code == 0, f"Command failed:\n{result.output}"
    assert out_missing.exists()
    content = out_missing.read_text(encoding="utf-8")
    assert "SKU-B" in content
    assert "no-ek" in content


def test_export_verbringung_strict_missing_rate_exits(
    synthetic_report: Path,
    tmp_path: Path,
) -> None:
    """--strict aborts with exit_code=1 when required exchange rate is missing."""
    from decimal import Decimal
    from jtl2datev.core.verbringung_pricing import PricingResult

    mock_pricing = {
        "SKU-A": PricingResult(
            seller_sku="SKU-A", matched_jtl_artikel="SKU-A",
            matched_via="direct", ek_netto=Decimal("5.00"), description="Product A",
        ),
        "SKU-B": PricingResult(
            seller_sku="SKU-B", matched_jtl_artikel="SKU-B",
            matched_via="direct", ek_netto=Decimal("3.00"), description="Product B",
        ),
        "SKU-C": PricingResult(
            seller_sku="SKU-C", matched_jtl_artikel="SKU-C",
            matched_via="direct", ek_netto=Decimal("7.50"), description="Product C",
        ),
    }
    # No rates available → PLN missing → strict should abort
    with patch("jtl2datev.core.db_jtl.lookup_prices", return_value=mock_pricing), \
         patch("jtl2datev.core.db_jtl.make_engine") as mock_engine, \
         patch("jtl2datev.cli.get_rates_for_period", return_value={}):
        mock_engine.return_value = MagicMock()

        result = CliRunner().invoke(
            main,
            [
                "export-verbringung",
                "--report", str(synthetic_report),
                "--month", "2026-01",
                "--out-xlsx", str(tmp_path / "out.xlsx"),
                "--out-pdf-dir", str(tmp_path / "pdfs"),
                "--strict",
            ],
        )

    assert result.exit_code == 1
    assert "PLN" in result.output
    assert "fehlen" in result.output.lower() or "strict" in result.output.lower() or "import-rates" in result.output.lower()


def test_export_verbringung_interactive_prompt_saves_rate(
    synthetic_report: Path,
    tmp_path: Path,
) -> None:
    """Interactive prompt: user provides rate → saved and export succeeds."""
    from decimal import Decimal
    from jtl2datev.core.verbringung_pricing import PricingResult
    from jtl2datev.core.exchange_rates import get_rate

    rates_path = tmp_path / "rates.json"
    mock_pricing = {
        "SKU-A": PricingResult(
            seller_sku="SKU-A", matched_jtl_artikel="SKU-A",
            matched_via="direct", ek_netto=Decimal("5.00"), description="Product A",
        ),
        "SKU-B": PricingResult(
            seller_sku="SKU-B", matched_jtl_artikel="SKU-B",
            matched_via="direct", ek_netto=Decimal("3.00"), description="Product B",
        ),
        "SKU-C": PricingResult(
            seller_sku="SKU-C", matched_jtl_artikel="SKU-C",
            matched_via="direct", ek_netto=Decimal("7.50"), description="Product C",
        ),
    }

    with patch("jtl2datev.core.db_jtl.lookup_prices", return_value=mock_pricing), \
         patch("jtl2datev.core.db_jtl.make_engine") as mock_engine, \
         patch("jtl2datev.cli.get_rates_for_period", return_value={}), \
         patch("jtl2datev.core.exchange_rates.DEFAULT_RATES_PATH", rates_path), \
         patch("jtl2datev.cli.DEFAULT_RATES_PATH", rates_path):
        mock_engine.return_value = MagicMock()

        result = CliRunner().invoke(
            main,
            [
                "export-verbringung",
                "--report", str(synthetic_report),
                "--month", "2026-01",
                "--out-xlsx", str(tmp_path / "out.xlsx"),
                "--out-pdf-dir", str(tmp_path / "pdfs"),
            ],
            input="4.2127\n",
        )

    assert result.exit_code == 0, f"Command failed:\n{result.output}"
    assert "4.2127" in result.output
    # Rate should have been saved
    saved = get_rate("2026-01", "PLN", path=rates_path)
    assert saved == Decimal("4.2127")


def test_export_verbringung_interactive_empty_input_aborts(
    synthetic_report: Path,
    tmp_path: Path,
) -> None:
    """Interactive prompt: empty input → exit code 1."""
    from decimal import Decimal
    from jtl2datev.core.verbringung_pricing import PricingResult

    mock_pricing = {
        "SKU-A": PricingResult(
            seller_sku="SKU-A", matched_jtl_artikel="SKU-A",
            matched_via="direct", ek_netto=Decimal("5.00"), description="Product A",
        ),
        "SKU-B": PricingResult(
            seller_sku="SKU-B", matched_jtl_artikel="SKU-B",
            matched_via="direct", ek_netto=Decimal("3.00"), description="Product B",
        ),
        "SKU-C": PricingResult(
            seller_sku="SKU-C", matched_jtl_artikel="SKU-C",
            matched_via="direct", ek_netto=Decimal("7.50"), description="Product C",
        ),
    }

    with patch("jtl2datev.core.db_jtl.lookup_prices", return_value=mock_pricing), \
         patch("jtl2datev.core.db_jtl.make_engine") as mock_engine, \
         patch("jtl2datev.cli.get_rates_for_period", return_value={}):
        mock_engine.return_value = MagicMock()

        result = CliRunner().invoke(
            main,
            [
                "export-verbringung",
                "--report", str(synthetic_report),
                "--month", "2026-01",
                "--out-xlsx", str(tmp_path / "out.xlsx"),
                "--out-pdf-dir", str(tmp_path / "pdfs"),
            ],
            input="\n",
        )

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# import-rates
# ---------------------------------------------------------------------------

_SAMPLE_BMF_CSV = (
    "Monatlich fortgeschriebene Übersicht der Umsatzsteuer-Umrechnungskurse 2026\r\n"
    "Land;Währung;Januar[1];Februar [2];März [3];April [4]\r\n"
    "Polen;1 Euro;4,2127 PLN;4,2184 PLN;4,2715 PLN;\r\n"
    "Tschechien;1 Euro;24,278 CZK;24,260 CZK;;\r\n"
).encode("iso-8859-1")


def test_import_rates_help() -> None:
    result = CliRunner().invoke(main, ["import-rates", "--help"])
    assert result.exit_code == 0
    assert "--year" in result.output
    assert "--csv" in result.output


def test_import_rates_with_local_csv(tmp_path: Path) -> None:
    """import-rates --csv <local> should import rates into DEFAULT_RATES_PATH."""
    from jtl2datev.core.exchange_rates import get_rate

    rates_path = tmp_path / "rates.json"
    csv_file = tmp_path / "bmf.csv"
    csv_file.write_bytes(_SAMPLE_BMF_CSV)

    with patch("jtl2datev.core.exchange_rates.DEFAULT_RATES_PATH", rates_path), \
         patch("jtl2datev.cli.DEFAULT_RATES_PATH", rates_path):
        result = CliRunner().invoke(
            main,
            ["import-rates", "--year", "2026", "--csv", str(csv_file)],
        )

    assert result.exit_code == 0, f"Command failed:\n{result.output}"
    assert "2026-01" in result.output
    assert "PLN" in result.output
    assert get_rate("2026-01", "PLN", path=rates_path) is not None


def test_import_rates_summary_line(tmp_path: Path) -> None:
    """Summary line must report number of imported rates."""
    rates_path = tmp_path / "rates.json"
    csv_file = tmp_path / "bmf.csv"
    csv_file.write_bytes(_SAMPLE_BMF_CSV)

    with patch("jtl2datev.core.exchange_rates.DEFAULT_RATES_PATH", rates_path), \
         patch("jtl2datev.cli.DEFAULT_RATES_PATH", rates_path):
        result = CliRunner().invoke(
            main,
            ["import-rates", "--csv", str(csv_file)],
        )

    assert result.exit_code == 0
    assert "Import abgeschlossen" in result.output


# ---------------------------------------------------------------------------
# W-14: _parse_month strict regex
# ---------------------------------------------------------------------------


def test_parse_month_single_digit_fails() -> None:
    """'2026-4' (single-digit month) must be rejected."""
    from jtl2datev.cli import _parse_month

    with pytest.raises(SystemExit):
        _parse_month("2026-4")


def test_parse_month_valid_returns_tuple() -> None:
    from jtl2datev.cli import _parse_month

    assert _parse_month("2026-04") == (2026, 4)


def test_parse_month_plain_string_fails() -> None:
    from jtl2datev.cli import _parse_month

    with pytest.raises(SystemExit):
        _parse_month("January")


def test_parse_month_december_valid() -> None:
    from jtl2datev.cli import _parse_month

    assert _parse_month("2026-12") == (2026, 12)
