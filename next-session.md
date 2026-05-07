# Next Session

## Status

**Marketplace-Suffix-Strip + Q1-Reconciliation abgeschlossen (2026-05-07).**
- JTL-Konvention: Mehrteil-Sendungen mit `_N`-Suffix in `cExterneAuftragsnummer` (z.B. `406-0538474-1507531_1`). Helper `_strip_marketplace_suffix()` entfernt `_\d+$` in `db_jtl.py`.
- **TransactionID & Belegfeld 1:** Zeigen Original-Order-ID ohne Suffix. DocumentID bleibt Eindeutig-Schlüssel.
- **Q1-DATEV-Cross-Check Engine vs. Jera:** 13.892 Belege, Σ Soll exakt 298.824,55 €, Saldo-Diff +25,70 € (0,1‰), hauptsächlich Jera-Datenqualität (internale IDs vs. Marketplace-Order-IDs). Engine ist Single Source of Truth.
- **Q1-DutyPay-Reconciliation:** DocumentID-Match (statt TX-ID), 13.411 Schnittmenge, Δ −33,95 € (Rundungen).
- 189 Tests grün, ruff clean.
- Siehe `docs/status.md` für Details.

**Repository-Umstellung auf Header-Eckdaten (2026-05-06) abgeschlossen.**
- SQL-Queries lesen Brutto/Netto direkt aus Eckdaten-Tabellen (`tRechnungEckdaten` / `tExternerBelegEckdaten` / `vGutschriftEckdaten`).
- Position-Joins für Beträge entfallen; Coverage Q1 2026 = 100% (273 Gutschriften, 12.287 externe Belege, alle mit Eckdaten).
- Versandkosten-Bug bei externen Belegen gefixt (wurde vorher durch `Vater IS NULL`-Filter fälschlich gefiltert).
- VAT-Rate-Format-Bug gefixt (`2E+1` → `20`).
- Q1-Smoke MAR 2026: Engine vs. Jera Δ −0,03 € über 4807 Belege.
- 177 Tests grün, ruff clean.

**DATEV-Export-Pipeline produktionsreif** für DE-Steuerberater.
- 87 Tests grün, ruff clean.
- 4 Monatsexporte (Jan-Apr 2026) konsistent vs. Jera (wo verfügbar).
- Engine ab April einzige Quelle (Jera EOL nach Software-Update).
- Konten-Mapping nach Jera-Konvention vollständig validiert.
- Audit-Modus (`--audit` Flag) für interne Tax-Rule-Tracing implementiert.
- Compare-Modus (`--compare-to` Flag) für Q1-Reconciliation gegen Referenz aktiv.

**DutyPay-Export-Pipeline produktionsreif** (analog DATEV).
- 165 Tests grün, ruff/mypy clean.
- `export-dutypay` + `export-dutypay-delta` CLI-Commands.
- Automatische Archivierung & Delta-Workflow implementiert.
- DutyPay auf Invoice-Granularität umgestellt (1 Zeile pro Beleg, Item-/Adressfelder leer; konsistent mit Profil 1 / OSS-Mindestpflichtfelder).

## Offene Punkte

0. **Mixed-VAT-Pre-Flight-Check** (`jtl2datev mixed-vat-check --month YYYY-MM`): listet Belege mit gemischten Steuersätzen auf Artikel-Positionen (externe Belege typ=1, mit Vater-Referenz). **Q1 2026: 0 Belege mit Mixed-VAT.** Pre-Flight-Tooling-Item.

1. **`RawInvoiceLine`-Modell-Cleanup:** Item-Felder (sku, description, quantity, weight, manufacturer, commodity_code, …) entsorgen, da bei Header-Umstellung systematisch leer. Reines Refactoring, keine Verhaltensänderung.

2. **DATEV-Export braucht Archiv- und Delta-Mechanismus** (analog DutyPay).
   - `export` und `export-delta` CLI-Commands: nutzen vorhandenes `core/archive.py` (generisch, von DutyPay-Block).
   - Automatische Archivierung unter `exports/datev/<YYYY-MM>/` (nicht unter dutypay/). User hatte bisher Excel/PowerQuery-Methode.

3. **Taxually-Export implementieren** — eigenständiger Exporter direkt aus JTL (nicht aus DutyPay-Output abgeleitet).
   - **Format:** XLSX, Sheet `Your data`, 20 Spalten, Dezimaltrennzeichen Punkt, VAT-Rate dezimal (0,19 statt 19).
   - **Länderexporte:** Lokale Meldungen FR/IT/ES/PL/CZ/GB (parallel zum OSS).
   - **Refund-Vorzeichen:** negativ. Transaction-Types: `SALE`, `REFUND`, `SALE-REFUND` (Taxually-exklusiv), konsequent uppercase.
   - **Numerische Spalten:** konsequent Number-Typ schreiben (alte Excel-Skripte hatten Gross teils als String).
   - **Archiv/Delta:** nach Implementation analoge Funktionen nutzen wie DutyPay (gleiche `core/archive.py`-Basis).

4. **Taxually-Archiv/Delta:** Sobald Exporter steht.

5. **Lager-Verbringungen (separates Tool, *nach* DutyPay+Taxually):** Eigene Eingangs- (Amazon-Transaktionsbericht) und Ausgangsdatei. Nicht aus JTL-DB ableitbar.

6. **Probebuchungen filtern (optional):** Belege mit Umsatz 0,00 € raus (z.B. SR202602155/156). Risk: Audit-Trail-Vollständigkeit vs. Noise-Reduktion.

7. **Steuerberater-Klärung (User):** Beleginfo-Felder DATEV (aktuell Spalten 13-17 als Art/Inhalt 1-5). Prüfen ob auf Zusatzinformation-Spalten umsteigen soll (Jera nutzte andere Feldnamen).

8. **VIES-Online-Validierung (langfristig):** Aktuell Format-Plausibilität. Echte VIES-API mit Cache für 100% B2B-Sicherheit.

9. **Restliche DB-Klärungen:** `nSteuereinstellung` (0/10/15/20-Bedeutung), `tRechnungKorrektur`-Vollständigkeit (own invoices credit note logic), `tRechnungStorno`-Auswirkung auf `nIstStorniert`.

10. **Temu-Filter perspektivisch entfernen:** Laut User keine neuen Temu-Belege mehr seit Januar 2026. Der Filter kann komplett entfallen, sobald sichergestellt ist, dass kein neuer Temu-Import stattfindet.

## Notizen für Orchestrator

- Vor jeder Coding-Aufgabe: Interface/Signaturen festlegen, dann an Coder-Agent delegieren.
- Nach Coding-Aufgabe: Docs-Agent fasst Änderungen in passender `docs/*.md` zusammen.
- Erledigtes hier rausnehmen → `docs/status.md`.
- DB ist read-only: nur SELECT, keine DDL/INSERT/UPDATE/DELETE.
