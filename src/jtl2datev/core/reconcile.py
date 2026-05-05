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

        # Marketplace-Facilitator: marketplace collects local VAT itself; JTL stores
        # the gross rate paid by the customer, our DATEV booking goes net. This is
        # an expected divergence, not a problem — surface as info-only.
        is_marketplace_facilitator = decision.treatment == TaxTreatment.MARKETPLACE_FACILITATOR

        if decision.expected_vat_rate != line.vat_rate:
            # Lines with 0% VAT in a taxable treatment are typically shipping,
            # discounts, or otherwise tax-free positions — not actionable as a
            # tax-rate mismatch, downgrade to info.
            zero_in_taxable = (
                line.vat_rate == 0
                and decision.treatment in (TaxTreatment.DOMESTIC, TaxTreatment.OSS_B2C)
            )
            severity = "info" if (is_marketplace_facilitator or zero_in_taxable) else "warn"
            mismatches.append(
                ReconcileMismatch(
                    invoice_no=invoice.invoice_no,
                    line_no=line.line_no,
                    field="vat_rate",
                    jtl_value=str(line.vat_rate),
                    engine_value=str(decision.expected_vat_rate),
                    severity=severity,
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
                    severity="info" if is_marketplace_facilitator else "error",
                )
            )

    return mismatches
