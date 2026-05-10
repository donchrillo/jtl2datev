"""Smoke-Tests für FastAPI-Skeleton.

Tests verifizieren Routing, Period-Validation und Exception-Handler.
Echte DB-Aufrufe werden gemockt — Service-Layer-Logik ist separat getestet.
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest

# httpx + fastapi werden via pip install jtl2datev[api] eingezogen
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from jtl2datev.api.main import app  # noqa: E402

_PREFIX = "/api/v1/jtl-datev"


@pytest.fixture
def client() -> TestClient:
    """TestClient mit gemockter Engine + JWT-Auth overridden — kein echter DB-Connect."""
    from jtl2datev.api.auth import verify_jwt

    app.dependency_overrides[verify_jwt] = lambda: {"sub": "test-user"}
    with patch("jtl2datev.api.main.make_engine", return_value=MagicMock()):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    response = client.get(f"{_PREFIX}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "jtl2datev"


def test_openapi_lists_all_endpoints(client: TestClient) -> None:
    response = client.get(f"{_PREFIX}/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = set(spec["paths"].keys())
    assert f"{_PREFIX}/export/datev" in paths
    assert f"{_PREFIX}/export/dutypay" in paths
    assert f"{_PREFIX}/export/taxually" in paths
    assert f"{_PREFIX}/reconcile" in paths
    assert f"{_PREFIX}/mixed-vat-check" in paths
    assert f"{_PREFIX}/health" in paths


def test_period_validation_rejects_bad_format(client: TestClient) -> None:
    response = client.get(f"{_PREFIX}/reconcile?period=2026-1")
    assert response.status_code == 400
    assert "Period-Format" in response.json()["detail"]


def test_period_validation_rejects_text(client: TestClient) -> None:
    response = client.get(f"{_PREFIX}/reconcile?period=januar")
    assert response.status_code == 400


def test_period_required(client: TestClient) -> None:
    response = client.get(f"{_PREFIX}/reconcile")
    assert response.status_code == 422  # FastAPI validation


def test_mixed_vat_check_returns_list(client: TestClient) -> None:
    """Empty-result-path: Mock-Repo gibt leere Liste zurück."""
    fake_repo = MagicMock()
    fake_repo.find_mixed_vat_belege.return_value = []
    with patch("jtl2datev.api.dependencies.JtlInvoiceRepository", return_value=fake_repo):
        response = client.get(f"{_PREFIX}/mixed-vat-check?period=2026-01")
    assert response.status_code == 200
    assert response.json() == []


def test_mixed_vat_check_serializes_belege(client: TestClient) -> None:
    """Mock-Repo gibt einen Beleg zurück → JSON-Serialisierung prüfen."""
    from decimal import Decimal

    from jtl2datev.core.preflight import MixedVatBeleg

    fake_belege = [
        MixedVatBeleg(
            source="jtl_own",
            pk=12345,
            belegnr="R-DE-2026-001",
            datum=dt.date(2026, 1, 15),
            vat_rates=(Decimal("7"), Decimal("19")),
            external_order_no="404-1234567-8901234",
            position_count=3,
            total_brutto=Decimal("119.99"),
        ),
    ]
    fake_repo = MagicMock()
    fake_repo.find_mixed_vat_belege.return_value = fake_belege
    with patch("jtl2datev.api.dependencies.JtlInvoiceRepository", return_value=fake_repo):
        response = client.get(f"{_PREFIX}/mixed-vat-check?period=2026-01")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["belegnr"] == "R-DE-2026-001"
    assert body[0]["vat_rates"] == ["7", "19"]
    assert body[0]["total_brutto"] == "119.99"
