"""Tests for core/preflight.py and the mixed-vat-check CLI command."""
from datetime import date
from decimal import Decimal

from click.testing import CliRunner
from sqlalchemy import create_engine, text

from jtl2datev.cli import main
from jtl2datev.core.preflight import MixedVatBeleg, find_mixed_vat_belege


# ── CLI smoke-test ────────────────────────────────────────────────────────────


def test_mixed_vat_check_help() -> None:
    result = CliRunner().invoke(main, ["mixed-vat-check", "--help"])
    assert result.exit_code == 0
    assert "Pre-Flight" in result.output
    assert "--from" in result.output
    assert "--to" in result.output
    assert "--out" in result.output


# ── Unit tests with in-memory SQLite ─────────────────────────────────────────
#
# SQLite schema mirrors only the columns used by the three _SQL_*_MIXED queries.
# MSSQL-specific syntax (TOP, schemas) is not used in the queries we test here
# because we re-define the SQL via text() to match SQLite's dialect-free subset.
# Instead, we test find_mixed_vat_belege via a thin integration path by monkeypatching
# the module-level SQL constants.


def _make_sqlite_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        # own invoices
        conn.execute(text("""
            CREATE TABLE tRechnung (
                kRechnung INTEGER PRIMARY KEY,
                cRechnungsnr TEXT,
                dErstellt TEXT,
                cExterneAuftragsnummer TEXT,
                nIstEntwurf INTEGER DEFAULT 0,
                nIstProforma INTEGER DEFAULT 0
            )
        """))
        conn.execute(text("""
            CREATE TABLE tRechnungPosition (
                kRechnungPosition INTEGER PRIMARY KEY,
                kRechnung INTEGER,
                fMwSt REAL,
                fVkBruttoGesamt REAL,
                kKonfigVaterRechnungPos INTEGER,
                kStuecklisteRechnungPos INTEGER
            )
        """))
        # external belege
        conn.execute(text("""
            CREATE TABLE tExternerBeleg (
                kExternerBeleg INTEGER PRIMARY KEY,
                cBelegnr TEXT,
                dBelegdatumUtc TEXT,
                nBelegtyp INTEGER DEFAULT 0
            )
        """))
        conn.execute(text("""
            CREATE TABLE tExternerBelegTransaktion (
                kExternerBelegTransaktion INTEGER PRIMARY KEY,
                kExternerBeleg INTEGER,
                cExterneAuftragsnummer TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE tExternerBelegPosition (
                kExternerBelegPosition INTEGER PRIMARY KEY,
                kExternerBelegTransaktion INTEGER,
                kExternerBelegPositionVater INTEGER,
                fMwStSatz REAL,
                fVkBrutto REAL
            )
        """))
        # credit notes
        conn.execute(text("""
            CREATE TABLE tgutschrift (
                kGutschrift INTEGER PRIMARY KEY,
                cGutschriftNr TEXT,
                dErstellt TEXT,
                kRechnung INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE tGutschriftPos (
                kGutschriftPos INTEGER PRIMARY KEY,
                tGutschrift_kGutschrift INTEGER,
                fMwSt REAL,
                fVkBruttoGesamt REAL,
                kGutschriftStueckliste INTEGER DEFAULT 0
            )
        """))
    return engine


def _seed_mixed_own(engine):
    """Invoice 1 has two rates (7 & 19); invoice 2 has one rate (19) — should not appear."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO tRechnung VALUES (1, 'RE-0001', '2026-02-15', 'ORDER-1', 0, 0)"
        ))
        conn.execute(text(
            "INSERT INTO tRechnung VALUES (2, 'RE-0002', '2026-02-16', 'ORDER-2', 0, 0)"
        ))
        # Invoice 1: two positions with different rates
        conn.execute(text(
            "INSERT INTO tRechnungPosition VALUES (10, 1, 19.0, 11.90, NULL, 0)"
        ))
        conn.execute(text(
            "INSERT INTO tRechnungPosition VALUES (11, 1, 7.0, 5.35, NULL, 0)"
        ))
        # Invoice 2: single rate
        conn.execute(text(
            "INSERT INTO tRechnungPosition VALUES (20, 2, 19.0, 23.80, NULL, 0)"
        ))


def test_find_mixed_vat_own_invoices(monkeypatch) -> None:
    """find_mixed_vat_belege returns invoice with mixed VAT from own-invoice table."""
    import jtl2datev.core.preflight as pf

    engine = _make_sqlite_engine()
    _seed_mixed_own(engine)

    # Patch SQL to SQLite-compatible variants (no schemas, no HAVING workaround needed)
    monkeypatch.setattr(pf, "_SQL_OWN_MIXED", text("""
        SELECT
            r.kRechnung AS pk,
            r.cRechnungsnr AS belegnr,
            r.dErstellt AS datum,
            r.cExterneAuftragsnummer AS external_order_no,
            COUNT(DISTINCT p.fMwSt) AS distinct_vat_count,
            COUNT(p.kRechnungPosition) AS position_count,
            SUM(p.fVkBruttoGesamt) AS total_brutto
        FROM tRechnung r
        JOIN tRechnungPosition p ON p.kRechnung = r.kRechnung
        WHERE r.nIstEntwurf = 0
          AND r.nIstProforma = 0
          AND r.dErstellt >= :date_from
          AND r.dErstellt < :date_to_excl
          AND p.kKonfigVaterRechnungPos IS NULL
          AND (p.kStuecklisteRechnungPos IS NULL OR p.kStuecklisteRechnungPos = 0)
          AND p.fVkBruttoGesamt != 0
        GROUP BY r.kRechnung, r.cRechnungsnr, r.dErstellt, r.cExterneAuftragsnummer
        HAVING COUNT(DISTINCT p.fMwSt) > 1
        ORDER BY r.dErstellt, r.kRechnung
    """))
    monkeypatch.setattr(pf, "_SQL_OWN_RATES", text("""
        SELECT p.kRechnung, p.fMwSt
        FROM tRechnungPosition p
        WHERE p.kRechnung IN :pks
          AND p.kKonfigVaterRechnungPos IS NULL
          AND (p.kStuecklisteRechnungPos IS NULL OR p.kStuecklisteRechnungPos = 0)
          AND p.fVkBruttoGesamt != 0
    """))
    # Empty stubs for external + credit-note (no data seeded)
    monkeypatch.setattr(pf, "_SQL_EXT_MIXED", text(
        "SELECT NULL AS pk, NULL AS belegnr, NULL AS datum, NULL AS external_order_no,"
        " 0 AS distinct_vat_count, 0 AS position_count, 0 AS total_brutto"
        " WHERE 1=0"
    ))
    monkeypatch.setattr(pf, "_SQL_CN_MIXED", text(
        "SELECT NULL AS pk, NULL AS belegnr, NULL AS datum, NULL AS external_order_no,"
        " 0 AS distinct_vat_count, 0 AS position_count, 0 AS total_brutto"
        " WHERE 1=0"
    ))

    results = find_mixed_vat_belege(engine, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))

    assert len(results) == 1
    b = results[0]
    assert b.source == "jtl_own"
    assert b.pk == 1
    assert b.belegnr == "RE-0001"
    assert Decimal("7") in b.vat_rates
    assert Decimal("19") in b.vat_rates
    assert b.position_count == 2
    assert b.total_brutto == Decimal("17.25")  # 11.90 + 5.35


def test_find_mixed_vat_no_results(monkeypatch) -> None:
    """Returns empty list when no mixed-VAT invoices exist."""
    import jtl2datev.core.preflight as pf

    engine = _make_sqlite_engine()
    _seed_mixed_own(engine)

    empty_stub = text(
        "SELECT NULL AS pk, NULL AS belegnr, NULL AS datum, NULL AS external_order_no,"
        " 0 AS distinct_vat_count, 0 AS position_count, 0 AS total_brutto"
        " WHERE 1=0"
    )
    monkeypatch.setattr(pf, "_SQL_OWN_MIXED", empty_stub)
    monkeypatch.setattr(pf, "_SQL_EXT_MIXED", empty_stub)
    monkeypatch.setattr(pf, "_SQL_CN_MIXED", empty_stub)

    results = find_mixed_vat_belege(engine, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))
    assert results == []


def test_mixed_vat_beleg_is_namedtuple() -> None:
    b = MixedVatBeleg(
        source="jtl_external",
        pk=99,
        belegnr="EXT-001",
        datum=date(2026, 3, 1),
        vat_rates=(Decimal("0"), Decimal("22")),
        external_order_no="406-123456",
        position_count=3,
        total_brutto=Decimal("47.83"),
    )
    assert b.source == "jtl_external"
    assert b.vat_rates[0] == Decimal("0")
    assert b.total_brutto == Decimal("47.83")
