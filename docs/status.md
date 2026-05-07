# Status / Archiv

Hier wandert Erledigtes aus `next-session.md` rein. Nur bei Bedarf lesen.

## 2026-05-07 — TransactionID-Konvention finalisiert + Q1-2026-Reconciliation abgeschlossen

**TransactionID-Finalisierung:**
- **Primär:** TX = `invoice.jtl_external_order_no` (Marketplace-Order-ID). Fallback im DB-Layer auf JTL-Wawi-interne Auftragsnummer (`tRechnungEckdaten.cAuftragsnummern`).
- **Letzter Fallback:** Jera-PK-Konvention `{Prefix}{kPK}` (own: `R{kRechnung}`, Storno: `SR{kRechnung}`, external: `ER{kExternerBeleg}`, refund: `EG{kExternerBeleg}`, credit: `G{kGutschrift}`, storno-credit: `SRK{kGutschrift}`).
- **Q1-Stichprobe Januar:** 5329 Belege → 3373 Wawi-IDs, 1547 Amazon, 187 Otto, 116 sonstige (eBay/Kaufland), 106 Temu. **0 PK-Fallbacks** ausgelöst.
- Suchbar im JTL-Frontend; Join mit DATEV-Export möglich (gleiche Order-ID in Belegfeld 1).

**DocumentID unverändert:** `cRechnungsnr` / `cBelegnr` / `cGutschriftNr`. Hinweis: Rechnungsnummern ohne Buchstaben-Prefix können in Excel Wissenschaftsnotation triggern.

**SRK-Semantik verankert:**
- Storno einer Rechnungskorrektur (Gutschrift-Belegnr mit Prefix "SRK") wird ökonomisch als **Erlös behandelt** → `is_credit_note=False` → SALE mit positivem Vorzeichen, deckungsgleich mit Jera-Buchung.
- Begründung: Storno einer RK = Rückgängigmachung der Gutschrift. Beispielfall Kunde 11067353.
- RawInvoice erweitert um `jtl_primary_key: int | None`.

**Q1-2026-Reconciliation finale Ergebnisse:**
- Engine Σ Brutto 272.308,33 € / Netto 230.384,79 € (14.001 Belege).
- Jera-Ref (Hauptdateien JAN/FEB/MAR ohne _fehler.csv) Σ 272.308,45 € / 230.384,88 €.
- **Δ = −0,12 € Brutto / −0,09 € Netto** = reine Cent-Rundungsdrift auf ~50 Belegen.
- Buchungslogik bestätigt; bis Ende März **0 Engine-only-Belege mit Wert ≠ 0** (4 Engine-only Belege haben Σ 0,00 €, Probebuchungen).
- `DutyPay_Diff_01.csv` ist kein eigenständiger Block, sondern User-Korrekturschleife (darf nicht mit-summiert werden).

**Temu-Filter perspektivisch:** Aus DB-Query `_SQL_OWN` entfernt, sitzt jetzt ausschließlich in `core/datev.py` (DutyPay-Spec verlangt vollständige Auslandsverkaufs-Liste; OSS-irrelevant).

**Tests:** 182/3 grün (8 neue Tests in `TestTransactionID`), ruff clean.

---

## 2026-05-06 — Repository-Umstellung auf Header-Eckdaten

**Was:** SQL-Queries in `core/db_jtl.py` (`_SQL_OWN`, `_SQL_EXTERNAL`, `_SQL_CREDIT_NOTES`) lesen Brutto/Netto direkt aus den Eckdaten-Tabellen / -View; Position-Joins entfallen. Pro Beleg wird eine synthetische Single-Line mit Header-Werten + abgeleiteter VAT-Rate erzeugt.

**Bug gefixt:** Versandkosten externer Amazon-Belege (Typ 0 mit Positions-Details) wurden vorher fälschlich gefiltert, weil der `kExternerBelegPositionVater IS NULL`-Filter sie mit echten Bundle-Children rauswarf. Header-Total ist die garantierte Wahrheit (100% Coverage, 100% Match Σ Pos).

**Filter-Korrektionen:** `nIstExterneRechnung=0` aus `_SQL_OWN` wieder entfernt (war versehentlich neu hinzugefügt). Temu-Filter (`cExterneAuftragsnummer NOT LIKE 'PO%'`) explizit auch im `_SQL_OWN`.

**Format-Fix:** `_vat_rate_str` in `dutypay.py` gibt für ganze Zahlen jetzt `'20'` statt `'2E+1'`.

**Verifikation Q1 2026:**
- MAR-Engine vs. Jera Δ −0,03 € über 4807 Belege.
- JAN/FEB Δ −1908 €/−429 € (Engine-vs-Jera-Drift wie zuvor dokumentiert, nicht durch Umstellung neu eingeführt).

**Tests:** 177 passed, 3 skipped. ruff clean.

**Folge-Items:** Mixed-VAT-Pre-Flight-Check; RawInvoiceLine-Modell-Cleanup.

---

## 2026-05-06 — DutyPay-Export produktionsreif + Archiv/Delta-Workflow

**Core-Deliverables:**
- `core/dutypay.py` Exporter (98 Spalten DATEV-Spec), `core/dutypay_delta.py` für Diff-Logik, `core/archive.py` generischer Archiv-Helfer.
- `export-dutypay` + `export-dutypay-delta` CLI-Commands; automatische Archivierung unter `exports/dutypay/<YYYY-MM>/`.
- Delta-Diff vergleicht JTL-Stand gegen letzten Archiv-Stand; `--shift-to-period YYYY-MM` für Datums-Umschreibung (OSS-Nachzüglers).
- 163 Tests grün, ruff/mypy clean.

**Spec & Validierung:**
- `docs/dutypay-format.md`: 98-Spalten-Referenz, KindOfBusiness-Entscheidungstabelle, abgeleitete Felder (TAX_REPORTING_SCHEME, TAX_COLLECTION_RESPONSIBILITY, Incoterms, MarketZone), Vorzeichen-Regel, OSS-Pflichtfeld-Matrix.
- Refund-Vorzeichen (REFUND/B2B-REFUND/EXPORT-REFUND → negative Beträge) verifiziert.
- TransportCode konstant `5` (Jera-Default v1), TransactionID = JTL-Belegnummer.

**DB & Models:**
- `core/models.py` erweitert (Adress- + Artikelstamm-Felder optional).
- `core/db_jtl.py` SQL-Queries angepasst (Adress-Spalten gemäß JTL-Schema; Temu-Filter aus SQL entfernt — DutyPay enthält Temu-Belege wieder, jera-deckungsgleich, OSS-irrelevant).
- Settings: `export_archive_root: Path = Path("exports")` (via `.env` überschreibbar).

**Q1 2026 Validierung gegen Jera:**
- Engine-Output ist Obermenge: alle Jera-Belege enthalten, plus nach Jera-Export entstandene Belege, plus Temu-Belege jera-deckungsgleich.

> **Korrektur 2026-05-06 (geltende Regeln, überschreiben ältere Einträge unten):**
> - **Storno-Filter überall entfernt.** `nStorno`/`nIstStorniert`/„Storno"-Flags
>   in *jeder* Tabelle (eigene Rechnungen, externe Belege, Gutschriften) werden
>   **nicht** als Skip-Kriterium verwendet. Begründung: Eine stornierte Rechnung
>   hat zwingend ein Gutschriftsdokument (oder muss eines haben); ohne den
>   Storno-Beleg fehlte die Gegenbuchung.
> - **Otto liegt nicht in `tExternerBeleg`.** `Rechnung.tExternerBeleg` enthält
>   ausschließlich Amazon-VCS-Belege. Otto/eBay/Kaufland/JTL-manuell laufen
>   alle über `Rechnung.tRechnung` (`_fetch_own`). Ältere Status-Einträge, die
>   „Amazon/Otto" zusammen unter „externe Belege" zählen, sind insoweit falsch.

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
