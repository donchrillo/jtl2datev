"""Pre-flight checks before DATEV / DutyPay export.

Currently: Mixed-VAT detection — find invoices whose line items carry more than
one distinct VAT rate. The header-level engine derives a single synthetic rate
from Eckdaten; when item-level rates differ, that derived rate is meaningless.
"""
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, NamedTuple

from sqlalchemy import Engine, text

from jtl2datev.core.reference_data import HARD_MIN_INVOICE_DATE as _MIN_DATE

logger = logging.getLogger(__name__)

Source = Literal["jtl_own", "jtl_external", "jtl_credit_note"]


class MixedVatBeleg(NamedTuple):
    source: Source
    pk: int
    belegnr: str
    datum: date
    vat_rates: tuple[Decimal, ...]  # sorted ascending
    external_order_no: str | None
    position_count: int
    total_brutto: Decimal


# ── Own invoices (Rechnung.tRechnung + Rechnung.tRechnungPosition) ────────────
#
# Vater-filter: kKonfigVaterRechnungPos IS NULL AND kStuecklisteRechnungPos = 0
#   kKonfigVaterRechnungPos  — set on Konfigartikel child positions
#   kStuecklisteRechnungPos  — set on Stücklisten child positions (>0 when child)
# Zero-Brutto filter: fVkBruttoGesamt != 0

_SQL_OWN_MIXED = text("""
SELECT
    r.kRechnung                     AS pk,
    r.cRechnungsnr                  AS belegnr,
    r.dErstellt                     AS datum,
    r.cExterneAuftragsnummer        AS external_order_no,
    COUNT(DISTINCT p.fMwSt)         AS distinct_vat_count,
    COUNT(p.kRechnungPosition)      AS position_count,
    SUM(p.fVkBruttoGesamt)          AS total_brutto
FROM Rechnung.tRechnung r
JOIN Rechnung.tRechnungPosition p
    ON p.kRechnung = r.kRechnung
WHERE r.nIstEntwurf = 0
  AND r.nIstProforma = 0
  AND r.dErstellt >= :date_from
  AND r.dErstellt < :date_to_excl
  AND p.kKonfigVaterRechnungPos IS NULL
  AND (p.kStuecklisteRechnungPos IS NULL OR p.kStuecklisteRechnungPos = 0)
  AND p.fVkBruttoGesamt != 0
GROUP BY
    r.kRechnung,
    r.cRechnungsnr,
    r.dErstellt,
    r.cExterneAuftragsnummer
HAVING COUNT(DISTINCT p.fMwSt) > 1
ORDER BY r.dErstellt, r.kRechnung
""")

# Detail query: fetch the actual VAT rates for a set of kRechnung PKs
_SQL_OWN_RATES = text("""
SELECT
    p.kRechnung,
    p.fMwSt
FROM Rechnung.tRechnungPosition p
WHERE p.kRechnung IN :pks
  AND p.kKonfigVaterRechnungPos IS NULL
  AND (p.kStuecklisteRechnungPos IS NULL OR p.kStuecklisteRechnungPos = 0)
  AND p.fVkBruttoGesamt != 0
""")

# ── External belege (Rechnung.tExternerBeleg + tExternerBelegPosition) ────────
#
# Linkage: tExternerBelegPosition.kExternerBelegTransaktion
#          → tExternerBelegTransaktion.kExternerBelegTransaktion
#          → tExternerBelegTransaktion.kExternerBeleg
# Vater-filter: kExternerBelegPositionVater IS NULL

_SQL_EXT_MIXED = text("""
SELECT
    eb.kExternerBeleg               AS pk,
    eb.cBelegnr                     AS belegnr,
    eb.dBelegdatumUtc               AS datum,
    tr.cExterneAuftragsnummer       AS external_order_no,
    COUNT(DISTINCT p.fMwStSatz)     AS distinct_vat_count,
    COUNT(p.kExternerBelegPosition) AS position_count,
    SUM(p.fVkBrutto)                AS total_brutto
FROM Rechnung.tExternerBeleg eb
JOIN Rechnung.tExternerBelegTransaktion tr
    ON tr.kExternerBeleg = eb.kExternerBeleg
JOIN Rechnung.tExternerBelegPosition p
    ON p.kExternerBelegTransaktion = tr.kExternerBelegTransaktion
WHERE eb.dBelegdatumUtc >= :date_from
  AND eb.dBelegdatumUtc < :date_to_excl
  AND eb.nBelegtyp IN (0, 1, 2)
  AND p.kExternerBelegPositionVater IS NULL
  AND p.fVkBrutto != 0
GROUP BY
    eb.kExternerBeleg,
    eb.cBelegnr,
    eb.dBelegdatumUtc,
    tr.cExterneAuftragsnummer
HAVING COUNT(DISTINCT p.fMwStSatz) > 1
ORDER BY eb.dBelegdatumUtc, eb.kExternerBeleg
""")

_SQL_EXT_RATES = text("""
SELECT
    tr.kExternerBeleg,
    p.fMwStSatz
FROM Rechnung.tExternerBelegPosition p
JOIN Rechnung.tExternerBelegTransaktion tr
    ON tr.kExternerBelegTransaktion = p.kExternerBelegTransaktion
WHERE tr.kExternerBeleg IN :pks
  AND p.kExternerBelegPositionVater IS NULL
  AND p.fVkBrutto != 0
""")

# ── Own credit notes (dbo.tgutschrift + dbo.tGutschriftPos) ──────────────────
#
# tGutschriftPos has no explicit Vater column. kGutschriftStueckliste = 0 means
# top-level position; values > 0 indicate a Stückliste child.

_SQL_CN_MIXED = text("""
SELECT
    g.kGutschrift                   AS pk,
    g.cGutschriftNr                 AS belegnr,
    g.dErstellt                     AS datum,
    r.cExterneAuftragsnummer        AS external_order_no,
    COUNT(DISTINCT p.fMwSt)         AS distinct_vat_count,
    COUNT(p.kGutschriftPos)         AS position_count,
    SUM(p.fVkBruttoGesamt)          AS total_brutto
FROM dbo.tgutschrift g
JOIN dbo.tGutschriftPos p
    ON p.tGutschrift_kGutschrift = g.kGutschrift
LEFT JOIN Rechnung.tRechnung r
    ON r.kRechnung = g.kRechnung
WHERE g.dErstellt >= :date_from
  AND g.dErstellt < :date_to_excl
  AND (p.kGutschriftStueckliste IS NULL OR p.kGutschriftStueckliste = 0)
  AND p.fVkBruttoGesamt != 0
GROUP BY
    g.kGutschrift,
    g.cGutschriftNr,
    g.dErstellt,
    r.cExterneAuftragsnummer
HAVING COUNT(DISTINCT p.fMwSt) > 1
ORDER BY g.dErstellt, g.kGutschrift
""")

_SQL_CN_RATES = text("""
SELECT
    p.tGutschrift_kGutschrift       AS kGutschrift,
    p.fMwSt
FROM dbo.tGutschriftPos p
WHERE p.tGutschrift_kGutschrift IN :pks
  AND (p.kGutschriftStueckliste IS NULL OR p.kGutschriftStueckliste = 0)
  AND p.fVkBruttoGesamt != 0
""")


def _to_date(val: object) -> date:
    from datetime import datetime

    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return date.fromisoformat(val[:10])
    raise TypeError(f"Cannot convert {type(val)} to date")


def _decimal(val: object) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def _fetch_rates(
    conn: object,
    sql_rates: object,
    pk_col: str,
    pks: list[int],
) -> dict[int, list[Decimal]]:
    """Return {pk: [distinct fMwSt values]} for the given PKs."""
    if not pks:
        return {}
    from sqlalchemy import bindparam

    stmt = sql_rates.bindparams(bindparam("pks", expanding=True))
    result = conn.execute(stmt, {"pks": pks})  # type: ignore[union-attr]
    rates: dict[int, list[Decimal]] = {}
    for row in result.mappings():
        pk = int(row[pk_col])
        rate = _decimal(row[list(row.keys())[-1]])
        rates.setdefault(pk, []).append(rate)
    return rates


def _query_mixed(
    conn: object,
    sql_mixed: object,
    sql_rates: object,
    date_from: date,
    date_to_excl: date,
    pk_col: str,
    source: Source,
) -> list[MixedVatBeleg]:
    params = {"date_from": date_from, "date_to_excl": date_to_excl}
    result = conn.execute(sql_mixed, params)  # type: ignore[union-attr]
    rows = list(result.mappings())
    if not rows:
        return []

    pks = [int(r["pk"]) for r in rows]
    rates_by_pk = _fetch_rates(conn, sql_rates, pk_col, pks)

    out: list[MixedVatBeleg] = []
    for r in rows:
        pk = int(r["pk"])
        raw_rates = rates_by_pk.get(pk, [])
        distinct = tuple(sorted(set(raw_rates)))
        out.append(
            MixedVatBeleg(
                source=source,
                pk=pk,
                belegnr=str(r["belegnr"] or pk),
                datum=_to_date(r["datum"]),
                vat_rates=distinct,
                external_order_no=r["external_order_no"] or None,
                position_count=int(r["position_count"]),
                total_brutto=_decimal(r["total_brutto"]),
            )
        )
    return out


def find_mixed_vat_belege(
    engine: Engine,
    date_from: date,
    date_to: date,
) -> list[MixedVatBeleg]:
    """Return all invoices/credit-notes with mixed VAT rates on item positions.

    Covers three document types: own invoices, external (Amazon VCS) belege,
    and own credit notes. Only top-level positions are considered; sub-positions
    (Konfigartikel / Stückliste children) are excluded.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to the JTL MSSQL database (read-only).
    date_from / date_to:
        Inclusive date range (both ends included).
    """
    hard_min = max(date_from, _MIN_DATE)
    date_to_excl = date_to + timedelta(days=1)

    results: list[MixedVatBeleg] = []

    with engine.connect() as conn:
        own = _query_mixed(
            conn, _SQL_OWN_MIXED, _SQL_OWN_RATES, hard_min, date_to_excl,
            "kRechnung", "jtl_own"
        )
        logger.info("find_mixed_vat_belege: %d own invoices with mixed VAT", len(own))
        results.extend(own)

        ext = _query_mixed(
            conn, _SQL_EXT_MIXED, _SQL_EXT_RATES, hard_min, date_to_excl,
            "kExternerBeleg", "jtl_external"
        )
        logger.info("find_mixed_vat_belege: %d external belege with mixed VAT", len(ext))
        results.extend(ext)

        cn = _query_mixed(
            conn, _SQL_CN_MIXED, _SQL_CN_RATES, hard_min, date_to_excl,
            "kGutschrift", "jtl_credit_note"
        )
        logger.info("find_mixed_vat_belege: %d credit notes with mixed VAT", len(cn))
        results.extend(cn)

    results.sort(key=lambda b: (b.datum, b.source, b.pk))
    return results
