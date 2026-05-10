# Next Session

## Status

**Pipeline erweitert: Fremdwährung, DutyPay-Export, Taxually-Export, DATEV-Archiv, Amazon-Verbringungen (6-Tier-Lookup: B-Ware + ASIN), BMF-Wechselkurs-Import (2026-05-08). Sprint A (IO-Sicherheit) + Sprint B (Tax-Korrektheit) + Sprint C Phase 1 (Architektur-Hygiene) + Sprint C Phase 3 (BuchungsRow-Refactor) + Sprint D (Compliance-Polish) + W-5 (DutyPay-Vorzeichen-Check) umgesetzt (2026-05-10).**

**Architektur-Cleanup:** `core/reference_data.py` zentralisiert Stammdaten (EU-Länder, Währungen, Plattformen, Min-Datum). `RawInvoiceLine` auf Kern-Felder reduziert (12 nie gelesene Item-Felder entfernt). `BuchungsRow`-Dataclass mit 22 benannten Feldern, `to_csv_row()`-Methode als Single Source of Truth für 124-Spalten-Mapping. 427 Tests grün.

**Verbringungen-SKU-Mapping:** Q1-2026 100 % aufgelöst (Tier 5 B-Ware + Tier 6 ASIN-Lookup, 0 unresolved).

**Compliance-Polish (Sprint D):**
- **W-14:** `cli.py` Monats-Parser strikter (Regex `^\d{4}-\d{2}$`).
- **W-11:** `core/exchange_rates.py` BMF-CSV-Encoding-Detection (utf-8-sig → utf-8 → iso-8859-1) + Sanity-Check.
- **W-12:** `core/verbringung_parser.py` Amazon-TSV-Encoding-Detection (utf-8-sig → utf-8 → utf-16 → utf-16-le → cp1252).
- **W-10:** `core/db_jtl.py` + `cli.py` Context-Manager `managed_engine()`, alle 8 CLI-Commands mit sauberer `engine.dispose()` via `with`-Block.
- **W-15:** `core/verbringung_pricing.py` DB-Connection einmalig öffnen, an alle Tier-Funktionen durchreichen (statt 9 separate `engine.connect()`-Aufrufe pro Lookup).

**Standardworkflow (erweitert um Verbringungen):**
```
jtl2datev mixed-vat-check --month YYYY-MM
jtl2datev reconcile --month YYYY-MM
jtl2datev export --month YYYY-MM
jtl2datev export-dutypay --month YYYY-MM
jtl2datev export-dutypay-delta --month YYYY-MM  # falls nachgelagerte Belege
jtl2datev export-taxually --month YYYY-MM
jtl2datev export-taxually-delta --month YYYY-MM  # falls nachgelagerte Belege
jtl2datev export-verbringung --report ... --month YYYY-MM  # Amazon-FBA-Transfers
jtl2datev export-delta --month YYYY-MM          # falls nachgelagerte Belege
```

**W-5 (DutyPay-Vorzeichen-Check):** `core/dutypay.py:determine_kind_of_business()` klassifiziert jetzt Belege auch dann als REFUND, wenn `total_gross < 0` ist — unabhängig vom `is_credit_note`-Flag. Mismatch (Flag ≠ Vorzeichen, Brutto ≠ 0) loggt WARNING. Schützt vor manuellen Korrekturbelegen in `tRechnung` ohne Gutschrift-Flag.

**B-9 (Repository-Interface):** `core/repositories.py` um `InvoiceRepository.find_mixed_vat_belege()` und neue ABC `ArticlePricingRepository.lookup_ek_prices()` erweitert. JTL-Implementierungen `JtlInvoiceRepository.find_mixed_vat_belege` und neue `JtlArticlePricingRepository` in `core/db_jtl.py`. CLI (`mixed-vat-check`, `export-verbringung`) ruft jetzt Repository-Methoden statt freie Modul-Funktionen → ERP-Migration berührt nur noch Repository-Implementierungen, nicht CLI/Service-Layer.

**W-20 (Stammdaten-Hygiene):** `_DEBITOR_BY_PAYMENT`, `_DOMESTIC_MAP` (vorher funktions-lokal in `rules.py`) und `STANDARD_VAT_RATE` (vorher in `tax_engine.py`) nach `core/reference_data.py` umgezogen — alle drei sind Mandanten-/Stammdaten und gehören zur zentralen Single Source of Truth. `vat_rate_for(country, on_date=None)`-Helper als zukunftsfähige Signatur für Period-Validity (Logik selbst noch nicht implementiert, Tool produktiv erst 2026). Module-lokale Re-Bindings erhalten — kein API-Bruch.

**Tests:** 430 passed, 14 skipped. ruff clean (für berührte Dateien; 2 pre-existing Lint-Fehler in `cli.py` Top-of-File unverändert).

## Offene Punkte — Audit & Dateneingabe

0. **Manuelle Prüfung 4 ERROR/UNKNOWN-Belege (User):** Siehe `docs/audit-q1-2026-error-belege.md`. Nach Prüfung evtl. Engine-Re-Export DATEV März 2026.

1. **Engine-only-Belege Feb/Mar Validierung:** Q1-Reconcile zeigt ~590 sequentielle Belege `202630260xxx` (FEB) / `202650012xxx` (MAR) die in Engine vorkommen, aber nicht in Jera-PowerQuery-Export. Prüfen ob tatsächlich Taxually-meldepflichtig oder Doppel-Einspielung.

4. **Steuerberater-Klärung (User):** Beleginfo-Felder DATEV (aktuell Spalten 13-17 als Art/Inhalt 1-5). Prüfen ob auf Zusatzinformation-Spalten umsteigen soll (Jera nutzte andere Feldnamen).

5. **VIES-Online-Validierung (langfristig):** Aktuell Format-Plausibilität. Echte VIES-API mit Cache für 100% B2B-Sicherheit.

6. **Restliche DB-Klärungen:** `nSteuereinstellung` (0/10/15/20-Bedeutung), `tRechnungKorrektur`-Vollständigkeit (own invoices credit note logic), `tRechnungStorno`-Auswirkung auf `nIstStorniert`.

8. **SK-Departure-Bewegungen Taxually-Klärung (User):** SK→CZ/DE/PL FC_TRANSFERs werden aktuell mit leerer Departure-VAT-ID exportiert. Steuerlich ordnen die Finanzämter diese bisher Amazon zu (nicht uns), Pro-Forma-PDFs werden weiterhin als Beleg erzeugt. Offen: Verarbeitet Taxually XLSX-Zeilen mit leerer SK-VAT überhaupt? Falls nein, alternative Strategien: (a) SK-Departure-Zeilen aus dem XLSX rausfiltern (PDFs trotzdem behalten), (b) komplett weglassen. Vor Q2-Meldung klären.

## Bei ERP-/Frontend-Migration angehen

Diese Tasks ergeben erst Sinn, wenn das neue System (FastAPI + React 19) konkret aufgebaut wird — Design hängt vom realen Deployment-Kontext ab (Auth-Schema, Storage-Backend, Frontend-Anforderungen).

- **FastAPI-Auth + CORS** — API-Key/OAuth2 + CORS-Whitelist für React-Origins.
- **FastAPI-Verbringungs-Endpoint** — Pydantic-Body mit `exchange_rates` + Multipart-Upload des Amazon-Reports (oder Pre-Signed-URL).
- **FastAPI-Delta-Endpoints** — Baseline-Auflösung per Body/Upload, Storage-Backend (S3 o.ä.) statt lokales `exports/`.
- **W-20-Settings-Override** — Konten-Mappings (`DOMESTIC_ACCOUNT_BY_WAREHOUSE`, `DEBITOR_BY_PAYMENT`) aus Settings/DB pro Mandant statt Modul-Konstanten. Notwendig sobald Multi-Mandanten-Betrieb.

## Sonstige offene Code-Lücken

- **W-20-Period-Validity** (deferred bis Re-Exports älterer Monate nötig werden): `STANDARD_VAT_RATE` von `dict[country, rate]` auf `dict[country, list[(from_date, rate)]]` umstellen, `vat_rate_for(country, on_date)` echte Period-Logik geben. Aufwand >4h. Aktuell wird `on_date` ignoriert.

## History (erledigt 2026-05-10)

- W-16-A: CLI → `cli/`-Package mit 9 Modulen.
- W-16-B: `core/services/` mit DATEV/DutyPay/Taxually-Services + Delta-Varianten.
- W-16-B-Rest: Verbringung/Reconcile/Mixed-VAT zusätzlich als Services. Alle 8 Exporter/Tools sind service-fähig.
- FastAPI-Skeleton: `src/jtl2datev/api/` mit 5 Endpoints (DATEV/DutyPay/Taxually-Export, Reconcile-Report, Mixed-VAT-Check). Lifespan-Engine, typed Exception-Handlers, OpenAPI/Swagger unter `/docs`.
- W-19 durch B-9 abgedeckt — `ArticlePricingRepository` in `core/repositories.py` + `core/db_jtl.py`.

## Notizen für Orchestrator

- Vor jeder Coding-Aufgabe: Interface/Signaturen festlegen, dann an Coder-Agent delegieren.
- Nach Coding-Aufgabe: Docs-Agent fasst Änderungen in passender `docs/*.md` zusammen.
- Erledigtes hier rausnehmen → `docs/status.md`.
- DB ist read-only: nur SELECT, keine DDL/INSERT/UPDATE/DELETE.
