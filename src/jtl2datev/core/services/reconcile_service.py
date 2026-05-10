"""Reconcile-Service: Vergleich JTL-Steuerdaten ↔ eigene Engine."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from jtl2datev.core.config import Settings
from jtl2datev.core.pipeline import ReconcileReport, run_reconcile
from jtl2datev.core.repositories import InvoiceRepository

__all__ = ["ReconcileRequest", "ReconcileResult", "reconcile"]


@dataclass(frozen=True)
class ReconcileRequest:
    repo: InvoiceRepository
    settings: Settings
    date_from: date
    date_to: date
    sample_limit: int = 20


@dataclass(frozen=True)
class ReconcileResult:
    report: ReconcileReport


def reconcile(req: ReconcileRequest) -> ReconcileResult:
    """Vergleicht JTL-Header-Steuerdaten mit Engine-Entscheidungen."""
    invoices = req.repo.fetch_invoices(date_from=req.date_from, date_to=req.date_to)
    report = run_reconcile(
        invoices,
        own_vat_countries=req.settings.own_vat_countries,
        sample_limit=req.sample_limit,
    )
    return ReconcileResult(report=report)
