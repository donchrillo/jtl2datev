"""FastAPI-Dependencies: Settings, Engine-Lifecycle, Repository-Konstruktion.

Engine wird app-weit gehalten (single instance mit Connection-Pool) und beim
Shutdown disposed — siehe lifespan in api/main.py. Pro Request wird daraus
ein frisches Repository konstruiert.
"""
from __future__ import annotations

import datetime as dt
import re
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status

from jtl2datev.core.config import Settings
from jtl2datev.core.db_jtl import JtlArticlePricingRepository, JtlInvoiceRepository

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton-Settings (env-based via pydantic-settings)."""
    return Settings()


def get_invoice_repo(request: Request) -> JtlInvoiceRepository:
    """Pro-Request-Repository über die app-weite Engine."""
    engine = request.app.state.engine
    return JtlInvoiceRepository(engine)


def get_pricing_repo(request: Request) -> JtlArticlePricingRepository:
    engine = request.app.state.engine
    return JtlArticlePricingRepository(engine)


def parse_period(period: str) -> tuple[dt.date, dt.date, str]:
    """Validiert Period-Parameter ('YYYY-MM') und gibt (date_from, date_to, period_str) zurück."""
    if not _MONTH_RE.fullmatch(period):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiges Period-Format: {period!r}. Erwartet YYYY-MM.",
        )
    year, month = int(period[:4]), int(period[5:7])
    date_from = dt.date(year, month, 1)
    if month == 12:
        next_month_first = dt.date(year + 1, 1, 1)
    else:
        next_month_first = dt.date(year, month + 1, 1)
    date_to = next_month_first - dt.timedelta(days=1)
    return date_from, date_to, period


SettingsDep = Depends(get_settings)
InvoiceRepoDep = Depends(get_invoice_repo)
PricingRepoDep = Depends(get_pricing_repo)
PeriodDep = Depends(parse_period)
