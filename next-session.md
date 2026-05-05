# Next Session

## Status

Datenleseschicht + Steuer-Engine + Reconcile + **DATEV-Export** stehen
(73 Tests grün, ruff clean). Smoke gegen Jera-Sample März 2026:
4823 Buchungen vs. 4807 (Δ +16). Konten-Verteilung sehr nah am Original
(größte Abweichung 4001000 ist nun Δ +28 — vorher +995, Fix war
EU→DE-OSS-Sonderfall).

## Offene Punkte

### 1. Kundenname / Adressdaten in `RawInvoice`

`PartyAddress` hat aktuell nur `country_iso`, `region`, `vat_id`. Für DATEV
sollten Vorname + Nachname rein, damit Buchungstext und Beleginfo „Kundenname"
gefüllt werden können. Anpassen:
- `models.py`: `PartyAddress.first_name: str | None`, `last_name: str | None`, `company: str | None`
- `db_jtl.py`: `cVorname`, `cName`, `cFirma` in den 3 SQL-Queries mitlesen + mappen
- `datev.py`: Buchungstext-Format `f"{invoice.invoice_no} {bill_to.first_name or ''} {bill_to.last_name or ''}"`

### 2. GB-Lager-Edge-Cases (Engine)

Engine markiert `wh=GB, dest=EU` als UNKNOWN, weil `GB` nicht in `EU_COUNTRIES`.
Jera bucht solche Fälle korrekt auf 4121000 (UK-Re-Export = Drittlandsausfuhr).
~67 Belege im März 2026 betroffen. Fix:
- Engine: GB-Lager-Sonderfall → wenn `wh=="GB"` und `dest != "GB"` → THIRD_COUNTRY-äquivalent
- `rules.py` für THIRD_COUNTRY+wh=GB → 4121000 (passt schon)

### 3. DutyPay-Export

Separater Output für OSS-Bericht (DutyPay-Tool). Format-Sample liegt unter
`samples/jera/DutyPay-Sale-2026-MAR.csv`. Kommt in `core/dutypay.py` als
zweiter Writer; gleiche `RawInvoice`-Modelle, anderes Output-Format.

### 4. Marketplace-Facilitator Reconcile-Severity

`reconcile.py` sollte für `treatment == MARKETPLACE_FACILITATOR` Mismatches
mit severity `info` produzieren (kein Konflikt — Amazon kassiert UK-VAT selbst,
JTL speichert Roh-Wert).

### 5. VIES-Online-Validierung (langfristig)

Aktuell: Format-Plausibilitätscheck (`looks_like_valid_vat_id`).
Echte VIES-API-Anbindung mit Cache für definitive B2B-Klassifikation.

### 6. Restliche DB-Klärungen

- `nSteuereinstellung`-Werte 0/10/15/20: Bedeutung
- `Rechnung.tRechnungKorrektur` — Spalten + Verknüpfung (für is_credit_note bei eigenen Belegen)
- `Rechnung.tRechnungStorno` — Auswirkung auf Buchung
- VAT-Berechnung `tExternerBelegPosition` mit Menge >1 (aktuell Annäherung)

### 7. Steuer-/Länder-Regeln verfeinern (`docs/tax-rules.md`)

- konkrete USt-Sätze + Sachkonten-Übersicht je Lagerland — größtenteils erledigt durch `rules.py`, aber Doku noch nicht synchronisiert
- Belegfeld 2 — Inhalt klären (in Sample manchmal 8-stellige Zahl, vermutlich JTL-Auftrags-Key)

## Notizen für Orchestrator

- Vor jeder Coding-Aufgabe: Interface/Signaturen festlegen, dann an Coder-Agent delegieren.
- Nach Coding-Aufgabe: Docs-Agent fasst Änderungen in passender `docs/*.md` zusammen.
- Erledigtes hier rausnehmen → `docs/status.md`.
- DB ist read-only: nur SELECT, keine DDL/INSERT/UPDATE/DELETE.
