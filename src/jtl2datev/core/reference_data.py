"""Central reference data — single source of truth for static lookup tables.

All modules that need EU membership, country→currency, or platform→country
mappings should import from here.
"""
from __future__ import annotations

from datetime import date

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
