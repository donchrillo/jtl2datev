# Architektur

## Leitlinien

- **Konsolen-First, Library-Kern**: `core/` ist eine reine Python-Library ohne CLI-/UI-/Framework-Abhängigkeiten. `cli.py` ist nur Adapter.
- **Spätere Migration**: Wenn die Logik steht, wandert `core/` in das ERP-Monorepo (FastAPI + React 19). Dort wird ein FastAPI-Router um die gleichen Funktionen gebaut, das Frontend ruft sie über die API.
- **Repository-Pattern für DB**: JTL heute, eigenes ERP morgen. Tausch über Interface, nicht über Code-Änderung im Kern.

## Kern-Module (geplant)

| Modul | Verantwortung |
|---|---|
| `core/config.py` | Pydantic-Settings: DB-Connection, DATEV-Mandant, Konten-Mappings |
| `core/models.py` | Domain-Modelle: `Invoice`, `InvoiceLine`, `Customer`, `TaxInfo` |
| `core/repositories.py` | Abstrakte Interfaces: `InvoiceRepository`, `CustomerRepository` |
| `core/db_jtl.py` | JTL-MSSQL-Implementierung, read-only |
| `core/rules.py` | Steuer-/Konten-Logik (Land × Kundentyp × Steuersatz → Konto) |
| `core/datev.py` | DATEV-CSV-Erzeugung (EXTF Buchungsstapel) |
| `cli.py` | Click-Wrapper |

## Was noch offen ist

- Genauer DATEV-Header (Mandant, Berater, Format-Version)
- OSS-Verfahren ja/nein
- Versandlogik (mehrere Lager/Länder?)
- Buchungsperioden-Handling
