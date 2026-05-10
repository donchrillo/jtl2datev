"""BMF-Wechselkurs-Import-Command."""
from __future__ import annotations

from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.core.config import Settings


@main.command("import-rates")
@click.option(
    "--year",
    "year",
    default=None,
    type=int,
    metavar="YYYY",
    help="Jahr für den BMF-Import. Default: aktuelles Jahr.",
)
@click.option(
    "--csv",
    "csv_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Lokale CSV-Datei statt Download (z.B. für Tests oder Re-Import).",
)
def import_rates_cmd(year: int | None, csv_path: Path | None) -> None:
    """Importiert BMF-Umsatzsteuer-Umrechnungskurse ins lokale JSON-Store.

    Lädt die offizielle BMF-CSV (oder eine lokale CSV mit --csv) und speichert
    die Kurse in data/exchange_rates.json. Manuelle Einträge werden nicht
    überschrieben.
    """
    import datetime

    from jtl2datev.core.exchange_rates import import_bmf_rates

    effective_year = year if year is not None else datetime.date.today().year

    content: bytes | None = None
    if csv_path is not None:
        content = csv_path.read_bytes()
        click.echo(f"Lade lokale CSV: {csv_path}")
    else:
        click.echo(f"Lade BMF-CSV für {effective_year} ...")

    rates_path = Settings().rates_path
    try:
        imported = import_bmf_rates(effective_year, path=rates_path, content=content)
    except Exception as exc:
        click.echo(f"Fehler beim Import: {exc}")
        raise SystemExit(1) from exc

    total = 0
    for period in sorted(imported):
        currencies = imported[period]
        total += len(currencies)
        click.echo(f"  {period}: {', '.join(sorted(currencies))}")

    click.echo(f"\nImport abgeschlossen: {total} Kurse in {len(imported)} Perioden.")
    click.echo(f"Gespeichert: {rates_path}")
