"""DATEV-Export-Commands: export, export-delta. Dünner Wrapper über datev_service."""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile
from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.cli._common import _resolve_date_range


@main.command("export")
@click.option("--month", "month_str", required=False, default=None, metavar="YYYY-MM",
              help="Monat des Exports, z.B. 2026-01.")
@click.option("--from", "date_from", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Startdatum (inkl.), z.B. 2026-01-01.")
@click.option("--to", "date_to", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Enddatum (inkl.), z.B. 2026-01-31.")
@click.option("--out", "out_path", required=False, default=None,
              type=click.Path(path_type=Path),
              help="Ausgabepfad. Standard: exports/datev/YYYY-MM.csv (oder YYYY-MM-DD_YYYY-MM-DD.csv bei --from/--to).")
@click.option("--compare-to", "compare_to", default=None,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Optional: bestehender DATEV-Export (z.B. Jera). Buchungen, die "
              "von der Referenz abweichen (anderes Konto/BU oder gar nicht in Referenz), "
              "werden mit 'X' in Belegfeld 2 markiert.")
@click.option("--audit", is_flag=True, default=False,
              help="Audit-Modus: schreibt das Engine-Regel-Tag (z.B. 'OSS241-FR-IT') "
              "in Spalte 'Beleglink' (vor allen Beleginfo-Feldern). Vor Übergabe an "
              "den Steuerberater wieder entfernen.")
@click.option("--keep-zero-amount", is_flag=True, default=False,
              help="Belege mit Brutto-Summe = 0,00 € (Probebuchungen) NICHT ausfiltern. "
              "Standard: filtern. Für vollständigen Audit-Trail aktivieren.")
def export_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    out_path: Path | None,
    compare_to: Path | None,
    audit: bool,
    keep_zero_amount: bool,
) -> None:
    """Exportiert Rechnungen aus JTL als DATEV-CSV."""
    from jtl2datev.core.archive import archive_export
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.services.datev_service import (
        DatevExportRequest,
        export_datev,
    )

    df, dt_ = _resolve_date_range(date_from, date_to, month_str)

    if out_path is not None:
        effective_out = Path(out_path)
    elif month_str is not None:
        effective_out = Path("exports/datev") / f"{month_str}.csv"
    else:
        effective_out = Path("exports/datev") / f"{df}_{dt_}.csv"
    effective_out.parent.mkdir(parents=True, exist_ok=True)

    settings = Settings()

    if compare_to is not None:
        # Echo der Referenz-Größe vor dem Service-Aufruf — User-Feedback für
        # langlaufende Exports.
        from jtl2datev.core.datev import load_compare_map
        compare_map = load_compare_map(compare_to)
        click.echo(f"Vergleichsreferenz geladen: {len(compare_map):,} Order-IDs aus {compare_to}")

    try:
        with managed_engine(settings) as engine:
            result = export_datev(
                DatevExportRequest(
                    repo=JtlInvoiceRepository(engine),
                    settings=settings,
                    date_from=df,
                    date_to=dt_,
                    out_path=effective_out,
                    compare_path=compare_to,
                    audit=audit,
                    keep_zero_amount=keep_zero_amount,
                )
            )

        report = result.report
        click.echo(f"DATEV-Export geschrieben: {result.out_path}")
        click.echo(f"  Buchungen: {report.bookings_written}")
        click.echo(f"  Belege geskippt (Fehler):    {report.skipped_error}")
        click.echo(f"  Belege geskippt (unbekannt): {report.skipped_unknown}")
        click.echo(f"  Belege geskippt (0,00 €):    {report.skipped_zero_amount}")
        if compare_to is not None:
            click.echo(f"  Abweichungen markiert (X):   {report.diff_marked}")

        if month_str is not None:
            archived = archive_export(
                result.out_path,
                archive_root=settings.export_archive_root,
                kind="datev",
                period=month_str,
            )
            click.echo(f"DATEV-Export archiviert: {archived}")
    except Exception as exc:
        click.echo(f"Fehler beim Export: {exc}")
        raise SystemExit(1) from exc


@main.command("export-delta")
@click.option("--month", "month_str", required=False, default=None, metavar="YYYY-MM",
              help="Monat, für den das Delta berechnet wird. Aktiviert automatische Archivierung.")
@click.option("--from", "date_from", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Startdatum (inkl.). Bei --from/--to: kein Archiv, --baseline und --out Pflicht.")
@click.option("--to", "date_to", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Enddatum (inkl.). Bei --from/--to: kein Archiv, --baseline und --out Pflicht.")
@click.option("--baseline", "baseline_path", required=False, default=None,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Explizite Baseline-Datei (Standard bei --month: letzter archivierter Vollexport).")
@click.option("--out", "out_path", required=False, default=None,
              type=click.Path(path_type=Path),
              help="Ausgabepfad für die Delta-CSV. Pflichtfeld bei --from/--to.")
@click.option("--compare-to", "compare_to", default=None,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Optional: Vergleichsreferenz für den frischen Vollexport (wie bei export).")
@click.option("--audit", is_flag=True, default=False,
              help="Audit-Modus: schreibt das Engine-Regel-Tag in Spalte 'Beleglink'.")
@click.option("--keep-zero-amount", is_flag=True, default=False,
              help="Belege mit Brutto-Summe = 0,00 € (Probebuchungen) NICHT ausfiltern. Standard: filtern.")
def export_delta_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    baseline_path: Path | None,
    out_path: Path | None,
    compare_to: Path | None,
    audit: bool,
    keep_zero_amount: bool,
) -> None:
    """Berechnet DATEV-Delta-Export zwischen aktuellem JTL-Stand und letztem Vollexport.

    Mit --month: automatische Archivierung; Baseline wird automatisch ermittelt.
    Mit --from/--to: kein Archiv; --baseline und --out sind Pflicht.
    """
    from jtl2datev.core.archive import archive_delta, archive_export, latest_archive
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.services.datev_service import (
        DatevDeltaRequest,
        NoBaselineError,
        export_datev_delta,
    )

    date_from_d, date_to_d = _resolve_date_range(date_from, date_to, month_str)

    use_archive = month_str is not None
    if not use_archive and out_path is None:
        raise click.UsageError("Bei --from/--to ist --out Pflicht (kein automatisches Archiv).")
    if not use_archive and baseline_path is None:
        raise click.UsageError("Bei --from/--to ist --baseline Pflicht (kein automatisches Archiv).")

    settings = Settings()

    if baseline_path is not None:
        effective_baseline = baseline_path
    else:
        effective_baseline = latest_archive(
            settings.export_archive_root,
            kind="datev",
            period=month_str,  # type: ignore[arg-type]
        )
        if effective_baseline is None:
            click.echo(
                f"Keine Baseline-Datei gefunden — erst Vollexport laufen lassen: "
                f"jtl2datev export --month {month_str}"
            )
            raise SystemExit(1)

    click.echo(f"Baseline: {effective_baseline}")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        full_tmp = Path(tmp.name)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp2:
        delta_tmp = Path(tmp2.name)

    try:
        with managed_engine(settings) as engine:
            try:
                result = export_datev_delta(
                    DatevDeltaRequest(
                        repo=JtlInvoiceRepository(engine),
                        settings=settings,
                        date_from=date_from_d,
                        date_to=date_to_d,
                        baseline_path=effective_baseline,
                        full_out_path=full_tmp,
                        delta_out_path=delta_tmp,
                        compare_path=compare_to,
                        audit=audit,
                        keep_zero_amount=keep_zero_amount,
                    )
                )
            except NoBaselineError as exc:
                click.echo(str(exc))
                raise SystemExit(1) from exc

        if use_archive:
            archived_full = archive_export(
                result.full_out_path,
                archive_root=settings.export_archive_root,
                kind="datev",
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Frischer Vollexport archiviert: {archived_full}")

        click.echo(f"Delta: {len(result.new_keys)} neue Belege, {len(result.changed_keys)} geänderte Belege")
        if result.changed_keys:
            for key in result.changed_keys:
                click.echo(f"  Geändert: {key}")

        if use_archive:
            archived_delta = archive_delta(
                result.delta_out_path,
                archive_root=settings.export_archive_root,
                kind="datev",
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Delta archiviert: {archived_delta}")

        if out_path is not None:
            shutil.copy2(result.delta_out_path, out_path)
            click.echo(f"Delta geschrieben: {out_path}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Fehler beim DATEV-Delta-Export: {exc}")
        raise SystemExit(1) from exc
    finally:
        full_tmp.unlink(missing_ok=True)
        delta_tmp.unlink(missing_ok=True)
