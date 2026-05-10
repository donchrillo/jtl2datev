"""Export-Endpoints: liefern File-Downloads (CSV/XLSX).

Routen sind dünne Wrapper über `core/services/`. Antworten werden direkt
als StreamingResponse aus Bytes geliefert — kein Tempfile, kein BackgroundTask.
"""
from __future__ import annotations

import datetime as dt
from io import BytesIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from jtl2datev.api.auth import verify_jwt
from jtl2datev.api.dependencies import (
    InvoiceRepoDep,
    PeriodDep,
    SettingsDep,
)
from jtl2datev.core.config import Settings
from jtl2datev.core.datev import to_extf_buchungsstapel_bytes
from jtl2datev.core.db_jtl import JtlInvoiceRepository
from jtl2datev.core.dutypay import to_dutypay_csv_bytes
from jtl2datev.core.models import LineDecision
from jtl2datev.core.taxually import to_taxually_xlsx_bytes
from jtl2datev.core.tax_engine import decide

router = APIRouter(prefix="/export", dependencies=[Depends(verify_jwt)])


def _build_decisions_fn(settings: Settings):  # type: ignore[no-untyped-def]
    own_vat_countries = settings.own_vat_countries

    def decisions(inv):  # type: ignore[no-untyped-def]
        return [
            LineDecision(line=line, decision=decide(inv, line, own_vat_countries=own_vat_countries))
            for line in inv.lines
        ]

    return decisions


@router.post("/datev", summary="DATEV-EXTF-Buchungsstapel als CSV")
def datev_export(
    period: tuple[dt.date, dt.date, str] = PeriodDep,
    settings: Settings = SettingsDep,
    repo: JtlInvoiceRepository = InvoiceRepoDep,
    audit: bool = False,
    keep_zero_amount: bool = False,
) -> StreamingResponse:
    """Erzeugt DATEV-EXTF-Buchungsstapel-CSV für den angegebenen Monat."""
    date_from, date_to, period_str = period
    invoices = repo.fetch_invoices(date_from=date_from, date_to=date_to)
    payload, report = to_extf_buchungsstapel_bytes(
        invoices,
        settings=settings,
        date_from=date_from,
        date_to=date_to,
        decisions_by_invoice=_build_decisions_fn(settings),
        audit=audit,
        keep_zero_amount=keep_zero_amount,
    )
    filename = f"datev_{period_str}.csv"
    return StreamingResponse(
        BytesIO(payload),
        media_type="text/csv; charset=cp1252",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Bookings-Written": str(report.bookings_written),
            "X-Skipped-Error": str(report.skipped_error),
            "X-Skipped-Unknown": str(report.skipped_unknown),
            "X-Skipped-Zero-Amount": str(report.skipped_zero_amount),
        },
    )


@router.post("/dutypay", summary="DutyPay-OSS-CSV")
def dutypay_export(
    period: tuple[dt.date, dt.date, str] = PeriodDep,
    settings: Settings = SettingsDep,
    repo: JtlInvoiceRepository = InvoiceRepoDep,
) -> StreamingResponse:
    date_from, date_to, period_str = period
    invoices = repo.fetch_invoices(date_from=date_from, date_to=date_to)
    payload, report = to_dutypay_csv_bytes(invoices, own_vat_ids=settings.own_vat_ids)
    filename = f"dutypay_{period_str}.csv"
    return StreamingResponse(
        BytesIO(payload),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Rows-Written": str(report.rows_written),
            "X-Invoices-Processed": str(report.invoices_processed),
        },
    )


@router.post("/taxually", summary="Taxually-XLSX")
def taxually_export(
    period: tuple[dt.date, dt.date, str] = PeriodDep,
    settings: Settings = SettingsDep,
    repo: JtlInvoiceRepository = InvoiceRepoDep,
) -> StreamingResponse:
    date_from, date_to, period_str = period
    invoices = repo.fetch_invoices(date_from=date_from, date_to=date_to)
    payload, rows_written = to_taxually_xlsx_bytes(invoices)
    filename = f"taxually_{period_str}.xlsx"
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Rows-Written": str(rows_written),
        },
    )
