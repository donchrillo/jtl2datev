# Next Session

## Status

Architektur-Skelett + DB-Datenlese-Layer steht (12 Tests grün, ruff clean).
DB-Schema komplett erfasst (`docs/db-schema.md`), `fetch_invoices` implementiert:
708 eigene Rechnungen + 2835 externe Belege = 3543 April 2026.
`.env` vorhanden, Connection getestet.

**Nächste Phasen:** (1) Offene DB-Annahmen klären, (2) DATEV-Format-Spec + Steuer-Regeln verfeinern.

## Offene Punkte

### 1. Offene Annahmen aus `fetch_invoices`-Implementierung klären

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
