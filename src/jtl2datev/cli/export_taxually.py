"""Taxually-Export-Commands: Dünner Wrapper über taxually_service."""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile
from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.cli._common import _parse_month, _resolve_date_range


@main.command("export-taxually")
@click.option("--month", "month_str", required=False, default=None, metavar="YYYY-MM",
              help="Monat des Exports, z.B. 2026-01. Aktiviert automatische Archivierung.")
@click.option("--from", "date_from", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Startdatum (inkl.), z.B. 2026-01-01. Erfordert --out.")
@click.option("--to", "date_to", required=False, default=None,
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Enddatum (inkl.), z.B. 2026-01-31. Erfordert --out.")
@click.option("--out", "out_path", required=False, default=None,
              type=click.Path(path_type=Path),
              help="Ausgabepfad. Pflichtfeld bei --from/--to (kein Archiv). Bei --month: optionaler Zusatz-Pfad.")
def export_taxually_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    out_path: Path | None,
) -> None:
    """Exportiert Rechnungen aus JTL als Taxually XLSX.

    Mit --month: automatische Archivierung unter exports/taxually/YYYY-MM/.
    Mit --from/--to: kein Archiv, --out ist Pflicht.
    """
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.services.taxually_service import (
        TaxuallyExportRequest,
        export_taxually,
    )
    from jtl2datev.core.taxually import taxually_filename
    from jtl2datev.core.taxually_delta import archive_taxually_export

    date_from_d, date_to_d = _resolve_date_range(date_from, date_to, month_str)

    use_archive = month_str is not None
    if not use_archive and out_path is None:
        raise click.UsageError("Bei --from/--to ist --out Pflicht (kein automatisches Archiv).")

    settings = Settings()

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with managed_engine(settings) as engine:
            result = export_taxually(
                TaxuallyExportRequest(
                    repo=JtlInvoiceRepository(engine),
                    settings=settings,
                    date_from=date_from_d,
                    date_to=date_to_d,
                    out_path=tmp_path,
                )
            )

        if use_archive:
            archived = archive_taxually_export(
                tmp_path,
                archive_root=settings.export_archive_root,
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Taxually-Export archiviert: {archived}")

        if out_path is not None:
            resolved = Path(out_path)
            if resolved.is_dir():
                year, month = date_from_d.year, date_from_d.month
                resolved = resolved / taxually_filename(year, month)
            shutil.copy2(tmp_path, resolved)
            click.echo(f"Taxually-Export geschrieben: {resolved}")

        click.echo(f"  Zeilen: {result.rows_written}")
    except Exception as exc:
        click.echo(f"Fehler beim Taxually-Export: {exc}")
        raise SystemExit(1) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@main.command("export-taxually-delta")
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
@click.option("--shift-to-period", "shift_to_period", required=False, default=None, metavar="YYYY-MM",
              help="Überschreibt Transaction date in der Delta-XLSX für Folgemonats-Nachmeldung.")
@click.option("--out", "out_path", required=False, default=None,
              type=click.Path(path_type=Path),
              help="Ausgabepfad für die Delta-XLSX. Pflichtfeld bei --from/--to.")
def export_taxually_delta_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    baseline_path: Path | None,
    shift_to_period: str | None,
    out_path: Path | None,
) -> None:
    """Berechnet Taxually-Delta zwischen aktuellem JTL-Stand und letztem XLSX-Vollexport.

    Mit --month: automatische Archivierung; Baseline wird automatisch ermittelt.
    Mit --from/--to: kein Archiv; --baseline und --out sind Pflicht.
    """
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.services.taxually_service import (
        NoBaselineError,
        TaxuallyDeltaRequest,
        export_taxually_delta,
    )
    from jtl2datev.core.taxually_delta import (
        archive_taxually_delta,
        archive_taxually_export,
        latest_taxually_archive,
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
        effective_baseline = latest_taxually_archive(
            settings.export_archive_root,
            period=month_str,  # type: ignore[arg-type]
        )
        if effective_baseline is None:
            click.echo(
                f"Keine Baseline-Datei gefunden — erst Vollexport laufen lassen: "
                f"jtl2datev export-taxually --month {month_str}"
            )
            raise SystemExit(1)

    click.echo(f"Baseline: {effective_baseline}")

    shift_date: dt.date | None = None
    if shift_to_period is not None:
        shift_year, shift_month = _parse_month(shift_to_period)
        shift_date = dt.date(shift_year, shift_month, 1)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        full_tmp = Path(tmp.name)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp2:
        delta_tmp = Path(tmp2.name)

    try:
        with managed_engine(settings) as engine:
            try:
                result = export_taxually_delta(
                    TaxuallyDeltaRequest(
                        repo=JtlInvoiceRepository(engine),
                        settings=settings,
                        date_from=date_from_d,
                        date_to=date_to_d,
                        baseline_path=effective_baseline,
                        full_out_path=full_tmp,
                        delta_out_path=delta_tmp,
                        shift_to=shift_date,
                    )
                )
            except NoBaselineError as exc:
                click.echo(str(exc))
                raise SystemExit(1) from exc

        if use_archive:
            archived_full = archive_taxually_export(
                result.full_out_path,
                archive_root=settings.export_archive_root,
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Frischer Vollexport archiviert: {archived_full}")

        click.echo(f"Delta: {result.delta_invoice_count} neue Belege")

        if use_archive:
            archived_delta = archive_taxually_delta(
                result.delta_out_path,
                archive_root=settings.export_archive_root,
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Delta archiviert: {archived_delta}")

        if out_path is not None:
            shutil.copy2(result.delta_out_path, out_path)
            click.echo(f"Delta geschrieben: {out_path}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Fehler beim Taxually-Delta-Export: {exc}")
        raise SystemExit(1) from exc
    finally:
        full_tmp.unlink(missing_ok=True)
        delta_tmp.unlink(missing_ok=True)
