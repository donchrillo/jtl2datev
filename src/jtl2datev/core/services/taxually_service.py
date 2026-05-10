"""Taxually-Export-Service: Vollexport + Delta gegen Baseline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jtl2datev.core.config import Settings
from jtl2datev.core.repositories import InvoiceRepository
from jtl2datev.core.taxually import format_taxually_xlsx
from jtl2datev.core.taxually_delta import (
    NoBaselineError,
    compute_taxually_delta,
    write_taxually_delta_xlsx,
)

__all__ = [
    "TaxuallyExportRequest",
    "TaxuallyExportResult",
    "TaxuallyDeltaRequest",
    "TaxuallyDeltaResult",
    "NoBaselineError",
    "export_taxually",
    "export_taxually_delta",
]


@dataclass(frozen=True)
class TaxuallyExportRequest:
    repo: InvoiceRepository
    settings: Settings
    date_from: date
    date_to: date
    out_path: Path


@dataclass(frozen=True)
class TaxuallyExportResult:
    out_path: Path
    rows_written: int


@dataclass(frozen=True)
class TaxuallyDeltaRequest:
    repo: InvoiceRepository
    settings: Settings
    date_from: date
    date_to: date
    baseline_path: Path
    full_out_path: Path
    delta_out_path: Path
    shift_to: date | None = None  # erstes Datum des Shift-Monats


@dataclass(frozen=True)
class TaxuallyDeltaResult:
    full_out_path: Path
    delta_out_path: Path
    full_rows_written: int
    delta_invoice_count: int


def export_taxually(req: TaxuallyExportRequest) -> TaxuallyExportResult:
    """Schreibt Taxually-XLSX nach req.out_path."""
    invoices = list(req.repo.fetch_invoices(date_from=req.date_from, date_to=req.date_to))
    rows_written = format_taxually_xlsx(invoices, req.out_path)
    return TaxuallyExportResult(out_path=req.out_path, rows_written=rows_written)


def export_taxually_delta(req: TaxuallyDeltaRequest) -> TaxuallyDeltaResult:
    """Erzeugt frischen Vollexport + Delta-XLSX gegen Baseline.

    Wirft NoBaselineError wenn baseline_path nicht ladbar ist.
    """
    current_invoices = list(req.repo.fetch_invoices(date_from=req.date_from, date_to=req.date_to))
    full_rows = format_taxually_xlsx(current_invoices, req.full_out_path)

    delta_invoices = compute_taxually_delta(current_invoices, req.baseline_path)
    write_taxually_delta_xlsx(delta_invoices, req.delta_out_path, shift_to=req.shift_to)

    return TaxuallyDeltaResult(
        full_out_path=req.full_out_path,
        delta_out_path=req.delta_out_path,
        full_rows_written=full_rows,
        delta_invoice_count=len(delta_invoices),
    )
