"""Reconcile-Command: dünner Wrapper über reconcile_service."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.cli._common import _resolve_date_range


@main.command("reconcile")
@click.option("--month", "month_str", required=False, default=None, metavar="YYYY-MM",
              help="Monat des Reconcile, z.B. 2026-01.")
@click.option("--from", "date_from", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Startdatum (inkl.), z.B. 2026-01-01.")
@click.option("--to", "date_to", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Enddatum (inkl.), z.B. 2026-01-31.")
@click.option("--out-mismatches", "out_mismatches", default=None,
              type=click.Path(path_type=Path),
              help="Optional: alle Mismatches als CSV schreiben.")
def reconcile_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    out_mismatches: Path | None,
) -> None:
    """Vergleicht JTL-Steuerdaten mit eigener Engine und gibt Mismatch-Report aus."""
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.services.reconcile_service import (
        ReconcileRequest,
        reconcile,
    )

    df, dt_ = _resolve_date_range(date_from, date_to, month_str)

    settings = Settings()

    try:
        with managed_engine(settings) as engine:
            sample_limit = 1_000_000 if out_mismatches is not None else 20
            result = reconcile(
                ReconcileRequest(
                    repo=JtlInvoiceRepository(engine),
                    settings=settings,
                    date_from=df,
                    date_to=dt_,
                    sample_limit=sample_limit,
                )
            )
    except Exception as exc:
        click.echo(f"Fehler: {exc}")
        raise SystemExit(1) from exc

    report = result.report
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
            ext = f" [Ext: {mm.external_order_no}]" if mm.external_order_no else ""
            click.echo(
                f"  [{mm.severity.upper():5}] {mm.invoice_no}{ext} / Pos {mm.line_no}"
                f" | {mm.field}: JTL={mm.jtl_value!r} Engine={mm.engine_value!r}"
            )
        click.echo("")

    if out_mismatches is not None:
        _write_mismatches_csv(report, out_mismatches)
        click.echo(f"Mismatches geschrieben: {out_mismatches}")


def _write_mismatches_csv(report, path: Path) -> None:  # type: ignore[no-untyped-def]
    fieldnames = [
        "invoice_no", "external_order_no", "line_no",
        "severity", "field", "jtl_value", "engine_value",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for mm in report.sample_mismatches:
            writer.writerow({
                "invoice_no": mm.invoice_no,
                "external_order_no": mm.external_order_no or "",
                "line_no": mm.line_no,
                "severity": mm.severity,
                "field": mm.field,
                "jtl_value": mm.jtl_value,
                "engine_value": mm.engine_value,
            })
