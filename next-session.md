# Next Session

## Status

Architektur-Skelett + DB-Datenlese-Layer + Reconcile-Pipeline stehen
(20 Tests grün, ruff/mypy clean). 3 DB-Quellen integriert
(`Rechnung.tRechnung`, `tExternerBeleg`, `dbo.tgutschrift`). Engine ist
99,94% deckungsgleich mit JTL (8 Mismatches in Q1 2026 / 13 619 Belegen).

**Nächste Phasen:** (1) Engine-Feintuning anhand der Q1-Mismatches,
(2) DATEV-Format-Spec + Konten-Mapping, (3) DATEV-CSV-Export.

## Offene Punkte

### 1. Marketplace-Facilitator-Severity in Reconcile auf `info` setzen

Engine sagt 0% (Amazon kassiert UK/CH-VAT selbst), JTL speichert den Roh-VAT-Satz — das ist **kein Konflikt**, sondern erwartet. `core/reconcile.py` sollte für `treatment in {MARKETPLACE_FACILITATOR}` Mismatches mit severity=`info` produzieren statt `error`/`warn`.

### 2. VIES-Online-Validierung der USt-IdNrn (später)

Aktuell: Format-Plausibilitätscheck (`looks_like_valid_vat_id`). Echte VIES-API-Anbindung für definitive B2B-Klassifikation. Ergebnisse cachen.

### 2. Offene Annahmen aus `fetch_invoices`-Implementierung klären

- ~~`nTyp` 0/1~~: **bestätigt 2026-05-05** via `vRechnungLieferadresse`/`vRechnungRechnungsadresse`. `0` = Liefer, `1` = Rechnung.
- ~~Gutschriften eigener Rechnungen~~: **implementiert 2026-05-05** als `_fetch_credit_notes()`, dritte Quelle. Q1 2026: 245 Belege.
- **VAT-Berechnung `tExternerBelegPosition`**: Menge >1 → `vat_amount = brutto - netto` je Position (Annäherung; exakter wäre `Anzahl × (Brutto-Unit − Netto-Unit)`, in Amazon-Praxis typischerweise Gesamtpreise je Zeile).

### 2. DATEV-Format-Spezifikation (`docs/datev-format.md`)

- DATEV-Format konkret (vermutlich EXTF Buchungsstapel v7.0)
- Beispiel-Export aus Jera-Tool zum Abgleich
- Mandantennummer, Berater, Sachkonten-Längen
- Konfigurierbare Mappings (Erlöskonten je Steuersatz/Land/Lagerland)

### 3. Steuer-/Länder-Regeln verfeinern (`docs/tax-rules.md`)

- konkrete USt-Sätze + Sachkonten je Lagerland (DE/PL/CZ/FR/IT/ES/GB)
- Marketplace-Facilitator-Erkennung UK/CH (Amazon-Plattform-IDs 53 für UK;
  prüfen ob Beleg-Brutto = Netto bei Facilitator-Fällen)
- USt-IdNr.-Validierung (VIES) — JTL-seitig nicht ersichtlich, eigene Logik nötig
- Gutschriften-Konvention (`nBelegtyp=1` extern, `tRechnungKorrektur` eigene)

### 4. Restliche kleinere DB-Klärungen (siehe `docs/db-schema.md` „Offene Punkte")

- `nSteuereinstellung`-Werte 0/10/15/20: Bedeutung
- `Rechnung.tRechnungKorrektur` — Spalten + Verknüpfung
- `Rechnung.tRechnungStorno` — Auswirkung auf Buchung

## Notizen für Orchestrator

- Vor jeder Coding-Aufgabe: Interface/Signaturen festlegen, dann an Coder-Agent delegieren.
- Nach Coding-Aufgabe: Docs-Agent fasst Änderungen in passender `docs/*.md` zusammen.
- Erledigtes hier rausnehmen → `docs/status.md`.
- DB ist read-only: nur SELECT, keine DDL/INSERT/UPDATE/DELETE.
