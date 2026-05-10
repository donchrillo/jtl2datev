# Next Session

## STATUS 2026-05-11: Repo eingefroren

Der Code ist als `accounting`-Modul in toci-erp integriert. Weiterentwicklung dort.
Dieser Plan unten gilt nur, falls jtl2datev wieder separat aktiviert werden sollte.

---

## Stand: Sprint abgeschlossen, läuft End-to-End

jtl2datev ist als Tool in toci-erp integriert (Dev-Setup):
- Eigener uvicorn auf `127.0.0.1:8402`, via `~/toci-erp/start.sh` mitgestartet
- Frontend-Page `Tools → DATEV-Export` in toci-erp, gegated mit `accounting`-Permission
- Shared HS256-JWT (`SECRET_KEY` in beiden `.env`), Vite-Proxy `/api/v1/jtl-datev/*` → `:8402`
- **Caddy bleibt unangetastet** — läuft weiter nur für TEMU-stable
- Branch `feat/frontend-ready` (jtl2datev) gepusht, kein PR-Merge-Druck

## Was als Nächstes konkret ansteht

Keine Sprint-Folgearbeit zwingend. Nachziehbar wenn Zeit:

- **DATEV-Page von Smoke-Test-Niveau aus polieren** (User-Feedback erst sammeln)
- **`SECRET_KEY` ersetzen** vor jeder Produktion-Nutzung — dann in BEIDEN `.env`-Dateien gleichzeitig (sonst bricht JWT zwischen Services)
- **systemd-Unit für jtl2datev** statt start.sh-Mitstart (wenn Setup stabilisiert)

## Deferred bis ERP-Cutover (JTL ablöst)

Aus dem Senior-Cloud-Review, alles erst beim ERP-Ablöse-Sprint relevant:

- JTL-SQL-Lecks in `core/preflight.py` + `core/verbringung_pricing.py` hinter Repository-Methoden verstecken
- API-Router auf `InvoiceRepository`-ABC typen statt konkreter `JtlInvoiceRepository`
- `RawInvoice.source` Literal-Werte (`jtl_own` etc.) generalisieren
- Toci-erp-Schema ergänzen: `currency`, `currency_factor`, `warehouse_country`, `is_credit_note`, `invoice_no`
- Pydantic-Schemas mit `description`/`examples` für besseren TS-Codegen

## Offene Punkte — Audit & Dateneingabe

0. **Manuelle Prüfung 4 ERROR/UNKNOWN-Belege (User):** Siehe `docs/audit-q1-2026-error-belege.md`. Nach Prüfung evtl. Engine-Re-Export DATEV März 2026.

1. **Engine-only-Belege Feb/Mar Validierung:** Q1-Reconcile zeigt ~590 sequentielle Belege `202630260xxx` (FEB) / `202650012xxx` (MAR) die in Engine vorkommen, aber nicht in Jera-PowerQuery-Export. Prüfen ob tatsächlich Taxually-meldepflichtig oder Doppel-Einspielung.

4. **Steuerberater-Klärung (User):** Beleginfo-Felder DATEV (aktuell Spalten 13-17 als Art/Inhalt 1-5). Prüfen ob auf Zusatzinformation-Spalten umsteigen soll (Jera nutzte andere Feldnamen).

4b. **Steuerberater-Klärung CH-Buchung (User):** CH wird aktuell als regulärer Drittlandsexport gebucht (4121000), auch wenn Amazon die Schweizer MWSt einbehält (Plattformbesteuerung MWSTG Art. 20a ab 01.01.2025). Klären ob CH künftig wie GB als Marketplace-Facilitator (4328000) gebucht werden soll. Falls ja: in `core/tax_engine.py` `MARKETPLACE_FACILITATOR_DESTINATIONS` um `"CH"` erweitern (Sprint-B-Revert vom 2026-05-10 zurückrollen). Audit-Tag in `rules.py` Rule 8 (`THIRD-EU-{wh}-CH`) ist aktuell irreführend, weil CH kein EU-Land ist — Note „THIRD_COUNTRY to EU dest — verify" könnte angepasst werden, ist aber explizit „erstmal so lassen" (User 2026-05-10).

5. **VIES-Online-Validierung (langfristig):** Aktuell Format-Plausibilität. Echte VIES-API mit Cache für 100% B2B-Sicherheit.

6. **Restliche DB-Klärungen:** `nSteuereinstellung` (0/10/15/20-Bedeutung), `tRechnungKorrektur`-Vollständigkeit (own invoices credit note logic), `tRechnungStorno`-Auswirkung auf `nIstStorniert`.

8. **SK-Departure-Bewegungen Taxually-Klärung (User):** SK→CZ/DE/PL FC_TRANSFERs werden aktuell mit leerer Departure-VAT-ID exportiert. Steuerlich ordnen die Finanzämter diese bisher Amazon zu (nicht uns), Pro-Forma-PDFs werden weiterhin als Beleg erzeugt. Offen: Verarbeitet Taxually XLSX-Zeilen mit leerer SK-VAT überhaupt? Falls nein, alternative Strategien: (a) SK-Departure-Zeilen aus dem XLSX rausfiltern (PDFs trotzdem behalten), (b) komplett weglassen. Vor Q2-Meldung klären.

## Deferred bis Multi-Mandanten

- **W-20-Settings-Override:** Konten-Mappings (`DOMESTIC_ACCOUNT_BY_WAREHOUSE`, `DEBITOR_BY_PAYMENT`) aus Settings/DB pro Mandant statt Modul-Konstanten.
- **W-20-Period-Validity:** `STANDARD_VAT_RATE` auf Period-Gültigkeit (Logik noch nicht umgesetzt).

## Status: 437 Tests grün, API auth-geschützt, Frontend-Integration end-to-end verifiziert
