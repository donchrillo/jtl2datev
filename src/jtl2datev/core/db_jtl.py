import itertools
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterator

from sqlalchemy import Engine, text

from jtl2datev.core.config import Settings
from jtl2datev.core.models import PartyAddress, RawInvoice, RawInvoiceLine
from jtl2datev.core.repositories import InvoiceRepository

logger = logging.getLogger(__name__)

_MIN_DATE = date(2024, 11, 1)

_SQL_OWN = text("""
SELECT
    -- Header (Rechnung.tRechnung)
    r.kRechnung,
    r.cRechnungsnr            AS invoice_no,
    r.dErstellt               AS invoice_date,
    r.dLeistungsdatum         AS service_date,
    r.cWaehrung               AS currency,
    r.fWaehrungsfaktor        AS currency_factor,
    r.cVersandlandISO         AS warehouse_country,
    r.kKunde,
    r.cKundennr               AS customer_no,
    r.cKundeUstId             AS customer_vat_id,
    r.kPlattform              AS platform_id,
    r.cExterneAuftragsnummer  AS external_order_no,
    r.cZahlungsart            AS payment_method,
    r.kShop,
    -- cErloeskonto from dbo.tRechnung (complementary stub table)
    dr.cErloeskonto           AS revenue_account,
    -- Totals
    eck.fVkBruttoGesamt       AS total_gross,
    eck.fVkNettoGesamt        AS total_net,
    eck.cAuftragsnummern      AS jtl_internal_order_no,
    -- Platform name
    p.cName                   AS platform_name,
    -- Delivery address (nTyp=0)
    ship.cISO                 AS ship_country,
    ship.cBundesland          AS ship_region,
    ship.cVorname             AS ship_first_name,
    ship.cName                AS ship_last_name,
    ship.cFirma               AS ship_company,
    -- Billing address (nTyp=1)
    bill.cISO                 AS bill_country,
    bill.cBundesland          AS bill_region,
    bill.cVorname             AS bill_first_name,
    bill.cName                AS bill_last_name,
    bill.cFirma               AS bill_company,
    -- Position fields
    pos.kRechnungPosition     AS pos_key,
    pos.nSort                 AS line_no,
    pos.cArtNr                AS sku,
    pos.cName                 AS description,
    pos.fAnzahl               AS quantity,
    pos.fVkNettoGesamt        AS net,
    pos.fVkBruttoGesamt       AS gross,
    pos.fMwSt                 AS vat_rate,
    pos.nType                 AS position_type,
    pos.kSteuerschluessel     AS jtl_tax_key_id,
    poseck.fMwStBetrag        AS vat_amount
FROM Rechnung.tRechnung r
LEFT JOIN dbo.tRechnung dr
    ON dr.kRechnung = r.kRechnung
LEFT JOIN Rechnung.tRechnungEckdaten eck
    ON eck.kRechnung = r.kRechnung
LEFT JOIN dbo.tPlattform p
    ON p.nPlattform = r.kPlattform
LEFT JOIN Rechnung.tRechnungAdresse ship
    ON ship.kRechnung = r.kRechnung AND ship.nTyp = 0
LEFT JOIN Rechnung.tRechnungAdresse bill
    ON bill.kRechnung = r.kRechnung AND bill.nTyp = 1
JOIN Rechnung.tRechnungPosition pos
    ON pos.kRechnung = r.kRechnung
LEFT JOIN Rechnung.tRechnungPositionEckdaten poseck
    ON poseck.kRechnungPosition = pos.kRechnungPosition
WHERE r.nIstEntwurf = 0
  AND r.nIstProforma = 0
  -- nStorno=1 stays in: a stornierte Rechnung implies a counter-credit-note
  -- exists/must exist, and we need both halves for an auditable export.
  AND r.dErstellt >= :hard_min
  AND r.dErstellt >= :date_from
  AND r.dErstellt < :date_to_excl
  -- Skip Temu belege. Temu was tested in late 2025 then rolled back; the
  -- imported orders carry external order IDs starting with "PO-…". They are
  -- intentionally out of scope (a separate Temu reports importer handles them).
  AND (r.cExterneAuftragsnummer IS NULL OR r.cExterneAuftragsnummer NOT LIKE 'PO%')
  -- Bundle/configurator children carry no price/VAT — skip; the master line
  -- carries the totals. Master rows self-reference via kStuecklisteRechnungPos
  -- = kRechnungPosition; only true children (different value) must be filtered.
  AND (pos.kKonfigVaterRechnungPos IS NULL
       OR pos.kKonfigVaterRechnungPos = pos.kRechnungPosition)
  AND (pos.kStuecklisteRechnungPos IS NULL
       OR pos.kStuecklisteRechnungPos = pos.kRechnungPosition)
ORDER BY r.kRechnung, pos.nSort
""")

_SQL_EXTERNAL = text("""
SELECT
    -- Header
    eb.kExternerBeleg,
    eb.cBelegnr               AS invoice_no,
    eb.dBelegdatumUtc         AS invoice_date,
    eb.nBelegtyp              AS beleg_typ,
    eb.cWaehrungISO           AS currency,
    eb.fWaehrungsfaktor       AS currency_factor,
    eb.kPlattform             AS platform_id,
    eb.nDebitorenNr           AS debitor_nr,
    eb.cKaeuferUstId          AS customer_vat_id,
    -- Totals
    eck.fVkBrutto             AS total_gross,
    eck.fVkNetto              AS total_net,
    -- Platform name
    p.cName                   AS platform_name,
    -- Billing address (directly on header)
    eb.cRALandISO             AS bill_country,
    eb.cRAStaat               AS bill_region,
    eb.cRAName                AS bill_full_name,
    -- Delivery + warehouse from Transaktion
    tr.cLALandISO             AS ship_country,
    tr.cLAStaat               AS ship_region,
    tr.cLAName                AS ship_full_name,
    tr.cVALandISO             AS warehouse_country,
    tr.cExterneAuftragsnummer AS external_order_no,
    tr.kExternerBelegTransaktion AS transakt_key,
    -- Position fields
    ebp.kExternerBelegPosition AS pos_key,
    ebp.cArtNr                AS sku,
    ebp.cText                 AS description,
    ebp.fAnzahl               AS quantity,
    ebp.fVkNetto              AS net,
    ebp.fVkBrutto             AS gross,
    ebp.fMwStSatz             AS vat_rate,
    ebp.nPositionstyp         AS position_type,
    ebp.kSteuerschluessel     AS jtl_tax_key_id
FROM Rechnung.tExternerBeleg eb
LEFT JOIN Rechnung.tExternerBelegEckdaten eck
    ON eck.kExternerBeleg = eb.kExternerBeleg
LEFT JOIN dbo.tPlattform p
    ON p.nPlattform = eb.kPlattform
LEFT JOIN Rechnung.tExternerBelegTransaktion tr
    ON tr.kExternerBeleg = eb.kExternerBeleg
JOIN Rechnung.tExternerBelegPosition ebp
    ON ebp.kExternerBelegTransaktion = tr.kExternerBelegTransaktion
WHERE eb.dBelegdatumUtc >= :hard_min
  AND eb.dBelegdatumUtc >= :date_from
  AND eb.dBelegdatumUtc < :date_to_excl
  AND eb.nBelegtyp IN (0, 1, 2)
  -- Note: nIstStorniert=1 invoices stay in the export. JTL flags an invoice
  -- as storniert when a counter-credit-note (nBelegtyp=1 with cBezugsbelegnr
  -- = the original Belegnr) was issued; both bookings must hit the export
  -- so the audit trail is complete and the net effect is zero.
  -- Bundle children carry no price/VAT.
  AND ebp.kExternerBelegPositionVater IS NULL
ORDER BY eb.kExternerBeleg, ebp.kExternerBelegPosition
""")


_SQL_CREDIT_NOTES = text("""
SELECT
    -- Header (dbo.tgutschrift)
    g.kGutschrift,
    g.cGutschriftNr            AS invoice_no,
    g.dErstellt                AS invoice_date,
    g.cWaehrung                AS currency,
    g.fFaktor                  AS currency_factor,
    g.kKunde,
    g.cKundeUstId              AS customer_vat_id,
    g.kPlattform               AS platform_id,
    g.cErloeskonto             AS revenue_account,
    -- Lagerland + externe Auftragsnr + Zahlungsart aus Original-Rechnung
    r.cVersandlandISO          AS warehouse_country,
    r.cExterneAuftragsnummer   AS external_order_no,
    r.cZahlungsart             AS payment_method,
    eck.cAuftragsnummern       AS jtl_internal_order_no,
    -- Platform name
    p.cName                    AS platform_name,
    -- Delivery address (nTyp=0) from tRechnungAdresse
    ship.cISO                  AS ship_country,
    ship.cBundesland           AS ship_region,
    ship.cVorname              AS ship_first_name,
    ship.cName                 AS ship_last_name,
    ship.cFirma                AS ship_company,
    -- Billing address (nTyp=1) from tRechnungAdresse
    bill.cISO                  AS bill_country,
    bill.cBundesland           AS bill_region,
    bill.cVorname              AS bill_first_name,
    bill.cName                 AS bill_last_name,
    bill.cFirma                AS bill_company,
    -- Position fields (dbo.tGutschriftPos)
    pos.kGutschriftPos         AS pos_key,
    pos.nSort                  AS line_no,
    pos.cArtNr                 AS sku,
    pos.cString                AS description,
    pos.nAnzahl                AS quantity,
    pos.fVkNettoGesamt         AS net,
    pos.fVkBruttoGesamt        AS gross,
    pos.fMwSt                  AS vat_rate
FROM dbo.tgutschrift g
LEFT JOIN Rechnung.tRechnung r
    ON r.kRechnung = g.kRechnung
LEFT JOIN Rechnung.tRechnungEckdaten eck
    ON eck.kRechnung = g.kRechnung
LEFT JOIN dbo.tPlattform p
    ON p.nPlattform = g.kPlattform
LEFT JOIN Rechnung.tRechnungAdresse ship
    ON ship.kRechnung = g.kRechnung AND ship.nTyp = 0
LEFT JOIN Rechnung.tRechnungAdresse bill
    ON bill.kRechnung = g.kRechnung AND bill.nTyp = 1
JOIN dbo.tGutschriftPos pos
    ON pos.tGutschrift_kGutschrift = g.kGutschrift
WHERE g.kRechnung IS NOT NULL
  -- nStorno=1 stays in (audit-trail completeness — see _fetch_own).
  AND g.dErstellt >= :hard_min
  AND g.dErstellt >= :date_from
  AND g.dErstellt <  :date_to_excl
  -- Skip Temu credit notes (rolled-back Dec-2025 test): the original invoice
  -- carries an "PO-…" external order number.
  AND (r.cExterneAuftragsnummer IS NULL OR r.cExterneAuftragsnummer NOT LIKE 'PO%')
  -- Bundle children carry no price/VAT. Master rows self-reference via
  -- kGutschriftStueckliste = kGutschriftPos; only true children (different
  -- non-zero value) must be filtered out.
  AND (pos.kGutschriftStueckliste = 0
       OR pos.kGutschriftStueckliste = pos.kGutschriftPos)
ORDER BY g.kGutschrift, pos.nSort
""")


def _to_date(val: object) -> date:
    # datetime is a subclass of date, so check it first
    from datetime import datetime

    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    raise TypeError(f"Cannot convert {type(val)} to date")


def _decimal(val: object) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


class JtlInvoiceRepository(InvoiceRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def fetch_invoices(self, *, date_from: date, date_to: date) -> Iterator[RawInvoice]:
        yield from self._fetch_own(date_from=date_from, date_to=date_to)
        yield from self._fetch_external(date_from=date_from, date_to=date_to)
        yield from self._fetch_credit_notes(date_from=date_from, date_to=date_to)

    def _fetch_own(self, *, date_from: date, date_to: date) -> Iterator[RawInvoice]:
        hard_min = max(date_from, _MIN_DATE)
        date_to_excl = date_to + timedelta(days=1)

        params = {
            "hard_min": _MIN_DATE,
            "date_from": hard_min,
            "date_to_excl": date_to_excl,
        }

        skipped_null_warehouse = 0
        yielded = 0

        with self._engine.connect() as conn:
            conn = conn.execution_options(stream_results=True)
            result = conn.execute(_SQL_OWN, params)
            rows = result.mappings()

            for inv_key, group in itertools.groupby(rows, key=lambda r: r["kRechnung"]):
                group_rows = list(group)
                first = group_rows[0]

                warehouse = first["warehouse_country"]
                if not warehouse:
                    logger.warning(
                        "tRechnung kRechnung=%s has NULL cVersandlandISO — skipping",
                        inv_key,
                    )
                    skipped_null_warehouse += 1
                    continue

                ship_country = first["ship_country"] or ""
                bill_country = first["bill_country"] or ""

                ship_to = PartyAddress(
                    country_iso=ship_country,
                    region=first["ship_region"],
                    first_name=first["ship_first_name"] or None,
                    last_name=first["ship_last_name"] or None,
                    company=first["ship_company"] or None,
                )
                bill_to = PartyAddress(
                    country_iso=bill_country,
                    region=first["bill_region"],
                    vat_id=first["customer_vat_id"] or None,
                    first_name=first["bill_first_name"] or None,
                    last_name=first["bill_last_name"] or None,
                    company=first["bill_company"] or None,
                )

                lines: list[RawInvoiceLine] = []
                for i, row in enumerate(group_rows):
                    lines.append(
                        RawInvoiceLine(
                            line_no=row["line_no"] if row["line_no"] is not None else i,
                            sku=row["sku"] or None,
                            description=row["description"] or None,
                            quantity=_decimal(row["quantity"]),
                            net=_decimal(row["net"]),
                            gross=_decimal(row["gross"]),
                            vat_rate=_decimal(row["vat_rate"]),
                            vat_amount=_decimal(row["vat_amount"]),
                            position_type=row["position_type"],
                            jtl_tax_key_id=row["jtl_tax_key_id"],
                        )
                    )

                inv_date_raw = first["invoice_date"]
                svc_date_raw = first["service_date"]

                # TODO: add credit note support when tRechnungKorrektur is in scope
                yield RawInvoice(
                    source="jtl_own",
                    invoice_no=first["invoice_no"] or str(inv_key),
                    invoice_date=_to_date(inv_date_raw),
                    service_date=_to_date(svc_date_raw) if svc_date_raw else None,
                    currency=first["currency"] or "EUR",
                    currency_factor=_decimal(first["currency_factor"]) or Decimal("1"),
                    warehouse_country=warehouse.strip(),
                    ship_to=ship_to,
                    bill_to=bill_to,
                    customer_no=first["customer_no"] or None,
                    platform_id=first["platform_id"],
                    platform_name=first["platform_name"] or None,
                    is_credit_note=False,
                    lines=tuple(lines),
                    jtl_revenue_account=first["revenue_account"] or None,
                    # Fallback: when no marketplace order ID exists (rare manual JTL
                    # invoice), use the internal Wawi order number from
                    # tRechnungEckdaten.cAuftragsnummern (a comma list — first entry).
                    jtl_external_order_no=(
                        first["external_order_no"]
                        or (first["jtl_internal_order_no"] or "").split(",", 1)[0].strip()
                        or None
                    ),
                    payment_method=first["payment_method"] or None,
                )
                yielded += 1

        if skipped_null_warehouse:
            logger.warning(
                "_fetch_own: skipped %d invoices with NULL warehouse_country",
                skipped_null_warehouse,
            )
        logger.info("_fetch_own: fetched %d own invoices", yielded)

    def _fetch_external(self, *, date_from: date, date_to: date) -> Iterator[RawInvoice]:
        hard_min = max(date_from, _MIN_DATE)
        date_to_excl = date_to + timedelta(days=1)

        params = {
            "hard_min": _MIN_DATE,
            "date_from": hard_min,
            "date_to_excl": date_to_excl,
        }

        skipped_null_warehouse = 0
        yielded = 0

        with self._engine.connect() as conn:
            conn = conn.execution_options(stream_results=True)
            result = conn.execute(_SQL_EXTERNAL, params)
            rows = result.mappings()

            for beleg_key, group in itertools.groupby(rows, key=lambda r: r["kExternerBeleg"]):
                group_rows = list(group)
                first = group_rows[0]

                beleg_typ = first["beleg_typ"]
                # nBelegtyp: 0=Rechnung (B2C), 1=Gutschrift, 2=Restposten-Aufkäufer-Rechnung (B2B)
                # 0 und 2 sind reguläre Rechnungen; B2B-Behandlung folgt aus cKaeuferUstId+Land-Differenz.
                warehouse = first["warehouse_country"]
                if not warehouse or not warehouse.strip():
                    logger.warning(
                        "tExternerBeleg kExternerBeleg=%s has NULL cVALandISO — skipping",
                        beleg_key,
                    )
                    skipped_null_warehouse += 1
                    continue

                ship_country = first["ship_country"] or ""
                bill_country = first["bill_country"] or ""

                ship_to = PartyAddress(
                    country_iso=ship_country.strip(),
                    region=first["ship_region"] or None,
                    last_name=first["ship_full_name"] or None,
                )
                bill_to = PartyAddress(
                    country_iso=bill_country.strip(),
                    region=first["bill_region"] or None,
                    vat_id=first["customer_vat_id"] or None,
                    last_name=first["bill_full_name"] or None,
                )

                lines: list[RawInvoiceLine] = []
                for i, row in enumerate(group_rows):
                    net = _decimal(row["net"])
                    gross = _decimal(row["gross"])
                    # vat_amount not stored directly — derive from gross - net
                    vat_amount = gross - net
                    lines.append(
                        RawInvoiceLine(
                            line_no=i,
                            sku=row["sku"] or None,
                            description=row["description"] or None,
                            quantity=_decimal(row["quantity"]),
                            net=net,
                            gross=gross,
                            vat_rate=_decimal(row["vat_rate"]),
                            vat_amount=vat_amount,
                            position_type=row["position_type"],
                            jtl_tax_key_id=row["jtl_tax_key_id"],
                        )
                    )

                debitor_nr = first["debitor_nr"]
                customer_no = str(debitor_nr) if debitor_nr else None

                yield RawInvoice(
                    source="jtl_external",
                    invoice_no=first["invoice_no"] or str(beleg_key),
                    invoice_date=_to_date(first["invoice_date"]),
                    service_date=None,
                    currency=(first["currency"] or "EUR").strip(),
                    currency_factor=_decimal(first["currency_factor"]) or Decimal("1"),
                    warehouse_country=warehouse.strip(),
                    ship_to=ship_to,
                    bill_to=bill_to,
                    customer_no=customer_no,
                    platform_id=first["platform_id"],
                    platform_name=first["platform_name"] or None,
                    # nBelegtyp 1 = Gutschrift (amounts already negative in DB); 0/2 = Rechnung
                    is_credit_note=(beleg_typ == 1),
                    lines=tuple(lines),
                    jtl_revenue_account=None,
                    jtl_external_order_no=first["external_order_no"] or None,
                    # External belege are VCS (Amazon) — no cZahlungsart column; fix to Amazon
                    payment_method="AmazonPayments",
                )
                yielded += 1

        if skipped_null_warehouse:
            logger.warning(
                "_fetch_external: skipped %d belege with NULL warehouse_country",
                skipped_null_warehouse,
            )
        logger.info("_fetch_external: fetched %d external belege", yielded)

    def _fetch_credit_notes(self, *, date_from: date, date_to: date) -> Iterator[RawInvoice]:
        hard_min = max(date_from, _MIN_DATE)
        date_to_excl = date_to + timedelta(days=1)

        params = {
            "hard_min": _MIN_DATE,
            "date_from": hard_min,
            "date_to_excl": date_to_excl,
        }

        skipped_null_warehouse_cn = 0
        yielded = 0

        with self._engine.connect() as conn:
            conn = conn.execution_options(stream_results=True)
            result = conn.execute(_SQL_CREDIT_NOTES, params)
            rows = result.mappings()

            for gutschrift_key, group in itertools.groupby(rows, key=lambda r: r["kGutschrift"]):
                group_rows = list(group)
                first = group_rows[0]

                warehouse = first["warehouse_country"]
                if not warehouse or not warehouse.strip():
                    logger.warning(
                        "tgutschrift kGutschrift=%s has NULL cVersandlandISO — skipping",
                        gutschrift_key,
                    )
                    skipped_null_warehouse_cn += 1
                    continue

                ship_country = first["ship_country"] or ""
                bill_country = first["bill_country"] or ""

                ship_to = PartyAddress(
                    country_iso=ship_country.strip(),
                    region=first["ship_region"] or None,
                    first_name=first["ship_first_name"] or None,
                    last_name=first["ship_last_name"] or None,
                    company=first["ship_company"] or None,
                )
                bill_to = PartyAddress(
                    country_iso=bill_country.strip(),
                    region=first["bill_region"] or None,
                    vat_id=first["customer_vat_id"] or None,
                    first_name=first["bill_first_name"] or None,
                    last_name=first["bill_last_name"] or None,
                    company=first["bill_company"] or None,
                )

                lines: list[RawInvoiceLine] = []
                for i, row in enumerate(group_rows):
                    net = _decimal(row["net"])
                    gross = _decimal(row["gross"])
                    vat_amount = gross - net
                    lines.append(
                        RawInvoiceLine(
                            line_no=row["line_no"] if row["line_no"] is not None else i,
                            sku=row["sku"] or None,
                            description=row["description"] or None,
                            quantity=_decimal(row["quantity"]),
                            net=net,
                            gross=gross,
                            vat_rate=_decimal(row["vat_rate"]),
                            vat_amount=vat_amount,
                        )
                    )

                raw_currency = first["currency"] or "EUR"
                currency = raw_currency.strip()[:3]

                kunde = first["kKunde"]
                customer_no = str(kunde) if kunde else None

                yield RawInvoice(
                    source="jtl_credit_note",
                    invoice_no=first["invoice_no"] or str(gutschrift_key),
                    invoice_date=_to_date(first["invoice_date"]),
                    service_date=None,
                    currency=currency,
                    currency_factor=_decimal(first["currency_factor"]) or Decimal("1"),
                    warehouse_country=warehouse.strip(),
                    ship_to=ship_to,
                    bill_to=bill_to,
                    customer_no=customer_no,
                    platform_id=first["platform_id"],
                    platform_name=first["platform_name"] or None,
                    is_credit_note=True,
                    lines=tuple(lines),
                    jtl_revenue_account=first["revenue_account"] or None,
                    jtl_external_order_no=(
                        first["external_order_no"]
                        or (first["jtl_internal_order_no"] or "").split(",", 1)[0].strip()
                        or None
                    ),
                    payment_method=first["payment_method"] or None,
                )
                yielded += 1

        if skipped_null_warehouse_cn:
            logger.warning(
                "_fetch_credit_notes: skipped %d credit notes with NULL warehouse_country",
                skipped_null_warehouse_cn,
            )
        logger.info("_fetch_credit_notes: fetched %d credit notes", yielded)


def make_engine(settings: Settings) -> Engine:
    from sqlalchemy import create_engine

    return create_engine(settings.sqlalchemy_url, fast_executemany=True)
