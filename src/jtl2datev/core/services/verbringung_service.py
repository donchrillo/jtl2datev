"""Verbringungs-Export-Service: Amazon-FBA-Transfers → Taxually-XLSX + Pro-Forma-PDFs.

Service ist pure: nimmt vorab geparste Movements + komplette Wechselkurs-
Tabelle. Wenn Kurse fehlen, wirft er MissingExchangeRatesError — der Aufrufer
ist verantwortlich für interaktive Prompts (CLI) bzw. HTTP-400 (FastAPI).
"""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from jtl2datev.core.repositories import ArticlePricingRepository
from jtl2datev.core.verbringung_parser import MovementRow
from jtl2datev.core.verbringung_pdf import COUNTRY_CURRENCIES, generate_proforma_pdfs
from jtl2datev.core.verbringung_pricing import PricingResult, extract_bware_stem
from jtl2datev.core.verbringung_taxually import format_verbringung_xlsx

__all__ = [
    "VerbringungExportRequest",
    "VerbringungExportResult",
    "MissingExchangeRatesError",
    "required_currencies_for",
    "export_verbringung",
]


class MissingExchangeRatesError(Exception):
    """Wechselkurse für mind. eine benötigte Währung fehlen.

    Aufrufer (CLI: prompt; FastAPI: 400-Response mit Liste) muss handeln.
    """

    def __init__(self, missing_currencies: list[str]) -> None:
        self.missing_currencies = missing_currencies
        super().__init__(
            f"Wechselkurse fehlen: {', '.join(missing_currencies)}"
        )


@dataclass(frozen=True)
class VerbringungExportRequest:
    movements: list[MovementRow]
    pricing_repo: ArticlePricingRepository
    period: str  # "YYYY-MM"
    exchange_rates: dict[str, Decimal]
    out_xlsx: Path
    out_pdf_dir: Path
    out_missing_ek: Path | None = None  # None = nicht schreiben
    out_bware_summary: Path | None = None  # None = nicht schreiben
    bware_strategy: str = "ten_percent"


@dataclass(frozen=True)
class VerbringungExportResult:
    out_xlsx: Path
    rows_written: int
    pdf_paths: list[Path]
    pricing: dict[str, PricingResult]
    missing_ek_path: Path | None
    missing_ek_count: int
    bware_summary_path: Path | None
    bware_count: int
    bware_stem_count: int
    bware_fallback_count: int
    fc_count: int
    inbound_count: int
    skus_mapped: int
    skus_unmapped: int


def required_currencies_for(movements: list[MovementRow]) -> set[str]:
    """Welche Nicht-EUR-Währungen werden für PDF-Bewertung benötigt?"""
    required: set[str] = set()
    for mv in movements:
        for country in (mv.departure_country, mv.arrival_country):
            cur = COUNTRY_CURRENCIES.get(country)
            if cur and cur != "EUR":
                required.add(cur)
    return required


def export_verbringung(req: VerbringungExportRequest) -> VerbringungExportResult:
    """Erzeugt XLSX + Pro-Forma-PDFs + optional Missing-EK- und B-Ware-CSVs.

    Wirft MissingExchangeRatesError, falls für die Movements benötigte
    Nicht-EUR-Kurse nicht in req.exchange_rates enthalten sind.
    """
    required = required_currencies_for(req.movements)
    missing = sorted(required - set(req.exchange_rates.keys()))
    if missing:
        raise MissingExchangeRatesError(missing)

    movements = req.movements
    fc_count = sum(1 for m in movements if m.transaction_type == "FC_TRANSFER")
    inbound_count = sum(1 for m in movements if m.transaction_type == "INBOUND")

    # Pricing-Lookup via Repository (JTL-spezifisch oder ERP-spezifisch)
    unique_skus = list({m.seller_sku for m in movements})
    asin_by_sku = {m.seller_sku: m.asin for m in movements if m.asin and m.seller_sku}
    pricing = req.pricing_repo.lookup_ek_prices(
        unique_skus,
        asin_by_sku=asin_by_sku,
        bware_strategy=req.bware_strategy,
    )
    skus_mapped = sum(1 for p in pricing.values() if p.ek_netto is not None)
    skus_unmapped = len(unique_skus) - skus_mapped

    # XLSX-Export
    req.out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    rows_written = format_verbringung_xlsx(movements, pricing, req.out_xlsx)

    # PDF-Export
    pdf_paths = generate_proforma_pdfs(
        movements=movements,
        pricing=pricing,
        period=req.period,
        output_dir=req.out_pdf_dir,
        exchange_rates=req.exchange_rates if req.exchange_rates else None,
    )

    # Missing-EK-CSV (B-Ware-SKUs sind bepreist via is_bware → ausgeschlossen)
    missing_rows = [
        (sku, pr) for sku, pr in pricing.items()
        if pr.ek_netto is None and not pr.is_bware
    ]
    missing_ek_path: Path | None = None
    if missing_rows and req.out_missing_ek is not None:
        _write_missing_ek_csv(missing_rows, movements, req.out_missing_ek)
        missing_ek_path = req.out_missing_ek

    # B-Ware-Summary-CSV
    bware_rows = [(sku, pr) for sku, pr in pricing.items() if pr.is_bware]
    bware_summary_path: Path | None = None
    if bware_rows and req.out_bware_summary is not None:
        _write_bware_summary_csv(bware_rows, movements, req.out_bware_summary)
        bware_summary_path = req.out_bware_summary

    bware_stem_count = sum(1 for _, pr in bware_rows if pr.matched_via == "bware-stem")
    bware_fallback_count = sum(1 for _, pr in bware_rows if pr.matched_via == "bware-fallback")

    return VerbringungExportResult(
        out_xlsx=req.out_xlsx,
        rows_written=rows_written,
        pdf_paths=pdf_paths,
        pricing=pricing,
        missing_ek_path=missing_ek_path,
        missing_ek_count=len(missing_rows),
        bware_summary_path=bware_summary_path,
        bware_count=len(bware_rows),
        bware_stem_count=bware_stem_count,
        bware_fallback_count=bware_fallback_count,
        fc_count=fc_count,
        inbound_count=inbound_count,
        skus_mapped=skus_mapped,
        skus_unmapped=skus_unmapped,
    )


def _write_missing_ek_csv(
    missing_rows: list[tuple[str, PricingResult]],
    movements: list[MovementRow],
    out_path: Path,
) -> None:
    missing_skus = {sku for sku, _ in missing_rows}
    counts: Counter[str] = Counter()
    qty: Counter[str] = Counter()
    asin: dict[str, str] = {}
    desc: dict[str, str] = {}
    for mv in movements:
        if mv.seller_sku in missing_skus:
            counts[mv.seller_sku] += 1
            qty[mv.seller_sku] += mv.qty
            asin.setdefault(mv.seller_sku, mv.asin)
            desc.setdefault(mv.seller_sku, mv.description)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow([
            "seller_sku", "asin", "description", "movement_count",
            "total_qty", "reason",
        ])
        for sku, pr in sorted(missing_rows, key=lambda x: x[0]):
            reason = "no-ek" if pr.matched_jtl_artikel else "no-mapping"
            writer.writerow([
                sku, asin.get(sku, ""), desc.get(sku, ""),
                counts.get(sku, 0), qty.get(sku, 0), reason,
            ])


def _write_bware_summary_csv(
    bware_rows: list[tuple[str, PricingResult]],
    movements: list[MovementRow],
    out_path: Path,
) -> None:
    bware_skus = {sku for sku, _ in bware_rows}
    counts: Counter[str] = Counter()
    qty: Counter[str] = Counter()
    for mv in movements:
        if mv.seller_sku in bware_skus:
            counts[mv.seller_sku] += 1
            qty[mv.seller_sku] += mv.qty

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow([
            "seller_sku", "stem", "qty_total", "movements",
            "ek_basis", "ek_used", "source",
        ])
        for sku, pr in sorted(bware_rows, key=lambda x: x[0]):
            stem = extract_bware_stem(sku) or ""
            ek_basis = str(pr.bware_pricing_basis) if pr.bware_pricing_basis is not None else ""
            ek_used = str(pr.ek_netto) if pr.ek_netto is not None else ""
            source = pr.matched_via or ""
            writer.writerow([
                sku, stem, qty.get(sku, 0), counts.get(sku, 0),
                ek_basis, ek_used, source,
            ])
