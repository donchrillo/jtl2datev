"""Tests for core/dutypay.py — DutyPay OSS CSV exporter."""
from __future__ import annotations

import csv
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from jtl2datev.core.dutypay import (
    DUTYPAY_COLUMNS,
    KindOfBusiness,
    _incoterms,
    _market_zone,
    _tax_collection_responsibility,
    _tax_reporting_scheme,
    determine_kind_of_business,
    dutypay_filename,
    write_dutypay_csv,
)
from jtl2datev.core.models import PartyAddress, RawInvoice, RawInvoiceLine


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _addr(
    country: str,
    *,
    vat_id: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    company: str | None = None,
    zip_code: str | None = None,
    city: str | None = None,
    street: str | None = None,
) -> PartyAddress:
    return PartyAddress(
        country_iso=country,
        vat_id=vat_id,
        first_name=first_name,
        last_name=last_name,
        company=company,
        zip_code=zip_code,
        city=city,
        street=street,
    )


def _line(
    gross: Decimal = Decimal("119.00"),
    net: Decimal = Decimal("100.00"),
    vat_rate: Decimal = Decimal("19"),
) -> RawInvoiceLine:
    return RawInvoiceLine(
        line_no=1,
        net=net,
        gross=gross,
        vat_amount=gross - net,
        vat_rate=vat_rate,
    )


def _invoice(
    wh: str = "DE",
    dest: str = "DE",
    *,
    is_credit_note: bool = False,
    vat_id: str | None = None,
    external_order_no: str | None = None,
    invoice_no: str = "R-DE-2026-001",
    invoice_date: date = date(2026, 1, 2),
    lines: tuple[RawInvoiceLine, ...] | None = None,
    currency: str = "EUR",
    ship_zip: str | None = None,
    ship_city: str | None = None,
    ship_street: str | None = None,
    marketplace_country: str | None = None,
) -> RawInvoice:
    if lines is None:
        lines = (_line(),)
    return RawInvoice(
        source="jtl_own",
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        currency=currency,
        currency_factor=Decimal("1"),
        warehouse_country=wh,
        ship_to=_addr(dest, zip_code=ship_zip, city=ship_city, street=ship_street),
        bill_to=_addr(dest, vat_id=vat_id),
        is_credit_note=is_credit_note,
        lines=lines,
        jtl_external_order_no=external_order_no,
        marketplace_country=marketplace_country,
    )


_OWN_VAT_IDS = {
    "DE": "DE249030238",
    "FR": "FR54820509628",
    "IT": "IT00185379997",
    "PL": "PL5263144779",
}


# ── KindOfBusiness decision tree ─────────────────────────────────────────────

class TestKindOfBusiness:
    def test_domestic_sale(self) -> None:
        inv = _invoice(wh="DE", dest="DE")
        assert determine_kind_of_business(inv) == KindOfBusiness.SALE

    def test_domestic_refund(self) -> None:
        inv = _invoice(wh="DE", dest="DE", is_credit_note=True)
        assert determine_kind_of_business(inv) == KindOfBusiness.REFUND

    def test_b2b_cross_border_eu(self) -> None:
        inv = _invoice(wh="DE", dest="IT", vat_id="IT05041920967")
        assert determine_kind_of_business(inv) == KindOfBusiness.B2B

    def test_b2b_refund(self) -> None:
        inv = _invoice(wh="DE", dest="IT", vat_id="IT05041920967", is_credit_note=True)
        assert determine_kind_of_business(inv) == KindOfBusiness.B2B_REFUND

    def test_export_third_country(self) -> None:
        inv = _invoice(wh="DE", dest="CH")
        assert determine_kind_of_business(inv) == KindOfBusiness.EXPORT

    def test_export_gb(self) -> None:
        inv = _invoice(wh="DE", dest="GB")
        assert determine_kind_of_business(inv) == KindOfBusiness.EXPORT

    def test_export_turkey(self) -> None:
        inv = _invoice(wh="DE", dest="TR")
        assert determine_kind_of_business(inv) == KindOfBusiness.EXPORT

    def test_export_refund(self) -> None:
        inv = _invoice(wh="DE", dest="CH", is_credit_note=True)
        assert determine_kind_of_business(inv) == KindOfBusiness.EXPORT_REFUND

    def test_export_refund_gb(self) -> None:
        inv = _invoice(wh="DE", dest="GB", is_credit_note=True)
        assert determine_kind_of_business(inv) == KindOfBusiness.EXPORT_REFUND

    def test_cross_border_b2c_is_sale(self) -> None:
        # cross-border EU without VAT ID → SALE (OSS)
        inv = _invoice(wh="DE", dest="FR")
        assert determine_kind_of_business(inv) == KindOfBusiness.SALE

    def test_cross_border_eu_refund_no_vat_id(self) -> None:
        inv = _invoice(wh="DE", dest="FR", is_credit_note=True)
        assert determine_kind_of_business(inv) == KindOfBusiness.REFUND

    def test_eu_warehouse_domestic_sale(self) -> None:
        inv = _invoice(wh="FR", dest="FR")
        assert determine_kind_of_business(inv) == KindOfBusiness.SALE

    # W-5: Vorzeichen-Check sekundiert is_credit_note-Flag
    def test_negative_gross_without_flag_is_refund(self, caplog) -> None:
        # Manueller Korrekturbeleg in tRechnung mit negativem Brutto, kein is_credit_note
        neg_line = _line(gross=Decimal("-119.00"), net=Decimal("-100.00"))
        inv = _invoice(wh="DE", dest="DE", is_credit_note=False, lines=(neg_line,))
        with caplog.at_level("WARNING", logger="jtl2datev.core.dutypay"):
            kind = determine_kind_of_business(inv)
        assert kind == KindOfBusiness.REFUND
        assert any("is_credit_note=False" in r.message and "total_gross=-119" in r.message
                   for r in caplog.records)

    def test_credit_note_flag_with_positive_gross_warns_but_refund(self, caplog) -> None:
        # SRK-Sonderfall (is_credit_note=False bereits gesetzt durch Repository)
        # ist hier nicht abgebildet — wir testen stattdessen umgekehrte Inkonsistenz:
        # is_credit_note=True bei positivem Brutto soll WARN + REFUND-Klassifikation behalten.
        inv = _invoice(wh="DE", dest="DE", is_credit_note=True)  # positive default line
        with caplog.at_level("WARNING", logger="jtl2datev.core.dutypay"):
            kind = determine_kind_of_business(inv)
        assert kind == KindOfBusiness.REFUND
        assert any("is_credit_note=True" in r.message and "total_gross=119" in r.message
                   for r in caplog.records)

    def test_zero_gross_no_warning(self, caplog) -> None:
        # 0,00-€-Belege (Probebuchungen) dürfen nicht warnen, egal welcher Flag
        zero_line = _line(gross=Decimal("0"), net=Decimal("0"))
        inv = _invoice(wh="DE", dest="DE", is_credit_note=True, lines=(zero_line,))
        with caplog.at_level("WARNING", logger="jtl2datev.core.dutypay"):
            kind = determine_kind_of_business(inv)
        assert kind == KindOfBusiness.REFUND  # Flag entscheidet
        assert not any("DutyPay-Klassifikation" in r.message for r in caplog.records)


# ── Derived field tests ───────────────────────────────────────────────────────

class TestMarketZone:
    # Fallback heuristic (no marketplace_country)
    def test_sale_fallback_uses_target_zone(self) -> None:
        inv = _invoice(wh="DE", dest="IT")
        assert _market_zone(inv, KindOfBusiness.SALE) == "IT"

    def test_refund_fallback_uses_target_zone(self) -> None:
        inv = _invoice(wh="DE", dest="IT", is_credit_note=True)
        assert _market_zone(inv, KindOfBusiness.REFUND) == "IT"

    def test_b2b_fallback_uses_source_zone(self) -> None:
        inv = _invoice(wh="DE", dest="IT", vat_id="IT05041920967")
        assert _market_zone(inv, KindOfBusiness.B2B) == "DE"

    def test_export_fallback_uses_source_zone(self) -> None:
        inv = _invoice(wh="DE", dest="CH")
        assert _market_zone(inv, KindOfBusiness.EXPORT) == "DE"

    def test_b2b_refund_fallback_uses_source_zone(self) -> None:
        inv = _invoice(wh="DE", dest="IT", vat_id="IT05041920967", is_credit_note=True)
        assert _market_zone(inv, KindOfBusiness.B2B_REFUND) == "DE"

    def test_export_refund_fallback_uses_source_zone(self) -> None:
        inv = _invoice(wh="DE", dest="CH", is_credit_note=True)
        assert _market_zone(inv, KindOfBusiness.EXPORT_REFUND) == "DE"

    # marketplace_country overrides heuristic regardless of source/target
    def test_marketplace_country_overrides_sale(self) -> None:
        inv = _invoice(wh="FR", dest="GB", marketplace_country="GB")
        assert _market_zone(inv, KindOfBusiness.EXPORT) == "GB"

    def test_marketplace_country_gb_overrides_fr_source(self) -> None:
        # Jera-Ref case: FR → GB, Amazon.co.uk → MarketZone must be GB
        inv = _invoice(wh="FR", dest="GB", marketplace_country="GB")
        assert _market_zone(inv, KindOfBusiness.EXPORT) == "GB"

    def test_marketplace_country_de_for_domestic_sale(self) -> None:
        inv = _invoice(wh="DE", dest="DE", marketplace_country="DE")
        assert _market_zone(inv, KindOfBusiness.SALE) == "DE"

    def test_marketplace_country_none_falls_back(self) -> None:
        # Explicit None → heuristic kicks in
        inv = _invoice(wh="DE", dest="FR", marketplace_country=None)
        assert _market_zone(inv, KindOfBusiness.SALE) == "FR"


class TestTaxReportingScheme:
    def test_export_gb_gives_uk_voec(self) -> None:
        assert _tax_reporting_scheme(KindOfBusiness.EXPORT, "GB") == "UK_VOEC-IMPORT"

    def test_export_refund_gb_gives_uk_voec(self) -> None:
        assert _tax_reporting_scheme(KindOfBusiness.EXPORT_REFUND, "GB") == "UK_VOEC-IMPORT"

    def test_export_non_gb_empty(self) -> None:
        assert _tax_reporting_scheme(KindOfBusiness.EXPORT, "CH") == ""

    def test_sale_gb_empty(self) -> None:
        assert _tax_reporting_scheme(KindOfBusiness.SALE, "GB") == ""

    def test_b2b_gb_empty(self) -> None:
        assert _tax_reporting_scheme(KindOfBusiness.B2B, "GB") == ""


class TestTaxCollectionResponsibility:
    def test_export_with_external_order_is_marketplace(self) -> None:
        inv = _invoice(wh="DE", dest="GB", external_order_no="ER149091")
        assert _tax_collection_responsibility(KindOfBusiness.EXPORT, inv) == "MARKETPLACE"

    def test_export_without_external_order_is_empty(self) -> None:
        inv = _invoice(wh="DE", dest="CH")
        assert _tax_collection_responsibility(KindOfBusiness.EXPORT, inv) == ""

    def test_sale_never_marketplace(self) -> None:
        inv = _invoice(wh="DE", dest="DE", external_order_no="ER12345")
        assert _tax_collection_responsibility(KindOfBusiness.SALE, inv) == ""

    def test_export_refund_with_external_order(self) -> None:
        inv = _invoice(wh="DE", dest="GB", is_credit_note=True, external_order_no="ER149091")
        assert _tax_collection_responsibility(KindOfBusiness.EXPORT_REFUND, inv) == "MARKETPLACE"


class TestIncoterms:
    def test_b2b_is_ddp(self) -> None:
        assert _incoterms(KindOfBusiness.B2B) == "DDP"

    def test_export_is_ddp(self) -> None:
        assert _incoterms(KindOfBusiness.EXPORT) == "DDP"

    def test_b2b_refund_is_ddp(self) -> None:
        assert _incoterms(KindOfBusiness.B2B_REFUND) == "DDP"

    def test_export_refund_is_ddp(self) -> None:
        assert _incoterms(KindOfBusiness.EXPORT_REFUND) == "DDP"

    def test_sale_is_empty(self) -> None:
        assert _incoterms(KindOfBusiness.SALE) == ""

    def test_refund_is_empty(self) -> None:
        assert _incoterms(KindOfBusiness.REFUND) == ""


# ── Vorzeichen tests ──────────────────────────────────────────────────────────

class TestSignRule:
    def _get_mz_gross_net(self, invoice: RawInvoice) -> tuple[str, str]:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([invoice], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        idx_gross = header.index("MarketZoneGross")
        idx_net = header.index("MarketZoneNet")
        return row[idx_gross], row[idx_net]

    def test_sale_positive(self) -> None:
        inv = _invoice(wh="DE", dest="DE", lines=(_line(gross=Decimal("119"), net=Decimal("100")),))
        gross, net = self._get_mz_gross_net(inv)
        assert gross == "119,00"
        assert net == "100,00"

    def test_refund_negative(self) -> None:
        inv = _invoice(wh="DE", dest="DE", is_credit_note=True,
                       lines=(_line(gross=Decimal("119"), net=Decimal("100")),))
        gross, net = self._get_mz_gross_net(inv)
        assert gross == "-119,00"
        assert net == "-100,00"

    def test_b2b_refund_negative(self) -> None:
        inv = _invoice(wh="DE", dest="IT", vat_id="IT05041920967", is_credit_note=True,
                       lines=(_line(gross=Decimal("100"), net=Decimal("100"), vat_rate=Decimal("0")),))
        gross, net = self._get_mz_gross_net(inv)
        assert gross == "-100,00"
        assert net == "-100,00"

    def test_export_refund_negative(self) -> None:
        inv = _invoice(wh="DE", dest="CH", is_credit_note=True,
                       lines=(_line(gross=Decimal("50"), net=Decimal("50"), vat_rate=Decimal("0")),))
        gross, net = self._get_mz_gross_net(inv)
        assert gross == "-50,00"
        assert net == "-50,00"

    def test_refund_already_negative_db_amounts_not_double_negated(self) -> None:
        # JTL stores credit note amounts as negative in the DB.
        # Engine must produce negative output regardless of input sign.
        inv = _invoice(wh="DE", dest="DE", is_credit_note=True,
                       lines=(_line(gross=Decimal("-119"), net=Decimal("-100")),))
        gross, net = self._get_mz_gross_net(inv)
        assert gross == "-119,00"
        assert net == "-100,00"

    def test_b2b_refund_already_negative_db_amounts(self) -> None:
        inv = _invoice(wh="DE", dest="IT", vat_id="IT05041920967", is_credit_note=True,
                       lines=(_line(gross=Decimal("-100"), net=Decimal("-100"), vat_rate=Decimal("0")),))
        gross, net = self._get_mz_gross_net(inv)
        assert gross == "-100,00"
        assert net == "-100,00"

    def test_export_refund_already_negative_db_amounts(self) -> None:
        inv = _invoice(wh="DE", dest="CH", is_credit_note=True,
                       lines=(_line(gross=Decimal("-50"), net=Decimal("-50"), vat_rate=Decimal("0")),))
        gross, net = self._get_mz_gross_net(inv)
        assert gross == "-50,00"
        assert net == "-50,00"

    def test_sale_amounts_never_negated(self) -> None:
        # Positive sales must never produce negative output.
        inv = _invoice(wh="DE", dest="FR",
                       lines=(_line(gross=Decimal("23.80"), net=Decimal("20.00")),))
        gross, net = self._get_mz_gross_net(inv)
        assert gross == "23,80"
        assert net == "20,00"


# ── TransportCode tests ───────────────────────────────────────────────────────

class TestTransportCode:
    def _get_transport_code(self, invoice: RawInvoice) -> str:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([invoice], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        return row[header.index("TransportCode")]

    def test_transport_code_always_5(self) -> None:
        inv = _invoice()
        assert self._get_transport_code(inv) == "5"


# ── TransactionID tests ───────────────────────────────────────────────────────

class TestTransactionID:
    def _get_transaction_id(self, invoice: RawInvoice) -> str:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([invoice], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        return row[header.index("TransactionID")]

    def test_transaction_id_is_external_order_no(self) -> None:
        inv = _invoice(invoice_no="R1252980", external_order_no="404-5433421-0313123")
        assert self._get_transaction_id(inv) == "404-5433421-0313123"

    def test_transaction_id_falls_back_to_pk_when_no_order(self) -> None:
        inv = _invoice(invoice_no="R1252980", external_order_no=None)
        inv = inv.model_copy(update={"jtl_primary_key": 1252980})
        assert self._get_transaction_id(inv) == "R1252980"

    def test_transaction_id_external_uses_marketplace_order(self) -> None:
        inv = _invoice(invoice_no="DE6000RBNL56FU", external_order_no="404-5433421-0313123")
        inv = inv.model_copy(update={"source": "jtl_external", "jtl_primary_key": 146496})
        assert self._get_transaction_id(inv) == "404-5433421-0313123"

    def test_transaction_id_storno_credit_note_uses_internal_order(self) -> None:
        # SRK ohne Marketplace-Order: Fallback ist die Wawi-interne Auftragsnr aus
        # tRechnungEckdaten.cAuftragsnummern, die im DB-Layer schon in
        # jtl_external_order_no fließt.
        inv = _invoice(invoice_no="SRK20260239", external_order_no="21-12042-08233")
        inv = inv.model_copy(update={"source": "jtl_credit_note", "jtl_primary_key": 742273})
        assert self._get_transaction_id(inv) == "21-12042-08233"

    def test_transaction_id_fallback_pk_storno_own(self) -> None:
        # Edge-case: weder externe noch interne Auftragsnr → SR{kRechnung}-Fallback
        inv = _invoice(invoice_no="SR202650099999", external_order_no=None)
        inv = inv.model_copy(update={"jtl_primary_key": 999999})
        assert self._get_transaction_id(inv) == "SR999999"

    def test_transaction_id_fallback_pk_storno_credit_note(self) -> None:
        inv = _invoice(invoice_no="SRK20260239", external_order_no=None)
        inv = inv.model_copy(update={"source": "jtl_credit_note", "jtl_primary_key": 742253})
        assert self._get_transaction_id(inv) == "SRK742253"

    def test_transaction_id_fallback_pk_external_refund(self) -> None:
        inv = _invoice(invoice_no="XRK-181", is_credit_note=True, external_order_no=None)
        inv = inv.model_copy(update={"source": "jtl_external", "jtl_primary_key": 149395})
        assert self._get_transaction_id(inv) == "EG149395"

    def test_document_id_unchanged(self) -> None:
        inv = _invoice(invoice_no="R-DE-249030238-2026-1", external_order_no="404-5433421-0313123")
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        assert row[header.index("DocumentID")] == "R-DE-249030238-2026-1"
        assert row[header.index("TransactionID")] == "404-5433421-0313123"


# ── Header / column count test ────────────────────────────────────────────────

class TestHeader:
    def test_column_count(self) -> None:
        assert len(DUTYPAY_COLUMNS) == 98

    def test_csv_header_matches_columns(self) -> None:
        inv = _invoice()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
        assert header == list(DUTYPAY_COLUMNS)

    def test_each_row_has_98_columns(self) -> None:
        # Multi-line invoice produces exactly 1 data row; all 98 columns must be present.
        inv = _invoice(lines=(_line(), _line()))
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            next(reader)  # header
            rows = list(reader)
        assert len(rows) == 1
        assert len(rows[0]) == 98


# ── Reporting period and filename ─────────────────────────────────────────────

class TestHelpers:
    def test_dutypay_filename(self) -> None:
        assert dutypay_filename(2026, 1) == "DutyPay-SALE-2026-JAN.csv"
        assert dutypay_filename(2026, 12) == "DutyPay-SALE-2026-DEC.csv"
        assert dutypay_filename(2025, 3) == "DutyPay-SALE-2025-MAR.csv"

    def test_reporting_period_in_csv(self) -> None:
        inv = _invoice(invoice_date=date(2026, 3, 15))
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        idx = header.index("ReportingPeriod")
        assert row[idx] == "2026-MAR"


# ── Integration: multi-invoice write ─────────────────────────────────────────

class TestWriteDutyPayCsv:
    def test_multi_invoice_pos_nr_increments(self) -> None:
        # inv1 has 2 lines but produces exactly 1 row (amounts aggregated)
        inv1 = _invoice(invoice_no="R-001", lines=(_line(), _line()))
        inv2 = _invoice(invoice_no="R-002", lines=(_line(),))
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        report = write_dutypay_csv([inv1, inv2], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        assert report.rows_written == 2
        assert report.invoices_processed == 2

        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            next(reader)  # header
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0][0] == "1"
        assert rows[1][0] == "2"

    def test_multi_line_invoice_amounts_aggregated(self) -> None:
        # 2-line invoice: gross 119 + 59.50, net 100 + 50 → totals 178.50 / 150.00
        inv = _invoice(
            invoice_no="R-003",
            lines=(
                _line(gross=Decimal("119.00"), net=Decimal("100.00")),
                _line(gross=Decimal("59.50"), net=Decimal("50.00")),
            ),
        )
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        report = write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        assert report.rows_written == 1
        assert report.invoices_processed == 1

        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        assert row[header.index("MarketZoneGross")] == "178,50"
        assert row[header.index("MarketZoneNet")] == "150,00"
        assert row[header.index("ItemQuantity")] == "1"

    def test_item_and_address_fields_empty(self) -> None:
        inv = _invoice(
            wh="DE", dest="FR",
            ship_zip="75001", ship_city="Paris", ship_street="Rue de Rivoli",
        )
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)

        empty_fields = [
            "ItemID", "ItemName", "ItemDescription", "CommodityCode",
            "ItemUnit", "ItemSalesPrice", "ItemPurchasePrice", "ItemWeight",
            "ItemManufacturer", "ItemManufacturerZone", "MPN", "Brand",
            "GTIN", "ASIN", "ISBN", "UPC", "JAN",
            "TPCompanyName",
            "TransactionPartner Form Of Address", "TransactionPartner First Name",
            "TransactionPartner Family Name", "TransactionPartner Tax-ID",
            "TransactionPartner Street", "TransactionPartner House Number",
            "TransactionPartner Additional Address", "TransactionPartner ZIP",
            "TransactionPartner City", "TransactionPartner Region",
            "TransactionPartner Country IsoCode",
            "BillingAddress Company Name", "BillingAddress Street",
            "BillingAddress ZIP", "BillingAddress City",
            "BillingAddress Country ISOCode",
        ]
        for field_name in empty_fields:
            assert row[header.index(field_name)] == "", f"{field_name} should be empty"

    def test_rows_written_equals_invoices_processed(self) -> None:
        invoices = [
            _invoice(invoice_no="R-A", lines=(_line(),)),
            _invoice(invoice_no="R-B", lines=(_line(), _line(), _line())),
            _invoice(invoice_no="R-C", lines=(_line(),)),
        ]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        report = write_dutypay_csv(invoices, out_path=path, own_vat_ids=_OWN_VAT_IDS)
        assert report.rows_written == report.invoices_processed == 3

    def test_b2b_source_vat_id_filled(self) -> None:
        inv = _invoice(wh="DE", dest="IT", vat_id="IT05041920967",
                       lines=(_line(vat_rate=Decimal("0"), gross=Decimal("100"), net=Decimal("100")),))
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        idx_src_vat = header.index("SourceZoneVatID")
        idx_tgt_vat = header.index("TargetZoneVatID")
        assert row[idx_src_vat] == "DE249030238"
        assert row[idx_tgt_vat] == "IT05041920967"

    def test_sale_source_vat_id_empty(self) -> None:
        inv = _invoice(wh="DE", dest="DE")
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        idx = header.index("SourceZoneVatID")
        assert row[idx] == ""

    def test_export_gb_uk_voec_and_marketplace(self) -> None:
        inv = _invoice(wh="DE", dest="GB", external_order_no="ER149091",
                       lines=(_line(vat_rate=Decimal("0"), gross=Decimal("50"), net=Decimal("50")),))
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        assert row[header.index("TAX_REPORTING_SCHEME")] == "UK_VOEC-IMPORT"
        assert row[header.index("TAX_COLLECTION_RESPONSIBILITY")] == "MARKETPLACE"
        assert row[header.index("Incoterms")] == "DDP"
        assert row[header.index("KindOfBusiness")] == "EXPORT"

    def test_temu_beleg_included_in_dutypay(self) -> None:
        # Temu belege (DE→DE B2C, external_order_no starts with "PO-") must appear
        # in the DutyPay output. The DATEV exporter filters them; DutyPay does not.
        inv = _invoice(
            wh="DE",
            dest="DE",
            external_order_no="PO-123456789",
            invoice_no="R-DE-249030238-2025-9999",
        )
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        report = write_dutypay_csv([inv], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        assert report.rows_written == 1, "Temu beleg must be included in DutyPay output"
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        assert row[header.index("DocumentID")] == "R-DE-249030238-2025-9999"


# ── SourceZoneCurrencyCode, TargetZoneCurrencyCode, MarketZoneCurrencyCode ────

class TestZoneCurrencyCodes:
    """Zone currency codes are derived from zone countries, not from invoice currency."""

    def _get_row(self, invoice: RawInvoice) -> tuple[list[str], list[str]]:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        write_dutypay_csv([invoice], out_path=path, own_vat_ids=_OWN_VAT_IDS)
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            row = next(reader)
        path.unlink()
        return header, row

    def test_de_warehouse_gbp_invoice_source_is_eur(self) -> None:
        inv = _invoice(wh="DE", dest="GB", currency="GBP")
        header, row = self._get_row(inv)
        # SourceZone=DE → EUR (not GBP invoice currency)
        assert row[header.index("SourceZoneCurrencyCode")] == "EUR"
        # No marketplace_country set; dest=GB → heuristic MarketZone=GB (EXPORT) → DE
        # EXPORT kind → fallback is warehouse (DE → EUR); MarketZone=DE
        # Actually: dest=GB → EXPORT → fallback MarketZone = source_zone=DE → EUR
        assert row[header.index("MarketZoneCurrencyCode")] == "EUR"

    def test_fr_warehouse_eur_invoice_source_is_eur(self) -> None:
        inv = _invoice(wh="FR", dest="FR", currency="EUR")
        header, row = self._get_row(inv)
        assert row[header.index("SourceZoneCurrencyCode")] == "EUR"
        assert row[header.index("MarketZoneCurrencyCode")] == "EUR"

    def test_pl_warehouse_eur_invoice_source_is_pln(self) -> None:
        inv = _invoice(wh="PL", dest="AT", currency="EUR")
        header, row = self._get_row(inv)
        assert row[header.index("SourceZoneCurrencyCode")] == "PLN"
        # SALE: fallback MarketZone=target=AT → EUR
        assert row[header.index("MarketZoneCurrencyCode")] == "EUR"

    def test_cz_warehouse_source_is_czk(self) -> None:
        inv = _invoice(wh="CZ", dest="PL", currency="PLN")
        header, row = self._get_row(inv)
        assert row[header.index("SourceZoneCurrencyCode")] == "CZK"

    def test_target_zone_currency_from_dest_country(self) -> None:
        # TargetZoneCurrencyCode is derived from dest country currency.
        inv_de_gb = _invoice(wh="DE", dest="GB", currency="GBP")
        header, row = self._get_row(inv_de_gb)
        assert row[header.index("TargetZoneCurrencyCode")] == "GBP"

        inv_fr_fr = _invoice(wh="FR", dest="FR", currency="EUR")
        header, row = self._get_row(inv_fr_fr)
        assert row[header.index("TargetZoneCurrencyCode")] == "EUR"

        inv_pl_at = _invoice(wh="PL", dest="AT", currency="EUR")
        header, row = self._get_row(inv_pl_at)
        assert row[header.index("TargetZoneCurrencyCode")] == "EUR"

        inv_pl_se = _invoice(wh="PL", dest="SE", currency="SEK")
        header, row = self._get_row(inv_pl_se)
        assert row[header.index("TargetZoneCurrencyCode")] == "SEK"

    def test_marketplace_country_gb_gives_gbp_market_currency(self) -> None:
        # FR warehouse, GB dest, Amazon.co.uk → MarketZone=GB → GBP
        inv = _invoice(wh="FR", dest="GB", currency="GBP", marketplace_country="GB")
        header, row = self._get_row(inv)
        assert row[header.index("MarketZone")] == "GB"
        assert row[header.index("MarketZoneCurrencyCode")] == "GBP"

    def test_marketplace_country_fr_gives_eur_market_currency(self) -> None:
        inv = _invoice(wh="DE", dest="FR", currency="EUR", marketplace_country="FR")
        header, row = self._get_row(inv)
        assert row[header.index("MarketZone")] == "FR"
        assert row[header.index("MarketZoneCurrencyCode")] == "EUR"

    def test_marketplace_country_se_gives_sek_market_currency(self) -> None:
        inv = _invoice(wh="DE", dest="SE", currency="SEK", marketplace_country="SE")
        header, row = self._get_row(inv)
        assert row[header.index("MarketZone")] == "SE"
        assert row[header.index("MarketZoneCurrencyCode")] == "SEK"

    def test_item_currency_code_is_invoice_currency(self) -> None:
        inv = _invoice(wh="DE", dest="GB", currency="GBP")
        header, row = self._get_row(inv)
        assert row[header.index("ItemCurrencyCode")] == "GBP"
