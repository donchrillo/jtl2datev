# Aufgeschobene Review-Findings

> Stand: 2026-05-10
> Quelle: ehemalige Review-Reports vom 2026-05-09 (Tax/Architektur/Robustheit), konsolidiert in `CONSOLIDATED.md`. Erledigte Punkte (Sprint A–D + Einzel-Tickets) wurden umgesetzt; dieses Dokument hält die bewusst nicht angegangenen Findings fest.

## Bewusst nicht relevant

### B-6 (Anteil eBay UK) — entfällt
MF-Erkennung in `tax_engine.py` ist auf `_AMAZON_PLATFORM_PREFIX` gehängt; eBay-UK-Verkäufe würden als `THIRD_COUNTRY` durchlaufen. **Kein Handlungsbedarf:** ToCi macht kein eBay UK. Falls sich das ändert, müssen `_AMAZON_PLATFORM_PREFIX` zu einer Liste/Map erweitert und Tests ergänzt werden.

### B-5 (RO 21 % Stichtag) — irrelevant
Tool wird produktiv erst ab 2026-01-01 eingesetzt. Der RO-21%-Wechsel (vorheriger Satz 19 %) liegt vor diesem Stichtag, der heute hinterlegte Satz ist also für alle vom Tool gebuchten Belege korrekt. Keine Steuerberater-Rückfrage notwendig.

## Aufgeschoben (umsetzen wenn Anlass)

### B-7 — `gross==net`-MF-Trigger ohne £135-Schwelle
**Status:** Bewusst ausgelassen (Sprint-B-Commit `70d18b2`).
**Begründung:** Wir sind UK-VAT-registriert. Auch oberhalb £135 mit `gross==net` ist die Buchung als MF korrekt für unseren Fall — die Schwelle wäre nur für nicht-UK-registrierte Händler relevant.
**Wann angehen:** Falls UK-Steuerregistrierung aufgegeben wird oder Multi-Mandanten-Betrieb mit nicht-UK-registrierten Mandanten kommt.

### B-8 — SRK-Logik ohne Cross-Check zur Master-RK
**Status:** Aufgeschoben.
**Risiko:** Eine SRK (`R`-Beleg in `tGutschrift`) wird ohne Querprüfung gegen die zugehörige Master-Rechnung gebucht. Falls die Master-RK nicht im Export landet (z. B. weil außerhalb des Datumsbereichs), entsteht eine unausgeglichene Buchung.
**Wann angehen:** Bei Auftreten von SRK-Massenfällen oder wenn Reconcile entsprechende Mismatches meldet.

### W-2 — Period-Validity für VAT-Rates
**Status:** Helper-Signatur `vat_rate_for(country, on_date=None)` in `core/reference_data.py:144` vorhanden, `on_date` wird ignoriert.
**Wann angehen:** Bei Re-Exports älterer Monate über VAT-Wechsel-Stichtage hinweg (z. B. RO 19 % → 21 %, EE-Anpassungen). Aktuell nicht relevant, weil das Tool erst ab 2026-01-01 produktiv läuft.

### W-3 — VIES-Online-Validierung
**Status:** Aktuell nur Format-Plausibilität (`looks_like_valid_vat_id`).
**Wann angehen:** Langfristig, wenn echte B2B-Sicherheit benötigt wird oder eine VIES-Cache-Infrastruktur ohnehin existiert. Derzeit kein konkreter Schadensfall belegt.

### W-6, W-7 — Verbringungs-PDF Footer-Hinweise
**Offen:** §10 Abs. 4 UStG (Bewertungsmethode) und §16 Abs. 6 UStG (Monatsmittelkurs) sollen im PDF-Footer zitiert werden.
**Blocker:** Steuerberater-Freigabe für unsere Bewertungs­methode (10 % Listenpreis, Floor 0,01 €, Fallback 0,10 €).
**Wann angehen:** Nach Steuerberater-Termin.

## Steuerberater-Klärung CH-Buchung

Siehe `next-session.md` Punkt 4b. CH wird aktuell als Drittlandsexport (4121000) gebucht, auch wenn Amazon Schweizer MWSt einbehält (MWSTG Art. 20a). Klärung offen, ob CH künftig wie GB als Marketplace-Facilitator (4328000) behandelt werden soll. Falls ja: `tax_engine.py` `MARKETPLACE_FACILITATOR_DESTINATIONS` um `"CH"` erweitern und Test in `tests/test_tax_engine.py` zurückrollen (Commit `54d6eeb` rückgängig).
