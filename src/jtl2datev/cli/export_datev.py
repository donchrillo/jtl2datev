"""DATEV-Export-Commands: export, export-delta."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.cli._common import _resolve_date_range


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
@click.option(
    "--keep-zero-amount",
    is_flag=True,
    default=False,
    help="Belege mit Brutto-Summe = 0,00 € (Probebuchungen) NICHT ausfiltern. "
    "Standard: filtern. Für vollständigen Audit-Trail aktivieren.",
)
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
    from jtl2datev.core.config import Settings
    from jtl2datev.core.datev import load_compare_map, write_extf_buchungsstapel
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
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
        with managed_engine(settings) as engine:
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
                keep_zero_amount=keep_zero_amount,
            )
        click.echo(f"DATEV-Export geschrieben: {effective_out}")
        click.echo(f"  Buchungen: {report.bookings_written}")
        click.echo(f"  Belege geskippt (Fehler):    {report.skipped_error}")
        click.echo(f"  Belege geskippt (unbekannt): {report.skipped_unknown}")
        click.echo(f"  Belege geskippt (0,00 €):    {report.skipped_zero_amount}")
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
@click.option(
    "--keep-zero-amount",
    is_flag=True,
    default=False,
    help="Belege mit Brutto-Summe = 0,00 € (Probebuchungen) NICHT ausfiltern. "
    "Standard: filtern.",
)
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
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, managed_engine
    from jtl2datev.core.models import LineDecision
    from jtl2datev.core.tax_engine import decide

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
        with managed_engine(settings) as engine:
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
                keep_zero_amount=keep_zero_amount,
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
