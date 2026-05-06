"""Tests for JtlInvoiceRepository and db_jtl helpers.

Integration tests require a live DB (credentials in .env) and are marked
with @pytest.mark.integration. They are skipped automatically when the DB
is not reachable or .env is missing credentials.
"""

import os
from datetime import date
from decimal import Decimal

import pytest

from jtl2datev.core.db_jtl import derive_vat_rate


# ---------------------------------------------------------------------------
# Unit tests for derive_vat_rate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gross, net, expected",
    [
        # Standard DE 19 %
        (Decimal("119"), Decimal("100"), Decimal("19")),
        # Standard AT/FR 20 %
        (Decimal("120"), Decimal("100"), Decimal("20")),
        # DE reduced 7 %
        (Decimal("107"), Decimal("100"), Decimal("7")),
        # IE/PL/PT/SK 23 %
        (Decimal("123"), Decimal("100"), Decimal("23")),
        # B2B Reverse-Charge: gross == net → 0 %
        (Decimal("100"), Decimal("100"), Decimal("0")),
        # Export zero-rated: gross == net
        (Decimal("49.99"), Decimal("49.99"), Decimal("0")),
        # net == 0 edge case
        (Decimal("0"), Decimal("0"), Decimal("0")),
        # Amazon refund: negative amounts stay sign-consistent
        (Decimal("-119"), Decimal("-100"), Decimal("19")),
        # Rounding drift within 0.5 pp — should snap to 19
        (Decimal("119.05"), Decimal("100"), Decimal("19")),
        # "Weird" rate 18.5 % — no known rate within 0.5 pp → raw value returned
        (Decimal("118.5"), Decimal("100"), Decimal("18.50")),
        # CH 8.1 %
        (Decimal("108.10"), Decimal("100"), Decimal("8.1")),
        # HU 27 %
        (Decimal("127"), Decimal("100"), Decimal("27")),
    ],
)
def test_derive_vat_rate(gross: Decimal, net: Decimal, expected: Decimal) -> None:
    assert derive_vat_rate(gross, net) == expected


# ---------------------------------------------------------------------------
# Integration smoke test — hits the real JTL DB
# ---------------------------------------------------------------------------


def _db_available() -> bool:
    """True when .env credentials look populated (non-empty username)."""
    username = os.environ.get("SQL_USERNAME", "").strip()
    return bool(username)


@pytest.mark.integration
def test_fetch_invoices_april_2026_smoke() -> None:
    """Fetch invoices for April 2026 and assert at least one result."""
    if not _db_available():
        pytest.skip("SQL_USERNAME not set — DB not configured")

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine
    from jtl2datev.core.models import RawInvoice

    settings = Settings()
    engine = make_engine(settings)
    repo = JtlInvoiceRepository(engine)

    invoices = list(
        repo.fetch_invoices(date_from=date(2026, 4, 1), date_to=date(2026, 4, 30))
    )

    assert len(invoices) > 0, "Expected at least one invoice for April 2026"

    # Basic structural assertions on the first invoice
    first = invoices[0]
    assert isinstance(first, RawInvoice)
    assert first.source in {"jtl_own", "jtl_external"}
    assert first.invoice_no
    assert first.warehouse_country
    assert len(first.warehouse_country) == 2
    assert len(first.lines) > 0

    own_count = sum(1 for inv in invoices if inv.source == "jtl_own")
    ext_count = sum(1 for inv in invoices if inv.source == "jtl_external")
    cn_count = sum(1 for inv in invoices if inv.source == "jtl_credit_note")
    print(f"\nApril 2026: {own_count} own invoices, {ext_count} external belege, {cn_count} credit notes")


@pytest.mark.integration
def test_fetch_credit_notes_q1_2026_smoke() -> None:
    """Fetch all belege for Q1 2026 and assert credit notes are present."""
    if not _db_available():
        pytest.skip("SQL_USERNAME not set — DB not configured")

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine

    settings = Settings()
    engine = make_engine(settings)
    repo = JtlInvoiceRepository(engine)

    invoices = list(
        repo.fetch_invoices(date_from=date(2026, 1, 1), date_to=date(2026, 3, 31))
    )

    credit_notes = [inv for inv in invoices if inv.source == "jtl_credit_note"]
    assert len(credit_notes) >= 200, (
        f"Expected >= 200 credit notes for Q1 2026, got {len(credit_notes)}"
    )
    assert all(cn.is_credit_note is True for cn in credit_notes)
    assert all(cn.warehouse_country for cn in credit_notes)
    assert all(len(cn.warehouse_country) == 2 for cn in credit_notes)
    assert all(len(cn.lines) > 0 for cn in credit_notes)

    own_count = sum(1 for inv in invoices if inv.source == "jtl_own")
    ext_count = sum(1 for inv in invoices if inv.source == "jtl_external")
    print(
        f"\nQ1 2026: {own_count} own invoices, {ext_count} external belege, "
        f"{len(credit_notes)} credit notes"
    )


@pytest.mark.integration
def test_fetch_invoices_date_floor_enforced() -> None:
    """Asking for dates before 2024-11-01 must yield no results (hard floor)."""
    if not _db_available():
        pytest.skip("SQL_USERNAME not set — DB not configured")

    from jtl2datev.core.config import Settings
    from jtl2datev.core.db_jtl import JtlInvoiceRepository, make_engine

    settings = Settings()
    engine = make_engine(settings)
    repo = JtlInvoiceRepository(engine)

    # Request a range entirely before the hard minimum — should return nothing
    invoices = list(
        repo.fetch_invoices(date_from=date(2020, 1, 1), date_to=date(2020, 1, 31))
    )
    assert invoices == [], "Dates before 2024-11-01 must be blocked by hard floor"
