from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PartyAddress(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_iso: str  # 2-letter ISO
    region: str | None = None
    vat_id: str | None = None


class RawInvoiceLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    line_no: int
    sku: str | None = None
    description: str | None = None
    quantity: Decimal
    net: Decimal
    gross: Decimal
    vat_amount: Decimal
    vat_rate: Decimal  # e.g. Decimal("19.00")
    product_group_id: int | None = None
    position_type: int | None = None
    jtl_tax_key_id: int | None = None  # reference only, nullable


class RawInvoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Literal["jtl_own", "jtl_external", "jtl_credit_note"]
    invoice_no: str
    invoice_date: date
    service_date: date | None = None
    currency: str
    currency_factor: Decimal
    warehouse_country: str  # ISO-2, determines tax routing
    ship_to: PartyAddress
    bill_to: PartyAddress
    customer_no: str | None = None
    platform_id: int | None = None
    platform_name: str | None = None
    is_credit_note: bool
    lines: tuple[RawInvoiceLine, ...]
    jtl_revenue_account: str | None = None
    jtl_external_order_no: str | None = None


class TaxTreatment(StrEnum):
    DOMESTIC = "DOMESTIC"
    OSS_B2C = "OSS_B2C"
    IGL_B2B = "IGL_B2B"
    THIRD_COUNTRY = "THIRD_COUNTRY"
    MARKETPLACE_FACILITATOR = "MARKETPLACE_FACILITATOR"
    UNKNOWN = "UNKNOWN"


class TaxDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    treatment: TaxTreatment
    expected_vat_rate: Decimal
    tax_country: str
    cleaned_vat_id: str | None = None  # normalised UStId for DATEV (prefix added if needed)
    notes: tuple[str, ...] = ()


class LineDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    line: RawInvoiceLine
    decision: TaxDecision


class ReconcileMismatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    invoice_no: str
    line_no: int
    field: str
    jtl_value: str
    engine_value: str
    severity: Literal["info", "warn", "error"]
