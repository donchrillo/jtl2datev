"""Report-Endpoints: liefern JSON statt File-Downloads.

reconcile + mixed-vat-check sind primär Reports und passen besser zu JSON
als zu Datei-Downloads. CSV-Export bleibt CLI-Domäne.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from jtl2datev.api.auth import verify_jwt
from jtl2datev.api.dependencies import (
    InvoiceRepoDep,
    PeriodDep,
    SettingsDep,
)
from jtl2datev.core.config import Settings
from jtl2datev.core.db_jtl import JtlInvoiceRepository
from jtl2datev.core.services.mixed_vat_service import (
    MixedVatCheckRequest,
    check_mixed_vat,
)
from jtl2datev.core.services.reconcile_service import (
    ReconcileRequest,
    reconcile,
)

router = APIRouter(dependencies=[Depends(verify_jwt)])


class ReconcileSummary(BaseModel):
    period: str
    invoices_total: int
    lines_total: int
    invoices_with_any_mismatch: int
    treatments: dict[str, int]
    mismatches_by_severity: dict[str, int]
    mismatches_by_source: dict[str, int]


class MixedVatBelegOut(BaseModel):
    source: str
    pk: int
    belegnr: str
    datum: dt.date
    vat_rates: list[str]
    external_order_no: str | None
    position_count: int
    total_brutto: str  # Decimal als String — JSON-Präzision


@router.get("/reconcile", response_model=ReconcileSummary)
def reconcile_report(
    period: tuple[dt.date, dt.date, str] = PeriodDep,
    settings: Settings = SettingsDep,
    repo: JtlInvoiceRepository = InvoiceRepoDep,
    sample_limit: int = 20,
) -> ReconcileSummary:
    date_from, date_to, period_str = period
    result = reconcile(
        ReconcileRequest(
            repo=repo,
            settings=settings,
            date_from=date_from,
            date_to=date_to,
            sample_limit=sample_limit,
        )
    )
    r = result.report
    return ReconcileSummary(
        period=period_str,
        invoices_total=r.invoices_total,
        lines_total=r.lines_total,
        invoices_with_any_mismatch=r.invoices_with_any_mismatch,
        treatments={str(k): v for k, v in r.treatments.items()},
        mismatches_by_severity=dict(r.mismatches_by_severity),
        mismatches_by_source=dict(r.mismatches_by_source),
    )


@router.get("/mixed-vat-check", response_model=list[MixedVatBelegOut])
def mixed_vat_check_report(
    period: tuple[dt.date, dt.date, str] = PeriodDep,
    repo: JtlInvoiceRepository = InvoiceRepoDep,
) -> list[MixedVatBelegOut]:
    date_from, date_to, _ = period
    result = check_mixed_vat(
        MixedVatCheckRequest(
            repo=repo,
            date_from=date_from,
            date_to=date_to,
        )
    )
    return [
        MixedVatBelegOut(
            source=b.source,
            pk=b.pk,
            belegnr=b.belegnr,
            datum=b.datum,
            vat_rates=[str(r) for r in b.vat_rates],
            external_order_no=b.external_order_no,
            position_count=b.position_count,
            total_brutto=str(b.total_brutto),
        )
        for b in result.belege
    ]
