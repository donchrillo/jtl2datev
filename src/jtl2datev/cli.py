import logging
from datetime import date
from pathlib import Path

import click


@click.group()
def main() -> None:
    """jtl2datev — JTL-Rechnungen ins DATEV-Format exportieren."""
    logging.basicConfig(level=logging.INFO)


@main.command()
def version() -> None:
    from jtl2datev import __version__

    click.echo(__version__)


@main.command("export")
@click.option("--from", "date_from", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--to", "date_to", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--out", "out_path", required=True, type=click.Path(path_type=Path))
def export_cmd(date_from: date, date_to: date, out_path: Path) -> None:
    """Exportiert Rechnungen aus JTL als DATEV-CSV."""
    import datetime as dt

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine

    # click.DateTime returns datetime objects; core expects date
    df = date_from.date() if isinstance(date_from, dt.datetime) else date_from  # type: ignore[union-attr]
    dt_ = date_to.date() if isinstance(date_to, dt.datetime) else date_to  # type: ignore[union-attr]

    settings = Settings()

    try:
        engine = make_engine(settings)
        repo = JtlInvoiceRepository(engine)
        invoices = list(repo.fetch_invoices(date_from=df, date_to=dt_))
        logging.info("fetched %d invoices", len(invoices))
        click.echo(f"Fetched {len(invoices)} invoices — DATEV export not yet implemented")
    except NotImplementedError as exc:
        click.echo(f"Noch nicht implementiert: {exc} — siehe next-session.md")
    except Exception as exc:
        click.echo(f"DB nicht erreichbar oder Fehler: {exc}")


if __name__ == "__main__":
    main()
