"""Verbringungs-Export-Command (Amazon-FBA-Transfers)."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.cli._common import _parse_month
from jtl2datev.core.exchange_rates import DEFAULT_RATES_PATH, get_rates_for_period


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
    from jtl2datev.core.db_jtl import JtlArticlePricingRepository, managed_engine
    from jtl2datev.core.exchange_rates import set_rate
    from jtl2datev.core.verbringung_parser import parse_amazon_report
    from jtl2datev.core.verbringung_pdf import (
        COUNTRY_CURRENCIES,
        generate_proforma_pdfs,
    )
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
        unique_skus = list({m.seller_sku for m in movements})
        asin_by_sku = {m.seller_sku: m.asin for m in movements if m.asin and m.seller_sku}
        with managed_engine(settings) as engine:
            pricing_repo = JtlArticlePricingRepository(engine)
            pricing = pricing_repo.lookup_ek_prices(
                unique_skus,
                asin_by_sku=asin_by_sku,
                bware_strategy=bware_pricing_strategy,
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
