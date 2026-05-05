import csv
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
    from jtl2datev.core.datev import write_extf_buchungsstapel
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.models import LineDecision
    from jtl2datev.core.tax_engine import decide

    # click.DateTime returns datetime objects; core expects date
    df = date_from.date() if isinstance(date_from, dt.datetime) else date_from  # type: ignore[union-attr]
    dt_ = date_to.date() if isinstance(date_to, dt.datetime) else date_to  # type: ignore[union-attr]

    settings = Settings()

    def decisions(inv):  # type: ignore[no-untyped-def]
        return [
            LineDecision(line=line, decision=decide(inv, line, own_vat_countries=settings.own_vat_countries))
            for line in inv.lines
        ]

    try:
        engine = make_engine(settings)
        repo = JtlInvoiceRepository(engine)
        invoices_iter = repo.fetch_invoices(date_from=df, date_to=dt_)
        report = write_extf_buchungsstapel(
            invoices_iter,
            out_path=out_path,
            settings=settings,
            date_from=df,
            date_to=dt_,
            decisions_by_invoice=decisions,
        )
        click.echo(f"DATEV-Export geschrieben: {out_path}")
        click.echo(f"  Buchungen: {report.bookings_written}")
        click.echo(f"  Belege geskippt (Fehler):    {report.skipped_error}")
        click.echo(f"  Belege geskippt (unbekannt): {report.skipped_unknown}")
    except Exception as exc:
        click.echo(f"Fehler beim Export: {exc}")
        raise SystemExit(1) from exc


@main.command("reconcile")
@click.option("--from", "date_from", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--to", "date_to", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option(
    "--out-mismatches",
    "out_mismatches",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional: alle Mismatches als CSV schreiben.",
)
def reconcile_cmd(date_from: date, date_to: date, out_mismatches: Path | None) -> None:
    """Vergleicht JTL-Steuerdaten mit eigener Engine und gibt Mismatch-Report aus."""
    import datetime as dt

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.pipeline import run_reconcile

    df = date_from.date() if isinstance(date_from, dt.datetime) else date_from  # type: ignore[union-attr]
    dt_ = date_to.date() if isinstance(date_to, dt.datetime) else date_to  # type: ignore[union-attr]

    settings = Settings()

    try:
        engine = make_engine(settings)
        repo = JtlInvoiceRepository(engine)
        invoices = repo.fetch_invoices(date_from=df, date_to=dt_)
        sample_limit = 1_000_000 if out_mismatches is not None else 20
        report = run_reconcile(
            invoices,
            own_vat_countries=settings.own_vat_countries,
            sample_limit=sample_limit,
        )
    except Exception as exc:
        click.echo(f"Fehler: {exc}")
        raise SystemExit(1) from exc

    total_mismatches = sum(report.mismatches_by_severity.values())

    click.echo("")
    click.echo(f"=== Reconcile-Report {df} – {dt_} ===")
    click.echo(f"  Belege:    {report.invoices_total:>8,}")
    click.echo(f"  Positionen:{report.lines_total:>8,}")
    click.echo("")

    click.echo("--- Treatments ---")
    click.echo(f"  {'Treatment':<30} {'Anzahl':>8}  {'%':>6}")
    click.echo(f"  {'-'*30} {'-'*8}  {'-'*6}")
    for treatment, count in sorted(report.treatments.items(), key=lambda x: -x[1]):
        pct = count / report.lines_total * 100 if report.lines_total else 0.0
        click.echo(f"  {str(treatment):<30} {count:>8,}  {pct:>5.1f}%")
    click.echo("")

    mismatch_pct = (
        report.invoices_with_any_mismatch / report.invoices_total * 100
        if report.invoices_total
        else 0.0
    )
    click.echo("--- Mismatches ---")
    click.echo(f"  Belege mit Mismatches: {report.invoices_with_any_mismatch:,} ({mismatch_pct:.1f}%)")
    click.echo(f"  Mismatches gesamt:     {total_mismatches:,}")
    click.echo("")

    click.echo("  Nach Severity:")
    for sev in ("error", "warn", "info"):
        cnt = report.mismatches_by_severity.get(sev, 0)
        click.echo(f"    {sev:<8}: {cnt:,}")
    click.echo("")

    click.echo("  Nach Quelle:")
    for src, cnt in sorted(report.mismatches_by_source.items(), key=lambda x: -x[1]):
        click.echo(f"    {src:<20}: {cnt:,}")
    click.echo("")

    top5_wh = report.mismatches_by_warehouse.most_common(5)
    click.echo("  Top-5 Lagerländer mit Mismatches:")
    for wh, cnt in top5_wh:
        click.echo(f"    {wh}: {cnt:,}")
    click.echo("")

    sample = report.sample_mismatches[:10]
    if sample:
        click.echo("--- Sample-Mismatches (erste 10) ---")
        for mm in sample:
            click.echo(
                f"  [{mm.severity.upper():5}] {mm.invoice_no} / Pos {mm.line_no}"
                f" | {mm.field}: JTL={mm.jtl_value!r} Engine={mm.engine_value!r}"
            )
        click.echo("")

    if out_mismatches is not None:
        _write_mismatches_csv(report.sample_mismatches, out_mismatches, report)
        click.echo(f"Mismatches geschrieben: {out_mismatches}")


def _write_mismatches_csv(
    samples: list,
    path: Path,
    report: "object",  # ReconcileReport — avoid import at module level
) -> None:
    from jtl2datev.core.pipeline import ReconcileReport

    assert isinstance(report, ReconcileReport)

    # We need all mismatches, not just samples — re-collect from report
    # The report only stores up to sample_limit; write what we have.
    fieldnames = [
        "invoice_no",
        "line_no",
        "severity",
        "field",
        "jtl_value",
        "engine_value",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for mm in report.sample_mismatches:
            writer.writerow(
                {
                    "invoice_no": mm.invoice_no,
                    "line_no": mm.line_no,
                    "severity": mm.severity,
                    "field": mm.field,
                    "jtl_value": mm.jtl_value,
                    "engine_value": mm.engine_value,
                }
            )


if __name__ == "__main__":
    main()
