import logging
import re
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterator

from sqlalchemy import Engine, text

from jtl2datev.core.config import Settings
from jtl2datev.core.models import PartyAddress, RawInvoice, RawInvoiceLine
from jtl2datev.core.reference_data import HARD_MIN_INVOICE_DATE as _MIN_DATE, PLATFORM_COUNTRY as _PLATFORM_COUNTRY
from jtl2datev.core.preflight import MixedVatBeleg, find_mixed_vat_belege
from jtl2datev.core.repositories import ArticlePricingRepository, InvoiceRepository
from jtl2datev.core.tax_engine import STANDARD_VAT_RATE
from jtl2datev.core.verbringung_pricing import PricingResult, lookup_prices

logger = logging.getLogger(__name__)

_SUFFIX_RE = re.compile(r"_\d+$")


def _marketplace_country_for(platform_name: str | None, fallback: str) -> str:
    """Return ISO-2 country for a given tPlattform.cName.

    Returns the fallback (warehouse country) for None, generic "Amazon",
    or any unknown platform name, logging a warning for unrecognised values.
    """
    if not platform_name:
        return fallback
    if platform_name in _PLATFORM_COUNTRY:
        return _PLATFORM_COUNTRY[platform_name]
    logger.warning(
        "Unknown platform name %r — using fallback marketplace_country %r",
        platform_name,
        fallback,
    )
    return fallback


def _strip_marketplace_suffix(order_no: str | None) -> str | None:
    """JTL-Konvention: Mehrteilige Marketplace-Sendungen tragen `_1`, `_2`, ...
    Beispiel: '406-0538474-1507531_1' → '406-0538474-1507531'.
    None/leer wird unverändert durchgereicht."""
    if not order_no:
        return order_no
    return _SUFFIX_RE.sub("", order_no)

# All known VAT rates that can appear — standard rates per country plus 0 % and
# DE reduced rate. Sorted ascending so min() tie-breaks deterministically.
_KNOWN_RATES: list[Decimal] = sorted(
    {Decimal("0"), Decimal("7")} | set(STANDARD_VAT_RATE.values())
)

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
    -- Totals from Eckdaten (1 row per invoice — no position join needed)
    re.fVkBruttoGesamt        AS total_gross,
    re.fVkNettoGesamt         AS total_net,
    re.cAuftragsnummern       AS jtl_internal_order_no,
    -- Platform name
    p.cName                   AS platform_name,
    -- Delivery address (nTyp=0)
    ship.cISO                 AS ship_country,
    ship.cBundesland          AS ship_region,
    ship.cVorname             AS ship_first_name,
    ship.cName                AS ship_last_name,
    ship.cFirma               AS ship_company,
    ship.cPLZ                 AS ship_zip,
    ship.cOrt                 AS ship_city,
    ship.cStrasse             AS ship_street,
    ship.cAdresszusatz        AS ship_additional_address,
    -- Billing address (nTyp=1)
    bill.cISO                 AS bill_country,
    bill.cBundesland          AS bill_region,
    bill.cVorname             AS bill_first_name,
    bill.cName                AS bill_last_name,
    bill.cFirma               AS bill_company,
    bill.cPLZ                 AS bill_zip,
    bill.cOrt                 AS bill_city,
    bill.cStrasse             AS bill_street,
    bill.cAdresszusatz        AS bill_additional_address
FROM Rechnung.tRechnung r
LEFT JOIN dbo.tRechnung dr
    ON dr.kRechnung = r.kRechnung
JOIN Rechnung.tRechnungEckdaten re
    ON re.kRechnung = r.kRechnung
LEFT JOIN dbo.tPlattform p
    ON p.nPlattform = r.kPlattform
LEFT JOIN Rechnung.tRechnungAdresse ship
    ON ship.kRechnung = r.kRechnung AND ship.nTyp = 0
LEFT JOIN Rechnung.tRechnungAdresse bill
    ON bill.kRechnung = r.kRechnung AND bill.nTyp = 1
WHERE r.nIstEntwurf = 0
  AND r.nIstProforma = 0
  -- nStorno=1 stays in: a stornierte Rechnung implies a counter-credit-note
  -- exists/must exist, and we need both halves for an auditable export.
  AND r.dErstellt >= :hard_min
  AND r.dErstellt >= :date_from
  AND r.dErstellt < :date_to_excl
  -- Temu-Belege (cExterneAuftragsnummer LIKE 'PO%') bleiben drin: DutyPay-Spec
  -- verlangt vollständige Auslandsverkaufs-Liste (auch DE→DE B2C). Filter sitzt
  -- ausschließlich im DATEV-Exporter (core/datev.py).
ORDER BY r.kRechnung
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
    -- Totals from Eckdaten (100 % coverage, amounts negative for Gutschrift)
    eck.fVkBrutto             AS total_gross,
    eck.fVkNetto              AS total_net,
    -- Platform name
    p.cName                   AS platform_name,
    -- Billing address (directly on header)
    -- cRAAdresse1 carries full street+number; no separate cRAStrasse/cRAHausNr column
    eb.cRALandISO             AS bill_country,
    eb.cRAStaat               AS bill_region,
    eb.cRAName                AS bill_full_name,
    eb.cRAPostcode            AS bill_zip,
    eb.cRAOrt                 AS bill_city,
    eb.cRAAdresse1            AS bill_street,
    -- Delivery + warehouse from Transaktion
    -- cLAAdresse1 carries the full street+number line (embedded); no separate house-nr column
    tr.cLALandISO             AS ship_country,
    tr.cLAStaat               AS ship_region,
    tr.cLAName                AS ship_full_name,
    tr.cLAPostcode            AS ship_zip,
    tr.cLAOrt                 AS ship_city,
    tr.cLAAdresse1            AS ship_street,
    tr.cLAAdresse2            AS ship_additional_address,
    tr.cVALandISO             AS warehouse_country,
    tr.cExterneAuftragsnummer AS external_order_no,
    tr.kExternerBelegTransaktion AS transakt_key
FROM Rechnung.tExternerBeleg eb
LEFT JOIN Rechnung.tExternerBelegEckdaten eck
    ON eck.kExternerBeleg = eb.kExternerBeleg
LEFT JOIN dbo.tPlattform p
    ON p.nPlattform = eb.kPlattform
LEFT JOIN Rechnung.tExternerBelegTransaktion tr
    ON tr.kExternerBeleg = eb.kExternerBeleg
WHERE eb.dBelegdatumUtc >= :hard_min
  AND eb.dBelegdatumUtc >= :date_from
  AND eb.dBelegdatumUtc < :date_to_excl
  AND eb.nBelegtyp IN (0, 1, 2)
  -- Note: nIstStorniert=1 invoices stay in the export. JTL flags an invoice
  -- as storniert when a counter-credit-note (nBelegtyp=1 with cBezugsbelegnr
  -- = the original Belegnr) was issued; both bookings must hit the export
  -- so the audit trail is complete and the net effect is zero.
ORDER BY eb.kExternerBeleg
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
    -- Totals from vGutschriftEckdaten (positive values; vorzeichen applied downstream)
    ge.fPreisBrutto            AS total_gross,
    ge.fPreisNetto             AS total_net,
    -- Platform name
    p.cName                    AS platform_name,
    -- Delivery address (nTyp=0) from tRechnungAdresse
    ship.cISO                  AS ship_country,
    ship.cBundesland           AS ship_region,
    ship.cVorname              AS ship_first_name,
    ship.cName                 AS ship_last_name,
    ship.cFirma                AS ship_company,
    ship.cPLZ                  AS ship_zip,
    ship.cOrt                  AS ship_city,
    ship.cStrasse              AS ship_street,
    ship.cAdresszusatz         AS ship_additional_address,
    -- Billing address (nTyp=1) from tRechnungAdresse
    bill.cISO                  AS bill_country,
    bill.cBundesland           AS bill_region,
    bill.cVorname              AS bill_first_name,
    bill.cName                 AS bill_last_name,
    bill.cFirma                AS bill_company,
    bill.cPLZ                  AS bill_zip,
    bill.cOrt                  AS bill_city,
    bill.cStrasse              AS bill_street,
    bill.cAdresszusatz         AS bill_additional_address
FROM dbo.tgutschrift g
LEFT JOIN Rechnung.tRechnung r
    ON r.kRechnung = g.kRechnung
LEFT JOIN Rechnung.tRechnungEckdaten eck
    ON eck.kRechnung = g.kRechnung
JOIN dbo.vGutschriftEckdaten ge
    ON ge.kGutschrift = g.kGutschrift
LEFT JOIN dbo.tPlattform p
    ON p.nPlattform = g.kPlattform
LEFT JOIN Rechnung.tRechnungAdresse ship
    ON ship.kRechnung = g.kRechnung AND ship.nTyp = 0
LEFT JOIN Rechnung.tRechnungAdresse bill
    ON bill.kRechnung = g.kRechnung AND bill.nTyp = 1
WHERE g.kRechnung IS NOT NULL
  -- nStorno=1 stays in (audit-trail completeness — see _fetch_own).
  AND g.dErstellt >= :hard_min
  AND g.dErstellt >= :date_from
  AND g.dErstellt <  :date_to_excl
ORDER BY g.kGutschrift
""")


def _to_date(val: object) -> date:
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


def derive_vat_rate(gross: Decimal, net: Decimal) -> Decimal:
    """Derive VAT rate from header gross/net and snap to nearest known standard rate.

    Tolerates up to 0.5 percentage points of rounding drift. Returns the raw
    computed rate (2 dp) when no known rate is close enough.

    Edge-cases handled:
    - net == 0 or gross == net  → 0 % (Reverse-Charge / export / zero-rated)
    - gross == 0 and net == 0   → 0 %
    - negative amounts (Amazon refunds): (neg-neg)/neg is positive — correct
    """
    if net == Decimal("0") or gross == net:
        return Decimal("0")
    raw = (gross - net) / net * Decimal("100")
    best = min(_KNOWN_RATES, key=lambda r: abs(r - raw))
    if abs(best - raw) < Decimal("0.5"):
        return best
    return raw.quantize(Decimal("0.01"))


def _synthetic_line(gross: Decimal, net: Decimal) -> RawInvoiceLine:
    vat_rate = derive_vat_rate(gross, net)
    vat_amount = gross - net
    return RawInvoiceLine(
        line_no=0,
        net=net,
        gross=gross,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
    )


class JtlInvoiceRepository(InvoiceRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def fetch_invoices(self, *, date_from: date, date_to: date) -> Iterator[RawInvoice]:
        yield from self._fetch_own(date_from=date_from, date_to=date_to)
        yield from self._fetch_external(date_from=date_from, date_to=date_to)
        yield from self._fetch_credit_notes(date_from=date_from, date_to=date_to)

    def find_mixed_vat_belege(
        self, *, date_from: date, date_to: date
    ) -> list[MixedVatBeleg]:
        return find_mixed_vat_belege(self._engine, date_from=date_from, date_to=date_to)

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

            for row in result.mappings():
                inv_key = row["kRechnung"]

                warehouse = row["warehouse_country"]
                if not warehouse:
                    logger.warning(
                        "tRechnung kRechnung=%s has NULL cVersandlandISO — skipping",
                        inv_key,
                    )
                    skipped_null_warehouse += 1
                    continue

                ship_country = row["ship_country"] or ""
                bill_country = row["bill_country"] or ""

                ship_to = PartyAddress(
                    country_iso=ship_country,
                    region=row["ship_region"],
                    vat_id=row["customer_vat_id"] or None,
                    first_name=row["ship_first_name"] or None,
                    last_name=row["ship_last_name"] or None,
                    company=row["ship_company"] or None,
                    zip_code=row["ship_zip"] or None,
                    city=row["ship_city"] or None,
                    street=row["ship_street"] or None,
                    additional_address=row["ship_additional_address"] or None,
                )
                bill_to = PartyAddress(
                    country_iso=bill_country,
                    region=row["bill_region"],
                    vat_id=row["customer_vat_id"] or None,
                    first_name=row["bill_first_name"] or None,
                    last_name=row["bill_last_name"] or None,
                    company=row["bill_company"] or None,
                    zip_code=row["bill_zip"] or None,
                    city=row["bill_city"] or None,
                    street=row["bill_street"] or None,
                    additional_address=row["bill_additional_address"] or None,
                )

                gross = _decimal(row["total_gross"])
                net = _decimal(row["total_net"])
                line = _synthetic_line(gross, net)

                inv_date_raw = row["invoice_date"]
                svc_date_raw = row["service_date"]

                marketplace_country = _marketplace_country_for(
                    row["platform_name"] or None, warehouse.strip()
                )
                _own_cf = _decimal(row["currency_factor"])
                _own_currency = (row["currency"] or "EUR").strip().upper()
                if not _own_cf and _own_currency != "EUR":
                    logger.warning(
                        "_fetch_own %s: currency_factor=0/None for non-EUR currency %s"
                        " — using 1.0; check JTL data",
                        row["invoice_no"] or str(inv_key),
                        _own_currency,
                    )
                _own_cf = _own_cf or Decimal("1")
                yield RawInvoice(
                    source="jtl_own",
                    jtl_primary_key=int(inv_key) if inv_key is not None else None,
                    invoice_no=row["invoice_no"] or str(inv_key),
                    invoice_date=_to_date(inv_date_raw),
                    service_date=_to_date(svc_date_raw) if svc_date_raw else None,
                    currency=_own_currency,
                    currency_factor=_own_cf,
                    warehouse_country=warehouse.strip(),
                    ship_to=ship_to,
                    bill_to=bill_to,
                    customer_no=row["customer_no"] or None,
                    platform_id=row["platform_id"],
                    platform_name=row["platform_name"] or None,
                    marketplace_country=marketplace_country,
                    is_credit_note=False,
                    lines=(line,),
                    jtl_revenue_account=row["revenue_account"] or None,
                    # Fallback: when no marketplace order ID exists (rare manual JTL
                    # invoice), use the internal Wawi order number from
                    # tRechnungEckdaten.cAuftragsnummern (a comma list — first entry).
                    jtl_external_order_no=_strip_marketplace_suffix(
                        row["external_order_no"]
                        or (row["jtl_internal_order_no"] or "").split(",", 1)[0].strip()
                        or None
                    ),
                    payment_method=row["payment_method"] or None,
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

            for row in result.mappings():
                beleg_key = row["kExternerBeleg"]
                beleg_typ = row["beleg_typ"]
                # nBelegtyp: 0=Rechnung (B2C), 1=Gutschrift, 2=Restposten-Aufkäufer-Rechnung (B2B)
                # 0 und 2 sind reguläre Rechnungen; B2B-Behandlung folgt aus cKaeuferUstId+Land-Differenz.
                warehouse = row["warehouse_country"]
                if not warehouse or not warehouse.strip():
                    logger.warning(
                        "tExternerBeleg kExternerBeleg=%s has NULL cVALandISO — skipping",
                        beleg_key,
                    )
                    skipped_null_warehouse += 1
                    continue

                ship_country = row["ship_country"] or ""
                bill_country = row["bill_country"] or ""

                ship_to = PartyAddress(
                    country_iso=ship_country.strip(),
                    region=row["ship_region"] or None,
                    vat_id=row["customer_vat_id"] or None,
                    last_name=row["ship_full_name"] or None,
                    zip_code=row["ship_zip"] or None,
                    city=row["ship_city"] or None,
                    street=row["ship_street"] or None,
                    additional_address=row["ship_additional_address"] or None,
                )
                bill_to = PartyAddress(
                    country_iso=bill_country.strip(),
                    region=row["bill_region"] or None,
                    vat_id=row["customer_vat_id"] or None,
                    last_name=row["bill_full_name"] or None,
                    zip_code=row["bill_zip"] or None,
                    city=row["bill_city"] or None,
                    street=row["bill_street"] or None,
                )

                gross = _decimal(row["total_gross"])
                net = _decimal(row["total_net"])
                line = _synthetic_line(gross, net)

                debitor_nr = row["debitor_nr"]
                customer_no = str(debitor_nr) if debitor_nr else None

                marketplace_country = _marketplace_country_for(
                    row["platform_name"] or None, warehouse.strip()
                )
                _ext_cf = _decimal(row["currency_factor"])
                _ext_currency = (row["currency"] or "EUR").strip().upper()
                if not _ext_cf and _ext_currency != "EUR":
                    logger.warning(
                        "_fetch_external %s: currency_factor=0/None for non-EUR currency %s"
                        " — using 1.0; check JTL data",
                        row["invoice_no"] or str(beleg_key),
                        _ext_currency,
                    )
                _ext_cf = _ext_cf or Decimal("1")
                yield RawInvoice(
                    source="jtl_external",
                    jtl_primary_key=int(beleg_key) if beleg_key is not None else None,
                    invoice_no=row["invoice_no"] or str(beleg_key),
                    invoice_date=_to_date(row["invoice_date"]),
                    service_date=None,
                    currency=_ext_currency,
                    currency_factor=_ext_cf,
                    warehouse_country=warehouse.strip(),
                    ship_to=ship_to,
                    bill_to=bill_to,
                    customer_no=customer_no,
                    platform_id=row["platform_id"],
                    platform_name=row["platform_name"] or None,
                    marketplace_country=marketplace_country,
                    # nBelegtyp 1 = Gutschrift (amounts already negative in DB); 0/2 = Rechnung
                    is_credit_note=(beleg_typ == 1),
                    lines=(line,),
                    jtl_revenue_account=None,
                    jtl_external_order_no=_strip_marketplace_suffix(
                        row["external_order_no"] or None
                    ),
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

            for row in result.mappings():
                gutschrift_key = row["kGutschrift"]

                warehouse = row["warehouse_country"]
                if not warehouse or not warehouse.strip():
                    logger.warning(
                        "tgutschrift kGutschrift=%s has NULL cVersandlandISO — skipping",
                        gutschrift_key,
                    )
                    skipped_null_warehouse_cn += 1
                    continue

                ship_country = row["ship_country"] or ""
                bill_country = row["bill_country"] or ""

                ship_to = PartyAddress(
                    country_iso=ship_country.strip(),
                    region=row["ship_region"] or None,
                    vat_id=row["customer_vat_id"] or None,
                    first_name=row["ship_first_name"] or None,
                    last_name=row["ship_last_name"] or None,
                    company=row["ship_company"] or None,
                    zip_code=row["ship_zip"] or None,
                    city=row["ship_city"] or None,
                    street=row["ship_street"] or None,
                    additional_address=row["ship_additional_address"] or None,
                )
                bill_to = PartyAddress(
                    country_iso=bill_country.strip(),
                    region=row["bill_region"] or None,
                    vat_id=row["customer_vat_id"] or None,
                    first_name=row["bill_first_name"] or None,
                    last_name=row["bill_last_name"] or None,
                    company=row["bill_company"] or None,
                    zip_code=row["bill_zip"] or None,
                    city=row["bill_city"] or None,
                    street=row["bill_street"] or None,
                    additional_address=row["bill_additional_address"] or None,
                )

                # vGutschriftEckdaten stores positive values; is_credit_note=True
                # signals downstream (DATEV/DutyPay) to apply the negative sign.
                # Ausnahme: SRK = Storno einer Rechnungskorrektur (cGutschriftNr
                # beginnt mit "SRK"). Ökonomisch hebt das die ursprüngliche
                # Gutschrift wieder auf → der Betrag zählt als Erlös, nicht als
                # Refund. Wird daher als reguläre Rechnung (is_credit_note=False)
                # behandelt → SALE mit positivem Vorzeichen, exakt wie Jera bucht.
                inv_no_raw = row["invoice_no"] or str(gutschrift_key)
                is_storno_rk = inv_no_raw.upper().startswith("SRK")
                gross = _decimal(row["total_gross"])
                net = _decimal(row["total_net"])
                line = _synthetic_line(gross, net)

                raw_currency = row["currency"] or "EUR"
                currency = raw_currency.strip()[:3].upper()
                _cn_cf = _decimal(row["currency_factor"])
                if not _cn_cf and currency != "EUR":
                    logger.warning(
                        "_fetch_credit_notes %s: currency_factor=0/None for non-EUR currency %s"
                        " — using 1.0; check JTL data",
                        inv_no_raw,
                        currency,
                    )
                _cn_cf = _cn_cf or Decimal("1")

                kunde = row["kKunde"]
                customer_no = str(kunde) if kunde else None

                marketplace_country = _marketplace_country_for(
                    row["platform_name"] or None, warehouse.strip()
                )
                yield RawInvoice(
                    source="jtl_credit_note",
                    jtl_primary_key=int(gutschrift_key) if gutschrift_key is not None else None,
                    invoice_no=inv_no_raw,
                    invoice_date=_to_date(row["invoice_date"]),
                    service_date=None,
                    currency=currency,
                    currency_factor=_cn_cf,
                    warehouse_country=warehouse.strip(),
                    ship_to=ship_to,
                    bill_to=bill_to,
                    customer_no=customer_no,
                    platform_id=row["platform_id"],
                    platform_name=row["platform_name"] or None,
                    marketplace_country=marketplace_country,
                    is_credit_note=not is_storno_rk,
                    lines=(line,),
                    jtl_revenue_account=row["revenue_account"] or None,
                    jtl_external_order_no=_strip_marketplace_suffix(
                        row["external_order_no"]
                        or (row["jtl_internal_order_no"] or "").split(",", 1)[0].strip()
                        or None
                    ),
                    payment_method=row["payment_method"] or None,
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

    return create_engine(
        settings.sqlalchemy_url,
        fast_executemany=True,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"timeout": 10},
    )


@contextmanager
def managed_engine(settings: Settings):  # type: ignore[return]
    engine = make_engine(settings)
    try:
        yield engine
    finally:
        engine.dispose()


class JtlArticlePricingRepository(ArticlePricingRepository):
    """JTL-spezifische Implementierung von ArticlePricingRepository.

    Wrappt verbringung_pricing.lookup_prices (MSSQL-Tier-Lookup mit
    SKU-/B-Ware-/ASIN-Auflösung). ERP-Implementierungen brauchen ihre eigene
    Bewertungs-Logik und können nicht 1:1 die JTL-Tier-Strategie übernehmen.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        mapping_table: str = "dbo.pf_amazon_angebot_mapping",
        artikel_table: str = "dbo.tArtikel",
        beschreibung_table: str = "dbo.tArtikelBeschreibung",
        angebot_table: str = "dbo.pf_amazon_angebot",
    ) -> None:
        self._engine = engine
        self._mapping_table = mapping_table
        self._artikel_table = artikel_table
        self._beschreibung_table = beschreibung_table
        self._angebot_table = angebot_table

    def lookup_ek_prices(
        self,
        skus: list[str],
        *,
        asin_by_sku: dict[str, str] | None = None,
        bware_strategy: str = "ten_percent",
    ) -> dict[str, PricingResult]:
        return lookup_prices(
            skus,
            self._engine,
            mapping_table=self._mapping_table,
            artikel_table=self._artikel_table,
            beschreibung_table=self._beschreibung_table,
            angebot_table=self._angebot_table,
            bware_strategy=bware_strategy,
            asin_by_sku=asin_by_sku,
        )
