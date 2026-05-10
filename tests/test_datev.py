"""Tests for core/datev.py — EXTF Buchungsstapel writer."""
from __future__ import annotations

import csv
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from jtl2datev.core.config import Settings
from jtl2datev.core.datev import (
    ExportReport,
    _format_belegdatum,
    _format_decimal,
    _format_kurs,
    _sanitize_buchungstext,
    write_extf_buchungsstapel,
)
from jtl2datev.core.models import (
    LineDecision,
    PartyAddress,
    RawInvoice,
    RawInvoiceLine,
    TaxDecision,
    TaxTreatment,
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        sql_server="unused",
        sql_password="unused",
        datev_mandantennr=14974,
        datev_beraternr=10305,
    )


def _line(
    vat_rate: Decimal = Decimal("19"),
    gross: Decimal = Decimal("119"),
    net: Decimal = Decimal("100"),
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
    invoice_no: str = "R-DE-2026-001",
    invoice_date: date = date(2026, 3, 2),
    is_credit_note: bool = False,
    lines: tuple[RawInvoiceLine, ...] | None = None,
    vat_id: str | None = None,
    payment_method: str | None = "AmazonPayments",
    external_order_no: str | None = "TEST-ORDER-123",
    bill_to: PartyAddress | None = None,
    currency: str = "EUR",
    currency_factor: Decimal = Decimal("1"),
) -> RawInvoice:
    if lines is None:
        lines = (_line(),)
    if bill_to is None:
        bill_to = PartyAddress(country_iso=dest, vat_id=vat_id)
    return RawInvoice(
        source="jtl_external",
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        currency=currency,
        currency_factor=currency_factor,
        warehouse_country=wh,
        ship_to=PartyAddress(country_iso=dest),
        bill_to=bill_to,
        is_credit_note=is_credit_note,
        lines=lines,
        payment_method=payment_method,
        jtl_external_order_no=external_order_no,
        customer_no="12345",
    )


OWN_VAT_COUNTRIES: frozenset[str] = frozenset({"DE", "FR", "IT", "ES", "PL", "CZ", "GB"})


def _decisions(inv: RawInvoice) -> list[LineDecision]:
    from jtl2datev.core.tax_engine import decide as _decide
    return [
        LineDecision(line=line, decision=_decide(inv, line, own_vat_countries=OWN_VAT_COUNTRIES))
        for line in inv.lines
    ]


class TestFormatHelpers:
    def test_belegdatum_march_2(self) -> None:
        assert _format_belegdatum(date(2026, 3, 2)) == "203"

    def test_belegdatum_march_10(self) -> None:
        assert _format_belegdatum(date(2026, 3, 10)) == "1003"

    def test_belegdatum_march_27(self) -> None:
        assert _format_belegdatum(date(2026, 3, 27)) == "2703"

    def test_decimal_format_comma(self) -> None:
        assert _format_decimal(Decimal("1234.56")) == "1234,56"

    def test_decimal_format_two_decimals(self) -> None:
        assert _format_decimal(Decimal("47.6")) == "47,60"

    def test_decimal_negative_becomes_positive(self) -> None:
        # gross sums for credit notes are still positive
        assert _format_decimal(Decimal("-10.52")) == "10,52"


class TestSmoke:
    def test_writes_header_and_data_rows(self) -> None:
        invoices = [
            _invoice("DE", "DE", invoice_no="R-001"),
            _invoice("DE", "IT", invoice_no="R-002"),
        ]
        settings = _settings()

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)

        report = write_extf_buchungsstapel(
            iter(invoices),
            out_path=out,
            settings=settings,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            decisions_by_invoice=_decisions,
        )

        assert isinstance(report, ExportReport)
        assert report.bookings_written == 2

        with out.open(encoding="cp1252", newline="") as fh:
            content = fh.read()

        lines = content.split("\r\n")
        # row 1: EXTF header, row 2: column names, row 3+: data, last is empty
        assert lines[0].startswith("EXTF;700;21;Buchungsstapel")
        assert "Umsatz (ohne Soll/Haben-Kz)" in lines[1]
        assert len([row for row in lines[2:] if row.strip()]) == 2

        out.unlink()

    def test_encoding_cp1252(self) -> None:
        invoices = [_invoice("DE", "DE")]
        settings = _settings()

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)

        write_extf_buchungsstapel(
            iter(invoices),
            out_path=out,
            settings=settings,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            decisions_by_invoice=_decisions,
        )

        # Must be readable as cp1252
        content = out.read_bytes().decode("cp1252")
        assert "EXTF" in content
        out.unlink()

    def test_parseable_with_csv_reader(self) -> None:
        invoices = [_invoice("DE", "DE"), _invoice("FR", "IT")]
        settings = _settings()

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)

        write_extf_buchungsstapel(
            iter(invoices),
            out_path=out,
            settings=settings,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            decisions_by_invoice=_decisions,
        )

        with out.open(encoding="cp1252", newline="") as fh:
            rows = list(csv.reader(fh, delimiter=";"))

        # Row 0: EXTF header (124 cols)
        assert len(rows[0]) == 124
        # Row 1: column names (124 cols)
        assert len(rows[1]) == 124
        # Data rows: 2 invoices → 2 booking rows
        data_rows = rows[2:]
        assert len(data_rows) >= 2
        out.unlink()


class TestFieldContent:
    def _get_data_rows(self, invoices: list[RawInvoice]) -> list[list[str]]:
        settings = _settings()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)
        write_extf_buchungsstapel(
            iter(invoices),
            out_path=out,
            settings=settings,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            decisions_by_invoice=_decisions,
        )
        with out.open(encoding="cp1252", newline="") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        out.unlink()
        return rows[2:]  # skip header rows

    def test_belegdatum_format(self) -> None:
        inv = _invoice(invoice_date=date(2026, 3, 2))
        rows = self._get_data_rows([inv])
        assert rows[0][9] == "203"  # col 10 = index 9

    def test_sh_rechnung_is_s(self) -> None:
        inv = _invoice(is_credit_note=False)
        rows = self._get_data_rows([inv])
        assert rows[0][1] == "S"

    def test_sh_gutschrift_is_h(self) -> None:
        inv = _invoice(is_credit_note=True)
        rows = self._get_data_rows([inv])
        assert rows[0][1] == "H"

    def test_konto_amazon_debitor(self) -> None:
        inv = _invoice(payment_method="AmazonPayments")
        rows = self._get_data_rows([inv])
        assert rows[0][6] == "10005000"  # col 7 = index 6

    def test_gegenkonto_de_domestic(self) -> None:
        inv = _invoice("DE", "DE")
        rows = self._get_data_rows([inv])
        assert rows[0][7] == "4400000"  # col 8 = index 7

    def test_bu_key_oss_de_lager(self) -> None:
        inv = _invoice("DE", "IT")
        rows = self._get_data_rows([inv])
        assert rows[0][7] == "4320000"
        assert rows[0][8] == "240"  # BU key

    def test_bu_key_oss_fr_lager(self) -> None:
        inv = _invoice("FR", "IT")
        rows = self._get_data_rows([inv])
        assert rows[0][7] == "4320000"
        assert rows[0][8] == "241"

    def test_veranlagungsjahr(self) -> None:
        inv = _invoice(invoice_date=date(2026, 3, 2))
        rows = self._get_data_rows([inv])
        assert rows[0][91] == "2026"

    def test_eu_ursprung_for_non_de_warehouse(self) -> None:
        inv = _invoice("FR", "IT")
        rows = self._get_data_rows([inv])
        # col 123 (index 122) = EU-Land+UStID Ursprung
        assert rows[0][122] == "FR54820509628"

    def test_eu_ursprung_empty_for_de_warehouse(self) -> None:
        inv = _invoice("DE", "DE")
        rows = self._get_data_rows([inv])
        assert rows[0][122] == ""

    def test_eu_land_bestimmung_oss(self) -> None:
        inv = _invoice("DE", "IT")
        rows = self._get_data_rows([inv])
        assert rows[0][39] == "IT"  # col 40 = index 39

    def test_eu_satz_bestimmung_oss_it(self) -> None:
        inv = _invoice("DE", "IT")
        rows = self._get_data_rows([inv])
        assert rows[0][40] == "22"  # IT standard VAT rate


class TestHeaderFields:
    def test_mandant_in_header(self) -> None:
        settings = _settings()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)
        write_extf_buchungsstapel(
            iter([_invoice()]),
            out_path=out,
            settings=settings,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            decisions_by_invoice=_decisions,
        )
        with out.open(encoding="cp1252", newline="") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        out.unlink()

        header = rows[0]
        assert header[10] == "14974"   # col 11 = Mandantennummer
        assert header[11] == "10305"   # col 12 = Beraternummer
        assert header[13] == "7"       # col 14 = Account length

    def test_date_range_in_header(self) -> None:
        settings = _settings()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)
        write_extf_buchungsstapel(
            iter([_invoice()]),
            out_path=out,
            settings=settings,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            decisions_by_invoice=_decisions,
        )
        with out.open(encoding="cp1252", newline="") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        out.unlink()

        header = rows[0]
        assert header[14] == "20260301"   # col 15 = Datum von
        assert header[15] == "20260331"   # col 16 = Datum bis


class TestSkipRules:
    def test_unknown_treatment_skipped(self) -> None:
        # Force UNKNOWN by providing a line with 0% VAT and no VAT ID
        zero_line = _line(vat_rate=Decimal("0"), gross=Decimal("100"), net=Decimal("100"))
        inv_zero = _invoice("DE", "IT", lines=(zero_line,))

        settings = _settings()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)
        report = write_extf_buchungsstapel(
            iter([inv_zero]),
            out_path=out,
            settings=settings,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            decisions_by_invoice=_decisions,
        )
        out.unlink()

        # Belege are now written as placeholder rows with empty Gegenkonto
        # and "UNKNOWN" / "ERROR" in Belegfeld 2 — never silently dropped.
        assert report.bookings_written == 1
        assert report.skipped_unknown == 1

    def test_error_mismatch_skipped(self) -> None:
        """IGL B2B line with non-zero vat_amount triggers error skip."""
        bad_line = RawInvoiceLine(
            line_no=1,
            net=Decimal("100"),
            gross=Decimal("119"),  # non-zero VAT despite B2B 0%
            vat_amount=Decimal("19"),
            vat_rate=Decimal("0"),
        )
        inv = _invoice("DE", "FR", vat_id="FR12345678901", lines=(bad_line,))

        def forced_decisions(invoice: RawInvoice) -> list[LineDecision]:
            d = TaxDecision(
                treatment=TaxTreatment.IGL_B2B,
                expected_vat_rate=Decimal("0"),
                tax_country="DE",
                cleaned_vat_id="FR12345678901",
            )
            return [LineDecision(line=bad_line, decision=d)]

        settings = _settings()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)
        report = write_extf_buchungsstapel(
            iter([inv]),
            out_path=out,
            settings=settings,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            decisions_by_invoice=forced_decisions,
        )
        out.unlink()

        assert report.bookings_written == 1
        assert report.skipped_error == 1

    def test_error_placeholder_has_marker_and_empty_gegenkonto(self) -> None:
        bad_line = RawInvoiceLine(
            line_no=1,
            net=Decimal("100"), gross=Decimal("119"),
            vat_amount=Decimal("19"), vat_rate=Decimal("0"),
        )
        inv = _invoice("DE", "FR", vat_id="FR12345678901", lines=(bad_line,))

        def forced(invoice: RawInvoice) -> list[LineDecision]:
            d = TaxDecision(
                treatment=TaxTreatment.IGL_B2B,
                expected_vat_rate=Decimal("0"),
                tax_country="DE",
                cleaned_vat_id="FR12345678901",
            )
            return [LineDecision(line=bad_line, decision=d)]

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)
        try:
            write_extf_buchungsstapel(
                iter([inv]), out_path=out, settings=_settings(),
                date_from=date(2026, 3, 1), date_to=date(2026, 3, 31),
                decisions_by_invoice=forced,
            )
            with open(out, encoding="cp1252", newline="") as fh:
                import csv as _csv
                rows = list(_csv.reader(fh, delimiter=";"))
        finally:
            out.unlink()

        assert len(rows) == 3  # EXTF header + column header + 1 booking
        booking = rows[2]
        assert booking[7] == ""   # Gegenkonto leer
        assert booking[8] == ""   # BU leer
        assert booking[11] == "ERROR"


class TestPartyAddressDisplayName:
    def test_company_wins(self) -> None:
        addr = PartyAddress(country_iso="DE", first_name="Max", last_name="Muster", company="Acme GmbH")
        assert addr.display_name() == "Acme GmbH"

    def test_first_and_last(self) -> None:
        addr = PartyAddress(country_iso="DE", first_name="Max", last_name="Mustermann")
        assert addr.display_name() == "Mustermann Max"

    def test_last_name_only(self) -> None:
        addr = PartyAddress(country_iso="DE", last_name="Mustermann")
        assert addr.display_name() == "Mustermann"

    def test_empty_when_no_names(self) -> None:
        addr = PartyAddress(country_iso="DE")
        assert addr.display_name() == ""

    def test_strips_whitespace(self) -> None:
        addr = PartyAddress(country_iso="DE", company="  Acme GmbH  ")
        assert addr.display_name() == "Acme GmbH"


class TestSanitizeBuchungstext:
    def test_semicolon_replaced(self) -> None:
        assert ";" not in _sanitize_buchungstext("R-001; foo")

    def test_newline_replaced(self) -> None:
        assert "\n" not in _sanitize_buchungstext("R-001\nfoo")

    def test_max_60_chars(self) -> None:
        long_text = "R-" + "X" * 100
        result = _sanitize_buchungstext(long_text)
        assert len(result) <= 60


class TestBuchungstextWithCustomerName:
    def _get_data_rows(self, invoices: list[RawInvoice]) -> list[list[str]]:
        settings = _settings()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)
        write_extf_buchungsstapel(
            iter(invoices),
            out_path=out,
            settings=settings,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            decisions_by_invoice=_decisions,
        )
        with out.open(encoding="cp1252", newline="") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        out.unlink()
        return rows[2:]

    def test_buchungstext_contains_customer_name(self) -> None:
        addr = PartyAddress(country_iso="DE", first_name="Max", last_name="Mustermann")
        inv = _invoice(invoice_no="R-DE-2026-001", bill_to=addr)
        rows = self._get_data_rows([inv])
        buchungstext = rows[0][13]  # col 14 = index 13
        assert "Mustermann Max" in buchungstext
        assert buchungstext.startswith("R-DE-2026-001")

    def test_beleginfo3_kundenname_filled(self) -> None:
        addr = PartyAddress(country_iso="DE", first_name="Max", last_name="Mustermann")
        inv = _invoice(invoice_no="R-DE-2026-001", bill_to=addr)
        rows = self._get_data_rows([inv])
        assert rows[0][24] == "Kundenname"   # Beleginfo Art 3
        assert rows[0][25] == "Mustermann Max"  # Beleginfo Inhalt 3

    def test_buchungstext_no_name_when_empty(self) -> None:
        inv = _invoice(invoice_no="R-DE-2026-001")
        rows = self._get_data_rows([inv])
        buchungstext = rows[0][13]
        assert buchungstext == "R-DE-2026-001"

    def test_beleginfo3_empty_when_no_name(self) -> None:
        inv = _invoice(invoice_no="R-DE-2026-001")
        rows = self._get_data_rows([inv])
        assert rows[0][25] == ""

    def test_buchungstext_max_60_chars(self) -> None:
        addr = PartyAddress(country_iso="DE", company="Sehr langer Firmenname GmbH & Co. KG XYZ")
        inv = _invoice(invoice_no="R-DE-249030238-2026-322", bill_to=addr)
        rows = self._get_data_rows([inv])
        assert len(rows[0][13]) <= 60


class TestZeroAmountFilter:
    """Probebuchungen mit Brutto-Summe = 0,00 € werden standardmäßig ausgefiltert."""

    def _write(self, invoices: list[RawInvoice], *, keep_zero_amount: bool = False) -> ExportReport:
        settings = _settings()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)
        report = write_extf_buchungsstapel(
            iter(invoices),
            out_path=out,
            settings=settings,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            decisions_by_invoice=_decisions,
            keep_zero_amount=keep_zero_amount,
        )
        out.unlink()
        return report

    def _zero_invoice(self, invoice_no: str) -> RawInvoice:
        line = RawInvoiceLine(
            line_no=1,
            net=Decimal("0.00"),
            gross=Decimal("0.00"),
            vat_amount=Decimal("0.00"),
            vat_rate=Decimal("19"),
        )
        inv = _invoice(invoice_no=invoice_no)
        return RawInvoice(
            source=inv.source,
            invoice_no=inv.invoice_no,
            invoice_date=inv.invoice_date,
            currency=inv.currency,
            currency_factor=inv.currency_factor,
            warehouse_country=inv.warehouse_country,
            ship_to=inv.ship_to,
            bill_to=inv.bill_to,
            is_credit_note=inv.is_credit_note,
            lines=(line,),
            jtl_external_order_no=inv.jtl_external_order_no,
            marketplace_country=inv.marketplace_country,
        )

    def test_zero_amount_beleg_skipped_by_default(self) -> None:
        zero = self._zero_invoice("SR202602155")
        report = self._write([zero])
        assert report.bookings_written == 0
        assert report.skipped_zero_amount == 1

    def test_keep_zero_amount_flag_disables_filter(self) -> None:
        zero = self._zero_invoice("SR202602156")
        report = self._write([zero], keep_zero_amount=True)
        assert report.skipped_zero_amount == 0
        # Buchungen können 0 sein (kein Fehler-Skip), aber der Filter greift nicht.

    def test_normal_beleg_not_filtered(self) -> None:
        normal = _invoice(invoice_no="R-DE-2026-001")
        report = self._write([normal])
        assert report.skipped_zero_amount == 0
        assert report.bookings_written >= 1

    def test_zero_and_normal_mixed(self) -> None:
        zero = self._zero_invoice("SR202602155")
        normal = _invoice(invoice_no="R-DE-2026-002")
        report = self._write([zero, normal])
        assert report.skipped_zero_amount == 1
        assert report.bookings_written >= 1


class TestForeignCurrency:
    """EXTF Buchungsstapel: WKZ/Kurs/Basis-Umsatz columns for non-EUR invoices."""

    def _get_data_row(self, invoice: RawInvoice) -> list[str]:
        settings = _settings()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            out = Path(tmp.name)
        write_extf_buchungsstapel(
            iter([invoice]),
            out_path=out,
            settings=settings,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            decisions_by_invoice=_decisions,
        )
        with out.open(encoding="cp1252", newline="") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        out.unlink()
        return rows[2]  # first data row

    def test_eur_invoice_fx_columns_empty(self) -> None:
        inv = _invoice(currency="EUR", currency_factor=Decimal("1"))
        row = self._get_data_row(inv)
        assert row[2] == ""   # WKZ Umsatz
        assert row[3] == ""   # Kurs
        assert row[4] == ""   # Basis-Umsatz
        assert row[5] == ""   # WKZ Basis-Umsatz

    def test_gbp_invoice_fx_columns_filled(self) -> None:
        # 22,26 GBP at factor 0.8719 → Basis-Umsatz = 22.26 / 0.8719 = 25.53
        gbp_line = _line(
            gross=Decimal("22.26"),
            net=Decimal("22.26"),
            vat_rate=Decimal("0"),
        )
        inv = _invoice(
            wh="GB",
            dest="GB",
            invoice_no="FR500071NL56FD",
            currency="GBP",
            currency_factor=Decimal("0.8719"),
            lines=(gbp_line,),
        )
        row = self._get_data_row(inv)
        assert row[2] == "GBP"    # WKZ Umsatz
        assert row[3] == "0,8719" # Kurs
        assert row[4] == "25,53"  # Basis-Umsatz
        assert row[5] == "EUR"    # WKZ Basis-Umsatz

    def test_gbp_refund_basis_umsatz_same_sign_as_umsatz(self) -> None:
        # _format_decimal uses abs() for Umsatz; Basis-Umsatz must match.
        # Engine writes abs value; sign is controlled by S/H-Kennzeichen.
        gbp_line = _line(
            gross=Decimal("-22.26"),
            net=Decimal("-22.26"),
            vat_rate=Decimal("0"),
        )
        inv = _invoice(
            wh="GB",
            dest="GB",
            invoice_no="FR500071NL56FD-R",
            is_credit_note=True,
            currency="GBP",
            currency_factor=Decimal("0.8719"),
            lines=(gbp_line,),
        )
        row = self._get_data_row(inv)
        # Both Umsatz and Basis-Umsatz must be positive absolute values
        assert row[0] == "22,26"
        assert row[4] == "25,53"

    def test_format_kurs_four_decimals(self) -> None:
        assert _format_kurs(Decimal("0.8719")) == "0,8719"
        assert _format_kurs(Decimal("1")) == "1,0000"
        assert _format_kurs(Decimal("1.2")) == "1,2000"
