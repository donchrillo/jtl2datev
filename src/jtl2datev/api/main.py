"""FastAPI-App: Lifespan-Engine + Router + Exception-Handlers.

Skeleton-Status:
- 5 Endpoints (DATEV/DutyPay/Taxually-Export, Reconcile-Report, Mixed-VAT-Check)
- KEINE Auth (TODO: vor Produktiv-Deployment hinzufügen)
- KEIN CORS (Konfiguration kommt mit React-Frontend)
- KEIN Verbringungs-Endpoint (Pure-Service braucht Wechselkurse als Input —
  separates Pydantic-Body-Modell, eigener Sprint)
- KEINE Delta-Endpoints (Baseline-Auflösung ist CLI-Spezifik)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from jtl2datev import __version__
from jtl2datev.api.dependencies import get_settings
from jtl2datev.api.routers import exports, reports
from jtl2datev.core.db_jtl import make_engine
from jtl2datev.core.services.datev_service import NoBaselineError as DatevNoBaseline
from jtl2datev.core.services.dutypay_service import NoBaselineError as DutypayNoBaseline
from jtl2datev.core.services.taxually_service import NoBaselineError as TaxuallyNoBaseline
from jtl2datev.core.services.verbringung_service import MissingExchangeRatesError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Engine app-weit aufbauen + bei Shutdown disposen."""
    settings = get_settings()
    app.state.engine = make_engine(settings)
    logger.info("FastAPI lifespan: engine created (%s)", settings.sql_server)
    try:
        yield
    finally:
        app.state.engine.dispose()
        logger.info("FastAPI lifespan: engine disposed")


app = FastAPI(
    title="jtl2datev API",
    version=__version__,
    description=(
        "HTTP-Schnittstelle zum jtl2datev-Service-Layer. "
        "Demonstriert die Schichten-Trennung: Routes sind dünne Wrapper, "
        "Geschäftslogik lebt in core/services/."
    ),
    lifespan=lifespan,
)

app.include_router(exports.router)
app.include_router(reports.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# ── Exception-Handler: typed Service-Exceptions → HTTP-Responses ─────────────


@app.exception_handler(DatevNoBaseline)
@app.exception_handler(DutypayNoBaseline)
@app.exception_handler(TaxuallyNoBaseline)
async def no_baseline_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "no_baseline", "detail": str(exc)},
    )


@app.exception_handler(MissingExchangeRatesError)
async def missing_rates_handler(
    request: Request, exc: MissingExchangeRatesError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": "missing_exchange_rates",
            "missing_currencies": exc.missing_currencies,
            "detail": str(exc),
        },
    )


def run() -> None:
    """Entry-Point für `jtl2datev-api`."""
    import uvicorn

    uvicorn.run("jtl2datev.api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
