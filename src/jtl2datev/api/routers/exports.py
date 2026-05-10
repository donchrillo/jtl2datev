"""Export-Endpoints: liefern File-Downloads (CSV/XLSX).

Routen sind dünne Wrapper über `core/services/`. Tmp-Dateien werden via
BackgroundTask nach Auslieferung gelöscht.
"""
from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse

from jtl2datev.api.dependencies import (
    InvoiceRepoDep,
    PeriodDep,
    SettingsDep,
)
from jtl2datev.core.config import Settings
from jtl2datev.core.db_jtl import JtlInvoiceRepository
from jtl2datev.core.services.datev_service import (
    DatevExportRequest,
    export_datev,
)
from jtl2datev.core.services.dutypay_service import (
    DutypayExportRequest,
    export_dutypay,
)
from jtl2datev.core.services.taxually_service import (
    TaxuallyExportRequest,
    export_taxually,
)

router = APIRouter(prefix="/export", tags=["export"])


def _unlink_later(path: Path) -> None:
    """BackgroundTask-Helper: löscht tmp-Datei nach Response-Auslieferung."""
    path.unlink(missing_ok=True)


@router.post("/datev", summary="DATEV-EXTF-Buchungsstapel als CSV")
def datev_export(
    period: tuple[dt.date, dt.date, str] = PeriodDep,
    settings: Settings = SettingsDep,
    repo: JtlInvoiceRepository = InvoiceRepoDep,
    background: BackgroundTasks = None,  # type: ignore[assignment]
    audit: bool = False,
    keep_zero_amount: bool = False,
) -> FileResponse:
    """Erzeugt DATEV-EXTF-Buchungsstapel-CSV für den angegebenen Monat."""
    date_from, date_to, period_str = period
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        out_path = Path(tmp.name)

    result = export_datev(
        DatevExportRequest(
            repo=repo,
            settings=settings,
            date_from=date_from,
            date_to=date_to,
            out_path=out_path,
            audit=audit,
            keep_zero_amount=keep_zero_amount,
        )
    )

    background.add_task(_unlink_later, out_path)
    return FileResponse(
        path=result.out_path,
        media_type="text/csv",
        filename=f"datev_{period_str}.csv",
        headers={
            "X-Bookings-Written": str(result.report.bookings_written),
            "X-Skipped-Error": str(result.report.skipped_error),
            "X-Skipped-Unknown": str(result.report.skipped_unknown),
            "X-Skipped-Zero-Amount": str(result.report.skipped_zero_amount),
        },
    )


@router.post("/dutypay", summary="DutyPay-OSS-CSV")
def dutypay_export(
    period: tuple[dt.date, dt.date, str] = PeriodDep,
    settings: Settings = SettingsDep,
    repo: JtlInvoiceRepository = InvoiceRepoDep,
    background: BackgroundTasks = None,  # type: ignore[assignment]
) -> FileResponse:
    date_from, date_to, period_str = period
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        out_path = Path(tmp.name)

    result = export_dutypay(
        DutypayExportRequest(
            repo=repo,
            settings=settings,
            date_from=date_from,
            date_to=date_to,
            out_path=out_path,
        )
    )

    background.add_task(_unlink_later, out_path)
    return FileResponse(
        path=result.out_path,
        media_type="text/csv",
        filename=f"dutypay_{period_str}.csv",
        headers={
            "X-Rows-Written": str(result.report.rows_written),
            "X-Invoices-Processed": str(result.report.invoices_processed),
        },
    )


@router.post("/taxually", summary="Taxually-XLSX")
def taxually_export(
    period: tuple[dt.date, dt.date, str] = PeriodDep,
    settings: Settings = SettingsDep,
    repo: JtlInvoiceRepository = InvoiceRepoDep,
    background: BackgroundTasks = None,  # type: ignore[assignment]
) -> FileResponse:
    date_from, date_to, period_str = period
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        out_path = Path(tmp.name)

    result = export_taxually(
        TaxuallyExportRequest(
            repo=repo,
            settings=settings,
            date_from=date_from,
            date_to=date_to,
            out_path=out_path,
        )
    )

    background.add_task(_unlink_later, out_path)
    return FileResponse(
        path=result.out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"taxually_{period_str}.xlsx",
        headers={"X-Rows-Written": str(result.rows_written)},
    )
