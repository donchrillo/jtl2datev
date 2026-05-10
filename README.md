## Status (2026-05-11): Repo eingefroren

Der produktive Code-Stand ist als Modul `accounting` in [toci-erp](https://github.com/donchrillo/toci-erp) integriert. Dieses Repo wird vorerst nicht weiterentwickelt — bleibt aber als Referenz / Fallback aktiv. Neue Features und Bugfixes laufen über toci-erp.

---

# jtl2datev

Konsolen-Tool: liest Rechnungen/Gutschriften aus JTL-Datenbank, erzeugt DATEV-konformen Export.

## Architektur

3-schichtiges Design:
- **Core-Library** (`src/jtl2datev/core/`) — framework-agnostisch, Services, Repository, Domain-Models
- **CLI** (`src/jtl2datev/cli/`) — Click-Befehle, thin layer über Services
- **API** (`src/jtl2datev/api/`) — FastAPI-Router (optional, installiert via `pip install jtl2datev[api]`)

Detailinformationen zu Entwurfsentscheidungen siehe [docs/architecture.md](docs/architecture.md).

## Installation

```bash
# Grundinstallation (CLI + Core-Library)
pip install jtl2datev

# Mit FastAPI-API
pip install jtl2datev[api]

# Für Entwicklung
git clone https://github.com/donchrillo/jtl2datev.git
cd jtl2datev
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Schnelleinstieg

```bash
# Monatliche DATEV-Exporte (Q1 2026)
jtl2datev export --month 202601 --format datev
jtl2datev export --month 202602 --format datev
jtl2datev export --month 202603 --format datev

# DutyPay/Taxually (VAT-Meldungen)
jtl2datev export --month 202601 --format dutypay
jtl2datev export --month 202601 --format taxually

# Reconciliation & Audit
jtl2datev reconcile --month 202601
jtl2datev mixed-vat-check --month 202601

# Wechselkurs-Import
jtl2datev import-rates --date 2026-01-31
```

## Abhängigkeiten

- Python 3.12+
- SQLAlchemy 2.0 + pyodbc (JTL MSSQL)
- Pydantic v2 (Config & Models)
- Click (CLI)
- openpyxl, reportlab (Export)
- FastAPI + uvicorn (optional, für API)

Siehe [pyproject.toml](pyproject.toml) für vollständige Abhängigkeitsliste.

## Konfiguration

Umgebungsvariablen oder `.env`-Datei:

```ini
JTL_DB_CONNECTION_STRING=mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server
DATEV_EXPORT_PATH=/exports/datev
DUTYPAY_EXPORT_PATH=/exports/dutypay
LOG_LEVEL=INFO
```

## Dokumentation

- [docs/architecture.md](docs/architecture.md) — Design & Layer-Struktur
- [docs/db-schema.md](docs/db-schema.md) — JTL-DB-Erkenntnisse (Tabellen, Joins)
- [docs/datev-format.md](docs/datev-format.md) — DATEV-Export-Spezifikation
- [docs/dutypay-format.md](docs/dutypay-format.md) — DutyPay-Format
- [docs/taxually-format.md](docs/taxually-format.md) — Taxually-Format
- [docs/tax-rules.md](docs/tax-rules.md) — Länder- & Steuersatz-Logik
- [docs/review/](docs/review/) — Konsolidierte Review-Reports

## Status & Testing

- 437+ Tests (pytest)
- Ruff Lint, mypy Type-Check
- Integriert in toci-erp Backend (384 Tests grün)

Siehe [CLAUDE.md](CLAUDE.md) für Development-Guidelines und [next-session.md](next-session.md) für Aufgabenbacklog.

## License

Intern — siehe Repo-Besitzer für Details.
