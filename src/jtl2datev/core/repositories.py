# Implementations live in core/db_jtl.py for JTL-MSSQL;
# later e.g. core/db_toci.py for own ERP.

from abc import ABC, abstractmethod
from datetime import date
from typing import Iterator

from jtl2datev.core.models import RawInvoice
from jtl2datev.core.preflight import MixedVatBeleg
from jtl2datev.core.verbringung_pricing import PricingResult


class InvoiceRepository(ABC):
    @abstractmethod
    def fetch_invoices(self, *, date_from: date, date_to: date) -> Iterator[RawInvoice]:
        ...

    @abstractmethod
    def find_mixed_vat_belege(
        self, *, date_from: date, date_to: date
    ) -> list[MixedVatBeleg]:
        """Belege mit gemischten VAT-Sätzen auf Item-Ebene.

        Header-Engine kann gemischte Sätze nicht sinnvoll auf einen synthetischen
        Satz reduzieren — Aufrufer muss diese Belege manuell prüfen oder
        ausschließen.
        """
        ...


class ArticlePricingRepository(ABC):
    @abstractmethod
    def lookup_ek_prices(
        self,
        skus: list[str],
        *,
        asin_by_sku: dict[str, str] | None = None,
        bware_strategy: str = "ten_percent",
    ) -> dict[str, PricingResult]:
        """EK-Preise für Verbringungs-Bewertung (§10 Abs. 4 UStG).

        ERP-Implementierungen müssen die SKU/ASIN-Auflösung selbst stellen
        (Tier-Lookup ist JTL-spezifisch).
        """
        ...
