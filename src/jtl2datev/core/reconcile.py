from jtl2datev.core.models import LineDecision, RawInvoice, ReconcileMismatch, TaxTreatment

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

        if decision.expected_vat_rate != line.vat_rate:
            mismatches.append(
                ReconcileMismatch(
                    invoice_no=invoice.invoice_no,
                    line_no=line.line_no,
                    field="vat_rate",
                    jtl_value=str(line.vat_rate),
                    engine_value=str(decision.expected_vat_rate),
                    severity="warn",
                )
            )

        if decision.treatment in _ZERO_VAT_TREATMENTS and line.vat_amount != 0:
            mismatches.append(
                ReconcileMismatch(
                    invoice_no=invoice.invoice_no,
                    line_no=line.line_no,
                    field="vat_amount",
                    jtl_value=str(line.vat_amount),
                    engine_value="0",
                    severity="error",
                )
            )

    return mismatches
