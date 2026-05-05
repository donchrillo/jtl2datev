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
        quantity=Decimal("1"),
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
) -> RawInvoice:
    if lines is None:
        lines = (_line(),)
    return RawInvoice(
        source="jtl_external",
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        currency="EUR",
        currency_factor=Decimal("1"),
        warehouse_country=wh,
        ship_to=PartyAddress(country_iso=dest),
        bill_to=PartyAddress(country_iso=dest, vat_id=vat_id),
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

        assert report.bookings_written == 0
        assert report.skipped_unknown == 1

    def test_error_mismatch_skipped(self) -> None:
        """IGL B2B line with non-zero vat_amount triggers error skip."""
        bad_line = RawInvoiceLine(
            line_no=1,
            quantity=Decimal("1"),
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

        assert report.bookings_written == 0
        assert report.skipped_error == 1
