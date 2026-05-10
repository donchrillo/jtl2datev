# Next Session

## Tag 2.2 (nächste Sessions)

**Caddy + Service-Start** (User-Aufgabe). Caddy als Reverse-Proxy vor FastAPI (jtl2datev-api auf :8000, toci-erp auf :3000) mit shared TLS. Health-Checks, HTTP/2.

## Tag 2.3 (User-Integration)

**Frontend-Anbindung in toci-erp.** React 19 bindet `/api/v1/jtl-datev/...`-Endpoints an, JWT-Bearer-Token wird beim toci-erp-Login erzeugt und an alle jtl2datev-Requests mitgegeben.

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

## Status: 437 Tests grün, API komplett auth-geschützt, Framework-agnostischer Core
