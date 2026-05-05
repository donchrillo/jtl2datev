from click.testing import CliRunner

from jtl2datev.cli import main


def test_version() -> None:
    result = CliRunner().invoke(main, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"
