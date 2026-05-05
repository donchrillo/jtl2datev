# Implementations live in core/db_jtl.py for JTL-MSSQL;
# later e.g. core/db_toci.py for own ERP.

from abc import ABC, abstractmethod
from datetime import date
from typing import Iterator

from jtl2datev.core.models import RawInvoice


class InvoiceRepository(ABC):
    @abstractmethod
    def fetch_invoices(self, *, date_from: date, date_to: date) -> Iterator[RawInvoice]:
        ...
