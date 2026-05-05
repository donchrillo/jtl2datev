from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from .models import LineDecision, RawInvoice, ReconcileMismatch, TaxTreatment
from .reconcile import compare
from .tax_engine import decide

logger = logging.getLogger(__name__)


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
                # find the treatment for this line_no
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
