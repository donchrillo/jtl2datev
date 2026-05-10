"""DATEV-Export-Service: Vollexport + Delta gegen Baseline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jtl2datev.core.config import Settings
from jtl2datev.core.datev import (
    ExportReport,
    load_compare_map,
    write_extf_buchungsstapel,
)
from jtl2datev.core.datev_delta import (
    NoBaselineError,
    compute_delta,
    load_baseline,
    read_extf_csv,
    write_delta_extf,
)
from jtl2datev.core.models import LineDecision
from jtl2datev.core.repositories import InvoiceRepository
from jtl2datev.core.tax_engine import decide

__all__ = [
    "DatevExportRequest",
    "DatevExportResult",
    "DatevDeltaRequest",
    "DatevDeltaResult",
    "NoBaselineError",
    "export_datev",
    "export_datev_delta",
]


@dataclass(frozen=True)
class DatevExportRequest:
    repo: InvoiceRepository
    settings: Settings
    date_from: date
    date_to: date
    out_path: Path
    compare_path: Path | None = None
    audit: bool = False
    keep_zero_amount: bool = False


@dataclass(frozen=True)
class DatevExportResult:
    out_path: Path
    report: ExportReport
    compare_loaded: int  # Anzahl geladener Order-IDs (0 wenn keine compare_path)


@dataclass(frozen=True)
class DatevDeltaRequest:
    repo: InvoiceRepository
    settings: Settings
    date_from: date
    date_to: date
    baseline_path: Path
    full_out_path: Path
    delta_out_path: Path
    compare_path: Path | None = None
    audit: bool = False
    keep_zero_amount: bool = False


@dataclass(frozen=True)
class DatevDeltaResult:
    full_out_path: Path
    delta_out_path: Path
    full_report: ExportReport
    new_keys: list[str]
    changed_keys: list[str]


def _build_decisions_fn(settings: Settings):  # type: ignore[no-untyped-def]
    """Konstruiert die per-Beleg-Entscheidungs-Funktion aus Settings.

    Lebt im Service (nicht im Aufrufer), damit CLI/FastAPI denselben
    Steuerentscheidungs-Pfad verwenden.
    """
    own_vat_countries = settings.own_vat_countries

    def decisions(inv):  # type: ignore[no-untyped-def]
        return [
            LineDecision(line=line, decision=decide(inv, line, own_vat_countries=own_vat_countries))
            for line in inv.lines
        ]

    return decisions


def export_datev(req: DatevExportRequest) -> DatevExportResult:
    """Schreibt DATEV-EXTF-Buchungsstapel-CSV nach req.out_path.

    Atomar via .tmp + os.replace im Writer. Archivierung ist Aufrufer-
    Verantwortung (siehe core.archive.archive_export).
    """
    decisions_fn = _build_decisions_fn(req.settings)
    compare_map = load_compare_map(req.compare_path) if req.compare_path is not None else None
    invoices = req.repo.fetch_invoices(date_from=req.date_from, date_to=req.date_to)
    report = write_extf_buchungsstapel(
        invoices,
        out_path=req.out_path,
        settings=req.settings,
        date_from=req.date_from,
        date_to=req.date_to,
        decisions_by_invoice=decisions_fn,
        compare_map=compare_map,
        audit=req.audit,
        keep_zero_amount=req.keep_zero_amount,
    )
    return DatevExportResult(
        out_path=req.out_path,
        report=report,
        compare_loaded=len(compare_map) if compare_map is not None else 0,
    )


def export_datev_delta(req: DatevDeltaRequest) -> DatevDeltaResult:
    """Erzeugt frischen Vollexport + Delta-CSV gegen Baseline.

    Wirft NoBaselineError wenn baseline_path nicht ladbar ist.
    """
    _, _, baseline_rows = load_baseline(req.baseline_path)

    full_result = export_datev(
        DatevExportRequest(
            repo=req.repo,
            settings=req.settings,
            date_from=req.date_from,
            date_to=req.date_to,
            out_path=req.full_out_path,
            compare_path=req.compare_path,
            audit=req.audit,
            keep_zero_amount=req.keep_zero_amount,
        )
    )

    extf_header, col_header, current_rows = read_extf_csv(req.full_out_path)
    delta_rows, new_keys, changed_keys = compute_delta(
        current_rows=current_rows,
        baseline_rows=baseline_rows,
    )
    write_delta_extf(
        delta_rows,
        out_path=req.delta_out_path,
        extf_header_line=extf_header,
        column_header_line=col_header,
    )
    return DatevDeltaResult(
        full_out_path=req.full_out_path,
        delta_out_path=req.delta_out_path,
        full_report=full_result.report,
        new_keys=list(new_keys),
        changed_keys=list(changed_keys),
    )
