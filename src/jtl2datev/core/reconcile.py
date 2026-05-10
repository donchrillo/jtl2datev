from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Literal

from jtl2datev.core.models import LineDecision, RawInvoice, ReconcileMismatch, TaxTreatment
from jtl2datev.core.tax_engine import decide

logger = logging.getLogger(__name__)

_ZERO_VAT_TREATMENTS = {
    TaxTreatment.IGL_B2B,
    TaxTreatment.THIRD_COUNTRY,
    TaxTreatment.MARKETPLACE_FACILITATOR,
}


def compare(invoice: RawInvoice, decisions: list[LineDecision]) -> list[ReconcileMismatch]:
    mismatches: list[ReconcileMismatch] = []

    for ld in decisions:
        line = ld.line
        decision = ld.decision

        # Marketplace-Facilitator: marketplace collects local VAT itself; JTL stores
        # the gross rate paid by the customer, our DATEV booking goes net. This is
        # an expected divergence, not a problem — surface as info-only.
        is_marketplace_facilitator = decision.treatment == TaxTreatment.MARKETPLACE_FACILITATOR

        if decision.expected_vat_rate != line.vat_rate:
            # Lines with 0% VAT and gross 0 are typically shipping / discount /
            # tax-free positions — not actionable, downgrade to info.
            # Lines with 0% VAT but gross > 0 in a taxable treatment indicate
            # missing VAT (e.g. user error on a credit note) — keep as warn,
            # promote to error on credit notes where the operator should have
            # noticed.
            zero_vat_zero_gross = (
                line.vat_rate == 0
                and line.gross == 0
                and decision.treatment in (TaxTreatment.DOMESTIC, TaxTreatment.OSS_B2C)
            )
            zero_vat_with_gross = (
                line.vat_rate == 0
                and line.gross > 0
                and decision.treatment in (TaxTreatment.DOMESTIC, TaxTreatment.OSS_B2C)
            )
            severity: Literal["info", "warn", "error"]
            if is_marketplace_facilitator or zero_vat_zero_gross:
                severity = "info"
            elif zero_vat_with_gross and invoice.is_credit_note:
                severity = "error"
            else:
                severity = "warn"
            mismatches.append(
                ReconcileMismatch(
                    invoice_no=invoice.invoice_no,
                    external_order_no=invoice.jtl_external_order_no,
                    line_no=line.line_no,
                    field="vat_rate",
                    jtl_value=str(line.vat_rate),
                    engine_value=str(decision.expected_vat_rate),
                    severity=severity,
                )
            )

        if decision.treatment in _ZERO_VAT_TREATMENTS and line.vat_amount != 0:
            vat_amount_severity: Literal["info", "warn", "error"]
            if abs(line.vat_amount) <= Decimal("0.01"):
                vat_amount_severity = "warn"
            elif is_marketplace_facilitator:
                vat_amount_severity = "info"
            else:
                vat_amount_severity = "error"
            mismatches.append(
                ReconcileMismatch(
                    invoice_no=invoice.invoice_no,
                    external_order_no=invoice.jtl_external_order_no,
                    line_no=line.line_no,
                    field="vat_amount",
                    jtl_value=str(line.vat_amount),
                    engine_value="0",
                    severity=vat_amount_severity,
                )
            )

    return mismatches


@dataclass
class ReconcileReport:
    invoices_total: int = 0
    lines_total: int = 0
    treatments: Counter[TaxTreatment] = field(default_factory=Counter)
    mismatches_by_severity: Counter[str] = field(default_factory=Counter)
    mismatches_by_treatment: Counter[TaxTreatment] = field(default_factory=Counter)
    mismatches_by_warehouse: Counter[str] = field(default_factory=Counter)
    mismatches_by_source: Counter[str] = field(default_factory=Counter)
    invoices_with_any_mismatch: int = 0
    sample_mismatches: list[ReconcileMismatch] = field(default_factory=list)


def run_reconcile(
    invoices: Iterable[RawInvoice],
    *,
    own_vat_countries: frozenset[str],
    sample_limit: int = 20,
) -> ReconcileReport:
    report = ReconcileReport()

    for invoice in invoices:
        report.invoices_total += 1

        line_decisions: list[LineDecision] = []
        for line in invoice.lines:
            report.lines_total += 1
            decision = decide(invoice, line, own_vat_countries=own_vat_countries)
            report.treatments[decision.treatment] += 1
            line_decisions.append(LineDecision(line=line, decision=decision))

        mismatches = compare(invoice, line_decisions)

        if mismatches:
            report.invoices_with_any_mismatch += 1
            for mm in mismatches:
                report.mismatches_by_severity[mm.severity] += 1
                ld_map = {ld.line.line_no: ld.decision.treatment for ld in line_decisions}
                treatment = ld_map.get(mm.line_no)
                if treatment is not None:
                    report.mismatches_by_treatment[treatment] += 1
                report.mismatches_by_warehouse[invoice.warehouse_country] += 1
                report.mismatches_by_source[invoice.source] += 1
                if len(report.sample_mismatches) < sample_limit:
                    report.sample_mismatches.append(mm)

        if report.invoices_total % 1000 == 0:
            logger.info(
                "reconcile: processed %d invoices, %d mismatches so far",
                report.invoices_total,
                sum(report.mismatches_by_severity.values()),
            )

    return report
