"""Verbringungs-Export-Command (Amazon-FBA-Transfers).

CLI behält die interaktiven Wechselkurs-Prompts; Service ist pure und wird
nach Auflösung aller Kurse aufgerufen.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import click

from jtl2datev.cli import main
from jtl2datev.cli._common import _parse_month
from jtl2datev.core.config import Settings
from jtl2datev.core.exchange_rates import get_rates_for_period


@main.command("export-verbringung")
@click.option("--report", "report_path", required=True,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Pfad zur Amazon-Verbringungsliste (TSV).")
@click.option("--month", "month_str", required=True, metavar="YYYY-MM",
              help="Monat des Berichts, z.B. 2026-01. Steuert PFR-Nummerierung und Auto-Archiv.")
@click.option("--out-xlsx", "out_xlsx", default=None, type=click.Path(path_type=Path),
              help="Ausgabepfad für Taxually-XLSX. Default: exports/verbringung/YYYY-MM/verbringung_<ts>.xlsx")
@click.option("--out-pdf-dir", "out_pdf_dir", default=None, type=click.Path(path_type=Path),
              help="Ausgabeverzeichnis für Pro-Forma-PDFs. Default: exports/verbringung/YYYY-MM/pdfs/")
@click.option("--out-missing-ek", "out_missing_ek", default=None, type=click.Path(path_type=Path),
              help="Ausgabepfad für Missing-EK-CSV. Default: exports/verbringung/YYYY-MM/missing_ek_<ts>.csv")
@click.option("--strict", "strict", is_flag=True, default=False,
              help="Fehler statt interaktiver Nachfrage wenn Wechselkurse fehlen.")
@click.option("--bware-pricing-strategy", "bware_pricing_strategy",
              default="ten_percent", type=click.Choice(["ten_percent", "flat_10ct"]),
              show_default=True,
              help=("B-Ware EK-Strategie: 'ten_percent' (Stem-Lookup, 10% des Artikel-EK) "
                    "oder 'flat_10ct' (pauschal 0,10 EUR, kein Stem-Lookup)."))
@click.option("--out-bware-summary", "out_bware_summary", default=None, type=click.Path(path_type=Path),
              help="Ausgabepfad für B-Ware-Summary-CSV. Default: exports/verbringung/YYYY-MM/bware_summary_<ts>.csv")
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
    from decimal import Decimal, InvalidOperation

    from jtl2datev.core.db_jtl import JtlArticlePricingRepository, managed_engine
    from jtl2datev.core.exchange_rates import set_rate
    from jtl2datev.core.services.verbringung_service import (
        VerbringungExportRequest,
        export_verbringung,
        required_currencies_for,
    )
    from jtl2datev.core.verbringung_parser import parse_amazon_report

    year, month = _parse_month(month_str)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    archive_base = Path("exports") / "verbringung" / month_str
    effective_xlsx = out_xlsx or (archive_base / f"verbringung_{ts}.xlsx")
    effective_pdf_dir = out_pdf_dir or (archive_base / "pdfs")
    effective_missing_ek = out_missing_ek or (archive_base / f"missing_ek_{ts}.csv")
    effective_bware_summary = out_bware_summary or (archive_base / f"bware_summary_{ts}.csv")

    settings = Settings()
    rates_path = settings.rates_path
    try:
        # 1) Movements parsen, um benötigte Währungen zu bestimmen
        movements = parse_amazon_report(report_path)
        required = required_currencies_for(movements)

        # 2) Wechselkurse laden + ggf. via Prompt nachpflegen
        exchange_rates: dict[str, Decimal] = get_rates_for_period(month_str, path=rates_path)
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
                set_rate(month_str, currency, value, source="manual", path=rates_path)
                exchange_rates[currency] = value
                click.echo(f"  Kurs gespeichert: 1 EUR = {value} {currency} (manual)")

        # 3) Service mit kompletten Kursen aufrufen
        with managed_engine(settings) as engine:
            result = export_verbringung(
                VerbringungExportRequest(
                    movements=movements,
                    pricing_repo=JtlArticlePricingRepository(engine),
                    period=month_str,
                    exchange_rates=exchange_rates,
                    out_xlsx=effective_xlsx,
                    out_pdf_dir=effective_pdf_dir,
                    out_missing_ek=effective_missing_ek,
                    out_bware_summary=effective_bware_summary,
                    bware_strategy=bware_pricing_strategy,
                )
            )

        # 4) Echo-Summary
        click.echo(f"Verbringung-Export abgeschlossen: {month_str}")
        click.echo(f"  Bewegungen: FC_TRANSFER={result.fc_count}, INBOUND={result.inbound_count}")
        click.echo(f"  Routen / PDFs: {len(result.pdf_paths)}")
        click.echo(f"  SKUs: {result.skus_mapped} gemappt, {result.skus_unmapped} nicht gemappt")
        click.echo(f"  XLSX: {result.out_xlsx} ({result.rows_written} Zeilen)")
        click.echo(f"  PDFs: {effective_pdf_dir}")
        if result.bware_count:
            click.echo(
                f"  B-Ware: {result.bware_count} SKUs "
                f"(stem={result.bware_stem_count}, fallback={result.bware_fallback_count}) "
                f"→ {result.bware_summary_path}"
            )
        if result.missing_ek_count:
            click.echo(f"  Missing-EK: {result.missing_ek_path} ({result.missing_ek_count} SKUs)")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Fehler beim Verbringung-Export: {exc}")
        raise SystemExit(1) from exc
