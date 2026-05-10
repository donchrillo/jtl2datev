# Next Session

## Status

**Pipeline erweitert: Fremdwährung, DutyPay-Export, Taxually-Export, DATEV-Archiv, Amazon-Verbringungen (6-Tier-Lookup: B-Ware + ASIN), BMF-Wechselkurs-Import (2026-05-08). Sprint A (IO-Sicherheit) + Sprint B (Tax-Korrektheit) + Sprint C Phase 1 (Architektur-Hygiene) umgesetzt (2026-05-10).**

**Architektur-Cleanup:** `core/reference_data.py` zentralisiert Stammdaten (EU-Länder, Währungen, Plattformen, Min-Datum). `RawInvoiceLine` auf Kern-Felder reduziert (12 nie gelesene Item-Felder entfernt). 412 Tests grün.

**Verbringungen-SKU-Mapping:** Q1-2026 100 % aufgelöst (Tier 5 B-Ware + Tier 6 ASIN-Lookup, 0 unresolved).

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

**Tests:** 412 passed, 14 skipped. ruff clean.

## Offene Punkte — Audit & Dateneingabe

0. **Manuelle Prüfung 4 ERROR/UNKNOWN-Belege (User):** Siehe `docs/audit-q1-2026-error-belege.md`. Nach Prüfung evtl. Engine-Re-Export DATEV März 2026.

1. **Engine-only-Belege Feb/Mar Validierung:** Q1-Reconcile zeigt ~590 sequentielle Belege `202630260xxx` (FEB) / `202650012xxx` (MAR) die in Engine vorkommen, aber nicht in Jera-PowerQuery-Export. Prüfen ob tatsächlich Taxually-meldepflichtig oder Doppel-Einspielung.

3. **Probebuchungen filtern (optional):** Belege mit Umsatz 0,00 € raus (z.B. SR202602155/156). Risk: Audit-Trail-Vollständigkeit vs. Noise-Reduktion.

4. **Steuerberater-Klärung (User):** Beleginfo-Felder DATEV (aktuell Spalten 13-17 als Art/Inhalt 1-5). Prüfen ob auf Zusatzinformation-Spalten umsteigen soll (Jera nutzte andere Feldnamen).

5. **VIES-Online-Validierung (langfristig):** Aktuell Format-Plausibilität. Echte VIES-API mit Cache für 100% B2B-Sicherheit.

6. **Restliche DB-Klärungen:** `nSteuereinstellung` (0/10/15/20-Bedeutung), `tRechnungKorrektur`-Vollständigkeit (own invoices credit note logic), `tRechnungStorno`-Auswirkung auf `nIstStorniert`.

7. **Temu-Filter perspektivisch entfernen:** Laut User keine neuen Temu-Belege mehr seit Januar 2026. Der Filter kann komplett entfallen, sobald sichergestellt ist, dass kein neuer Temu-Import stattfindet.

8. **SK-Departure-Bewegungen Taxually-Klärung (User):** SK→CZ/DE/PL FC_TRANSFERs werden aktuell mit leerer Departure-VAT-ID exportiert. Steuerlich ordnen die Finanzämter diese bisher Amazon zu (nicht uns), Pro-Forma-PDFs werden weiterhin als Beleg erzeugt. Offen: Verarbeitet Taxually XLSX-Zeilen mit leerer SK-VAT überhaupt? Falls nein, alternative Strategien: (a) SK-Departure-Zeilen aus dem XLSX rausfiltern (PDFs trotzdem behalten), (b) komplett weglassen. Vor Q2-Meldung klären.

## Phase 2 (Erweiterungen)

- **B-9** CLI-Umstrukturierung: `cli.py` → `cli/`-Package (Sub-Commands pro Modul). 1–2 Tage, eigene Phase.
- **W-16** Service-Layer: `core/services/` (Abstraktions-Schicht über Repository + Tax-Engine + Export). 1–2 Tage.
- **W-19** Repository-Erweiterung: `ArticlePricingRepository` für artikel-bezogene Preis-Lookups. 1–4h.

## Notizen für Orchestrator

- Vor jeder Coding-Aufgabe: Interface/Signaturen festlegen, dann an Coder-Agent delegieren.
- Nach Coding-Aufgabe: Docs-Agent fasst Änderungen in passender `docs/*.md` zusammen.
- Erledigtes hier rausnehmen → `docs/status.md`.
- DB ist read-only: nur SELECT, keine DDL/INSERT/UPDATE/DELETE.
