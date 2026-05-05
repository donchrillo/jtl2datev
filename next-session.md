# Next Session

## Status

**DATEV-Export-Pipeline produktionsreif** für DE-Steuerberater.
- 87 Tests grün, ruff clean.
- 4 Monatsexporte (Jan-Apr 2026) konsistent vs. Jera (wo verfügbar).
- Engine ab April einzige Quelle (Jera EOL nach Software-Update).
- Konten-Mapping nach Jera-Konvention vollständig validiert.
- Audit-Modus (`--audit` Flag) für interne Tax-Rule-Tracing implementiert.
- Compare-Modus (`--compare-to` Flag) für Q1-Reconciliation gegen Referenz aktiv.

## Offene Punkte

1. **Steuerberater-Klärung (User):** Beleginfo-Felder (aktuell Spalten 13-17 als Art/Inhalt 1-5). Prüfen ob auf Zusatzinformation-Spalten umsteigen soll (Jera nutzte andere Feldnamen).

2. **DutyPay-Export:** Separates Output-Format für OSS-Report. Sample `samples/jera/DutyPay-Sale-2026-MAR.csv` analysieren, `core/dutypay.py` implementieren.

3. **TaxOily-Berichte je Lagerland:** Dritter Output-Pfad für lokale Steuerberater (FR/IT/ES/PL/CZ/GB). Routing per `--output-format` Flag.

4. **Probebuchungen filtern (optional):** Belege mit Umsatz 0,00 € raus (z.B. SR202602155/156). Risk: Audit-Trail-Vollständigkeit vs. Noise-Reduktion.

5. **VIES-Online-Validierung (langfristig):** Aktuell Format-Plausibilität. Echte VIES-API mit Cache für 100% B2B-Sicherheit.

6. **Restliche DB-Klärungen:** `nSteuereinstellung` (0/10/15/20-Bedeutung), `tRechnungKorrektur`-Vollständigkeit (own invoices credit note logic), `tRechnungStorno`-Auswirkung auf `nIstStorniert`, VAT-Berechnung `tExternerBelegPosition` bei Menge > 1.

## Notizen für Orchestrator

- Vor jeder Coding-Aufgabe: Interface/Signaturen festlegen, dann an Coder-Agent delegieren.
- Nach Coding-Aufgabe: Docs-Agent fasst Änderungen in passender `docs/*.md` zusammen.
- Erledigtes hier rausnehmen → `docs/status.md`.
- DB ist read-only: nur SELECT, keine DDL/INSERT/UPDATE/DELETE.
