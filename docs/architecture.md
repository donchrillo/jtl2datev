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
| `core/config.py` | ✓ | Pydantic-Settings: DB-Connection, DATEV-Mandant, Konten-Mappings, own_vat_ids |
| `core/models.py` | ✓ | RawInvoice, RawInvoiceLine (synthetisch mit Header-Aggregaten), PartyAddress (first_name/last_name/company), TaxTreatment, TaxDecision, LineDecision, ReconcileMismatch |
| `core/repositories.py` | ✓ | Abstrakte Interfaces: InvoiceRepository |
| `core/db_jtl.py` | ✓ | JTL-MSSQL-Implementierung, read-only. SQL-Queries lesen Brutto/Netto direkt aus Eckdaten-Tabellen. `fetch_invoices()` mit `_fetch_own()` (eBay/Kaufland/Otto/JTL-manuell; nutzt `tRechnungEckdaten`) + `_fetch_external()` (nur Amazon-VCS; nutzt `tExternerBelegEckdaten`) + `_fetch_credit_notes()` (nutzt `vGutschriftEckdaten`). Helper `derive_vat_rate(gross, net)` leitet Steuersatz ab mit Snap auf Standard-Rate (±0,5 pp Toleranz). Jede `RawInvoice` hat exakt eine `RawInvoiceLine` mit Header-Beträgen. |
| `core/tax_engine.py` | ✓ | Eigene Steuer-Engine: aus Beleg-Fakten → TaxTreatment (DOMESTIC / OSS_B2C / IGL_B2B / THIRD_COUNTRY / MARKETPLACE_FACILITATOR). VAT-ID-Format-Plausibilität, GB-Sonderfall. |
| `core/rules.py` | ✓ | Konten-Mapping: TaxTreatment × Lagerland × Bestimmung → (DATEV-Sachkonto, BU-Schlüssel). Jera-Konvention (IGL→4126, THIRD_COUNTRY→4121). Mit Audit-Tag-Support. |
| `core/reconcile.py` | ✓ | Plausi-Check: JTL-gespeichert vs. Engine. ReconcileMismatch-Report mit Severity (error/warning/info). Mismatch-CSV-Export. |
| `core/datev.py` | ✓ | DATEV-EXTF-CSV-Erzeugung (v7.0, Format 12). Windows-1252, CRLF. `BuchungsRow`-Dataclass (22 benannte Felder) mit `to_csv_row()`-Methode kapselt Spalten-Mapping. Flags `--compare-to` und `--audit` implementiert. |
| `core/dutypay.py` | ✓ | DutyPay-CSV-Export (98 Spalten OSS-Meldungsformat, openpyxl, UTF-8, Semikolon-Trennzeichen, Dezimalkomma). |
| `core/dutypay_delta.py` | ✓ | Delta-Diff für DutyPay (Match nach DocumentID, `--shift-to-period` für Folgemonats-Nachmeldungen). |
| `core/taxually.py` | ✓ | Taxually-XLSX-Export (20 Spalten, Sheet `Your data`, Punkt-Dezimal, VAT-Reporting-Country-Entscheidungslogik). |
| `core/taxually_delta.py` | ✓ | Delta-Diff für Taxually (Match nach DocumentID, `--shift-to-period` analog DutyPay). |
| `core/verbringung_parser.py` | ✓ | Amazon-Transactional-Report TXT-Parser (tab-separated, ~95 Spalten). Filter FC_TRANSFER + INBOUND. |
| `core/verbringung_pricing.py` | ✓ | SKU-Mapping (6-Tier-Lookup: Tier 1–4 Standard, Tier 5 B-Ware-Erkennung + 10%-Bewertung, Tier 6 ASIN-Lookup). EK-Netto-Lookup mit Fallback. `PricingResult` mit `is_bware`-Flag und `bware_pricing_basis`. Q1-2026 100% Coverage. |
| `core/verbringung_taxually.py` | ✓ | XLSX-Generator (20 Spalten, openpyxl), identisch zu Taxually-Format. B-Ware-Marker `(B-Ware)` in Description. |
| `core/verbringung_pdf.py` | ✓ | Pro-Forma-PDF (reportlab): Header, Fachtext, VAT-IDs, Tabelle, Währungs-Summen. B-Ware-Artikel-Beschreibung mit Suffix. |
| `core/exchange_rates.py` | ✓ | JSON-Storage (`data/exchange_rates.json`) + BMF-CSV-Importer. API: `load_rates`, `get_rate`, `set_rate`, `get_rates_for_period`, `fetch_bmf_csv`, `parse_bmf_csv`, `import_bmf_rates`. |
| `core/reference_data.py` | ✓ | Stammdaten-Zentralisierung: EU_MEMBER_STATES, COUNTRY_CURRENCY, PLATFORM_COUNTRY, HARD_MIN_INVOICE_DATE. Single Source für länder-/währungs-/plattformübergreifende Constants. |
| `core/archive.py` | ✓ | Generischer Archiv-Helfer für DATEV/DutyPay/Taxually/Verbringungen (Auto-Verzeichniserstellung, Timestamp-Naming). |
| `cli.py` | ✓ | Click-Wrapper: `export`, `export-delta`, `export-dutypay`, `export-dutypay-delta`, `export-taxually`, `export-taxually-delta`, `export-verbringung`, `import-rates`, `mixed-vat-check`, `reconcile`. Error-Handling für DB/Validation. |

Legend: ✓ = Implementiert/Getestet, ⧖ = Stub

## Datenfluss (Stand 2026-05-06, Header-Eckdaten-Umstellung)

```
JTL-MSSQL
 ├─ Rechnung.tRechnung + tRechnungEckdaten    ┐  Repository
 │  + tRechnungAdresse (eBay, Kaufland,       │  liest ROHFAKTEN
 │   Otto, JTL-manuell)                       │  direkt aus Eckdaten:
 ├─ Rechnung.tExternerBeleg* + Eckdaten       │  Brutto/Netto-Header,
 │  (NUR Amazon-VCS)                          │  Lager, Lieferland,
 ├─ dbo.vGutschriftEckdaten + tgutschrift     │  USt-IdNr., Plattform
 │  (Gutschriften/Korrekturen)                │  (Position-Joins
 └─ JTL-Steuerschluessel/Erloeskonto          │   entfallen für Beträge)
    (mitgelesen als Referenz)                 │
                                               ▼
                                core/models.py
                                  RawInvoice mit synth. Single-Line
                                  (1 RawInvoiceLine mit Header-Beträgen
                                   + abgeleiteter VAT-Rate)
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
                        core/datev.py + core/dutypay.py + core/taxually.py
                           (EXTF-CSV / DutyPay-CSV / Taxually-XLSX)
                                               │
                                               ▼
                   core/archive.py (Auto-Archivierung unter exports/)
```

### IO-Sicherheit: Atomic Writes & Archiv-Race-Prevention

Alle Schreibvorgänge nutzen **tmp + replace** für Fehler-Sicherheit:
- DATEV-Export (`core/datev.py`): `<path>.tmp` → `os.replace()`, tmp-Cleanup bei Exception
- DutyPay/Taxually-XLSX (`core/dutypay.py`, `core/taxually.py`): openpyxl-`save()` auf `.tmp`, dann rename
- Verbringungen-XLSX (`core/verbringung_taxually.py`): analog tmp+replace
- Exchange-Rates-JSON (`core/exchange_rates.py`): atomic json-dump

Auto-Archive-Race-Prevention:
- Timestamp-Format: Microseconds (`%Y-%m-%d_%H-%M-%S-%f`) statt Sekunden
- Collision-Suffix-Fallback (`_2`, `_3`, …) für identische Timestamps in parallelen Runs
- `core/archive.py:archive_export()` und `archive_delta()` nutzen beide Mechanismen

Effekt: Kein korrupter CSV/XLSX möglich bei Strg+C, parallelen Läufen oder Festplattenfehler-Fehler.

### DB-Ressourcen-Management: `managed_engine()` Context-Manager

Alle 8 CLI-Commands verwenden `managed_engine(settings)` Context-Manager:
```python
with managed_engine(settings) as engine:
    repo = JtlInvoiceRepository(engine)
    # Logik
    # Garantierte engine.dispose() bei Exit (auch Exception)
```

Effekt: Verbindungs-Pool-Cleanup, keine Ressourcen-Leaks bei sequentiellen Läufen.

### Encoding-Robustheit: File-Import

Externe CSV/TSV-Dateien (BMF-Wechselkurse, Amazon-Transactional-Reports) mit Encoding-Detection:
- **BMF-CSV** (`core/exchange_rates.py`): utf-8-sig → utf-8 → iso-8859-1 Fallback
- **Amazon-TSV** (`core/verbringung_parser.py`): utf-8-sig → utf-8 → utf-16 → utf-16-le → cp1252 Fallback

Jeder Parser hat `_detect_encoding()` Helper.

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
| eBay, Kaufland, Otto, JTL-manuell | `Rechnung.tRechnung` — `_fetch_own()`. Otto liegt **nicht** in `tExternerBeleg`, sondern wie alle anderen Eigen-Belege in `tRechnung`. |
| Amazon (ab 2024-11-01) | `Rechnung.tExternerBeleg*` (VCS-Import) — `_fetch_external()`. **Nur Amazon** landet hier. |
| Amazon (vor 2024-11-01 / manuell korrigiert) | `Rechnung.tRechnung` — `_fetch_own()` (Sonderfälle, `cZahlungsart='AmazonPayments'`) |
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

## Migration ins TOCI-ERP (FastAPI + React 19)

Die hier aufgebaute Logik wandert 1:1 ins künftige ERP-System. Heute ist `jtl2datev` ein konsolen-gesteuertes Tool, später wird die gleiche Geschäftslogik über HTTP-APIs verfügbar sein. Dank strikter Framework-Unabhängigkeit (keine CLI-Importe im `core/`) passiert der Umzug ohne Code-Umschreiben.

### Schichten-Mapping

| Schicht                              | Heute                            | Im ERP-System                                |
|--------------------------------------|----------------------------------|-----------------------------------------------|
| Geschäftslogik (framework-agnostisch)| `src/jtl2datev/core/*.py`        | `backend/core/modules/jtl2datev/` (oder analog) |
| DB-Adapter (swappable)               | `core/repositories.py` (ABC) → `core/db_jtl.py` (MSSQL) | Neue Impl. `core/db_toci.py` gegen eigenes ERP-Schema, Interface bleibt |
| CLI-Wrapper                          | `src/jtl2datev/cli.py` (Click)   | Wegfällt — durch FastAPI-Routen ersetzt        |
| Konfiguration                        | `core/config.py` (Pydantic Settings) | bleibt, ggf. via FastAPI-Dependency-Injection |
| Filesystem-Archive                   | `core/archive.py` (lokales FS)   | bei Bedarf S3/Object-Storage-Adapter, isolierte Schicht |

### Warum der Umzug sauber läuft

**`core/` ist heute bereits framework-frei:**
- Kein `click`, kein `print()` — ausschließlich `logging`.
- DB-Engine wird per Konstruktor injiziert: `JtlInvoiceRepository(engine)`. In FastAPI direkt per `Depends()` bereitstellbar.
- Pipeline-Funktionen (`write_dutypay_csv`, `compute_delta`, `write_extf_csv`) arbeiten mit Iterator/Iterable, schreiben Output — reine Library-Calls, keine CLI-Funktionen.

**Beispiel: CLI heute vs. FastAPI morgen**

Heute (Click-basiert):
```
jtl2datev export-dutypay --month 2026-01 --out /tmp
```

Morgen (FastAPI-basiert):
```python
@router.post("/exports/dutypay")
async def export_dutypay(month: str, repo: InvoiceRepository = Depends(get_repo)):
    date_from, date_to = parse_month(month)
    invoices = repo.fetch_invoices(date_from=date_from, date_to=date_to)
    write_dutypay_csv(invoices, out_path=tmp_path, own_vat_ids=settings.own_vat_ids)
    archived = archive_export(tmp_path, ...)
    return {"path": str(archived), "rows": ...}
```

**Das Entscheidende:** Beide rufen **dieselbe** `write_dutypay_csv`-Funktion. Logik-Code wandert 1:1, nur der Wrapper wechselt.

### Migrations-Checkliste

1. **`core/db_jtl.py` → `core/db_toci.py`**: Heute SQLAlchemy + MSSQL gegen JTL-Schema. Später neue Repo-Implementation gegen TOCI-ERP-Schema. Die Schnittstelle (`InvoiceRepository`) bleibt; `fetch_invoices()` liefert dieselben `RawInvoice`-Objekte.

2. **Geschäftslogik unverändert**: `dutypay.py`, `datev.py`, `tax_engine.py`, `rules.py` — alle bleiben wie sie sind.

3. **`core/config.py`** (`Settings`, Pydantic v2) passt direkt in FastAPI als Dependency.

4. **`core/archive.py`** ggf. um Object-Storage-Adapter erweitern (S3, GCS) — oder lokal-FS-Version beibehalten.

5. **Tests**: Bestehende Unit-Tests in `tests/` bleiben gültig. Sie testen Library-Funktionen direkt, nicht die CLI.

### Kernaussage

Was hier in `jtl2datev` gebaut wird, ist effektiv schon das spätere `backend/core/modules/jtl2datev/` des ERP. Nur `cli.py` fällt weg, und `db_jtl.py` wird perspektivisch durch `db_toci.py` ergänzt oder ersetzt. Alle übrigen Module — Steuern, Regeln, DATEV-Export — wandern ohne Änderung mit.
