from jtl2datev.core.models import RawInvoice, RawInvoiceLine, TaxDecision


def map_to_datev_account(
    invoice: RawInvoice,
    line: RawInvoiceLine,
    decision: TaxDecision,
    *,
    account_map: dict,
) -> tuple[str, str]:
    """Returns (sachkonto, ust_schluessel)."""
    raise NotImplementedError("DATEV account mapping pending: see docs/datev-format.md")
