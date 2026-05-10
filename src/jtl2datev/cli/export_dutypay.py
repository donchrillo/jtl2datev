"""DutyPay-Export-Commands: Dünner Wrapper über dutypay_service."""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile
from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.cli._common import _parse_month, _resolve_date_range


@main.command("export-dutypay")
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
def export_dutypay_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    out_path: Path | None,
) -> None:
    """Exportiert Rechnungen aus JTL als DutyPay OSS-CSV.

    Mit --month: automatische Archivierung unter exports/dutypay/YYYY-MM/.
    Mit --from/--to: kein Archiv, --out ist Pflicht.
    """
    from jtl2datev.core.archive import archive_export
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.dutypay import dutypay_filename
    from jtl2datev.core.services.dutypay_service import (
        DutypayExportRequest,
        export_dutypay,
    )

    date_from_d, date_to_d = _resolve_date_range(date_from, date_to, month_str)

    use_archive = month_str is not None
    if not use_archive and out_path is None:
        raise click.UsageError("Bei --from/--to ist --out Pflicht (kein automatisches Archiv).")

    settings = Settings()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with managed_engine(settings) as engine:
            result = export_dutypay(
                DutypayExportRequest(
                    repo=JtlInvoiceRepository(engine),
                    settings=settings,
                    date_from=date_from_d,
                    date_to=date_to_d,
                    out_path=tmp_path,
                )
            )

        if use_archive:
            archived = archive_export(
                tmp_path,
                archive_root=settings.export_archive_root,
                kind="dutypay",
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"DutyPay-Export archiviert: {archived}")

        if out_path is not None:
            resolved = Path(out_path)
            if resolved.is_dir():
                year, month = date_from_d.year, date_from_d.month
                resolved = resolved / dutypay_filename(year, month)
            shutil.copy2(tmp_path, resolved)
            click.echo(f"DutyPay-Export geschrieben: {resolved}")

        report = result.report
        click.echo(f"  Zeilen: {report.rows_written}")
        click.echo(f"  Belege: {report.invoices_processed}")
        for kind, cnt in sorted(report.kind_counts.items()):
            click.echo(f"    {kind}: {cnt}")
    except Exception as exc:
        click.echo(f"Fehler beim DutyPay-Export: {exc}")
        raise SystemExit(1) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@main.command("export-dutypay-delta")
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
              help="Überschreibt ReportingPeriod und Datumsfelder in der Delta-CSV für Folgemonats-Nachmeldung.")
@click.option("--out", "out_path", required=False, default=None,
              type=click.Path(path_type=Path),
              help="Ausgabepfad für die Delta-CSV. Pflichtfeld bei --from/--to.")
def export_dutypay_delta_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    baseline_path: Path | None,
    shift_to_period: str | None,
    out_path: Path | None,
) -> None:
    """Berechnet Delta-Export zwischen aktuellem JTL-Stand und letztem Vollexport.

    Mit --month: automatische Archivierung; Baseline wird automatisch ermittelt.
    Mit --from/--to: kein Archiv; --baseline und --out sind Pflicht.
    """
    from jtl2datev.core.archive import archive_delta, archive_export, latest_archive
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.services.dutypay_service import (
        DutypayDeltaRequest,
        NoBaselineError,
        export_dutypay_delta,
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
            kind="dutypay",
            period=month_str,  # type: ignore[arg-type]
        )
        if effective_baseline is None:
            click.echo(
                f"Keine Baseline-Datei gefunden — erst Vollexport laufen lassen: "
                f"jtl2datev export-dutypay --month {month_str}"
            )
            raise SystemExit(1)

    click.echo(f"Baseline: {effective_baseline}")

    shift_tuple: tuple[int, int] | None = None
    if shift_to_period is not None:
        shift_year, shift_month = _parse_month(shift_to_period)
        shift_tuple = (shift_year, shift_month)

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        full_tmp = Path(tmp.name)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp2:
        delta_tmp = Path(tmp2.name)

    try:
        with managed_engine(settings) as engine:
            try:
                result = export_dutypay_delta(
                    DutypayDeltaRequest(
                        repo=JtlInvoiceRepository(engine),
                        settings=settings,
                        date_from=date_from_d,
                        date_to=date_to_d,
                        baseline_path=effective_baseline,
                        full_out_path=full_tmp,
                        delta_out_path=delta_tmp,
                        shift_to_period=shift_tuple,
                    )
                )
            except NoBaselineError as exc:
                click.echo(str(exc))
                raise SystemExit(1) from exc

        if use_archive:
            archived_full = archive_export(
                result.full_out_path,
                archive_root=settings.export_archive_root,
                kind="dutypay",
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Frischer Vollexport archiviert: {archived_full}")

        click.echo(f"Delta: {len(result.new_ids)} neue Belege, {len(result.changed_ids)} geänderte Belege")
        if result.changed_ids:
            for doc_id in result.changed_ids:
                click.echo(f"  Geändert: {doc_id}")

        if use_archive:
            archived_delta = archive_delta(
                result.delta_out_path,
                archive_root=settings.export_archive_root,
                kind="dutypay",
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Delta archiviert: {archived_delta}")

        if out_path is not None:
            shutil.copy2(result.delta_out_path, out_path)
            click.echo(f"Delta geschrieben: {out_path}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Fehler beim Delta-Export: {exc}")
        raise SystemExit(1) from exc
    finally:
        full_tmp.unlink(missing_ok=True)
        delta_tmp.unlink(missing_ok=True)
