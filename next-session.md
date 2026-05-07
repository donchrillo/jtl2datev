# Next Session

## Status

**Pipeline abgeschlossen: Fremdwährung, DutyPay-Export, DATEV-Archiv, Standardworkflow (2026-05-07 Spätstunde).**

1. **Fremdwährungs-Handling DATEV + DutyPay** (Commit `e0b54eb`):
   - DATEV: `WKZ Umsatz`, `Kurs`, `Basis-Umsatz`, `WKZ Basis-Umsatz` bei Fremdwährung-Belegen aus `invoice.currency_factor` (JTL `fWaehrungsfaktor`).
   - DutyPay: SourceZone/Target/MarketZoneCurrencyCode konsistent abgeleitet; MarketZone aus `marketplace_country` (Amazon-Sites-Mapping, Fallback Lager-Land).
   - `RawInvoice.marketplace_country: str | None = None` neu.
   - Q1 2026 Verifikation: Engine ↔ Jera matchen 1:1 für alle Fremdwährungs-Belege (GBP/PLN/SEK).

2. **Pre-Flight-Command `mixed-vat-check`** (Commit `7982c6c`):
   - `jtl2datev mixed-vat-check --from … --to …` (oder `--month`) listet Belege mit gemischten Steuersätzen.
   - SQL gegen `tRechnungPosition`, `tExternerBelegPosition`, `tGutschriftPos`, Vater-Position-Filter pro Tabelle.
   - Q1 2026 Live-Run: 0 Treffer.

3. **CLI-Vereinheitlichung** (Commits `dd03366` + `b3d99eb`):
   - Alle 5 Commands akzeptieren entweder `--from`/`--to` oder `--month`.
   - Zentraler Helper `_resolve_date_range()`.
   - DutyPay-Archive nur bei `--month`-Modus; bei `--from`/`--to` ist `--out` Pflicht.

4. **DATEV-Auto-Archive + `export-delta`** (Commit `e1dfa14`):
   - `jtl2datev export --month` archiviert automatisch unter `exports/datev/<YYYY-MM>/<timestamp>.csv`.
   - Neuer Command `jtl2datev export-delta --month` berechnet Delta gegen letzten archivierten Vollexport.
   - Match-Strategie: Belegnr aus Buchungstext (erster Token).
   - EXTF-Format: cp1252-Encoding, Header-/Spaltenzeilen bleiben in Delta-CSV.

5. **`--shift-to-period` shiftet PostingDateInvoice** (Commit `f429fa2`).

6. **Audit-Liste angelegt** (Commit `5094cfd`):
   - `docs/audit-q1-2026-error-belege.md` — 4 ERROR/UNKNOWN-Belege im DATEV-März-Export zur manuellen Prüfung.

**Q1 + Apr 2026 Re-Exporte mit Auto-Archive:** Alle vier Monate archiviert unter `exports/datev/<YYYY-MM>/`, `exports/dutypay/<YYYY-MM>/`.

**Standardworkflow (NEU):**
```
jtl2datev mixed-vat-check --month YYYY-MM
jtl2datev reconcile --month YYYY-MM
jtl2datev export --month YYYY-MM
jtl2datev export-dutypay --month YYYY-MM
jtl2datev export-delta --month YYYY-MM          # falls nachgelagerte Belege
jtl2datev export-dutypay-delta --month YYYY-MM
```

**Tests:** 277 passed, 3 skipped. ruff clean.

## Offene Punkte

0. **Manuelle Prüfung 4 ERROR/UNKNOWN-Belege (User, morgen):** Siehe `docs/audit-q1-2026-error-belege.md`. Nach Prüfung evtl. Engine-Re-Export DATEV März 2026.

1. **`RawInvoiceLine`-Modell-Cleanup:** Item-Felder (sku, description, quantity, weight, manufacturer, commodity_code, …) entsorgen, da bei Header-Umstellung systematisch leer. Reines Refactoring, keine Verhaltensänderung.

2. **Taxually-Export implementieren** — eigenständiger Exporter direkt aus JTL (nicht aus DutyPay-Output abgeleitet).
   - **Format:** XLSX, Sheet `Your data`, 20 Spalten, Dezimaltrennzeichen Punkt, VAT-Rate dezimal (0,19 statt 19).
   - **Länderexporte:** Lokale Meldungen FR/IT/ES/PL/CZ/GB (parallel zum OSS).
   - **Refund-Vorzeichen:** negativ. Transaction-Types: `SALE`, `REFUND`, `SALE-REFUND` (Taxually-exklusiv), konsequent uppercase.
   - **Numerische Spalten:** konsequent Number-Typ schreiben (alte Excel-Skripte hatten Gross teils als String).
   - **Archiv/Delta:** nach Implementation analoge Funktionen nutzen wie DutyPay (gleiche `core/archive.py`-Basis).

3. **Taxually-Archiv/Delta:** Sobald Exporter steht.

4. **Lager-Verbringungen (separates Tool, *nach* DutyPay+Taxually):** Eigene Eingangs- (Amazon-Transaktionsbericht) und Ausgangsdatei. Nicht aus JTL-DB ableitbar.

5. **Probebuchungen filtern (optional):** Belege mit Umsatz 0,00 € raus (z.B. SR202602155/156). Risk: Audit-Trail-Vollständigkeit vs. Noise-Reduktion.

6. **Steuerberater-Klärung (User):** Beleginfo-Felder DATEV (aktuell Spalten 13-17 als Art/Inhalt 1-5). Prüfen ob auf Zusatzinformation-Spalten umsteigen soll (Jera nutzte andere Feldnamen).

7. **VIES-Online-Validierung (langfristig):** Aktuell Format-Plausibilität. Echte VIES-API mit Cache für 100% B2B-Sicherheit.

8. **Restliche DB-Klärungen:** `nSteuereinstellung` (0/10/15/20-Bedeutung), `tRechnungKorrektur`-Vollständigkeit (own invoices credit note logic), `tRechnungStorno`-Auswirkung auf `nIstStorniert`.

9. **Temu-Filter perspektivisch entfernen:** Laut User keine neuen Temu-Belege mehr seit Januar 2026. Der Filter kann komplett entfallen, sobald sichergestellt ist, dass kein neuer Temu-Import stattfindet.

## Notizen für Orchestrator

- Vor jeder Coding-Aufgabe: Interface/Signaturen festlegen, dann an Coder-Agent delegieren.
- Nach Coding-Aufgabe: Docs-Agent fasst Änderungen in passender `docs/*.md` zusammen.
- Erledigtes hier rausnehmen → `docs/status.md`.
- DB ist read-only: nur SELECT, keine DDL/INSERT/UPDATE/DELETE.
