"""DutyPay-Export-Commands: export-dutypay, export-dutypay-delta."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.cli._common import _parse_month, _resolve_date_range


@main.command("export-dutypay")
@click.option(
    "--month",
    "month_str",
    required=False,
    default=None,
    metavar="YYYY-MM",
    help="Monat des Exports, z.B. 2026-01. Aktiviert automatische Archivierung.",
)
@click.option(
    "--from",
    "date_from",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Startdatum (inkl.), z.B. 2026-01-01. Erfordert --out.",
)
@click.option(
    "--to",
    "date_to",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Enddatum (inkl.), z.B. 2026-01-31. Erfordert --out.",
)
@click.option(
    "--out",
    "out_path",
    required=False,
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabepfad. Pflichtfeld bei --from/--to (kein Archiv). Bei --month: optionaler Zusatz-Pfad.",
)
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
    import shutil
    import tempfile

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.dutypay import dutypay_filename, write_dutypay_csv

    date_from_d, date_to_d = _resolve_date_range(date_from, date_to, month_str)

    use_archive = month_str is not None
    if not use_archive and out_path is None:
        raise click.UsageError("Bei --from/--to ist --out Pflicht (kein automatisches Archiv).")

    settings = Settings()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with managed_engine(settings) as engine:
            repo = JtlInvoiceRepository(engine)
            invoices_iter = repo.fetch_invoices(date_from=date_from_d, date_to=date_to_d)
            report = write_dutypay_csv(
                invoices_iter,
                out_path=tmp_path,
                own_vat_ids=settings.own_vat_ids,
            )

        if use_archive:
            from jtl2datev.core.archive import archive_export

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
@click.option(
    "--month",
    "month_str",
    required=False,
    default=None,
    metavar="YYYY-MM",
    help="Monat, für den das Delta berechnet wird. Aktiviert automatische Archivierung.",
)
@click.option(
    "--from",
    "date_from",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Startdatum (inkl.). Bei --from/--to: kein Archiv, --baseline und --out Pflicht.",
)
@click.option(
    "--to",
    "date_to",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Enddatum (inkl.). Bei --from/--to: kein Archiv, --baseline und --out Pflicht.",
)
@click.option(
    "--baseline",
    "baseline_path",
    required=False,
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Explizite Baseline-Datei (Standard bei --month: letzter archivierter Vollexport).",
)
@click.option(
    "--shift-to-period",
    "shift_to_period",
    required=False,
    default=None,
    metavar="YYYY-MM",
    help="Überschreibt ReportingPeriod und Datumsfelder in der Delta-CSV für Folgemonats-Nachmeldung.",
)
@click.option(
    "--out",
    "out_path",
    required=False,
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabepfad für die Delta-CSV. Pflichtfeld bei --from/--to.",
)
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
    import shutil
    import tempfile

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.dutypay import DUTYPAY_COLUMNS, write_dutypay_csv
    from jtl2datev.core.dutypay_delta import (
        NoBaselineError,
        compute_delta,
        load_baseline,
        write_delta_csv,
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
        from jtl2datev.core.archive import latest_archive

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
    baseline_rows = load_baseline(effective_baseline)

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        current_tmp = Path(tmp.name)

    try:
        with managed_engine(settings) as engine:
            repo = JtlInvoiceRepository(engine)
            invoices_iter = repo.fetch_invoices(date_from=date_from_d, date_to=date_to_d)
            write_dutypay_csv(
                invoices_iter,
                out_path=current_tmp,
                own_vat_ids=settings.own_vat_ids,
            )

        if use_archive:
            from jtl2datev.core.archive import archive_export

            archived_full = archive_export(
                current_tmp,
                archive_root=settings.export_archive_root,
                kind="dutypay",
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Frischer Vollexport archiviert: {archived_full}")

        import csv as csv_mod

        with current_tmp.open(encoding="utf-8", newline="") as fh:
            reader = csv_mod.DictReader(fh, delimiter=";")
            current_rows = list(reader)

        delta_rows, new_ids, changed_ids = compute_delta(
            current_rows=current_rows,
            baseline_rows=baseline_rows,
            key_col="DocumentID",
        )

        click.echo(f"Delta: {len(new_ids)} neue Belege, {len(changed_ids)} geänderte Belege")
        if changed_ids:
            for doc_id in changed_ids:
                click.echo(f"  Geändert: {doc_id}")

        shift_tuple: tuple[int, int] | None = None
        if shift_to_period is not None:
            shift_year, shift_month = _parse_month(shift_to_period)
            shift_tuple = (shift_year, shift_month)

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp2:
            delta_tmp = Path(tmp2.name)

        try:
            write_delta_csv(
                delta_rows,
                out_path=delta_tmp,
                fieldnames=list(DUTYPAY_COLUMNS),
                shift_to_period=shift_tuple,
            )

            if use_archive:
                from jtl2datev.core.archive import archive_delta

                archived_delta = archive_delta(
                    delta_tmp,
                    archive_root=settings.export_archive_root,
                    kind="dutypay",
                    period=month_str,  # type: ignore[arg-type]
                )
                click.echo(f"Delta archiviert: {archived_delta}")

            if out_path is not None:
                shutil.copy2(delta_tmp, out_path)
                click.echo(f"Delta geschrieben: {out_path}")

        finally:
            delta_tmp.unlink(missing_ok=True)

    except NoBaselineError as exc:
        click.echo(str(exc))
        raise SystemExit(1) from exc
    except Exception as exc:
        click.echo(f"Fehler beim Delta-Export: {exc}")
        raise SystemExit(1) from exc
    finally:
        current_tmp.unlink(missing_ok=True)
