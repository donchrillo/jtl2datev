# Status / Archiv

Hier wandert Erledigtes aus `next-session.md` rein. Nur bei Bedarf lesen.

## 2026-05-05 — DATEV-Export-Sprint: Jera-Konventionen, Audit-Modus, 4-Monatsabgleich

**Vergleich Engine vs. Jera März 2026:**
- 4807 Belege Jera, 4807 Belege Engine — 0 Konto/BU-Differenzen (außer 4 ERROR/UNKNOWN-Marker).
- **April 2026 (Jera EOL):** 5068 Buchungen Engine, 0 Marker, 112 Audit-Tag-Cluster erfasst.

**Sprint-Highlights:**
- **Jera-Konvention für IGL/THIRD-COUNTRY:** alle IGL_B2B → 4126000 (DE-Lager: 4125000 obsolet), alle THIRD_COUNTRY → 4121000 (einheitlich).
- **Bundle-Self-Reference-Bug gefixt:** Master-Position self-referenziert via `kStuecklisteRechnungPos = kRechnungPosition`; `IS NULL`-Filter korrigiert.
- **Storno-Filter entfernt:** `nIstStorniert=1` bleibt drin (Audit-Trail-Vollständigkeit); Storno-Gutschrift als eigene `nBelegtyp=1`-Zeile.
- **Temu-Filter:** Belege mit `cExterneAuftragsnummer LIKE 'PO%'` ausgeschlossen (Test-Rollback 2025).
- **VCS-IDU-Belege drin:** Amazon Italien Erstattungen ohne Rechnung (JTL-Manuel-Einträge); Jera-Inkonsistenz dokumentiert.
- **CLI-Flags für Validierung:** `--compare-to <ref.csv>` (X-Marker bei Abweichung), `--audit` (Regel-Tags in Beleglink-Spalte).
- **Kundenname in Buchungstext:** PartyAddress + `display_name()` nach Jera-Konvention (Surname-First).
- **87 Tests grün**, ruff clean. 4 Monatsexporte Jan-Apr 2026 in `exports/`.

## 2026-05-05 — DATEV-EXTF-Export funktionsfähig

- `core/rules.py` mit Konten-Lookup-Algorithmus aus `docs/datev-format.md`
  (DOMESTIC, OSS_B2C 240/241, IGL_B2B → 4125/4126/4001, MF→4328000,
  EXPORT_LOCAL_VAT→4325000, Drittland 4120/4121).
- `core/datev.py` mit EXTF-CSV-Writer: 124 Spalten, cp1252-Encoding,
  CRLF, Komma-Dezimal, Belegdatum-Format `DDMM` (Tag ohne führende Null).
- Settings erweitert: Mandant 14974 / Berater 10305 / WJ 2026-01-01 /
  Account-Length 7 / `own_vat_ids` (DE/GB/FR/IT/PL/CZ/ES) / Default-Debitor 10000000.
- `RawInvoice.payment_method` neues Feld; in den 3 DB-Pfaden befüllt
  (eigen aus `cZahlungsart`, extern fix `AmazonPayments`, GS aus Original-Rechnung).
- Debitor-Mapping nach Zahlungsart: 10001-10012, Default 10000000.
- CLI `export --from --to --out` schreibt EXTF-Datei + Skip-Statistik.
- 73 Tests grün, ruff clean.
- **Smoke-Run März 2026:** 4823 Buchungen geschrieben (Jera: 4807, Δ +16).
  Konten-Verteilung in den Top-Konten alle nah am Jera-Sample.
  Größter Bug-Fix: EU→DE-OSS-Sonderfall (Konto 4001000 BU 285 statt
  4320000 BU 241), reduzierte Δ von +995 auf +28.

## 2026-05-05 — Engine-Fix: VAT-ID-Format-Plausibilitätscheck

- `looks_like_valid_vat_id()` Helper: erste 2 Zeichen müssen EU/GB/CH-Prefix sein, mind. 4 Zeichen, alphanumerisch danach. Volle VIES-Validierung kommt später.
- Bug-Symptom: Marketplace-Kunden hatten teils Junk-Werte in `cKundeUstId`/`cKaeuferUstId` (z.B. spanische CIF `B06800015`); Engine hat das fälschlich als B2B → Reverse-Charge → 0% behandelt.
- Fix: Format-Fail → fallback OSS_B2C mit Note. Echte EU-USt-IdNrn (Format-valid) werden weiterhin als IGL_B2B behandelt.
- 2 neue Unit-Tests, alle 22 grün.
- **Reconcile-Effekt Q1 2026:** Mismatch-Belege **8 → 1**, Mismatches gesamt **26 → 2**. Engine-Match jetzt **99.99%**.
- Verbleibender Mismatch ist kein Bug: ES-Lager → UK-Kunde → Amazon.co.uk; Engine sagt MARKETPLACE_FACILITATOR (0%), JTL speichert 20% UK-VAT (Roh-Info). Beide korrekt in ihrem Kontext — sollte später als `info`-severity geflaggt werden.

## 2026-05-05 — Reconcile-Pipeline + erster Engine-Test gegen Q1 2026

- Neuer `core/pipeline.py` mit `ReconcileReport` (Counters: Treatments, Mismatches by severity/source/warehouse) und streaming `run_reconcile()`.
- Neuer CLI-Command `jtl2datev reconcile --from --to [--out-mismatches CSV]`.
- `Settings.own_vat_countries: frozenset[str]` (Default DE/FR/IT/ES/PL/CZ/GB; via ENV `OWN_VAT_COUNTRIES=DE,FR,…` übersteuerbar).
- 9 Pipeline-Tests, 20 Unit-Tests grün, ruff/mypy clean.
- **Q1 2026 Ergebnis (13 619 Belege, 17 120 Positionen):**
  - Treatments: DOMESTIC 59,5% / OSS_B2C 35,0% / IGL_B2B 3,3% / THIRD_COUNTRY 2,2%
  - **Engine-Übereinstimmung mit JTL: 99,94%** — nur 8 Belege / 26 Mismatches
  - Mismatches Top-Lager: CZ 8, IT 6, DE 6, FR 4, ES 2
  - Quellen: 20× extern, 6× eigen
  - Auffälliges Muster: Engine sagt 0% VAT bei Belegen, wo JTL 21%/22% gespeichert hat — typische Marketplace-Facilitator-Fehlentscheidung der Engine (zB DE-Lager → IT-Kunde wird fälschlich als facilitator klassifiziert). Verfeinerung der Engine-Regeln in nächster Phase.
- CSV-Export aller Mismatches via `--out-mismatches`.

## 2026-05-05 — Gutschriften-Quelle (`dbo.tgutschrift`) integriert

- **`_fetch_credit_notes()`** dritte Quelle in `JtlInvoiceRepository`. Liest `dbo.tgutschrift` + `dbo.tGutschriftPos`, JOIN auf `Rechnung.tRechnung` (Lagerland + externe Auftragsnr) + `tRechnungAdresse` (nTyp=0/1) + `dbo.tPlattform`. Filter: `nStorno=0`, `kRechnung IS NOT NULL`, Datum-Floor 2024-11-01.
- `RawInvoice.source` Literal um `"jtl_credit_note"` erweitert. `is_credit_note=True` immer.
- Beträge bleiben **positiv** (Gutschrift-Brutto-Konvention; DATEV-Vorzeichen kommt später).
- `nBelegtyp=2` in externen Belegen wird als reguläre B2B-Restposten-Rechnung gelesen (Liquidationen, vom User abgeschaltet aber historische Belege bleiben).
- Smoke Q1 2026: 1.441 eigene + 11.933 extern + 245 Gutschriften = 13.619 Belege.
- 10 Unit-Tests grün, 3 Integration-Tests skipped (default).

## 2026-05-05 — `fetch_invoices` implementiert

- **JtlInvoiceRepository.fetch_invoices()** vollständig implementiert mit zwei privaten Helpern:
  - `_fetch_own()`: `Rechnung.tRechnung` + `Rechnung.tRechnungPosition` + `tRechnungPositionEckdaten`. Streaming-Cursor mit `itertools.groupby` über `kRechnung`. Joins zu `dbo.tPlattform`, `tRechnungAdresse` (nTyp=0/1), `tRechnungEckdaten`. Filter: `nStorno=0 AND nIstEntwurf=0 AND nIstProforma=0 AND nIstExterneRechnung=0`.
  - `_fetch_external()`: `tExternerBeleg` + `tExternerBelegTransaktion` + `tExternerBelegPosition` + `tExternerBelegEckdaten`. `nBelegtyp=1` → `is_credit_note=True`; `nBelegtyp=0/2` → reguläre Rechnung (Typ 2 = B2B-Aufkäufer, geklärt 2026-05-05). VAT berechnet als Brutto−Netto. NULL-`cVersandlandISO` → Skip + Logging.
  - Datum-Floor 2024-11-01 als Sicherheitsnetz hardcoded.
- **Felder gemappt**: RawInvoice (`warehouse_country`, `invoice_date`, `lines`, `gross_amount`, `net_amount`, `vat_amount`, `is_credit_note`); RawInvoiceLine (`gross`, `net`, `vat`, `vat_rate`).
- **Tests**: 2 Integration-Tests (Smoke + Datum-Floor) mit `@pytest.mark.integration`. 10 Unit-Tests grün.
- **Smoke-Run April 2026**: 708 eigene + 2835 extern = 3543 Belege.

## 2026-05-05 — DB-Erkundung Teil 2 + Schema-Korrekturen

- **Wichtige Korrektur:** `dbo.tRechnung` hat nur 15 Spalten (Stub, enthält
  aber `cErloeskonto`!). Die früher vermuteten ~60 Spalten leben in
  `Rechnung.tRechnung` (47 Spalten, anderes Schema, gleicher PK).
- Position-Basistabelle eigene Rechnungen: `Rechnung.tRechnungPosition`
  (25 Spalten) + `tRechnungPositionEckdaten` (1:1, enthält `fMwStBetrag`).
- Beträge eigener Rechnungen: `Rechnung.tRechnungEckdaten` (Brutto/Netto/
  Bezahl-/Mahnstatus).
- Adressen: `Rechnung.tRechnungAdresse` mit `nTyp` 0/1 (zwei Adressen je Beleg).
- Externer-Beleg-Schema komplett erfasst: `tExternerBeleg` (32 Spalten,
  `nBelegtyp` 0=Rechnung B2C/1=Gutschrift/2=Restposten-B2B), `tExternerBelegEckdaten`,
  `tExternerBelegTransaktion` (Liefer-/Versandadresse + Order-ID),
  `tExternerBelegPosition`.
- Plattform-Lookup: `dbo.tPlattform` (51=Amazon.de, 53=UK, 54=FR, 56=IT,
  57=ES, 60=NL, 31=ebay.de, 8=SCX/Kaufland).
- **`dbo.tSteuerschluessel` enthält nur 1 Eintrag** (Platzhalter „JTL2Datev",
  Schlüssel-Nr 14). DATEV-Mapping in JTL nicht gepflegt → bestätigt eigene
  Engine; nur Roh-VAT-Sätze (`fMwSt`, `fMwStSatz`) sind brauchbar.
- Volumen: 1.16 Mio aktive Rechnungen, 156k externe Belege. Versandländer:
  DE/PL/CZ/FR/IT/ES/GB.
- `.env` jetzt vorhanden, DB-Connection getestet (SQL Server 2017, tociuser).

## 2026-05-05 — Architektur-Skelett implementiert

- `core/config.py` (Pydantic-Settings, MSSQL+pyodbc-URL, DATEV-Mandant-Stubs)
- `core/models.py` (PartyAddress, RawInvoice, RawInvoiceLine, TaxTreatment StrEnum, TaxDecision, LineDecision, ReconcileMismatch — alle frozen)
- `core/repositories.py` (abstrakte InvoiceRepository-Interfaces)
- `core/db_jtl.py` (JtlInvoiceRepository mit fetch_invoices-Stub, make_engine-Factory)
- `core/tax_engine.py` (eigene Steuer-Entscheidungslogik: Inland / OSS B2C / IGL B2B / Drittland / Marketplace-Facilitator UK/CH; EU_COUNTRIES Konstante)
- `core/reconcile.py` (Vergleich JTL-gespeichert vs. Engine; ReconcileMismatch bei VAT-Abweichung)
- `core/rules.py`, `core/datev.py` (Stubs)
- `cli.py` (export --from --to --out Command; Error-Handling für NotImplementedError und DB-Fehler)
- 10 Tests grün (tax_engine, reconcile, cli), ruff clean, Deps via `uv pip install -e ".[dev]"` installt
- `.env` noch nicht angelegt (User-Aufgabe)

## 2026-05-05 — Strategiewechsel: eigene Steuer-Engine

- Entscheidung: Wir replizieren JTLs Steuerschlüssel-Logik NICHT. Stattdessen
  eigene Engine (`core/tax_engine.py`) auf Rohfakten + Plausi-Check
  (`core/reconcile.py`) gegen JTLs gespeicherte Werte.
- Begründung: Amazon liefert teils falsche Steuern (B2B-Fehlklassifikation
  trotz ungültiger USt-IdNr.); JTL übernimmt diese Werte. Existierende Tools
  (Taxdoo, Jera) erkennen genau diese Inkonsistenzen.
- Vorteil: Engine ist wiederverwendbar im TOCI-ERP, JTLs DATEV-Steuerschluessel-
  Mapping muss nicht reverse-engineered werden.
- Konsequenz: DB-Layer liest Rohfakten (`dbo.tRechnung` +
  `Rechnung.tExternerBeleg*`), JTLs Steuerentscheidung nur als Referenz.

## 2026-05-05 — JTL-DB-Erkundung (Teil 1)

- Verbindungsdaten dokumentiert (`192.168.178.2:50000/eazybusiness`, SQL-Login),
  `.env.example` angelegt, `.env` gitignored.
- Geschäftsmodell erfasst: Lager DE + Amazon-FBA in CZ/PL/IT/FR/ES/UK, eigene
  USt-IDs in jedem Lagerland; OSS aktiv für EU-grenzüberschreitend; lokale
  Steuerberater für Lager-→-eigenes-Lagerland; UK/CH Spezialfall (Marketplace-
  Facilitator); eigene Rechnungen nur eBay+Kaufland; Amazon/Otto extern; TEMU
  raus.
- JTL-2.0-Schema erkundet: ~60-Spalten-`tRechnung` mit allen Routing-Feldern
  (`nIstExterneRechnung`, `cVersandlandISO`, `cErloeskonto`, `cKundeUstId`,
  `kPlattform`, …); externe Belege haben eigenen Schlüsselraum
  (`vExternerBelegSteuerermittlungsdaten`); Steuerschlüssel-Routing in
  `Steuern.vSteuerschluessel` (Standard / IGL / UstIGL / ReverseCharge).
- Architektur-Datenfluss skizziert.

## 2026-05-05 — Projekt-Setup
- Verzeichnisstruktur, venv (Python 3.12, uv), `pyproject.toml` mit Deps-Stubs
- `CLAUDE.md` (schlank), `next-session.md`, Doku-Skelette in `docs/`
- Agenten-Definitionen: `coder` (Sonnet 4.6), `docs-writer` (Haiku 4.5)
- Entscheidung: Konsolen-First, Core-Library framework-agnostisch, später Port auf FastAPI + React 19 im ERP-Repo
