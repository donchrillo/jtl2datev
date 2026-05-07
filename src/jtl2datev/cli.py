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
@click.option(
    "--month",
    "month_str",
    required=True,
    metavar="YYYY-MM",
    help="Monat des Exports, z.B. 2026-01.",
)
@click.option(
    "--out",
    "out_path",
    required=False,
    default=None,
    type=click.Path(path_type=Path),
    help="Ausgabepfad. Standard: exports/datev/YYYY-MM.csv",
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
    month_str: str,
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

    year, month = _parse_month(month_str)
    df, dt_ = _month_date_range(year, month)

    effective_out: Path
    if out_path is not None:
        effective_out = Path(out_path)
    else:
        effective_out = Path("exports/datev") / f"{month_str}.csv"
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


def _month_date_range(year: int, month: int) -> "tuple":
    import datetime as _dt

    date_from = _dt.date(year, month, 1)
    if month == 12:
        date_to_excl = _dt.date(year + 1, 1, 1)
    else:
        date_to_excl = _dt.date(year, month + 1, 1)
    return date_from, date_to_excl - _dt.timedelta(days=1)


@main.command("export-dutypay")
@click.option(
    "--month",
    "month_str",
    required=True,
    metavar="YYYY-MM",
    help="Monat des Exports, z.B. 2026-01.",
)
@click.option(
    "--out",
    "out_path",
    required=False,
    default=None,
    type=click.Path(path_type=Path),
    help="Optionaler zusätzlicher Ausgabepfad (neben der automatischen Archivierung).",
)
def export_dutypay_cmd(month_str: str, out_path: Path | None) -> None:
    """Exportiert Rechnungen aus JTL als DutyPay OSS-CSV (+ automatische Archivierung)."""
    import tempfile

    from jtl2datev.core.archive import archive_export
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.dutypay import dutypay_filename, write_dutypay_csv

    year, month = _parse_month(month_str)
    date_from, date_to_incl = _month_date_range(year, month)
    settings = Settings()

    # Write to a temp file first, then archive + optional copy to --out.
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        engine = make_engine(settings)
        repo = JtlInvoiceRepository(engine)
        invoices_iter = repo.fetch_invoices(date_from=date_from, date_to=date_to_incl)
        report = write_dutypay_csv(
            invoices_iter,
            out_path=tmp_path,
            own_vat_ids=settings.own_vat_ids,
        )

        archived = archive_export(
            tmp_path,
            archive_root=settings.export_archive_root,
            kind="dutypay",
            period=month_str,
        )
        click.echo(f"DutyPay-Export archiviert: {archived}")

        if out_path is not None:
            resolved = Path(out_path)
            if resolved.is_dir():
                resolved = resolved / dutypay_filename(year, month)
            import shutil
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
    required=True,
    metavar="YYYY-MM",
    help="Monat, für den das Delta berechnet wird.",
)
@click.option(
    "--baseline",
    "baseline_path",
    required=False,
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Explizite Baseline-Datei (Standard: letzter archivierter Vollexport für den Monat).",
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
    help="Optionaler zusätzlicher Pfad für die Delta-CSV.",
)
def export_dutypay_delta_cmd(
    month_str: str,
    baseline_path: Path | None,
    shift_to_period: str | None,
    out_path: Path | None,
) -> None:
    """Berechnet Delta-Export zwischen aktuellem JTL-Stand und letztem Vollexport."""
    import shutil
    import tempfile

    from jtl2datev.core.archive import archive_delta, archive_export, latest_archive
    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.dutypay import DUTYPAY_COLUMNS, write_dutypay_csv
    from jtl2datev.core.dutypay_delta import (
        NoBaselineError,
        compute_delta,
        load_baseline,
        write_delta_csv,
    )

    year, month = _parse_month(month_str)
    date_from, date_to_incl = _month_date_range(year, month)
    settings = Settings()

    # Resolve baseline
    if baseline_path is not None:
        effective_baseline = baseline_path
    else:
        effective_baseline = latest_archive(
            settings.export_archive_root,
            kind="dutypay",
            period=month_str,
        )
        if effective_baseline is None:
            click.echo(
                f"Keine Baseline-Datei gefunden — erst Vollexport laufen lassen: "
                f"jtl2datev export-dutypay --month {month_str}"
            )
            raise SystemExit(1)

    click.echo(f"Baseline: {effective_baseline}")
    baseline_rows = load_baseline(effective_baseline)

    # Fresh full export into temp file
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        current_tmp = Path(tmp.name)

    try:
        engine = make_engine(settings)
        repo = JtlInvoiceRepository(engine)
        invoices_iter = repo.fetch_invoices(date_from=date_from, date_to=date_to_incl)
        write_dutypay_csv(
            invoices_iter,
            out_path=current_tmp,
            own_vat_ids=settings.own_vat_ids,
        )

        # Archive the fresh full export so next delta can use it as baseline
        archived_full = archive_export(
            current_tmp,
            archive_root=settings.export_archive_root,
            kind="dutypay",
            period=month_str,
        )
        click.echo(f"Frischer Vollexport archiviert: {archived_full}")

        # Load current rows for diff
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

        # Parse shift-to-period if given
        shift_tuple: tuple[int, int] | None = None
        if shift_to_period is not None:
            shift_year, shift_month = _parse_month(shift_to_period)
            shift_tuple = (shift_year, shift_month)

        # Write delta to temp file, then archive + optional copy
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp2:
            delta_tmp = Path(tmp2.name)

        try:
            write_delta_csv(
                delta_rows,
                out_path=delta_tmp,
                fieldnames=list(DUTYPAY_COLUMNS),
                shift_to_period=shift_tuple,
            )

            archived_delta = archive_delta(
                delta_tmp,
                archive_root=settings.export_archive_root,
                kind="dutypay",
                period=month_str,
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


@main.command("mixed-vat-check")
@click.option("--from", "date_from", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--to", "date_to", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Optionaler Pfad für CSV-Output. Ohne --out: nur Konsolen-Bericht.",
)
def mixed_vat_check_cmd(date_from: date, date_to: date, out_path: Path | None) -> None:
    """Pre-Flight: Belege mit gemischten Steuersätzen auf Artikel-Positionen.

    Listet Belege, die auf ihren Hauptpositionen (ohne Versand/Sub-Positionen)
    mehr als einen MwStSatz tragen. Vor DATEV-/DutyPay-Export laufen lassen
    und betroffene Belege in JTL prüfen/korrigieren.
    """
    import datetime as dt

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import make_engine
    from jtl2datev.core.preflight import find_mixed_vat_belege

    df = date_from.date() if isinstance(date_from, dt.datetime) else date_from  # type: ignore[union-attr]
    dt_ = date_to.date() if isinstance(date_to, dt.datetime) else date_to  # type: ignore[union-attr]

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


if __name__ == "__main__":
    main()
