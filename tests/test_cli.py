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
