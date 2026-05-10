"""Central reference data — single source of truth for static lookup tables.

All modules that need EU membership, country→currency, or platform→country
mappings should import from here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

EU_MEMBER_STATES: frozenset[str] = frozenset(
    {
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
        "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
        "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    }
)

# ISO-2 country → ISO-4217 currency.
# EUR-zone members (including HR since 2023) map to EUR.
# Non-EUR EU members and relevant third countries listed individually.
# Union of dutypay._COUNTRY_CURRENCY and verbringung_pdf.COUNTRY_CURRENCIES —
# all overlapping entries are consistent.
COUNTRY_CURRENCY: dict[str, str] = {
    # EUR-zone
    **{c: "EUR" for c in (
        "DE", "AT", "BE", "CY", "EE", "ES", "FI", "FR", "GR", "HR",
        "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK",
    )},
    # Non-EUR EU members
    "CZ": "CZK",
    "DK": "DKK",
    "HU": "HUF",
    "PL": "PLN",
    "RO": "RON",
    "SE": "SEK",
    "BG": "BGN",
    # Non-EU third countries
    "GB": "GBP",
    "CH": "CHF",
    "NO": "NOK",
    "US": "USD",
}

# Explicit mapping of known tPlattform.cName values → ISO-2 country.
# "Amazon" (generic) is intentionally absent — it has no clear single market.
PLATFORM_COUNTRY: dict[str, str] = {
    "Amazon.de": "DE",
    "Amazon.fr": "FR",
    "Amazon.it": "IT",
    "Amazon.es": "ES",
    "Amazon.com.be": "BE",
    "Amazon.nl": "NL",
    "Amazon.se": "SE",
    "Amazon.pl": "PL",
    "Amazon.co.uk": "GB",
}

# Hard floor date for invoice fetching — invoices before this date are excluded.
# JTL data quality before 2024-11-01 was insufficient for automated processing.
HARD_MIN_INVOICE_DATE: date = date(2024, 11, 1)


# ── DATEV chart-of-accounts mappings (Mandanten-spezifisch) ──────────────────
# Wenn das Tool später für mehrere Mandanten läuft, gehören diese Tabellen in
# Settings/DB. Aktuell: Single-Mandant-Defaults.

# Sachkonto-Mapping pro Lagerland für Inlands-Buchungen (TaxTreatment.DOMESTIC).
DOMESTIC_ACCOUNT_BY_WAREHOUSE: dict[str, str] = {
    "DE": "4400000",
    "FR": "4324000",
    "IT": "4326000",
    "ES": "4323000",
    "PL": "4327000",
    "CZ": "4322000",
    "GB": "4325000",
}

# Debitor-Konto pro Zahlungsmethode. Keys sind kleingeschrieben + getrimmt;
# Lookup erfolgt über lower().strip() in map_to_debitor_account.
DEBITOR_BY_PAYMENT: dict[str, int] = {
    "bar": 10001000,
    "bar bei selbstabholung": 10001000,
    "überweisung": 10002000,
    "vorkasse": 10002000,
    "rechnung manuell": 10002000,
    "paypal": 10004000,
    "paypal-express": 10004000,
    "amazonpayments": 10005000,
    "amazon payments": 10005000,
    "amazon_payments": 10005000,
    "ebay rechnungskauf": 10006000,
    "ebay managed payments": 10006000,
    "gewährleistung": 10007000,
    "real": 10008000,
    "kaufland": 10008000,
    "kaufland.de": 10008000,
    "rechnung_mit_klarna": 10009000,
    "sofortbezahlen klarna": 10009000,
    "shopify_payments": 10010000,
    "otto": 10011000,
    "otto.de": 10011000,
    "temu": 10012000,
}


# ── VAT-Sätze (Standard-Sätze pro Land, aktueller Stand) ─────────────────────
# Period-Validity (zeitabhängige Sätze für historische Re-Exports) noch nicht
# implementiert — siehe vat_rate_for(). Tool produktiv ab 2026, daher noch
# nicht akut. Wenn Re-Exports älterer Monate nötig werden, hier ein
# {country: [(from_date, rate), …]}-Modell einziehen.
STANDARD_VAT_RATE: dict[str, Decimal] = {
    "AT": Decimal("20"),
    "BE": Decimal("21"),
    "BG": Decimal("20"),
    "CY": Decimal("19"),
    "CZ": Decimal("21"),
    "DE": Decimal("19"),
    "DK": Decimal("25"),
    "EE": Decimal("24"),  # ab 01.07.2025 (vorher 22 %)
    "ES": Decimal("21"),
    "FI": Decimal("25.5"),
    "FR": Decimal("20"),
    "GR": Decimal("24"),
    "HR": Decimal("25"),
    "HU": Decimal("27"),
    "IE": Decimal("23"),
    "IT": Decimal("22"),
    "LT": Decimal("21"),
    "LU": Decimal("17"),
    "LV": Decimal("21"),
    "MT": Decimal("18"),
    "NL": Decimal("21"),
    "PL": Decimal("23"),
    "PT": Decimal("23"),
    "RO": Decimal("21"),  # ab 01.01.2026 (vorher 19 %, OUG 156/2024)
    "SE": Decimal("25"),
    "SI": Decimal("22"),
    "SK": Decimal("23"),
    "GB": Decimal("20"),
    "CH": Decimal("8.1"),
}


def vat_rate_for(country: str, on_date: date | None = None) -> Decimal | None:
    """Standard-VAT-Satz für *country*, optional zum Stichtag *on_date*.

    Aktuell ohne Period-Validity — *on_date* wird ignoriert. Signatur ist
    bewusst zukunftsfähig: Sobald historische Re-Exports anstehen, kann
    STANDARD_VAT_RATE auf {country: [(from_date, rate), …]} erweitert werden,
    ohne Aufrufstellen anzupassen.
    """
    return STANDARD_VAT_RATE.get(country)
