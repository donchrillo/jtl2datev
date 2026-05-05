# Architektur

## Leitlinien

- **Konsolen-First, Library-Kern**: `core/` ist eine reine Python-Library ohne CLI-/UI-/Framework-Abhängigkeiten. `cli.py` ist nur Adapter.
- **Spätere Migration**: Wenn die Logik steht, wandert `core/` in das ERP-Monorepo (FastAPI + React 19). Dort wird ein FastAPI-Router um die gleichen Funktionen gebaut, das Frontend ruft sie über die API.
- **Repository-Pattern für DB**: JTL heute, eigenes ERP morgen. Tausch über Interface, nicht über Code-Änderung im Kern.
- **Eigene Steuer-Engine, JTL-Tax nur als Referenz** (Entscheidung 2026-05-05):
  Wir replizieren NICHT JTLs `Steuern.*`-Schlüssellogik. Stattdessen lesen wir
  die rohen Beleg-Fakten (Versandland, Lieferland, Rechnungsland, USt-IdNr.,
  Plattform, Beträge je Position) und wenden unsere eigenen Regeln an. JTLs
  gespeicherter Steuerschlüssel/Erlöskonto wird mitgelesen und dient nur als
  **Plausi-Referenz**: Mismatch-Erkennung wie bei Taxdoo/Jera. Begründung:
  Amazon liefert teilweise falsche Steuern (z.B. PL→IT mit polnischer USt
  statt italienischer), JTL speichert das so, der DATEV-Export muss aber das
  **korrekte** Ergebnis enthalten oder einen Konflikt anzeigen. Wiederverwendung:
  diese Engine wandert mit ins TOCI-ERP.

## Kern-Module (implementiert als Skelett)

| Modul | Status | Verantwortung |
|---|---|---|
| `core/config.py` | ✓ | Pydantic-Settings: DB-Connection, DATEV-Mandant, Konten-Mappings |
| `core/models.py` | ✓ | RawInvoice, RawInvoiceLine, PartyAddress, TaxTreatment, TaxDecision, LineDecision, ReconcileMismatch |
| `core/repositories.py` | ✓ | Abstrakte Interfaces: InvoiceRepository |
| `core/db_jtl.py` | ✓ | JTL-MSSQL-Implementierung, read-only. `fetch_invoices()` mit `_fetch_own()` + `_fetch_external()` (Streaming-Cursor, 2026-05-05) |
| `core/tax_engine.py` | ✓ | Eigene Steuer-Engine: aus Beleg-Fakten (Versandland, Lieferland, Rechnungsland, USt-IdNr., Plattform, Sätze) → TaxTreatment-Entscheidung (Inland / OSS B2C / IGL B2B / Drittland / Marketplace-Facilitator UK/CH) |
| `core/rules.py` | ⧖ | Konten-Mapping (Steuerentscheidung × Lagerland × Plattform → DATEV-Sachkonto + USt-Schlüssel). Stub. |
| `core/reconcile.py` | ✓ | Plausi-Check: Vergleich JTL-gespeichert vs. eigene Engine — ReconcileMismatch-Report bei Abweichungen |
| `core/datev.py` | ⧖ | DATEV-CSV-Erzeugung (EXTF Buchungsstapel). Stub. |
| `cli.py` | ✓ | Click-Wrapper, `export --from --to --out`. Error-Handling für NotImplementedError + DB-Fehler. |

Legend: ✓ = Implementiert/Getestet, ⧖ = Stub

## Datenfluss (Stand 2026-05-05, revidiert)

```
JTL-MSSQL
 ├─ dbo.tRechnung + tRechnungPosition          ┐  Repository
 ├─ Rechnung.tExternerBeleg* (Amazon/Otto)     │  liest ROHFAKTEN
 └─ JTL-eigener Steuerschluessel/Erloeskonto   │  (Lager, Lieferland,
    (mitgelesen als Referenz)                  │   Beträge, USt-IdNr.,
                                               │   Plattform, Sätze)
                                               ▼
                                core/models.py  (RawInvoice — neutral)
                                               │
                                               ▼
                                core/tax_engine.py
                                  → korrekte Steuerentscheidung
                                  (Inland / OSS / IGL-B2B / Drittland /
                                   Marketplace-Facilitator UK/CH)
                                               │
                                               ▼
                                core/reconcile.py  ─► Mismatch-Report
                                  (JTL-gespeichert vs. Engine-berechnet)
                                               │
                                               ▼
                                core/rules.py  (DATEV-Sachkonto +
                                                USt-Schlüssel-Mapping)
                                               │
                                               ▼
                                core/datev.py  (EXTF-CSV)
```

### Steuer-Engine: Eingaben

Die Engine bekommt nur Fakten, **nie** JTLs Steuerentscheidung als Input
(die fließt nur in `reconcile.py`):

- Versand-/Lagerland (`cVersandlandISO`)
- Rechnungsland + Bundesland
- Lieferland + Bundesland
- USt-IdNr. des Kunden (+ Validitätsstatus, falls vorhanden)
- Plattform (`kPlattform`, eBay/Kaufland/Amazon/Otto)
- Belegdatum / Leistungsdatum
- je Position: Steuersatz % (vom Beleg), Netto, Brutto, Warengruppe?

### Steuer-Engine: Ausgabe je Position

- `tax_treatment ∈ { domestic, oss_b2c, igl_b2b, third_country, marketplace_facilitator }`
- Soll-Steuersatz (was sollte korrekterweise drauf?)
- Land der Steuerschuld
- Hinweis-Flag bei Sonderfall (UK/CH-Amazon, Differenz zu JTL etc.)

### Geschäftsregeln-Kurzfassung (siehe `tax-rules.md`)

- Lagerland == Zielland → lokale USt (eigene Steuer-IDs in DE/FR/IT/ES/PL/CZ/UK)
- Lagerland != Zielland innerhalb EU → OSS
- EU-B2B mit gültiger USt-IdNr. → Reverse-Charge
- Drittland (außer eigene Lokal-Lager) → steuerfrei §4 Nr. 1a
- UK/CH über Amazon → Marketplace-Facilitator-Spezialfall (Amazon zieht Steuer)

### Quellen-Routing für Rechnungen

| Quelle             | JTL-Daten                                          |
|--------------------|----------------------------------------------------|
| eBay, Kaufland     | `dbo.tRechnung` (eigene), `nIstExterneRechnung=0` |
| Amazon, Otto       | externe Belege — TBD: `tRechnung.nIstExterneRechnung=1` ODER `tExternerBeleg*`. Beziehung muss noch geklärt werden. |
| TEMU               | **außerhalb dieses Tools**                         |

## Was noch offen ist

**Klärungen zu `fetch_invoices`-Implementierung** (dokumentiert in `next-session.md` Punkt 1):
- `nTyp` 0/1 in `tRechnungAdresse` (Liefer- vs. Rechnungsadresse)
- `tRechnungKorrektur`-Tabelle und Gutschrift-Logik (Kreditnoten-Erkennung)
- VAT-Berechnung `tExternerBelegPosition` (Mengen-Handling)

**Blocker für `core/rules.py` + `core/datev.py`:**
- DATEV-Format genau (EXTF Buchungsstapel v7.0? Andere?)
- Echte DATEV-Steuerschlüssel-Codes (in `Steuern.vSteuerschluesselDaten`)
- Mandant, Berater, Sachkonten-Längen, Buchungsperioden-Format
- Konten-Mapping je Lagerland × Kundentyp × Steuersatz
- Beispiel-Export aus Jera-Tool (zum Abgleich)
