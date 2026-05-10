"""DutyPay-Export-Service: Vollexport + Delta gegen Baseline."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jtl2datev.core.config import Settings
from jtl2datev.core.dutypay import (
    DUTYPAY_COLUMNS,
    DutyPayReport,
    write_dutypay_csv,
)
from jtl2datev.core.dutypay_delta import (
    NoBaselineError,
    compute_delta,
    load_baseline,
    write_delta_csv,
)
from jtl2datev.core.repositories import InvoiceRepository

__all__ = [
    "DutypayExportRequest",
    "DutypayExportResult",
    "DutypayDeltaRequest",
    "DutypayDeltaResult",
    "NoBaselineError",
    "export_dutypay",
    "export_dutypay_delta",
]


@dataclass(frozen=True)
class DutypayExportRequest:
    repo: InvoiceRepository
    settings: Settings
    date_from: date
    date_to: date
    out_path: Path


@dataclass(frozen=True)
class DutypayExportResult:
    out_path: Path
    report: DutyPayReport


@dataclass(frozen=True)
class DutypayDeltaRequest:
    repo: InvoiceRepository
    settings: Settings
    date_from: date
    date_to: date
    baseline_path: Path
    full_out_path: Path
    delta_out_path: Path
    shift_to_period: tuple[int, int] | None = None  # (year, month)


@dataclass(frozen=True)
class DutypayDeltaResult:
    full_out_path: Path
    delta_out_path: Path
    full_report: DutyPayReport
    new_ids: list[str]
    changed_ids: list[str]


def export_dutypay(req: DutypayExportRequest) -> DutypayExportResult:
    """Schreibt DutyPay-OSS-CSV nach req.out_path."""
    invoices = req.repo.fetch_invoices(date_from=req.date_from, date_to=req.date_to)
    report = write_dutypay_csv(
        invoices,
        out_path=req.out_path,
        own_vat_ids=req.settings.own_vat_ids,
    )
    return DutypayExportResult(out_path=req.out_path, report=report)


def export_dutypay_delta(req: DutypayDeltaRequest) -> DutypayDeltaResult:
    """Erzeugt frischen Vollexport + Delta-CSV gegen Baseline.

    Wirft NoBaselineError wenn baseline_path nicht ladbar ist.
    """
    baseline_rows = load_baseline(req.baseline_path)

    full_result = export_dutypay(
        DutypayExportRequest(
            repo=req.repo,
            settings=req.settings,
            date_from=req.date_from,
            date_to=req.date_to,
            out_path=req.full_out_path,
        )
    )

    with req.full_out_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        current_rows = list(reader)

    delta_rows, new_ids, changed_ids = compute_delta(
        current_rows=current_rows,
        baseline_rows=baseline_rows,
        key_col="DocumentID",
    )
    write_delta_csv(
        delta_rows,
        out_path=req.delta_out_path,
        fieldnames=list(DUTYPAY_COLUMNS),
        shift_to_period=req.shift_to_period,
    )
    return DutypayDeltaResult(
        full_out_path=req.full_out_path,
        delta_out_path=req.delta_out_path,
        full_report=full_result.report,
        new_ids=list(new_ids),
        changed_ids=list(changed_ids),
    )
