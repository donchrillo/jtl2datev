"""Mixed-VAT-Pre-Flight-Command: dünner Wrapper über mixed_vat_service."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.cli._common import _resolve_date_range


@main.command("mixed-vat-check")
@click.option("--month", "month_str", required=False, default=None, metavar="YYYY-MM",
              help="Monat des Checks, z.B. 2026-01.")
@click.option("--from", "date_from", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Startdatum (inkl.), z.B. 2026-01-01.")
@click.option("--to", "date_to", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Enddatum (inkl.), z.B. 2026-01-31.")
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None,
              help="Optionaler Pfad für CSV-Output. Ohne --out: nur Konsolen-Bericht.")
def mixed_vat_check_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    out_path: Path | None,
) -> None:
    """Pre-Flight: Belege mit gemischten Steuersätzen auf Artikel-Positionen.

    Listet Belege, die auf ihren Hauptpositionen (ohne Versand/Sub-Positionen)
    mehr als einen MwStSatz tragen. Vor DATEV-/DutyPay-Export laufen lassen
    und betroffene Belege in JTL prüfen/korrigieren.
    """
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.services.mixed_vat_service import (
        MixedVatCheckRequest,
        check_mixed_vat,
    )

    df, dt_ = _resolve_date_range(date_from, date_to, month_str)

    settings = Settings()

    try:
        with managed_engine(settings) as engine:
            result = check_mixed_vat(
                MixedVatCheckRequest(
                    repo=JtlInvoiceRepository(engine),
                    date_from=df,
                    date_to=dt_,
                )
            )
    except Exception as exc:
        click.echo(f"Fehler beim Mixed-VAT-Check: {exc}")
        raise SystemExit(1) from exc

    belege = result.belege
    own = [b for b in belege if b.source == "jtl_own"]
    ext = [b for b in belege if b.source == "jtl_external"]
    cn = [b for b in belege if b.source == "jtl_credit_note"]

    click.echo("")
    click.echo(f"Mixed-VAT-Pre-Flight-Check {df} bis {dt_}")
    click.echo("")
    click.echo(f"  Eigene Rechnungen:    {len(own):>3} Belege mit gemischten Steuersätzen")
    click.echo(f"  Externe Belege:       {len(ext):>3} Belege mit gemischten Steuersätzen")
    click.echo(f"  Eigene Gutschriften:  {len(cn):>3} Belege mit gemischten Steuersätzen")

    if belege:
        click.echo("")
        click.echo("Treffer:")
        for b in belege:
            rates_str = ", ".join(f"{r:g}%" for r in b.vat_rates)
            order_str = f"  ext.Order={b.external_order_no}" if b.external_order_no else ""
            click.echo(
                f"  {b.source:<20}  {b.belegnr}  (pk={b.pk})"
                f"  {b.datum.strftime('%d.%m.%Y')}"
                f"  Sätze: {rates_str}"
                f"  Σ {b.total_brutto:,.2f} €"
                f"{order_str}"
            )
        click.echo("")
        click.echo(f"→ {len(belege)} Beleg(e) benötigen manuelle Prüfung in JTL.")
    else:
        click.echo("")
        click.echo("Keine Mixed-VAT-Belege im Zeitraum — Export kann gestartet werden.")

    if out_path is not None:
        _write_mixed_vat_csv(belege, out_path)
        click.echo(f"CSV geschrieben: {out_path}")


def _write_mixed_vat_csv(belege: list, path: Path) -> None:
    fieldnames = [
        "source", "pk", "belegnr", "datum", "vat_rates",
        "external_order_no", "position_count", "total_brutto",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for b in belege:
            writer.writerow({
                "source": b.source,
                "pk": b.pk,
                "belegnr": b.belegnr,
                "datum": b.datum.isoformat(),
                "vat_rates": ";".join(str(r) for r in b.vat_rates),
                "external_order_no": b.external_order_no or "",
                "position_count": b.position_count,
                "total_brutto": str(b.total_brutto),
            })
