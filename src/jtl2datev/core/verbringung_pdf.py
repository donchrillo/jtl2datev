"""Pro-forma invoice PDF generator for Amazon intra-Community movements.

One PDF per route (departure_country → arrival_country) per period.
Layout mirrors the reference PDFs in samples/verbringungen/.
"""
from __future__ import annotations

import calendar
import io
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from jtl2datev.core.config import OWN_VAT_IDS_VERBRINGUNG
from jtl2datev.core.reference_data import COUNTRY_CURRENCY as _COUNTRY_CURRENCY_ALL
from jtl2datev.core.verbringung_parser import MovementRow
from jtl2datev.core.verbringung_pricing import PricingResult

logger = logging.getLogger(__name__)

COUNTRY_NAMES_DE: dict[str, str] = {
    "DE": "Deutschland",
    "PL": "Polen",
    "CZ": "Tschechien",
    "IT": "Italien",
    "ES": "Spanien",
    "FR": "Frankreich",
    "SK": "Slowakei",
    "GB": "Großbritannien",
    "AT": "Österreich",
    "BE": "Belgien",
    "NL": "Niederlande",
}

COUNTRY_NAMES_EN: dict[str, str] = {
    "DE": "Germany",
    "PL": "Poland",
    "CZ": "Czech Republic",
    "IT": "Italy",
    "ES": "Spain",
    "FR": "France",
    "SK": "Slovakia",
    "GB": "United Kingdom",
    "AT": "Austria",
    "BE": "Belgium",
    "NL": "Netherlands",
}

COUNTRY_CURRENCIES: dict[str, str] = _COUNTRY_CURRENCY_ALL

_SENDER_LINES = [
    "ToCi Vertrieb OHG",
    "In der Beckuhl 64",
    "DE 46569 Hünxe",
]

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN = 2.0 * cm


class _NumberedCanvas(pdf_canvas.Canvas):
    """Canvas subclass that writes 'Page X of Y' after the full page count is known."""

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._page_states: list[dict] = []

    def showPage(self) -> None:  # type: ignore[override]
        self._page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._page_states)
        for state in self._page_states:
            self.__dict__.update(state)
            self.setFont("Helvetica", 8)
            self.drawRightString(
                _PAGE_WIDTH - _MARGIN,
                _PAGE_HEIGHT - _MARGIN + 0.3 * cm,
                f"Page {self._pageNumber} of {total}",  # type: ignore[attr-defined]
            )
            pdf_canvas.Canvas.showPage(self)
        pdf_canvas.Canvas.save(self)


def _period_end_date(period: str) -> date:
    year, month = int(period[:4]), int(period[5:7])
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def _fmt(val: Decimal) -> str:
    """Format Decimal as German number string (period thousands, comma decimal)."""
    quantized = val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{quantized:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _convert(eur_amount: Decimal, rate: Decimal | None) -> Decimal | None:
    if rate is None:
        return None
    return (eur_amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _route_key(row: MovementRow) -> tuple[str, str]:
    return (row.departure_country, row.arrival_country)


def _ek(row: MovementRow, pricing: dict[str, PricingResult]) -> Decimal:
    pr = pricing.get(row.seller_sku)
    if pr is None or pr.ek_netto is None:
        return Decimal("0")
    return pr.ek_netto


def _article_nr(row: MovementRow, pricing: dict[str, PricingResult]) -> str:
    pr = pricing.get(row.seller_sku)
    if pr is not None and pr.matched_jtl_artikel:
        return pr.matched_jtl_artikel
    return row.seller_sku


def _desc(row: MovementRow, pricing: dict[str, PricingResult]) -> str:
    pr = pricing.get(row.seller_sku)
    base = (pr.description if pr is not None and pr.description else None) or row.description
    if pr is not None and pr.is_bware:
        return f"{base} (B-Ware)" if base else "(B-Ware)"
    return base


def _build_pdf(
    movements: list[MovementRow],
    pricing: dict[str, PricingResult],
    period: str,
    pfr_number: str,
    departure_country: str,
    arrival_country: str,
    own_vat_ids: dict[str, str],
    exchange_rates: dict[str, Decimal] | None,
    output_path: Path | None = None,
) -> bytes | None:
    period_end = _period_end_date(period)

    dep_name_de = COUNTRY_NAMES_DE.get(departure_country, departure_country)
    dep_name_en = COUNTRY_NAMES_EN.get(departure_country, departure_country)
    arr_name_de = COUNTRY_NAMES_DE.get(arrival_country, arrival_country)
    arr_name_en = COUNTRY_NAMES_EN.get(arrival_country, arrival_country)
    dep_currency = COUNTRY_CURRENCIES.get(departure_country, "EUR")
    arr_currency = COUNTRY_CURRENCIES.get(arrival_country, "EUR")

    dep_vat = own_vat_ids.get(departure_country, "")
    arr_vat = own_vat_ids.get(arrival_country, "")

    dep_rate = (exchange_rates or {}).get(dep_currency) if dep_currency != "EUR" else None
    arr_rate = (exchange_rates or {}).get(arr_currency) if arr_currency != "EUR" else None

    show_dep_col = dep_currency != "EUR" and dep_rate is not None
    show_arr_col = arr_currency != "EUR" and arr_rate is not None
    has_extra_col = show_dep_col or show_arr_col

    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=10)
    bold_small = ParagraphStyle("BoldSmall", parent=normal, fontSize=8, leading=10,
                                fontName="Helvetica-Bold")
    title_st = ParagraphStyle("Title", parent=normal, fontSize=11, leading=14,
                               fontName="Helvetica-Bold")

    story: list = []

    # Title
    story.append(Paragraph("Pro-Forma Rechnung (Invoice)", title_st))
    story.append(Spacer(1, 0.15 * cm))
    for line in _SENDER_LINES:
        story.append(Paragraph(line, small))
    story.append(Spacer(1, 0.35 * cm))

    # Invoice meta table
    meta = [
        ["Rechnungs-Nr. / Invoice no.:", pfr_number],
        ["Datum / Date:", period_end.strftime("%d.%m.%Y")],
        ["Periode / Period:", period],
    ]
    meta_tbl = Table(meta, colWidths=[6 * cm, 10 * cm])
    meta_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 0.35 * cm))

    # Legal text
    story.append(Paragraph(
        f"Steuerfreie innergemeinschaftliche Verbringung von {dep_name_de} nach {arr_name_de} "
        "(§4 Nr.1b.) UStG i.V.m. § 6a Abs. 2 UStG)",
        small,
    ))
    story.append(Paragraph(
        f"VAT-exempt intra-Community Movement from {dep_name_en} to {arr_name_en} "
        "(Art. 17 i.c.w. Art. 138 EU-Directive 2006/112/EC)",
        small,
    ))
    story.append(Spacer(1, 0.25 * cm))

    if dep_vat:
        story.append(Paragraph(
            f"Umsatzsteuer-ID / VAT identification number {dep_name_en}: {dep_vat}",
            small,
        ))
    if arr_vat:
        story.append(Paragraph(
            f"Umsatzsteuer-ID / VAT identification number {arr_name_en}: {arr_vat}",
            small,
        ))
    story.append(Spacer(1, 0.35 * cm))

    # Build item table
    # Column layout:
    # With non-EUR currency: Menge | Artikel-Nr. | Warenbezeichnung | Preis(EUR) | Gesamtpreis(dep/arr) | Gesamtpreis(EUR)
    # EUR only: Menge | Artikel-Nr. | Warenbezeichnung | Preis | Gesamtpreis(EUR)
    if has_extra_col:
        if show_dep_col and show_arr_col:
            mid_cur_hdr = f"({dep_currency})"
            last_cur_hdr = f"({arr_currency})"
        elif show_dep_col:
            mid_cur_hdr = f"({dep_currency})"
            last_cur_hdr = "(EUR)"
        else:
            mid_cur_hdr = f"({arr_currency})"
            last_cur_hdr = "(EUR)"

        col_widths = [1.5 * cm, 3.5 * cm, 6.5 * cm, 2.0 * cm, 2.5 * cm, 2.5 * cm]
        col_header_row1 = ["", "", "", "(EUR)", mid_cur_hdr, last_cur_hdr]
        col_header_row2 = [
            "Menge\nQuantity",
            "Artikel-Nr.\nArticle no.",
            "Warenbezeichnung\nDescription of goods",
            "Preis\nprice",
            "Gesamtpreis\ntotal price",
            "Gesamtpreis\ntotal price",
        ]
        n_cols = 6
    else:
        col_widths = [1.5 * cm, 3.5 * cm, 8.5 * cm, 2.0 * cm, 3.0 * cm]
        col_header_row1 = ["", "", "- -", "", "(EUR)"]
        col_header_row2 = [
            "Menge\nQuantity",
            "Artikel-Nr.\nArticle no.",
            "Warenbezeichnung\nDescription of goods",
            "Preis\nprice",
            "Gesamtpreis\ntotal price",
        ]
        n_cols = 5

    sorted_mvs = sorted(
        movements,
        key=lambda r: (r.depart_date or r.complete_date or date.min, r.seller_sku),
    )

    total_eur = Decimal("0")
    total_mid: Decimal = Decimal("0")
    total_last: Decimal = Decimal("0")

    data_rows: list[list] = [col_header_row1, col_header_row2]

    for mv in sorted_mvs:
        ek_val = _ek(mv, pricing)
        qty = Decimal(str(mv.qty))
        row_eur = (ek_val * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_eur += row_eur

        qty_s = _fmt(qty)
        ek_s = _fmt(ek_val)
        eur_s = _fmt(row_eur)
        art = _article_nr(mv, pricing)
        description = _desc(mv, pricing)

        if has_extra_col:
            if show_dep_col:
                mid_val = _convert(row_eur, dep_rate) or Decimal("0")
            else:
                mid_val = _convert(row_eur, arr_rate) or Decimal("0")
            total_mid += mid_val
            mid_s = _fmt(mid_val)

            if show_arr_col and not (show_dep_col and show_arr_col):
                last_s = eur_s
                total_last += row_eur
            elif show_dep_col and show_arr_col:
                last_val = _convert(row_eur, arr_rate) or Decimal("0")
                total_last += last_val
                last_s = _fmt(last_val)
            else:
                last_s = eur_s
                total_last += row_eur

            data_rows.append([qty_s, art, description, ek_s, mid_s, last_s])
        else:
            total_last += row_eur
            data_rows.append([qty_s, art, description, ek_s, eur_s])

    # Totals row(s)
    if has_extra_col:
        if show_dep_col and show_arr_col:
            data_rows.append(["", "", "Summe / Total", "", _fmt(total_mid), _fmt(total_last)])
            data_rows.append(["", "", "Summe / Total (EUR)", "", "", _fmt(total_eur)])
        elif show_dep_col:
            # dep is non-EUR (e.g. CZK), last col is EUR
            data_rows.append(["", "", "Summe / Total", "", _fmt(total_mid), _fmt(total_eur)])
        else:
            # arr is non-EUR, dep is EUR: mid_col shows arr currency, last col EUR
            data_rows.append(["", "", "Summe / Total", "", _fmt(total_mid), _fmt(total_eur)])
    else:
        data_rows.append(["", "", "Summe / Total (EUR)", "", _fmt(total_eur)])

    # Table style
    n_rows = len(data_rows)
    last_data_idx = n_rows - 1
    second_last = n_rows - 2

    tbl = Table(data_rows, colWidths=col_widths, repeatRows=2)
    ts = TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LEADING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 2), (0, -1), "RIGHT"),      # qty col
        ("ALIGN", (3, 2), (-1, -1), "RIGHT"),      # price cols
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#E0E0E0")),
        ("LINEBELOW", (0, 1), (-1, 1), 0.5, colors.black),
        ("LINEABOVE", (0, last_data_idx), (-1, last_data_idx), 0.5, colors.black),
        ("FONTNAME", (0, last_data_idx), (-1, last_data_idx), "Helvetica-Bold"),
        ("FONTNAME", (0, second_last), (-1, second_last), "Helvetica-Bold"),
        ("WORDWRAP", (2, 2), (2, -1), 1),
    ])
    if show_dep_col and show_arr_col and n_rows >= 2:
        ts.add("FONTNAME", (0, second_last), (-1, second_last), "Helvetica-Bold")
        ts.add("LINEABOVE", (0, second_last), (-1, second_last), 0.5, colors.black)
    tbl.setStyle(ts)

    story.append(tbl)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        target: str | io.BytesIO = str(output_path)
    else:
        target = io.BytesIO()

    doc = BaseDocTemplate(
        target,  # type: ignore[arg-type]
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN + 0.5 * cm,
        bottomMargin=_MARGIN,
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    page_template = PageTemplate(id="main", frames=[frame])
    doc.addPageTemplates([page_template])

    doc.multiBuild(story, canvasmaker=_NumberedCanvas)

    if isinstance(target, io.BytesIO):
        return target.getvalue()
    return None


def to_verbringung_pdf_bytes(
    movements: list[MovementRow],
    pricing: dict[str, PricingResult],
    period: str,
    pfr_number: str,
    departure_country: str,
    arrival_country: str,
    own_vat_ids: dict[str, str] | None = None,
    exchange_rates: dict[str, Decimal] | None = None,
) -> bytes:
    """Build a single pro-forma invoice PDF as bytes. Does not touch the filesystem."""
    if own_vat_ids is None:
        own_vat_ids = OWN_VAT_IDS_VERBRINGUNG
    result = _build_pdf(
        movements=movements,
        pricing=pricing,
        period=period,
        pfr_number=pfr_number,
        departure_country=departure_country,
        arrival_country=arrival_country,
        own_vat_ids=own_vat_ids,
        exchange_rates=exchange_rates,
        output_path=None,
    )
    assert result is not None
    return result


def generate_proforma_pdfs(
    movements: list[MovementRow],
    pricing: dict[str, PricingResult],
    period: str,
    output_dir: Path,
    own_vat_ids: dict[str, str] | None = None,
    exchange_rates: dict[str, Decimal] | None = None,
    starting_pfr_number: int = 1,
) -> list[Path]:
    """Generate one pro-forma invoice PDF per route (departure→arrival).

    Returns list of generated PDF paths, sorted by route and PFR number.
    """
    if own_vat_ids is None:
        own_vat_ids = OWN_VAT_IDS_VERBRINGUNG

    by_route: dict[tuple[str, str], list[MovementRow]] = defaultdict(list)
    for mv in movements:
        by_route[_route_key(mv)].append(mv)

    sorted_routes = sorted(by_route.keys())

    year_short = period[2:4]
    month_str = period[5:7]

    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    for i, route in enumerate(sorted_routes):
        pfr_seq = starting_pfr_number + i
        pfr_number = f"PFR{year_short}-{month_str}-{pfr_seq:04d}"
        output_path = output_dir / f"{pfr_number}.pdf"

        dep, arr = route
        logger.info(
            "Generating %s: %s→%s (%d movements)",
            pfr_number, dep, arr, len(by_route[route]),
        )

        _build_pdf(
            movements=by_route[route],
            pricing=pricing,
            period=period,
            pfr_number=pfr_number,
            departure_country=dep,
            arrival_country=arr,
            own_vat_ids=own_vat_ids,
            exchange_rates=exchange_rates,
            output_path=output_path,
        )
        generated.append(output_path)

    logger.info("generate_proforma_pdfs: %d PDFs generated in %s", len(generated), output_dir)
    return generated
