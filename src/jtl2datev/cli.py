import csv
import datetime as dt
import logging
from pathlib import Path

import click

from jtl2datev.core.exchange_rates import DEFAULT_RATES_PATH, get_rates_for_period


@click.group()
def main() -> None:
    """jtl2datev — JTL-Rechnungen ins DATEV-Format exportieren."""
    logging.basicConfig(level=logging.INFO)


@main.command()
def version() -> None:
    from jtl2datev import __version__

    click.echo(__version__)


@main.command("export")
@click.option(
    "--month",
    "month_str",
    required=False,
    default=None,
    metavar="YYYY-MM",
    help="Monat des Exports, z.B. 2026-01.",
)
@click.option(
    "--from",
    "date_from",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Startdatum (inkl.), z.B. 2026-01-01.",
)
@click.option(
    "--to",
    "date_to",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Enddatum (inkl.), z.B. 2026-01-31.",
)
@click.option(
    "--out",
    "out_path",
    required=False,
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabepfad. Standard: exports/datev/YYYY-MM.csv (oder YYYY-MM-DD_YYYY-MM-DD.csv bei --from/--to).",
)
@click.option(
    "--compare-to",
    "compare_to",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional: bestehender DATEV-Export (z.B. Jera). Buchungen, die "
    "von der Referenz abweichen (anderes Konto/BU oder gar nicht in Referenz), "
    "werden mit 'X' in Belegfeld 2 markiert.",
)
@click.option(
    "--audit",
    is_flag=True,
    default=False,
    help="Audit-Modus: schreibt das Engine-Regel-Tag (z.B. 'OSS241-FR-IT') "
    "in Spalte 'Beleglink' (vor allen Beleginfo-Feldern). Vor Übergabe an "
    "den Steuerberater wieder entfernen.",
)
def export_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    out_path: Path | None,
    compare_to: Path | None,
    audit: bool,
) -> None:
    """Exportiert Rechnungen aus JTL als DATEV-CSV."""
    from jtl2datev.core.config import Settings
    from jtl2datev.core.datev import load_compare_map, write_extf_buchungsstapel
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.models import LineDecision
    from jtl2datev.core.tax_engine import decide

    df, dt_ = _resolve_date_range(date_from, date_to, month_str)

    effective_out: Path
    if out_path is not None:
        effective_out = Path(out_path)
    elif month_str is not None:
        effective_out = Path("exports/datev") / f"{month_str}.csv"
    else:
        effective_out = Path("exports/datev") / f"{df}_{dt_}.csv"
    effective_out.parent.mkdir(parents=True, exist_ok=True)

    settings = Settings()

    def decisions(inv):  # type: ignore[no-untyped-def]
        return [
            LineDecision(line=line, decision=decide(inv, line, own_vat_countries=settings.own_vat_countries))
            for line in inv.lines
        ]

    compare_map = load_compare_map(compare_to) if compare_to is not None else None
    if compare_map is not None:
        click.echo(f"Vergleichsreferenz geladen: {len(compare_map):,} Order-IDs aus {compare_to}")

    try:
        engine = make_engine(settings)
        repo = JtlInvoiceRepository(engine)
        invoices_iter = repo.fetch_invoices(date_from=df, date_to=dt_)
        report = write_extf_buchungsstapel(
            invoices_iter,
            out_path=effective_out,
            settings=settings,
            date_from=df,
            date_to=dt_,
            decisions_by_invoice=decisions,
            compare_map=compare_map,
            audit=audit,
        )
        click.echo(f"DATEV-Export geschrieben: {effective_out}")
        click.echo(f"  Buchungen: {report.bookings_written}")
        click.echo(f"  Belege geskippt (Fehler):    {report.skipped_error}")
        click.echo(f"  Belege geskippt (unbekannt): {report.skipped_unknown}")
        if compare_map is not None:
            click.echo(f"  Abweichungen markiert (X):   {report.diff_marked}")

        if month_str is not None:
            from jtl2datev.core.archive import archive_export

            archived = archive_export(
                effective_out,
                archive_root=settings.export_archive_root,
                kind="datev",
                period=month_str,
            )
            click.echo(f"DATEV-Export archiviert: {archived}")
    except Exception as exc:
        click.echo(f"Fehler beim Export: {exc}")
        raise SystemExit(1) from exc


def _parse_month(month_str: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' and return (year, month). Raises SystemExit on bad input."""
    try:
        year_s, month_s = month_str.split("-")
        return int(year_s), int(month_s)
    except ValueError:
        click.echo(f"Ungültiges Monatsformat: {month_str!r}. Erwartet: YYYY-MM")
        raise SystemExit(1)


def _month_date_range(year: int, month: int) -> tuple[dt.date, dt.date]:
    date_from = dt.date(year, month, 1)
    if month == 12:
        date_to_excl = dt.date(year + 1, 1, 1)
    else:
        date_to_excl = dt.date(year, month + 1, 1)
    return date_from, date_to_excl - dt.timedelta(days=1)


def _resolve_date_range(
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    month_str: str | None,
) -> tuple[dt.date, dt.date]:
    """Validate and resolve date input. Exactly one of (--from + --to) or
    --month must be provided. Returns (date_from, date_to_inclusive)."""
    has_range = date_from is not None and date_to is not None
    has_partial_range = (date_from is None) ^ (date_to is None)
    has_month = month_str is not None

    if has_partial_range:
        raise click.BadParameter("--from und --to müssen zusammen angegeben werden.")
    if has_month and has_range:
        raise click.BadParameter("Entweder --month oder --from/--to, nicht beides.")
    if not has_month and not has_range:
        raise click.BadParameter("Bitte entweder --month YYYY-MM oder --from/--to angeben.")
    if has_month:
        year, month = _parse_month(month_str)  # type: ignore[arg-type]
        return _month_date_range(year, month)
    assert date_from is not None and date_to is not None
    return date_from.date(), date_to.date()


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
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.dutypay import dutypay_filename, write_dutypay_csv

    date_from_d, date_to_d = _resolve_date_range(date_from, date_to, month_str)

    use_archive = month_str is not None
    if not use_archive and out_path is None:
        raise click.UsageError("Bei --from/--to ist --out Pflicht (kein automatisches Archiv).")

    settings = Settings()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        engine = make_engine(settings)
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
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
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

    # Resolve baseline
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
        engine = make_engine(settings)
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


@main.command("export-delta")
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
    "--out",
    "out_path",
    required=False,
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabepfad für die Delta-CSV. Pflichtfeld bei --from/--to.",
)
@click.option(
    "--compare-to",
    "compare_to",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional: Vergleichsreferenz für den frischen Vollexport (wie bei export).",
)
@click.option(
    "--audit",
    is_flag=True,
    default=False,
    help="Audit-Modus: schreibt das Engine-Regel-Tag in Spalte 'Beleglink'.",
)
def export_delta_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    baseline_path: Path | None,
    out_path: Path | None,
    compare_to: Path | None,
    audit: bool,
) -> None:
    """Berechnet DATEV-Delta-Export zwischen aktuellem JTL-Stand und letztem Vollexport.

    Mit --month: automatische Archivierung; Baseline wird automatisch ermittelt.
    Mit --from/--to: kein Archiv; --baseline und --out sind Pflicht.
    """
    import shutil
    import tempfile

    from jtl2datev.core.config import Settings
    from jtl2datev.core.datev import load_compare_map, write_extf_buchungsstapel
    from jtl2datev.core.datev_delta import (
        NoBaselineError,
        compute_delta,
        load_baseline,
        write_delta_extf,
    )
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.models import LineDecision
    from jtl2datev.core.tax_engine import decide

    date_from_d, date_to_d = _resolve_date_range(date_from, date_to, month_str)

    use_archive = month_str is not None
    if not use_archive and out_path is None:
        raise click.UsageError("Bei --from/--to ist --out Pflicht (kein automatisches Archiv).")
    if not use_archive and baseline_path is None:
        raise click.UsageError("Bei --from/--to ist --baseline Pflicht (kein automatisches Archiv).")

    settings = Settings()

    # Resolve baseline
    if baseline_path is not None:
        effective_baseline = baseline_path
    else:
        from jtl2datev.core.archive import latest_archive

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
    try:
        _, _, baseline_rows = load_baseline(effective_baseline)
    except Exception as exc:
        click.echo(f"Fehler beim Laden der Baseline: {exc}")
        raise SystemExit(1) from exc

    def decisions(inv):  # type: ignore[no-untyped-def]
        return [
            LineDecision(line=line, decision=decide(inv, line, own_vat_countries=settings.own_vat_countries))
            for line in inv.lines
        ]

    compare_map = load_compare_map(compare_to) if compare_to is not None else None

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        current_tmp = Path(tmp.name)

    try:
        engine = make_engine(settings)
        repo = JtlInvoiceRepository(engine)
        invoices_iter = repo.fetch_invoices(date_from=date_from_d, date_to=date_to_d)
        write_extf_buchungsstapel(
            invoices_iter,
            out_path=current_tmp,
            settings=settings,
            date_from=date_from_d,
            date_to=date_to_d,
            decisions_by_invoice=decisions,
            compare_map=compare_map,
            audit=audit,
        )

        if use_archive:
            from jtl2datev.core.archive import archive_export

            archived_full = archive_export(
                current_tmp,
                archive_root=settings.export_archive_root,
                kind="datev",
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Frischer Vollexport archiviert: {archived_full}")

        from jtl2datev.core.datev_delta import read_extf_csv

        extf_header, col_header, current_rows = read_extf_csv(current_tmp)

        delta_rows, new_keys, changed_keys = compute_delta(
            current_rows=current_rows,
            baseline_rows=baseline_rows,
        )

        click.echo(f"Delta: {len(new_keys)} neue Belege, {len(changed_keys)} geänderte Belege")
        if changed_keys:
            for key in changed_keys:
                click.echo(f"  Geändert: {key}")

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp2:
            delta_tmp = Path(tmp2.name)

        try:
            write_delta_extf(
                delta_rows,
                out_path=delta_tmp,
                extf_header_line=extf_header,
                column_header_line=col_header,
            )

            if use_archive:
                from jtl2datev.core.archive import archive_delta

                archived_delta = archive_delta(
                    delta_tmp,
                    archive_root=settings.export_archive_root,
                    kind="datev",
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
        click.echo(f"Fehler beim DATEV-Delta-Export: {exc}")
        raise SystemExit(1) from exc
    finally:
        current_tmp.unlink(missing_ok=True)


@main.command("export-taxually")
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
    import shutil
    import tempfile

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.taxually import format_taxually_xlsx, taxually_filename
    from jtl2datev.core.taxually_delta import archive_taxually_export

    date_from_d, date_to_d = _resolve_date_range(date_from, date_to, month_str)

    use_archive = month_str is not None
    if not use_archive and out_path is None:
        raise click.UsageError("Bei --from/--to ist --out Pflicht (kein automatisches Archiv).")

    settings = Settings()

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        engine = make_engine(settings)
        repo = JtlInvoiceRepository(engine)
        invoices = list(repo.fetch_invoices(date_from=date_from_d, date_to=date_to_d))
        rows_written = format_taxually_xlsx(invoices, tmp_path)

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

        click.echo(f"  Zeilen: {rows_written}")
    except Exception as exc:
        click.echo(f"Fehler beim Taxually-Export: {exc}")
        raise SystemExit(1) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@main.command("export-taxually-delta")
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
    help="Überschreibt Transaction date in der Delta-XLSX für Folgemonats-Nachmeldung.",
)
@click.option(
    "--out",
    "out_path",
    required=False,
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabepfad für die Delta-XLSX. Pflichtfeld bei --from/--to.",
)
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
    import shutil
    import tempfile

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.taxually import format_taxually_xlsx
    from jtl2datev.core.taxually_delta import (
        NoBaselineError,
        archive_taxually_delta,
        archive_taxually_export,
        compute_taxually_delta,
        latest_taxually_archive,
        write_taxually_delta_xlsx,
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

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        current_tmp = Path(tmp.name)

    try:
        engine = make_engine(settings)
        repo = JtlInvoiceRepository(engine)
        current_invoices = list(repo.fetch_invoices(date_from=date_from_d, date_to=date_to_d))
        format_taxually_xlsx(current_invoices, current_tmp)

        if use_archive:
            archived_full = archive_taxually_export(
                current_tmp,
                archive_root=settings.export_archive_root,
                period=month_str,  # type: ignore[arg-type]
            )
            click.echo(f"Frischer Vollexport archiviert: {archived_full}")

        delta_invoices = compute_taxually_delta(current_invoices, effective_baseline)
        click.echo(f"Delta: {len(delta_invoices)} neue Belege")

        shift_date: dt.date | None = None
        if shift_to_period is not None:
            shift_year, shift_month = _parse_month(shift_to_period)
            shift_date = dt.date(shift_year, shift_month, 1)

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp2:
            delta_tmp = Path(tmp2.name)

        try:
            write_taxually_delta_xlsx(delta_invoices, delta_tmp, shift_to=shift_date)

            if use_archive:
                archived_delta = archive_taxually_delta(
                    delta_tmp,
                    archive_root=settings.export_archive_root,
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
        click.echo(f"Fehler beim Taxually-Delta-Export: {exc}")
        raise SystemExit(1) from exc
    finally:
        current_tmp.unlink(missing_ok=True)


@main.command("reconcile")
@click.option(
    "--month",
    "month_str",
    required=False,
    default=None,
    metavar="YYYY-MM",
    help="Monat des Reconcile, z.B. 2026-01.",
)
@click.option(
    "--from",
    "date_from",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Startdatum (inkl.), z.B. 2026-01-01.",
)
@click.option(
    "--to",
    "date_to",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Enddatum (inkl.), z.B. 2026-01-31.",
)
@click.option(
    "--out-mismatches",
    "out_mismatches",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional: alle Mismatches als CSV schreiben.",
)
def reconcile_cmd(
    month_str: str | None,
    date_from: dt.datetime | None,
    date_to: dt.datetime | None,
    out_mismatches: Path | None,
) -> None:
    """Vergleicht JTL-Steuerdaten mit eigener Engine und gibt Mismatch-Report aus."""
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.pipeline import run_reconcile

    df, dt_ = _resolve_date_range(date_from, date_to, month_str)

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


@main.command("mixed-vat-check")
@click.option(
    "--month",
    "month_str",
    required=False,
    default=None,
    metavar="YYYY-MM",
    help="Monat des Checks, z.B. 2026-01.",
)
@click.option(
    "--from",
    "date_from",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Startdatum (inkl.), z.B. 2026-01-01.",
)
@click.option(
    "--to",
    "date_to",
    required=False,
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Enddatum (inkl.), z.B. 2026-01-31.",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Optionaler Pfad für CSV-Output. Ohne --out: nur Konsolen-Bericht.",
)
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
    from jtl2datev.core.db_jtl import make_engine
    from jtl2datev.core.preflight import find_mixed_vat_belege

    df, dt_ = _resolve_date_range(date_from, date_to, month_str)

    settings = Settings()

    try:
        engine = make_engine(settings)
        belege = find_mixed_vat_belege(engine, date_from=df, date_to=dt_)
    except Exception as exc:
        click.echo(f"Fehler beim Mixed-VAT-Check: {exc}")
        raise SystemExit(1) from exc

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
        "source",
        "pk",
        "belegnr",
        "datum",
        "vat_rates",
        "external_order_no",
        "position_count",
        "total_brutto",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for b in belege:
            writer.writerow(
                {
                    "source": b.source,
                    "pk": b.pk,
                    "belegnr": b.belegnr,
                    "datum": b.datum.isoformat(),
                    "vat_rates": ";".join(str(r) for r in b.vat_rates),
                    "external_order_no": b.external_order_no or "",
                    "position_count": b.position_count,
                    "total_brutto": str(b.total_brutto),
                }
            )


@main.command("export-verbringung")
@click.option(
    "--report",
    "report_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Pfad zur Amazon-Verbringungsliste (TSV).",
)
@click.option(
    "--month",
    "month_str",
    required=True,
    metavar="YYYY-MM",
    help="Monat des Berichts, z.B. 2026-01. Steuert PFR-Nummerierung und Auto-Archiv.",
)
@click.option(
    "--out-xlsx",
    "out_xlsx",
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabepfad für Taxually-XLSX. Default: exports/verbringung/YYYY-MM/verbringung_<ts>.xlsx",
)
@click.option(
    "--out-pdf-dir",
    "out_pdf_dir",
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabeverzeichnis für Pro-Forma-PDFs. Default: exports/verbringung/YYYY-MM/pdfs/",
)
@click.option(
    "--out-missing-ek",
    "out_missing_ek",
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabepfad für Missing-EK-CSV. Default: exports/verbringung/YYYY-MM/missing_ek_<ts>.csv",
)
@click.option(
    "--strict",
    "strict",
    is_flag=True,
    default=False,
    help="Fehler statt interaktiver Nachfrage wenn Wechselkurse fehlen.",
)
@click.option(
    "--bware-pricing-strategy",
    "bware_pricing_strategy",
    default="ten_percent",
    type=click.Choice(["ten_percent", "flat_10ct"]),
    show_default=True,
    help=(
        "B-Ware EK-Strategie: 'ten_percent' (Stem-Lookup, 10% des Artikel-EK) "
        "oder 'flat_10ct' (pauschal 0,10 EUR, kein Stem-Lookup)."
    ),
)
@click.option(
    "--out-bware-summary",
    "out_bware_summary",
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabepfad für B-Ware-Summary-CSV. Default: exports/verbringung/YYYY-MM/bware_summary_<ts>.csv",
)
def export_verbringung_cmd(
    report_path: Path,
    month_str: str,
    out_xlsx: Path | None,
    out_pdf_dir: Path | None,
    out_missing_ek: Path | None,
    strict: bool,
    bware_pricing_strategy: str,
    out_bware_summary: Path | None,
) -> None:
    """Erzeugt Taxually-XLSX und Pro-Forma-PDFs aus einem Amazon-Verbringungsbericht.

    Verbindet sich mit JTL-Datenbank für EK-Preise. Ohne --out-*: automatisches
    Archiv unter exports/verbringung/YYYY-MM/.

    Wechselkurse werden aus data/exchange_rates.json geladen (via import-rates befüllen).
    Bei fehlenden Kursen: interaktiver Prompt (oder --strict für sofortigen Abbruch).
    """
    import tempfile
    from decimal import Decimal, InvalidOperation

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import make_engine
    from jtl2datev.core.exchange_rates import set_rate
    from jtl2datev.core.verbringung_parser import parse_amazon_report
    from jtl2datev.core.verbringung_pdf import (
        COUNTRY_CURRENCIES,
        generate_proforma_pdfs,
    )
    from jtl2datev.core.verbringung_pricing import lookup_prices
    from jtl2datev.core.verbringung_taxually import format_verbringung_xlsx

    year, month = _parse_month(month_str)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    archive_base = Path("exports") / "verbringung" / month_str
    effective_xlsx = out_xlsx or (archive_base / f"verbringung_{ts}.xlsx")
    effective_pdf_dir = out_pdf_dir or (archive_base / "pdfs")
    effective_missing_ek = out_missing_ek or (archive_base / f"missing_ek_{ts}.csv")
    effective_bware_summary = out_bware_summary or (archive_base / f"bware_summary_{ts}.csv")

    try:
        # Parse report first to know which currencies are needed
        movements = parse_amazon_report(report_path)
        fc_count = sum(1 for m in movements if m.transaction_type == "FC_TRANSFER")
        inbound_count = sum(1 for m in movements if m.transaction_type == "INBOUND")

        # Determine required non-EUR currencies for this movement set
        required: set[str] = set()
        for mv in movements:
            for country in (mv.departure_country, mv.arrival_country):
                cur = COUNTRY_CURRENCIES.get(country)
                if cur and cur != "EUR":
                    required.add(cur)

        # Load available rates from JSON store
        exchange_rates: dict[str, Decimal] = get_rates_for_period(month_str, path=DEFAULT_RATES_PATH)

        # Check for missing rates
        missing_currencies = sorted(required - set(exchange_rates.keys()))
        if missing_currencies:
            bmf_url = (
                f"https://www.bundesfinanzministerium.de/Datenportal/Daten/offene-daten/"
                f"steuern-zoelle/umsatzsteuer-umrechnungskurse/datensaetze/"
                f"uu-kurse-{year}-csv.csv?__blob=publicationFile"
            )
            if strict:
                click.echo(
                    f"Fehler: Wechselkurse für {month_str} fehlen: {', '.join(missing_currencies)}\n"
                    f"Quelle BMF: {bmf_url}\n"
                    f"Tipp: jtl2datev import-rates --year {year}"
                )
                raise SystemExit(1)

            for currency in missing_currencies:
                click.echo(f"\nWechselkurs für {month_str} fehlt: {currency}")
                click.echo(f"Quelle BMF: {bmf_url}")
                raw = click.prompt(
                    f"1 EUR = ? {currency} (leer = Abbruch)",
                    default="",
                    show_default=False,
                )
                if not raw.strip():
                    click.echo(f"Abbruch: Kein Kurs für {currency} angegeben.")
                    raise SystemExit(1)
                raw_normalized = raw.strip().replace(",", ".")
                try:
                    value = Decimal(raw_normalized)
                except InvalidOperation:
                    click.echo(f"Ungültige Eingabe: {raw!r}")
                    raise SystemExit(1)
                set_rate(month_str, currency, value, source="manual", path=DEFAULT_RATES_PATH)
                exchange_rates[currency] = value
                click.echo(f"  Kurs gespeichert: 1 EUR = {value} {currency} (manual)")

        # Lookup prices from JTL
        settings = Settings()
        engine = make_engine(settings)
        unique_skus = list({m.seller_sku for m in movements})
        asin_by_sku = {m.seller_sku: m.asin for m in movements if m.asin and m.seller_sku}
        pricing = lookup_prices(
            unique_skus,
            engine,
            bware_strategy=bware_pricing_strategy,
            asin_by_sku=asin_by_sku,
        )

        mapped = sum(1 for p in pricing.values() if p.ek_netto is not None)
        unmapped = len(unique_skus) - mapped

        # XLSX export
        effective_xlsx.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_xlsx = Path(tmp.name)
        try:
            rows_written = format_verbringung_xlsx(movements, pricing, tmp_xlsx)
            import shutil
            shutil.copy2(tmp_xlsx, effective_xlsx)
        finally:
            tmp_xlsx.unlink(missing_ok=True)

        # PDF export — pass exchange_rates (may be empty dict if no non-EUR routes)
        pdf_paths = generate_proforma_pdfs(
            movements=movements,
            pricing=pricing,
            period=month_str,
            output_dir=effective_pdf_dir,
            exchange_rates=exchange_rates if exchange_rates else None,
        )

        # Missing EK CSV — B-Ware SKUs are priced (is_bware=True) and excluded here
        missing_rows = [
            (sku, pr)
            for sku, pr in pricing.items()
            if pr.ek_netto is None and not pr.is_bware
        ]
        from collections import Counter
        missing_counts: Counter[str] = Counter()
        missing_qty: Counter[str] = Counter()
        missing_asin: dict[str, str] = {}
        missing_desc: dict[str, str] = {}
        for mv in movements:
            if mv.seller_sku in {sku for sku, _ in missing_rows}:
                missing_counts[mv.seller_sku] += 1
                missing_qty[mv.seller_sku] += mv.qty
                missing_asin.setdefault(mv.seller_sku, mv.asin)
                missing_desc.setdefault(mv.seller_sku, mv.description)

        if missing_rows:
            effective_missing_ek.parent.mkdir(parents=True, exist_ok=True)
            with effective_missing_ek.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(["seller_sku", "asin", "description", "movement_count",
                                  "total_qty", "reason"])
                for sku, pr in sorted(missing_rows, key=lambda x: x[0]):
                    reason = "no-ek" if pr.matched_jtl_artikel else "no-mapping"
                    writer.writerow([
                        sku,
                        missing_asin.get(sku, ""),
                        missing_desc.get(sku, ""),
                        missing_counts.get(sku, 0),
                        missing_qty.get(sku, 0),
                        reason,
                    ])

        # B-Ware summary CSV
        bware_rows = [(sku, pr) for sku, pr in pricing.items() if pr.is_bware]
        bware_counts: Counter[str] = Counter()
        bware_qty: Counter[str] = Counter()
        bware_mv_ids: dict[str, list[str]] = {}
        for mv in movements:
            if mv.seller_sku in {sku for sku, _ in bware_rows}:
                bware_counts[mv.seller_sku] += 1
                bware_qty[mv.seller_sku] += mv.qty
                bware_mv_ids.setdefault(mv.seller_sku, []).append(mv.transaction_event_id)

        if bware_rows:
            from jtl2datev.core.verbringung_pricing import extract_bware_stem
            effective_bware_summary.parent.mkdir(parents=True, exist_ok=True)
            with effective_bware_summary.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow([
                    "seller_sku", "stem", "qty_total", "movements",
                    "ek_basis", "ek_used", "source",
                ])
                for sku, pr in sorted(bware_rows, key=lambda x: x[0]):
                    stem = extract_bware_stem(sku) or ""
                    movements_count = bware_counts.get(sku, 0)
                    qty_total = bware_qty.get(sku, 0)
                    ek_basis = str(pr.bware_pricing_basis) if pr.bware_pricing_basis is not None else ""
                    ek_used = str(pr.ek_netto) if pr.ek_netto is not None else ""
                    source = pr.matched_via or ""
                    writer.writerow([sku, stem, qty_total, movements_count,
                                     ek_basis, ek_used, source])

        bware_stem_count = sum(1 for _, pr in bware_rows if pr.matched_via == "bware-stem")
        bware_fallback_count = sum(1 for _, pr in bware_rows if pr.matched_via == "bware-fallback")

        click.echo(f"Verbringung-Export abgeschlossen: {month_str}")
        click.echo(f"  Bewegungen: FC_TRANSFER={fc_count}, INBOUND={inbound_count}")
        click.echo(f"  Routen / PDFs: {len(pdf_paths)}")
        click.echo(f"  SKUs: {mapped} gemappt, {unmapped} nicht gemappt")
        click.echo(f"  XLSX: {effective_xlsx} ({rows_written} Zeilen)")
        click.echo(f"  PDFs: {effective_pdf_dir}")
        if bware_rows:
            click.echo(
                f"  B-Ware: {len(bware_rows)} SKUs "
                f"(stem={bware_stem_count}, fallback={bware_fallback_count}) "
                f"→ {effective_bware_summary}"
            )
        if missing_rows:
            click.echo(f"  Missing-EK: {effective_missing_ek} ({len(missing_rows)} SKUs)")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Fehler beim Verbringung-Export: {exc}")
        raise SystemExit(1) from exc


@main.command("import-rates")
@click.option(
    "--year",
    "year",
    default=None,
    type=int,
    metavar="YYYY",
    help=f"Jahr für den BMF-Import. Default: aktuelles Jahr.",
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

    try:
        imported = import_bmf_rates(effective_year, path=DEFAULT_RATES_PATH, content=content)
    except Exception as exc:
        click.echo(f"Fehler beim Import: {exc}")
        raise SystemExit(1) from exc

    total = 0
    for period in sorted(imported):
        currencies = imported[period]
        total += len(currencies)
        click.echo(f"  {period}: {', '.join(sorted(currencies))}")

    click.echo(f"\nImport abgeschlossen: {total} Kurse in {len(imported)} Perioden.")
    click.echo(f"Gespeichert: {DEFAULT_RATES_PATH}")


if __name__ == "__main__":
    main()
