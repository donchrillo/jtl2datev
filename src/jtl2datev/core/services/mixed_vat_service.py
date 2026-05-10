"""Mixed-VAT-Pre-Flight-Service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from jtl2datev.core.preflight import MixedVatBeleg
from jtl2datev.core.repositories import InvoiceRepository

__all__ = ["MixedVatCheckRequest", "MixedVatCheckResult", "check_mixed_vat"]


@dataclass(frozen=True)
class MixedVatCheckRequest:
    repo: InvoiceRepository
    date_from: date
    date_to: date


@dataclass(frozen=True)
class MixedVatCheckResult:
    belege: list[MixedVatBeleg]


def check_mixed_vat(req: MixedVatCheckRequest) -> MixedVatCheckResult:
    """Listet Belege mit gemischten Steuersätzen auf Item-Positionen.

    Reine Repository-Delegation; Service existiert für Schichten-Konsistenz
    und FastAPI-Wiederverwendung.
    """
    belege = req.repo.find_mixed_vat_belege(date_from=req.date_from, date_to=req.date_to)
    return MixedVatCheckResult(belege=belege)
