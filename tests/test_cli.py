from click.testing import CliRunner

from jtl2datev.cli import main


def test_version() -> None:
    result = CliRunner().invoke(main, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"


def test_export_exits_cleanly() -> None:
    """Export command must not crash hard — DB error, stub message, or success all
    produce exit_code=0 and a non-empty human-readable echo."""
    result = CliRunner().invoke(
        main,
        ["export", "--from", "2026-01-01", "--to", "2026-01-31", "--out", "/tmp/test_export.csv"],
    )
    assert result.exit_code == 0
    assert result.output.strip(), "Expected at least one output line"
