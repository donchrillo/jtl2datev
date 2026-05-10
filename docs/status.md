# Status / Archiv

Hier wandert Erledigtes aus `next-session.md` rein. Nur bei Bedarf lesen.

## 2026-05-10 — W-20 (Stammdaten-Hygiene) umgesetzt

**`core/reference_data.py`:** drei weitere Konstanten zentralisiert:
- `DOMESTIC_ACCOUNT_BY_WAREHOUSE` (vorher funktions-lokal in `rules.py:map_to_datev_account` → wurde bei jedem Aufruf neu allokiert)
- `DEBITOR_BY_PAYMENT` (vorher `_DEBITOR_BY_PAYMENT` in `rules.py`)
- `STANDARD_VAT_RATE` (vorher in `tax_engine.py`)

**`vat_rate_for(country, on_date=None)`:** neuer Helper als zukunftsfähige Signatur — *on_date* wird aktuell ignoriert. Sobald historische Re-Exports älterer Monate anstehen, kann `STANDARD_VAT_RATE` auf `{country: [(from_date, rate), …]}` erweitert werden, ohne Aufrufstellen anzupassen.

**Module-lokale Re-Bindings:** `rules.py` importiert beide Mappings unter den bestehenden privaten Namen (`_DOMESTIC_MAP`, `_DEBITOR_BY_PAYMENT`); `tax_engine.py` re-exportiert `STANDARD_VAT_RATE`. Kein API-Bruch — alle Aufrufer (`datev.py`, `db_jtl.py`, `dutypay.py`) funktionieren unverändert.

**Bewusst nicht umgesetzt:**
- Period-Validity-Logik in `vat_rate_for` — Tool produktiv erst 2026, Re-Exports älterer Monate nicht akut.
- Settings-Overrides für Konten-Mappings — wird erst bei Multi-Mandanten-ERP relevant.

**Tests:** 430 passed, 14 skipped.

---

## 2026-05-10 — B-9 (Repository-Interface erweitert) umgesetzt

**Ziel:** ERP-Migration soll später nur Repository-Implementierungen tauschen, nicht CLI/Service-Layer.

**`core/repositories.py`:**
- `InvoiceRepository.find_mixed_vat_belege(date_from, date_to)` als zweite abstrakte Methode hinzugefügt — Mixed-VAT-Detection war bisher direkt am `Engine` (`preflight.find_mixed_vat_belege(engine, …)`) und damit am Repository vorbei.
- Neue ABC `ArticlePricingRepository.lookup_ek_prices(skus, *, asin_by_sku, bware_strategy)` — Verbringungs-Preis-Lookup war ebenfalls direkt am `Engine` (`verbringung_pricing.lookup_prices(skus, engine, …)`).

**`core/db_jtl.py`:**
- `JtlInvoiceRepository.find_mixed_vat_belege` delegiert an `preflight.find_mixed_vat_belege`.
- Neue `JtlArticlePricingRepository` wrappt `verbringung_pricing.lookup_prices`, parametrisiert die JTL-Tabellennamen (mapping/artikel/beschreibung/angebot) konstruktor-seitig.

**`cli.py`:** `mixed-vat-check` und `export-verbringung` instanziieren jetzt das jeweilige Repository statt die freien Modul-Funktionen direkt aufzurufen. Modul-Funktionen bleiben als Implementierungs-Detail erhalten (Test-Mocks und `preflight`-Tests nutzen sie weiter).

**Tests:** 430 passed (test_cli-Patch-Targets von `verbringung_pricing.lookup_prices` auf `db_jtl.lookup_prices` umgestellt — folgt der neuen Aufruf-Kette), 14 skipped.

---

## 2026-05-10 — W-5 (DutyPay-Vorzeichen-Check) umgesetzt

**`core/dutypay.py:determine_kind_of_business()`:** Klassifikation als REFUND erfolgt jetzt via `is_credit_note OR total_gross < 0`. Schützt vor manuellen Korrekturbelegen in `tRechnung`, die negatives Brutto haben, aber kein Gutschrift-Flag — vorher wären solche Belege als SALE klassifiziert worden, was zu inkonsistenter MarketZoneGross-Vorzeichenführung geführt hätte.

**Mismatch-WARN:** Wenn `is_credit_note != (total_gross < 0)` und Brutto ≠ 0, loggt der Pfad eine WARNING mit `invoice_no`, Flag- und Brutto-Wert (für Audit-Trail in `dutypay.log`).

**Tests:** 430 passed (+3 neue: negativ-ohne-Flag, positiv-mit-Flag, Null-Brutto-keine-Warnung), 14 skipped. ruff clean.

---

## 2026-05-10 — Sprint D (Compliance-Polish) umgesetzt

**Robustheit, Input-Validation, Ressourcen-Cleanup:**

**W-14** `cli.py`: `_parse_month()` strikter Regex `^\d{4}-\d{2}$` — "2026-4" wird abgelehnt.

**W-11** `core/exchange_rates.py`: BMF-CSV-Encoding-Detection (utf-8-sig → utf-8 → iso-8859-1) + Sanity-Check ≥4 Monatsspalten. `fetch_bmf_csv()` + `parse_bmf_csv()` robust gegen Varianten.

**W-12** `core/verbringung_parser.py`: Amazon-TSV-Encoding-Detection (utf-8-sig → utf-8 → utf-16 → utf-16-le → cp1252). `_detect_encoding()` Helper mit Fallback-Kette.

**W-10** `core/db_jtl.py` + `cli.py`: Context-Manager `managed_engine(settings)` — alle 8 CLI-Commands (`export`, `export-delta`, `export-dutypay`, `export-dutypay-delta`, `export-taxually`, `export-taxually-delta`, `export-verbringung`, `mixed-vat-check`, `reconcile`, `import-rates`) via `with managed_engine(...) as engine:` Block. Garantierte `engine.dispose()` Cleanup auch bei Exception.

**W-15** `core/verbringung_pricing.py`: `lookup_prices()` öffnet DB-Connection **einmalig**, reicht `conn` an alle Tier-Funktionen durch. Vorher: bis zu 9 separate `engine.connect()`-Aufrufe pro Lookup. Effekt: Ressourcenverbrauch bei Batch-Läufen deutlich reduziert.

**Tests:** 427 passed, 14 skipped (+15 neue Tests). ruff clean.

**Nicht umgesetzt (bewusst):**
- W-2 (period-validity STANDARD_VAT_RATE) — Tool produktiv erst 2026.
- W-3 (VIES-Cache) — >4h Aufwand, separat.
- W-6/W-7 (Verbringungs-PDF §10/§16-Hinweise) — Steuerberater-Freigabe nötig.

---

## 2026-05-10 — Sprint C Phase 3 (`BuchungsRow`-Dataclass) umgesetzt

**DATEV-Export-Modell refaktoriert — Feldabstraktion:**

**W-21** `core/datev.py`: Neue `BuchungsRow`-Dataclass mit 22 benannten Feldern (umsatz, soll_haben, wkz_umsatz, kurs, basis_umsatz, basis_wkz, abrechnungsgruppe, belegfeld1/2/3/4/5, beleginfo1/2/3/4/5, eu_verkaufsland, eu_umsatzsteuer_id, eu_geschaeftsreihe, veranlagungsjahr, festschreibung, audit_tag). Methode `to_csv_row()` kapselt Mapping auf 124-Spalten-Liste via `_IDX_*`-Konstanten (Single Source of Truth für Spaltenpositionen).

**`_build_row`-Refaktor:** gibt jetzt `BuchungsRow` statt `list[str]` zurück; alle drei Aufrufer in `write_extf_buchungsstapel` (regulärer Pfad, ERROR-Placeholder, UNKNOWN-Placeholder) nutzen `br.to_csv_row()`. Audit-Tag bekommt eigenes Feld, statt direkt in Beleglink-Spalte geschrieben zu werden.

**Indices-Verwaltung:** `_IDX_*`-Konstanten leben jetzt nur noch innerhalb von `to_csv_row()` — keine versehentliche Verwechslung mit CSV-Header-Position mehr möglich.

**Tests:** 412 passed, 14 skipped — keine Test-Anpassungen nötig (Tests inspizieren CSV-Output, nicht Indices).

---

## 2026-05-10 — Sprint C Phase 1 (Architektur-Hygiene Quick Wins) umgesetzt

**Stammdaten zentralisiert, RawInvoiceLine-Modell entschlackt:**

**W-17** `core/reference_data.py` angelegt — Single Source for Constants:
- `EU_MEMBER_STATES` (27 Länder, konsolidiert aus `EU_COUNTRIES` + `_EU_NON_DE`/`_EU_ALL`)
- `COUNTRY_CURRENCY` (konsolidiert aus `dutypay._COUNTRY_CURRENCY` + `verbringung_pdf.COUNTRY_CURRENCIES`)
- `PLATFORM_COUNTRY` (ehemals `_PLATFORM_COUNTRY` in `db_jtl.py`)
- `HARD_MIN_INVOICE_DATE` (ehemals `_MIN_DATE` in `db_jtl.py` + `preflight.py`)
Alle bestehenden Module konsumieren jetzt von dort; modul-lokale Re-Bindings erhalten (kein API-Bruch).

**W-18** `RawInvoiceLine` Cleanup: 12 nie gelesene Felder entfernt (sku, description, quantity, product_group_id, position_type, weight, manufacturer, manufacturer_country, commodity_code, long_description, unit, transport_code). Behalten: line_no, net, gross, vat_amount, vat_rate, jtl_tax_key_id. `_synthetic_line` in `db_jtl.py` gekürzt, 7 Test-Fixture-Dateien angepasst.

**W-20-light** `HARD_MIN_INVOICE_DATE` zentralisiert. `_DOMESTIC_MAP` / `_DEBITOR_BY_PAYMENT` / period-validity STANDARD_VAT_RATE bewusst nicht in Phase 1 (gehört später in Settings W-20-vollständig).

**Tests:** 412 passed, 14 skipped. Keine Verhaltensänderungen, reine Struktur-Hygiene.

---

## 2026-05-10 — Sprint B (Tax-Korrektheit) umgesetzt

**Sechs kritische Tax-Punkte aus CONSOLIDATED.md Zeilen 94-106 implementiert:**

**B-5** `core/tax_engine.py`: RO-Steuersatz 21% mit Stichtag 01.01.2026 + Quelle (OUG 156/2024) dokumentiert. Verification-Status: User hat klargestellt, dass ab 01.01.2026 21% gilt (kein Rollback).

**B-6** `core/tax_engine.py`: CH zu `MARKETPLACE_FACILITATOR_DESTINATIONS` ergänzt. Schweiz unterliegt seit 01.01.2025 Marketplace-Facilitator-Regeln (MWSTG Art. 20a). `gross==net`-Trigger gilt automatisch auch für CH (wie für UK).

**W-1** `core/taxually.py`: XI (Nordirland) zu erlaubten IC-Supply-Destinations hinzugefügt. `looks_like_valid_vat_id()` + `normalise_vat_id()` werden vor Übernahme von Customer-VAT-ID aufgerufen; ungültige Format-Treffer werden geloggt und ausgelassen.

**W-4** `core/tax_engine.py`: DE→DE B2B mit `vat_id` + 0% wird nicht mehr blind auf Reverse-Charge gemirror't. Nur §13b-Bauleistungen/Schrott/Reinigung sind echte RC-Fälle. Für alle anderen de-de-b2b-0%-Fälle: `expected_vat_rate=19` mit note, Reconcile wirft WARN.

**W-8** `core/reconcile.py`: Cent-Toleranz für Rounding `abs(vat_amount) <= 0,01` reduziert Mismatches mit severity `warn` (statt `error`) bei IGL_B2B/THIRD_COUNTRY/MARKETPLACE_FACILITATOR.

**W-13** `core/db_jtl.py`: `currency_factor=0` oder `None` bei Nicht-EUR-Währung loggt explizite WARNING an **allen drei Fetch-Stellen** (`_fetch_own`, `_fetch_external`, `_fetch_credit_notes`). Kein silent fallback auf 1.0 mehr ohne Log-Spur.

**Bewusst nicht umgesetzt (User-Entscheidung):**
- **B-7** (£135-Schwelle für UK-Versand): Amzon UK-MF-Volumen 99,5% aus UK-Lager. Schwelle praktisch irrelevant.
- **B-8** (SRK-Cross-Check Master-RK): Aufgeschoben bis Mai/Juni bei Bedarf.
- **F-7** (Period-Validity STANDARD_VAT_RATE): Tool produktiv erst ab 2026, nicht notwendig für Q1-Q2.

**Tests:** 412 passed, 14 skipped. Keine Verhaltensänderungen, nur steuerliche Korrektheit verschärft.

---

## 2026-05-10 — Sprint A (IO-Sicherheit) umgesetzt

**Fünf kritische Punkte aus Robustness-Review (CONSOLIDATED.md Zeilen 82-92) implementiert:**

**B-2** `core/archive.py`: Microsecond-Timestamps (`%Y-%m-%d_%H-%M-%S-%f`) + Collision-Suffix `_2`/`_3` in `archive_export()` und `archive_delta()` verhindern Race-Conditions bei Parallel-Runs.

**B-3** `core/dutypay.py:_safe()`: strippt zusätzlich `\n`, `\r`, `\t` (vorher nur `;`) → DutyPay-XLSX-Integrität gegen Zeilenumbruch-Injection.

**B-1** `core/datev.py:write_extf_buchungsstapel()`: atomic write via `<path>.tmp` + `os.replace()`, tmp-Datei bei Exception aufgeräumt. Analog in `core/taxually.py` (openpyxl-`wb.save()`) und `core/verbringung_taxually.py` umgestellt → kein korrupter Export bei Strg+C.

**W-9** `core/db_jtl.py:make_engine()`: `pool_pre_ping=True` (stale-connection-detection), `pool_recycle=1800` (30-min-Recycling), `connect_args={"timeout": 10}` (ODBC-Connect-Timeout) → verhindert 15s-Hangs, erkennt DB-Ausfälle schneller.

**B-4** `core/config.py:sqlalchemy_url()`: gibt jetzt `sqlalchemy.engine.URL`-Objekt via `URL.create()` zurück (statt String-Konkatenation) → Passwort nie mehr lesbar in Stack-Traces, automatische Maskierung in Error-Messages.

**Tests:** 407 passed, 14 skipped. Keine Verhaltensänderungen, nur Robustness-Härtung für Q2-Meldung.

---

## 2026-05-08 — Tier 5+6: B-Ware-Behandlung + ASIN-Lookup

**Q1-2026 Verbringungs-SKU-Coverage komplett aufgelöst (148 → 0 unresolved):**

**Tier 5 (B-Ware-Erkennung):**
- Pattern `amzn.gr.<STEM>-<HASH>-<SUFFIX>` erkannt via Regex; Stem iterativ extrahiert
- Bewertungsregel User-bestätigt 2026-05-08:
  - Stem-Match in Mapping/tArtikel → 10 % vom Netto-EK (Floor 0,01 €)
  - Kein Match → pauschal 0,10 €
  - ASIN-Match (Tier 6) → voller aktueller EK
- Config-Optionen: `bware_pricing_strategy: {ten_percent|flat_10ct}` (Default `ten_percent`), CLI-Flag `--bware-pricing-strategy`
- PDF-Marker: Description bekommt `(B-Ware)` bei Match
- Neuer Output `bware_summary_<ts>.csv`: seller_sku, stem, qty, movements, ek_basis, ek_used, source
- `PricingResult` erweitert: `is_bware: bool`, `bware_pricing_basis: Decimal | None`
- B-Ware-SKUs ausgeschlossen aus `missing_ek_*.csv`

**Tier 6 (ASIN-Lookup):**
- Schema-Findings (live-verifiziert):
  - `pf_amazon_angebot_fba` → **keine** ASIN-Spalte, entfällt
  - `tArtikel.cASIN` direkt vorhanden → Tier 6a (preferred)
  - `pf_amazon_angebot.cASIN1/2/3` vorhanden → Tier 6b
- Tier 6a: `tArtikel.cASIN = movement.asin` → voller EK
- Tier 6b: `pf_amazon_angebot.cASIN1 = movement.asin` → aktuelle SKU → Mapping → voller EK
- Position: bei B-Ware nach 5a/5b vor Fallback; sonst nach 1–4
- API: `lookup_prices(…, asin_by_sku: dict[str, str] | None = None)` — backward-compat

**Q1-Stats (523 einzigartige SKUs):**
- Tier 1 (direct): 235 (44,9%)
- Tier 4 (amzn-stem): 61 (11,7%)
- Tier 5 (bware-stem/fallback): 156 (29,8%)
- Tier 6 (asin-t/a): 70 (13,4%)
- Unresolved: 0 (0%)

**Tests:** 418 passed, 3 skipped (+28 Tests für B-Ware + ASIN).

---

## 2026-05-08 — BMF-Wechselkurs-Import + JSON-Storage

**Wechselkurs-Verwaltung komplett überarbeitet:**

- `core/exchange_rates.py` — JSON-Storage (`data/exchange_rates.json`) + BMF-CSV-Importer
  - API: `load_rates`, `get_rate`, `set_rate`, `get_rates_for_period`, `fetch_bmf_csv`, `parse_bmf_csv`, `import_bmf_rates`
  - Schema: `{"YYYY-MM": {"CCY": {"value": "...", "source": "BMF"|"manual"}}}`
- Neuer CLI-Command `jtl2datev import-rates [--year YYYY] [--csv PATH]` — lädt offizielle BMF-Datensätze
- BMF-CSV-URL stabil: `https://www.bundesfinanzministerium.de/Datenportal/Daten/offene-daten/steuern-zoelle/umsatzsteuer-umrechnungskurse/datensaetze/uu-kurse-{YEAR}-csv.csv?__blob=publicationFile` (ISO-8859-1, Semikolon, monatlich fortgeschrieben)
- Verhalten: `source=BMF`-Werte werden überschrieben, `source=manual`-Werte bleiben (User-Input hat Vorrang)
- `export-verbringung` erweitert: `--exchange-rates` TOML-Option entfernt, neuer Flag `--strict` für CI (bricht ab bei fehlendem Kurs). Default interaktiv: CLI fragt nach fehlenden Kursen, speichert als `source="manual"`.
- Initial-Import: 116 Kurse für Q1+Apr 2026 aus BMF (PLN/CZK/GBP/SEK/DKK/RON/HUF/USD etc.)
- `EXCHANGE_RATES`-Konstante aus `core/config.py` entfernt
- BMF-PDF von Repo-Root nach `samples/wechselkurse/` verschoben

**Tests:** 390 passed, 3 skipped (vorher 356 → +34: 28 für `test_exchange_rates.py`, 5 neue + Mock-Updates in `test_cli.py`).

**Live-Verifikation:** `jtl2datev export-verbringung --report samples/verbringungen/3871700020495.txt --month 2026-01 --strict` generiert 30 PDFs + XLSX, alle Fremdwährungs-Spalten korrekt aus JSON.

---

## 2026-05-07 (Spätstunde) — Amazon-Verbringungs-Tool (Export)

**Innergemeinschaftliche Lagerbewegungen aus Amazon-FBA-Reports exportiert:**

- `core/verbringung_parser.py` — Tab-separated TXT-Parser (95 Spalten), Filter FC_TRANSFER + INBOUND. ~1.2–3k Zeilen/Monat.
- `core/verbringung_pricing.py` — 4-Tier-SKU-Mapping: direct → fba-suffix-strip → tArtikel-direct → amzn.gr.-stem. EK-Netto-Lookup mit Fallback `fLetzterEK`.
- `core/verbringung_taxually.py` — XLSX-Export (20 Spalten, Sheet „Your data"), identisch zu Taxually-Format.
- `core/verbringung_pdf.py` — Pro-Forma-PDF (reportlab): Header (ToCi + Datum), Fachtext (§4 Nr.1b UStG), beide VAT-IDs, Tabelle (cArtNr, Name, Qty, EK, Summe), Summen pro Währung.
- `cli.py` erweitert: `export-verbringung --report … --month YYYY-MM [--out-xlsx/pdf/ek]`. Auto-Archive unter `exports/verbringung/<YYYY-MM>/`.

**Spezifikation:** `docs/verbringung.md` (CLI, XLSX-Mapping, PDF-Layout, SKU-Mapping-Tier, VAT-IDs, Wechselkurse, kein Delta-Command).

**Q1-2026-Verifikation (Samples):**

| Monat | FC_TRF | INBOUND | XLSX-Zeilen | PDFs | Unique SKUs |
|-------|--------|---------|-------------|------|------------|
| JAN | 1.231 | 10 | 1.241 | 30 | 347 |
| FEB | 801 | 3 | 804 | 25 | 289 |
| MAR | 972 | 2 | 974 | 27 | 302 |

→ Zeilenzahlen + PDF-Counts matchen 1:1 mit Transactional Reports. EK-Preis Coverage 100% (gemappte SKUs), 148 ungemappte katalogisiert.

**SKU-Mapping-Statistik (673 Unique):**
- Tier 1 (direct): 348 (51,7%)
- Tier 2 (fba-suffix): 1
- Tier 3 (tArtikel-direct): 1
- Tier 4 (amzn-stem): 175 (26,0%)
- Ungemappt: 148 (22%, davon ~130 amzn.gr.* ohne Mapping-Eintrag)

**Tests:** 356 passed, 3 skipped (inkl. +44 neue Verbringungen-Tests).

**Nachgereicht 2026-05-08:**
- VAT-IDs FR (FR54820509628) + GB (GB242492315) in `OWN_VAT_IDS_VERBRINGUNG` ergänzt.
- SK: keine Registrierung notwendig — slowakisches Lager ist reines Retourenlager (Endkunden-Retouren gehen ein, werden auf andere FBA-Lager verteilt; keine Versendungen an Kunden ab SK). Im Code als Kommentar dokumentiert.
- Klarstellung Rücksendungen Amazon → Hünxe: erscheinen grundsätzlich **nicht** im Amazon-Transactional-Report (weder Auto-Removals noch manuelle Rückforderungen). Der `is_return_to_user`-Marker bleibt als Vorsichtsmaßnahme.

**Offene Punkte:**
- 148 ungemappte SKUs in `pf_amazon_angebot_mapping` / `tArtikel.cArtNr` nachpflegen; SKU-Mapping-Strategie ggf. verfeinern.

---

## 2026-05-07 — Taxually-Export implementiert + Q1-Reconciliation

**Neuer Exporter `core/taxually.py` + `core/taxually_delta.py`:**
- XLSX-Format (openpyxl), Sheet `Your data`, 20 Spalten gemäß Taxually-Template
- 1 Zeile pro Belegdokument (Brutto/Netto aggregiert), nicht per Position
- Transaction type: `SALE` oder `REFUND` (uppercase); REFUND negativ
- VAT Reporting Country — dreistufige Regel:
  1. VAT > 0 → Customer's country (meldepflichtig in Kundenland, OSS-typisch)
  2. VAT = 0 + Kunde = GB → `GB` (UK-Lokalregistrierung)
  3. VAT = 0 sonst → Departure country (Verkäufer-Land, IC-Meldung/Export)
- Spalten 13–20 leer (Taxually rechnet selbst)

**CLI-Commands analog DutyPay:**
- `jtl2datev export-taxually --month YYYY-MM` → Auto-Archiv unter `exports/taxually/<YYYY-MM>/<timestamp>.xlsx`
- `jtl2datev export-taxually-delta --month YYYY-MM` → Delta gegen letzten Baseline
- `--shift-to-period YYYY-MM` → Datums-Umschreibung für Nachzügler-Meldungen

**Engine-Bug-Fix (Refund-Vorzeichen):**
- SR-Belege (Storno-Rechnungskorrektionen, Prefix `SRK`) als **SALE mit positivem Vorzeichen** geschrieben (ökonomisch Rückgängigmachung der Gutschrift)
- Alle anderen Gutschriften (normales Refund) als **REFUND mit negativem Vorzeichen**
- Logik: JTL speichert SRK mit `nBelegtyp=0` (Rechnung) → `is_credit_note=False` → korrekt als SALE

**Format-Spezifikation:** `docs/taxually-format.md` (20-Spalten-Mapping, VAT-Reporting-Land-Entscheidungsbaum, CLI-Workflow, Q1-Reconcile-Ergebnis)

**Q1-2026 Reconciliation gegen Jera-PowerQuery:**

| Monat | Engine Zeilen | Engine Distinct | Jera Zeilen | Jera Distinct | Δ Schnitt |
|-------|---------------|-----------------|-------------|---------------|-----------|
| JAN   | 5329          | 5329            | 5708        | 5329          | -0,13 €   |
| FEB   | 3865          | 3865            | 4146        | 3594          | +0,04 €   |
| MAR   | 4807          | 4807            | 5146        | 4490          | -0,03 €   |

- **JAN**: Engine = Jera (Distinct 5329/5329 match). Jera-Zeilen-Diff durch Position-Breakdown (Jera schreibt je Position + Versand).
- **FEB/MAR**: Engine Obermenge — zusätzliche 272 (FEB) / 318 (MAR) Belege `202630260xxx`/`202650012xxx` in Engine (nach User-Jera-Export eingespielt). Nur-Ref je 1 Beleg = Excel-Sci-Notation-Fehler (`2,03E+11`).
- **Q1 Gesamt**: Δ ≈ −0,12 € über 14k+ Belege (Cent-Rounding).

**Tests:** 16 Taxually-Tests grün, Gesamtsuite 293 passed / 3 skipped.

**Standardworkflow (erweitert um Taxually):**
```
jtl2datev mixed-vat-check --month YYYY-MM
jtl2datev reconcile --month YYYY-MM
jtl2datev export --month YYYY-MM
jtl2datev export-dutypay --month YYYY-MM
jtl2datev export-dutypay-delta --month YYYY-MM
jtl2datev export-taxually --month YYYY-MM          # Neu
jtl2datev export-taxually-delta --month YYYY-MM    # Neu (falls Nachzügler)
```

---

## 2026-05-07 (Spätstunde) — Fremdwährung, DutyPay-Export, DATEV-Archiv, Standardworkflow

**Fremdwährungs-Handling DATEV + DutyPay** (Commit `e0b54eb`):
- DATEV-Spalten `WKZ Umsatz`, `Kurs`, `Basis-Umsatz`, `WKZ Basis-Umsatz` bei Fremdwährung-Belegen korrekt befüllt. Kurs aus `invoice.currency_factor` (JTL `fWaehrungsfaktor`).
- DutyPay: SourceZone/Target/MarketZoneCurrencyCode konsistent aus Zonen-Ländern abgeleitet (EUR-Zone + CZK/DKK/HUF/PLN/RON/SEK/BGN/GBP/CHF/NOK/USD).
- MarketZone aus `marketplace_country` abgeleitet (10 Amazon-Sites, Fallback Lager-Land; Beispiel: Amazon.co.uk → GB).
- `RawInvoice.marketplace_country: str | None = None` neu.
- Verifikation Q1 2026: Engine ↔ Jera matchen 1:1 für alle Fremdwährungs-Belege (GBP/PLN/SEK).

**Pre-Flight-Command `mixed-vat-check`** (Commit `7982c6c`):
- `jtl2datev mixed-vat-check --from … --to …` (oder `--month`) listet Belege mit gemischten Steuersätzen auf Hauptpositionen.
- SQL-Queries gegen `tRechnungPosition`, `tExternerBelegPosition`, `tGutschriftPos`, Vater-Position-Filter pro Tabelle.
- Q1 2026 Live-Run: 0 Treffer in allen drei Beleg-Typen.

**CLI-Vereinheitlichung** (Commits `dd03366` + `b3d99eb`):
- DATEV-Export akzeptiert jetzt `--month YYYY-MM` (analog DutyPay).
- Alle 5 Commands (`export`, `export-dutypay`, `export-dutypay-delta`, `mixed-vat-check`, `reconcile`) akzeptieren **entweder** `--from`/`--to` **oder** `--month`.
- Validierung via zentralen Helper `_resolve_date_range()`.
- DutyPay-Archive: nur bei `--month`-Modus; bei `--from`/`--to` ist `--out` Pflicht.

**DATEV-Auto-Archive + `export-delta`** (Commit `e1dfa14`):
- `jtl2datev export --month` archiviert automatisch unter `exports/datev/<YYYY-MM>/<timestamp>.csv` (analog DutyPay).
- Neuer Command `jtl2datev export-delta --month` berechnet Delta gegen letzten archivierten Vollexport.
- Match-Strategie: Belegnr aus Buchungstext (erster Token) — eindeutig pro Buchung.
- EXTF-Format: cp1252-Encoding, Header-/Spaltenzeilen bleiben in Delta-CSV.

**`--shift-to-period` shiftet PostingDateInvoice** (Commit `f429fa2`).

**Audit-Liste** (Commit `5094cfd`):
- `docs/audit-q1-2026-error-belege.md` — 4 ERROR/UNKNOWN-Belege im DATEV-März-Export zur manuellen Prüfung.

**Q1 + Apr 2026 Re-Exporte mit Auto-Archive:**
- Alle vier Monate (Jan/Feb/Mar/Apr 2026) durchgelaufen und archiviert.
- Pro Monat: `exports/datev/<YYYY-MM>.csv` (aktueller Stand), `exports/datev/<YYYY-MM>/<timestamp>.csv` (Baseline für `export-delta`), `exports/dutypay/<YYYY-MM>/<timestamp>.csv` (Baseline für DutyPay-Delta).

**Tests:** 277 passed, 3 skipped. ruff clean.

**Standardworkflow:**
```
jtl2datev mixed-vat-check --month YYYY-MM
jtl2datev reconcile --month YYYY-MM
jtl2datev export --month YYYY-MM
jtl2datev export-dutypay --month YYYY-MM
jtl2datev export-delta --month YYYY-MM          # falls nachgelagerte Belege
jtl2datev export-dutypay-delta --month YYYY-MM
```

---

## 2026-05-07 — Marketplace-Suffix-Strip + Q1-DATEV-Reconciliation abgeschlossen

**Marketplace-Suffix-Strip (`_N`):**
- JTL-Konvention bei Mehrteil-Marketplace-Sendungen: `cExterneAuftragsnummer` mit Suffix `_1`, `_2`, … (z.B. `406-0538474-1507531_1` für Amazon 406-0538474-1507531 über 2+ Lager).
- Helper `_strip_marketplace_suffix()` in `db_jtl.py` entfernt Regex `_\d+$`, angewendet auf alle `_fetch_*`-Methoden.
- **Effekt:** DutyPay-TransactionID und DATEV-Belegfeld 1 zeigen Original-Order-ID ohne Suffix. Eindeutigkeit pro Beleg bleibt in DocumentID (`cRechnungsnr` / `cBelegnr` / `cGutschriftNr`).
- **Match:** direkter Join mit Marketplace-Order-IDs (Amazon Seller Central, Otto, etc.) und alte Jera-Refs funktionieren.
- **Tests:** 7 neue parametrisierte Unit-Tests in `test_db_jtl.py`, 189 passed, 3 skipped.

**Q1-2026 DATEV-Reconciliation (Cross-Check Engine vs. Jera-Refs):**
- **Dateien:** `samples/datev/01_Belege_ohne_Temu.csv`, `01_neue_Belege.csv`, `02_Belege_ohne_TEMU.csv`, `03_Belege_ohne_Temu.csv` (13.892 Belege).
- **Soll Engine = Ref exakt:** Σ 298.824,55 € (Brutto).
- **Saldo-Diff:** +25,70 € auf 13.892 Belegen (≈ 0,1 ‰).
  - Erklärbar: 3 Cent-Rundungen Σ +0,04 €.
  - 165/166 Engine-only / Ref-only Belege: alte Jera-Schnittstelle schrieb internale JTL-Kennungen (`kRechnung`) in Belegfeld 1, Engine schreibt konsistent Marketplace-Order-ID. Keine Engine-Änderung möglich (Ref-Datenqualität-Issue).
  - Amazon-Order 406-0538474-1507531: User-erstellte Korrektur-Rechnung mit `_1`-Suffix; Engine bucht beide Teile korrekt, nach Suffix-Strip auch im Reconciler matchend.
- **Konsequenz:** Engine ist Single Source of Truth. Bei zukünftigen Audits bevorzugt mit Engine-Output arbeiten.

**Q1-2026 DutyPay-Reconciliation re-run nach TX-ID-Umstellung:**
- TransactionID jetzt = Marketplace-Order-ID (statt Jera-PK-Konvention `R{pk}`/`G{pk}`).
- Reconciler von TransactionID-Match auf DocumentID-Match umgestellt; obsolete `_strip_storno_prefix`-Logik entfernt.
- **Ergebnis:** 13.411 Belege Schnittmenge, 42 Cent-Rundungen Σ −0,12 € Brutto (Q1-Total). `samples/duty/DutyPay-SALE-2026-FEB_fehler.csv` ist Duplikat der Haupt-FEB-Datei (vom Steuerberater nach DutyPay-Rückweisung neu hochgeladen) und wird im Reconciler nicht mit-summiert. 590 Engine-only / 1 Ref-only.
- Ref-only-Item: Sammelaggregation von 640 Belegen, durch Excel-Wissenschaftsnotation-Korruption (`2,03E+11` statt Ziffernfolge). Engine korrekt; Ref-Datenqualität.

**TX-ID-Spec-Konsequenz:** Engine-Output (Marketplace-Order-ID ohne Suffix) ist zuverlässiger als alte Jera-Refs mit teils internalen JTL-Kennungen oder Excel-zerstörter DocIDs.

**Tests:** 189 passed, 3 skipped.

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
