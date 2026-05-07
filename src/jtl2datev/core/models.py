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
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    zip_code: str | None = None
    city: str | None = None
    street: str | None = None
    house_number: str | None = None
    additional_address: str | None = None

    def display_name(self) -> str:
        """Single-line name for DATEV Buchungstext.

        Priority: company > "last_name first_name" > empty.
        Surname-first matches the Jera convention used by the German tax
        consultant; sorts naturally and is what the operator expects to see.
        """
        if self.company:
            return self.company.strip()
        parts = [p for p in (self.last_name, self.first_name) if p]
        return " ".join(parts).strip()


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
    # Article master fields — populated when available, left None otherwise
    weight: Decimal | None = None
    manufacturer: str | None = None
    manufacturer_country: str | None = None  # ISO-2
    commodity_code: str | None = None  # HS/HTS code
    long_description: str | None = None  # cText / longer item description
    unit: str | None = None  # cEinheit
    transport_code: int | None = None  # kVersandArt


class RawInvoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Literal["jtl_own", "jtl_external", "jtl_credit_note"]
    invoice_no: str
    jtl_primary_key: int | None = None  # kRechnung / kExternerBeleg / kGutschrift
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
    marketplace_country: str | None = None  # ISO-2; derived from kPlattform
    is_credit_note: bool
    lines: tuple[RawInvoiceLine, ...]
    jtl_revenue_account: str | None = None
    jtl_external_order_no: str | None = None
    payment_method: str | None = None  # cZahlungsart for debitor account mapping


class TaxTreatment(StrEnum):
    DOMESTIC = "DOMESTIC"
    OSS_B2C = "OSS_B2C"
    IGL_B2B = "IGL_B2B"
    THIRD_COUNTRY = "THIRD_COUNTRY"
    MARKETPLACE_FACILITATOR = "MARKETPLACE_FACILITATOR"
    EXPORT_LOCAL_VAT = "EXPORT_LOCAL_VAT"  # UK/CH delivery where we owe the destination VAT
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
