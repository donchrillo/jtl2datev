from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

from jtl2datev.core.config import Settings
from jtl2datev.core.models import LineDecision, RawInvoice, TaxTreatment
from jtl2datev.core.rules import DatevAccount, map_to_datev_account, map_to_debitor_account
from jtl2datev.core.tax_engine import STANDARD_VAT_RATE

logger = logging.getLogger(__name__)

# Exact column header row — 124 columns matching the EXTF Buchungsstapel v7 format
_COLUMN_HEADER = (
    "Umsatz (ohne Soll/Haben-Kz);"
    "Soll/Haben-Kennzeichen;"
    "WKZ Umsatz;"
    "Kurs;"
    "Basis-Umsatz;"
    "WKZ Basis-Umsatz;"
    "Konto;"
    "Gegenkonto (ohne BU-Schlüssel);"
    "BU-Schlüssel;"
    "Belegdatum;"
    "Belegfeld 1;"
    "Belegfeld 2;"
    "Skonto;"
    "Buchungstext;"
    "Postensperre;"
    "Diverse Adressnummer;"
    "Geschäftspartnerbank;"
    "Sachverhalt;"
    "Zinssperre;"
    "Beleglink;"
    "Beleginfo - Art 1;"
    "Beleginfo - Inhalt 1;"
    "Beleginfo - Art 2;"
    "Beleginfo - Inhalt 2;"
    "Beleginfo - Art 3;"
    "Beleginfo - Inhalt 3;"
    "Beleginfo - Art 4;"
    "Beleginfo - Inhalt 4;"
    "Beleginfo - Art 5;"
    "Beleginfo - Inhalt 5;"
    "Beleginfo - Art 6;"
    "Beleginfo - Inhalt 6;"
    "Beleginfo - Art 7;"
    "Beleginfo - Inhalt 7;"
    "Beleginfo - Art 8;"
    "Beleginfo - Inhalt 8;"
    "KOST1 - Kostenstelle;"
    "KOST2 - Kostenstelle;"
    "Kost-Menge;"
    "EU-Land und UStID (Bestimmung);"
    "EU-Steuersatz (Bestimmung);"
    "Abw. Versteuerungsart;"
    "Sachverhalt L+L;"
    "Funktionsergänzung L+L;"
    "BU 49 Hauptfunktionstyp;"
    "BU 49 Hauptfunktionsnummer;"
    "BU 49 Funktionsergänzung;"
    "Zusatzinformation - Art 1;"
    "Zusatzinformation- Inhalt 1;"
    "Zusatzinformation - Art 2;"
    "Zusatzinformation- Inhalt 2;"
    "Zusatzinformation - Art 3;"
    "Zusatzinformation- Inhalt 3;"
    "Zusatzinformation - Art 4;"
    "Zusatzinformation- Inhalt 4;"
    "Zusatzinformation - Art 5;"
    "Zusatzinformation- Inhalt 5;"
    "Zusatzinformation - Art 6;"
    "Zusatzinformation- Inhalt 6;"
    "Zusatzinformation - Art 7;"
    "Zusatzinformation- Inhalt 7;"
    "Zusatzinformation - Art 8;"
    "Zusatzinformation- Inhalt 8;"
    "Zusatzinformation - Art 9;"
    "Zusatzinformation- Inhalt 9;"
    "Zusatzinformation - Art 10;"
    "Zusatzinformation- Inhalt 10;"
    "Zusatzinformation - Art 11;"
    "Zusatzinformation- Inhalt 11;"
    "Zusatzinformation - Art 12;"
    "Zusatzinformation- Inhalt 12;"
    "Zusatzinformation - Art 13;"
    "Zusatzinformation- Inhalt 13;"
    "Zusatzinformation - Art 14;"
    "Zusatzinformation- Inhalt 14;"
    "Zusatzinformation - Art 15;"
    "Zusatzinformation- Inhalt 15;"
    "Zusatzinformation - Art 16;"
    "Zusatzinformation- Inhalt 16;"
    "Zusatzinformation - Art 17;"
    "Zusatzinformation- Inhalt 17;"
    "Zusatzinformation - Art 18;"
    "Zusatzinformation- Inhalt 18;"
    "Zusatzinformation - Art 19;"
    "Zusatzinformation- Inhalt 19;"
    "Zusatzinformation - Art 20;"
    "Zusatzinformation- Inhalt 20;"
    "Stück;"
    "Gewicht;"
    "Zahlweise;"
    "Forderungsart;"
    "Veranlagungsjahr;"
    "Zugeordnete Fälligkeit;"
    "Skontotyp;"
    "Auftragsnummer;"
    "Buchungstyp;"
    "Ust-Schlüssel (Anzahlungen);"
    "EU-Land (Anzahlungen);"
    "Sachverhalt L+L (Anzahlungen);"
    "EU-Steuersatz (Anzahlungen);"
    "Erlöskonto (Anzahlungen);"
    "Herkunft-Kz;"
    "Leerfeld;"
    "KOST-Datum;"
    "Mandatsreferenz;"
    "Skontosperre;"
    "Gesellschaftername;"
    "Beteiligtennummer;"
    "Identifikationsnummer;"
    "Zeichnernummer;"
    "Postensperre bis;"
    "Bezeichnung SoBil-Sachverhalt;"
    "Kennzeichen SoBil-Buchung;"
    "Festschreibung;"
    "Leistungsdatum;"
    "Datum Zuord.Steuerperiode;"
    "Fälligkeit;"
    "Generalumkehr (GU);"
    "Steuersatz;"
    "Land;"
    "Abrechnungsreferenz;"
    "BVV-Postion;"
    "EU-Land und UStID (Ursprung);"
    "EU-Steuersatz (Ursprung)"
)

_NUM_COLS = 124

# Column indices (0-based) for the fields we populate
_IDX_UMSATZ = 0
_IDX_SH = 1
_IDX_KONTO = 6
_IDX_GEGENKONTO = 7
_IDX_BU = 8
_IDX_BELEGDATUM = 9
_IDX_BELEGFELD1 = 10
_IDX_BELEGFELD2 = 11
_IDX_BUCHUNGSTEXT = 13
_IDX_BELEGLINK = 19  # Spalte 20 "Beleglink" — wir nutzen sie für den Audit-Tag (--audit)
_IDX_BELEGINFO_ART1 = 20
_IDX_BELEGINFO_INH1 = 21
_IDX_BELEGINFO_ART2 = 22
_IDX_BELEGINFO_INH2 = 23
_IDX_BELEGINFO_ART3 = 24
_IDX_BELEGINFO_INH3 = 25
_IDX_BELEGINFO_ART4 = 26
_IDX_BELEGINFO_INH4 = 27
_IDX_BELEGINFO_ART5 = 28
_IDX_BELEGINFO_INH5 = 29
_IDX_EU_LAND_BESTIMMUNG = 39
_IDX_EU_SATZ_BESTIMMUNG = 40
_IDX_VERANLAGUNGSJAHR = 91
_IDX_FESTSCHREIBUNG = 113
_IDX_EU_LAND_URSPRUNG = 122
_IDX_EU_SATZ_URSPRUNG = 123


@dataclass
class SkippedBeleg:
    invoice_no: str
    reason: str
    severity: str  # "unknown" | "error"


@dataclass
class ExportReport:
    bookings_written: int = 0
    skipped_error: int = 0
    skipped_unknown: int = 0
    skipped_details: list[SkippedBeleg] = field(default_factory=list)
    diff_marked: int = 0  # bookings marked with "X" in Belegfeld 2 (compare-to mismatch)


def load_compare_map(path: Path) -> dict[str, set[tuple[str, str]]]:
    """Read an existing DATEV CSV and index it by invoice number.

    The match key is the first whitespace-separated token of the Buchungstext,
    which is the invoice / Belegnummer (e.g. "R-DE-249030238-2026-322" out of
    "R-DE-249030238-2026-322 Kruse Cora"). Belegfeld 1 is *not* used as the
    key because its meaning has shifted over time (customer number until end
    of 2025, external order ID since January 2026; manual edits afterwards).

    Returns: invoice_no → set of (Konto, BU-Schlüssel) used in the reference.
    """
    out: dict[str, set[tuple[str, str]]] = {}
    with path.open(encoding="cp1252", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    for r in rows[2:]:
        if len(r) < 14:
            continue
        konto = r[7]
        bu = r[8]
        buchungstext = r[13]
        invoice_no = buchungstext.split(" ", 1)[0].strip() if buchungstext else ""
        if not invoice_no:
            continue
        out.setdefault(invoice_no, set()).add((konto, bu))
    return out


def _format_decimal(val: Decimal) -> str:
    return f"{abs(val):.2f}".replace(".", ",")


def _format_belegdatum(d: date) -> str:
    """DDMM: day without leading zero, month with leading zero."""
    return f"{d.day}{d.month:02d}"


def _to_cp1252(val: str) -> str:
    """Replace characters not encodable in cp1252 with '?'."""
    return val.encode("cp1252", errors="replace").decode("cp1252")


def _safe_text(val: str | None) -> str:
    """Strip semicolons and newlines to prevent CSV corruption; ensure cp1252-safe."""
    if not val:
        return ""
    cleaned = val.replace(";", " ").replace("\n", " ").replace("\r", " ").strip()
    return _to_cp1252(cleaned)


_BUCHUNGSTEXT_MAX_LEN = 60


def _sanitize_buchungstext(val: str) -> str:
    """Remove DATEV-problematic characters, ensure cp1252-safe, enforce 60-char limit."""
    cleaned = val.replace(";", " ").replace("\n", " ").replace("\r", " ").strip()
    return _to_cp1252(cleaned)[:_BUCHUNGSTEXT_MAX_LEN]


def _customer_name(invoice: RawInvoice) -> str:
    return invoice.bill_to.display_name()


def _make_extf_header(
    *,
    settings: Settings,
    date_from: date,
    date_to: date,
    timestamp: datetime,
) -> str:
    ts = timestamp.strftime("%Y%m%d%H%M%S") + "000"
    wj = settings.datev_wj_start.strftime("%Y%m%d")
    df = date_from.strftime("%Y%m%d")
    dt = date_to.strftime("%Y%m%d")
    bezeichnung = f"Belege {date_from.strftime('%Y/%m')}"
    # 124 fields — after field 22 (EUR) fill with empty until end
    # Fields: EXTF;700;21;Buchungsstapel;12;ts;;jtl2datev;jtl2datev;;mandant;berater;wj;acct_len;from;to;bez;jtl2datev;1;0;0;EUR;<102 empty>
    prefix = (
        f"EXTF;700;21;Buchungsstapel;12;{ts};;jtl2datev;jtl2datev;;"
        f"{settings.datev_mandantennr};{settings.datev_beraternr};"
        f"{wj};{settings.datev_account_length};"
        f"{df};{dt};{bezeichnung};jtl2datev;1;0;0;EUR"
    )
    # 22 fields so far, need 124 total → 102 more empty
    empties = ";" * (124 - 22)
    return prefix + empties


def _build_row(
    *,
    invoice: RawInvoice,
    gross_sum: Decimal,
    account: DatevAccount,
    debitor: str,
    decision_for_eu_cols: LineDecision | None,
    settings: Settings,
    buchungstext: str,
    customer_name: str = "",
    audit: bool = False,
) -> list[str]:
    row: list[str] = [""] * _NUM_COLS

    row[_IDX_UMSATZ] = _format_decimal(gross_sum)
    row[_IDX_SH] = "H" if invoice.is_credit_note else "S"
    row[_IDX_KONTO] = debitor
    row[_IDX_GEGENKONTO] = account.account
    row[_IDX_BU] = account.bu_key
    row[_IDX_BELEGDATUM] = _format_belegdatum(invoice.invoice_date)
    row[_IDX_BELEGFELD1] = _safe_text(invoice.jtl_external_order_no or "")
    row[_IDX_BUCHUNGSTEXT] = _safe_text(buchungstext)
    if audit and account.audit_tag:
        row[_IDX_BELEGLINK] = account.audit_tag

    # Beleginfo 1: Externerauftrag
    row[_IDX_BELEGINFO_ART1] = "Externerauftrag"
    row[_IDX_BELEGINFO_INH1] = _safe_text(invoice.jtl_external_order_no or "")
    # Beleginfo 2: KundenNr
    row[_IDX_BELEGINFO_ART2] = "KundenNr"
    row[_IDX_BELEGINFO_INH2] = _safe_text(invoice.customer_no or "")
    # Beleginfo 3: Kundenname
    row[_IDX_BELEGINFO_ART3] = "Kundenname"
    row[_IDX_BELEGINFO_INH3] = _safe_text(customer_name)
    # Beleginfo 4: geliefert aus
    row[_IDX_BELEGINFO_ART4] = "geliefert aus"
    row[_IDX_BELEGINFO_INH4] = invoice.warehouse_country
    # Beleginfo 5: geliefert nach
    row[_IDX_BELEGINFO_ART5] = "geliefert nach"
    row[_IDX_BELEGINFO_INH5] = invoice.ship_to.country_iso

    # EU columns (skip when no decision is available — error/unknown placeholder rows)
    if decision_for_eu_cols is not None:
        treatment = decision_for_eu_cols.decision.treatment
        if treatment == TaxTreatment.OSS_B2C:
            row[_IDX_EU_LAND_BESTIMMUNG] = invoice.ship_to.country_iso
            dest_rate = STANDARD_VAT_RATE.get(invoice.ship_to.country_iso)
            if dest_rate is not None:
                row[_IDX_EU_SATZ_BESTIMMUNG] = str(int(dest_rate) if dest_rate == int(dest_rate) else dest_rate)
        elif treatment == TaxTreatment.IGL_B2B:
            vat_id = decision_for_eu_cols.decision.cleaned_vat_id
            if vat_id:
                row[_IDX_EU_LAND_BESTIMMUNG] = vat_id

    # EU Ursprung: our own VAT ID when warehouse is non-DE
    if invoice.warehouse_country != "DE":
        own_vat = settings.own_vat_ids.get(invoice.warehouse_country, "")
        if own_vat:
            row[_IDX_EU_LAND_URSPRUNG] = own_vat

    # Veranlagungsjahr
    row[_IDX_VERANLAGUNGSJAHR] = str(invoice.invoice_date.year)

    # Festschreibung = 0 (not locked)
    row[_IDX_FESTSCHREIBUNG] = "0"

    return row


def write_extf_buchungsstapel(
    invoices: Iterable[RawInvoice],
    *,
    out_path: Path,
    settings: Settings,
    date_from: date,
    date_to: date,
    decisions_by_invoice: Callable[[RawInvoice], list[LineDecision]],
    compare_map: dict[str, set[tuple[str, str]]] | None = None,
    audit: bool = False,
) -> ExportReport:
    """Write EXTF Buchungsstapel CSV from invoices iterator."""
    report = ExportReport()
    timestamp = datetime.now(tz=timezone.utc)

    with out_path.open("w", encoding="cp1252", newline="") as fh:
        # Row 1: EXTF header
        fh.write(_make_extf_header(settings=settings, date_from=date_from, date_to=date_to, timestamp=timestamp))
        fh.write("\r\n")

        # Row 2: column header
        fh.write(_COLUMN_HEADER)
        fh.write("\r\n")

        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

        for invoice in invoices:
            # Temu pilot (late 2025) was rolled back. The imported orders carry
            # external order IDs starting with "PO-". They must not appear in
            # the DATEV export. DutyPay intentionally keeps them (DE→DE B2C).
            ext_no = invoice.jtl_external_order_no or ""
            if ext_no.startswith("PO"):
                logger.debug("DATEV export: skipping Temu beleg %s (%s)", invoice.invoice_no, ext_no)
                continue

            line_decisions = decisions_by_invoice(invoice)

            debitor = map_to_debitor_account(
                invoice,
                payment_method=invoice.payment_method,
                default=settings.datev_default_debitor,
            )
            customer_name = _customer_name(invoice)
            buchungstext = _sanitize_buchungstext(
                f"{invoice.invoice_no} {customer_name}".strip()
            )

            # Detect error / unknown belege — these still get a row but with
            # an empty Gegenkonto and a marker in Belegfeld 2 so the operator
            # can filter and correct manually instead of silently losing them.
            has_error = _has_error_mismatch(invoice, line_decisions)
            has_unknown = any(
                ld.decision.treatment == TaxTreatment.UNKNOWN for ld in line_decisions
            )
            problem_marker = ""
            if has_error:
                problem_marker = "ERROR"
                report.skipped_error += 1
                report.skipped_details.append(
                    SkippedBeleg(invoice.invoice_no, "error-level mismatch", "error")
                )
                logger.warning("DATEV export: %s flagged ERROR", invoice.invoice_no)
            elif has_unknown:
                problem_marker = "UNKNOWN"
                report.skipped_unknown += 1
                report.skipped_details.append(
                    SkippedBeleg(invoice.invoice_no, "UNKNOWN treatment", "unknown")
                )
                logger.warning("DATEV export: %s flagged UNKNOWN", invoice.invoice_no)

            if problem_marker:
                # Single placeholder row with empty Gegenkonto. Sum gross over
                # all lines so the operator at least sees the order total.
                gross_sum = sum((ld.line.gross for ld in line_decisions), Decimal("0"))
                first_ld = line_decisions[0] if line_decisions else None
                placeholder = DatevAccount(account="", bu_key="", audit_tag=problem_marker)
                row = _build_row(
                    invoice=invoice,
                    gross_sum=gross_sum,
                    account=placeholder,
                    debitor=debitor,
                    decision_for_eu_cols=first_ld,
                    settings=settings,
                    buchungstext=buchungstext,
                    customer_name=customer_name,
                    audit=audit,
                )
                row[_IDX_BELEGFELD2] = problem_marker
                writer.writerow(row)
                report.bookings_written += 1
                continue

            # Resolve account + debitor for each line
            line_accounts: list[tuple[LineDecision, DatevAccount]] = []
            for ld in line_decisions:
                acc = map_to_datev_account(invoice, ld.line, ld.decision)
                if acc.account == "0000000":
                    # Unmapped — treat as UNKNOWN going forward so we still
                    # write a placeholder row instead of dropping the booking.
                    logger.warning(
                        "DATEV export: no account for %s line %d (%s) — flagging UNKNOWN",
                        invoice.invoice_no, ld.line.line_no, acc.note,
                    )
                    line_accounts = []
                    break
                line_accounts.append((ld, acc))

            if not line_accounts:
                gross_sum = sum((ld.line.gross for ld in line_decisions), Decimal("0"))
                placeholder = DatevAccount(account="", bu_key="", audit_tag="UNKNOWN")
                row = _build_row(
                    invoice=invoice,
                    gross_sum=gross_sum,
                    account=placeholder,
                    debitor=debitor,
                    decision_for_eu_cols=line_decisions[0] if line_decisions else None,
                    settings=settings,
                    buchungstext=buchungstext,
                    customer_name=customer_name,
                    audit=audit,
                )
                row[_IDX_BELEGFELD2] = "UNKNOWN"
                report.skipped_unknown += 1
                writer.writerow(row)
                report.bookings_written += 1
                continue

            # Group lines by (account, bu_key) — aggregate gross + keep audit_tag
            groups: dict[tuple[str, str], tuple[Decimal, LineDecision, str]] = {}
            for ld, acc in line_accounts:
                key = (acc.account, acc.bu_key)
                if key not in groups:
                    groups[key] = (Decimal("0"), ld, acc.audit_tag)
                prev_sum, first_ld, tag = groups[key]
                groups[key] = (prev_sum + ld.line.gross, first_ld, tag)

            for (acct_no, bu_key), (gross_sum, first_ld, tag) in groups.items():
                datev_acct = DatevAccount(account=acct_no, bu_key=bu_key, audit_tag=tag)
                row = _build_row(
                    invoice=invoice,
                    gross_sum=gross_sum,
                    account=datev_acct,
                    debitor=debitor,
                    decision_for_eu_cols=first_ld,
                    settings=settings,
                    buchungstext=buchungstext,
                    customer_name=customer_name,
                    audit=audit,
                )
                if compare_map is not None:
                    ref = compare_map.get(invoice.invoice_no)
                    if ref is not None and (acct_no, bu_key) not in ref:
                        # Don't overwrite ERROR/UNKNOWN markers with X
                        if not row[_IDX_BELEGFELD2]:
                            row[_IDX_BELEGFELD2] = "X"
                            report.diff_marked += 1
                writer.writerow(row)
                report.bookings_written += 1

    logger.info(
        "DATEV export complete: %d bookings written, %d error-skipped, %d unknown-skipped",
        report.bookings_written,
        report.skipped_error,
        report.skipped_unknown,
    )
    return report


def _has_error_mismatch(invoice: RawInvoice, line_decisions: list[LineDecision]) -> bool:
    """Check if any line has an error-level reconcile condition.

    Errors:
    - Engine expects 0% VAT (IGL_B2B / THIRD_COUNTRY / MARKETPLACE_FACILITATOR)
      but JTL has a non-zero vat_amount.
    - Credit note with a positive gross but 0% VAT in a taxable treatment
      (DOMESTIC / OSS_B2C). This is the "operator forgot the VAT" pattern
      that surfaced in the reconcile report; Jera lands such bookings on
      the catch-all 4970000 ("DPD Schaden"). We skip them so the user
      corrects the source data and re-runs the export.
    """
    zero_vat_treatments = {
        TaxTreatment.IGL_B2B,
        TaxTreatment.THIRD_COUNTRY,
        TaxTreatment.MARKETPLACE_FACILITATOR,
    }
    taxable_treatments = {TaxTreatment.DOMESTIC, TaxTreatment.OSS_B2C}
    for ld in line_decisions:
        if ld.decision.treatment in zero_vat_treatments:
            if ld.line.vat_amount != Decimal("0"):
                return True
        if (
            invoice.is_credit_note
            and ld.decision.treatment in taxable_treatments
            and ld.line.vat_rate == Decimal("0")
            and ld.line.gross > Decimal("0")
        ):
            return True
    return False
