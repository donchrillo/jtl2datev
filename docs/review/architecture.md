# Architektur-Review

> Datum: 2026-05-09
> Reviewer: general-purpose (opus)
> Branch: main, Commit: 3c332a7710adb37b08ab40fb8fa61d2d95490ff8

## Zusammenfassung

Die Codebase ist überraschend sauber für ein Tool, das in wenigen Sprints
gewachsen ist. `core/` ist **tatsächlich framework-agnostisch** (kein
`click`, kein `print`, durchgehend `logging`), die Repository-Schnittstelle
existiert als ABC, Pydantic-Models sind frozen und wirken konsistent. Das
zentrale Problem ist **nicht** ein Designfehler, sondern strukturelle Erosion:
`cli.py` ist auf 1.572 Zeilen mit massiver Boilerplate-Duplikation gewachsen,
die drei Exporter-Familien (datev/dutypay/taxually) reimplementieren denselben
"Repo holen → Tempfile schreiben → archivieren → kopieren"-Loop, und mehrere
Konfigurations-Quellen (`OWN_VAT_IDS_VERBRINGUNG`, `_DEFAULT_OWN_VAT_IDS`,
`COUNTRY_CURRENCIES` in `verbringung_pdf.py` vs. `_COUNTRY_CURRENCY` in
`dutypay.py`, `EU_COUNTRIES` in `tax_engine.py` vs. `_EU_NON_DE` in `rules.py`)
duplizieren Stammdaten ohne Single-Source-of-Truth. Das ist kein ERP-Blocker,
aber genau der Tech-Debt, der beim FastAPI-Umzug erst sichtbar wird, wenn
zwei verschiedene Wahrheiten an zwei verschiedenen Endpunkten ausgespielt
werden.

## Top-3-Risiken für ERP-Migration

1. **`InvoiceRepository`-Interface ist ein Skelett** (1 Methode, 14 Zeilen).
   Sobald `db_toci.py` gebaut wird, wird klar, dass die JTL-Implementierung
   implizite Verträge an die Daten stellt (Marketplace-Order-ID-Konvention,
   `_strip_marketplace_suffix`, `derive_vat_rate` aus Header, SRK-Detektion
   per Belegnr-Prefix), die nirgends als Repository-Vertrag dokumentiert sind.
   Diese Konventionen leben heute halb in `db_jtl.py`, halb in den Konsumenten
   (`dutypay.py`, `datev.py`, `taxually.py`) — die Migration wird zwingend
   alle drei Stellen anfassen müssen.
2. **JTL-spezifische Konventionen lecken in den Core**: SRK-Storno-Detektion
   per `invoice_no.startswith("SRK")` (db_jtl.py:588), Jera-PK-Konvention
   `R{pk}/SR{pk}/G{pk}/SRK{pk}/ER{pk}/EG{pk}` als Fallback in `dutypay.py:368-376`,
   Temu-Filter per `ext_no.startswith("PO")` in `datev.py:405`, Marketplace-
   Order-ID-Suffix-Stripping in `db_jtl.py`. Wenn das ERP eigene Belegnummern
   vergibt, muss diese Logik entweder generisch werden oder per
   Adapter-Strategie austauschbar.
3. **`cli.py` Volumen vs. spätere FastAPI-Routen**: Die ~1.500 CLI-Zeilen
   enthalten echte Geschäftslogik (Date-Resolution, Baseline-Auflösung,
   Tempfile-Choreographie, Mismatch-CSV-Schreiber, B-Ware-Summary-Aggregation).
   Beim Umzug in FastAPI-Router ist nicht klar, wo der Cut zwischen "API-Layer"
   und "Library-Service" liegt. Aktuell wird das einfach in CLI dupliziert,
   im ERP würde es in jedem Router dupliziert.

## Findings

### BLOCKER

#### F-1: `InvoiceRepository` ist faktisch nicht swappable
- Datei: `src/jtl2datev/core/repositories.py` (gesamtes Interface, 14 Zeilen)
- Beschreibung: Die ABC hat genau eine Methode `fetch_invoices(date_from, date_to) -> Iterator[RawInvoice]`.
  Damit ist sie technisch swappable, aber der **Datenkontrakt** ist nicht
  dokumentiert. Verbringungen (`verbringung_pricing.lookup_prices`) gehen
  z.B. direkt an die `Engine` und an JTL-Tabellennamen
  (`dbo.pf_amazon_angebot_mapping`, `dbo.tArtikel`) vorbei am Repository.
  Die Tabellen-Namen sind als Default-Argumente parametrisiert — gut für
  SQLite-Tests, aber das Interface ist nicht in `repositories.py` deklariert.
  Mixed-VAT-Preflight (`preflight.find_mixed_vat_belege`) greift ebenfalls
  direkt auf `Engine` zu mit JTL-spezifischem SQL und ist nicht durch das
  Repository abgekoppelt.
- Refactor-Vorschlag:
  ```
  core/repositories.py
    class InvoiceRepository(ABC):
        def fetch_invoices(...)
        def find_mixed_vat_belege(...) -> Iterable[MixedVatBeleg]
    class ArticlePricingRepository(ABC):
        def lookup_ek_prices(skus, asin_by_sku) -> dict[str, PricingResult]
  core/db_jtl.py     → JtlInvoiceRepository    (SQL aus heute)
  core/db_jtl_pricing.py (oder im selben Modul)
                     → JtlArticlePricingRepository
  ```
  Der CLI/Service-Layer instanziiert die JTL-Variante, die Verbringungs-
  Pipeline bekommt das Pricing-Repository injiziert statt der `Engine`.
- Aufwand: 1-4h
- Migrations-Relevanz: HOCH. Ohne diese Erweiterung muss bei der ERP-Migration
  zusätzlich zu `db_jtl.py` auch `verbringung_pricing.py` und `preflight.py`
  fundamental umgeschrieben werden — drei statt einer Stelle.

#### F-2: CLI-Boilerplate-Explosion + Geschäftslogik im Wrapper
- Datei: `src/jtl2datev/cli.py` (1.572 Zeilen, 9 Commands)
- Beschreibung: Die drei Exporter (`export-dutypay`, `export-taxually`,
  `export` für DATEV) plus die drei zugehörigen `*-delta`-Commands haben fast
  identisches Strukturmuster (~80-150 Zeilen pro Command):
  - `_resolve_date_range(...)`
  - `use_archive = month_str is not None`
  - Validierungen "bei `--from/--to` ist `--out` Pflicht"
  - `Settings()`, `make_engine`, `repo`
  - `tempfile.NamedTemporaryFile`-Choreographie
  - Optionaler Archivierungs-Aufruf
  - Optionaler `shutil.copy2` zur Out-Datei
  - Cleanup-`finally`
  Das ist nicht "ähnlich" — das ist 90% identisch. Außerdem wandern
  Hilfsfunktionen wie `_write_mismatches_csv`, `_write_mixed_vat_csv` und
  die ganze B-Ware-Summary-Aggregation (~70 Zeilen in `export_verbringung_cmd`)
  in CLI, obwohl es Library-Logik ist.
- Refactor-Vorschlag:
  ```
  src/jtl2datev/cli/
    __init__.py     # main group + version + verbose option
    _common.py      # _resolve_date_range, _parse_month, _month_date_range,
                    # run_export_with_archive(...) high-level helper
    export_datev.py
    export_dutypay.py
    export_taxually.py
    export_verbringung.py
    reconcile.py
    mixed_vat.py
    import_rates.py

  core/export_runner.py
    @dataclass class ExportSpec:
        kind: Literal["datev","dutypay","taxually"]
        suffix: str
        writer: Callable[..., Any]
        archive_writer: Callable[..., Path]
    def run_export(spec, *, repo, settings, df, dt_, month_str,
                   out_path, **writer_kwargs) -> Report
  ```
  CLI-Commands schrumpfen damit auf ~30 Zeilen Click-Optionen + 1 Aufruf
  `run_export(...)`. Der Mismatch-Writer und der B-Ware-Summary-Aggregator
  gehen in `core/reconcile.py` bzw. `core/verbringung_pricing.py` (oder ein
  neues `core/verbringung_summary.py`).
- Aufwand: groß (1-2 Tage), aber inkrementell pro Command machbar
- Migrations-Relevanz: MITTEL-HOCH. Die heutigen CLI-Commands sind 1:1 die
  späteren FastAPI-Routen. Wenn `run_export(...)` als Library-Service
  existiert, wird der Router zum 5-Zeiler. Wenn nicht, dupliziert sich die
  ganze Tempfile-/Archive-Choreographie nochmal in der API-Schicht.

### WICHTIG

#### F-3: Konstanten-Duplikation zwischen Modulen
- Stellen:
  - `EU_COUNTRIES` (frozenset, 27 Länder) in `tax_engine.py:5`
  - `_EU_NON_DE` (26 Länder) + `_EU_ALL` (= +DE) in `rules.py:11`
  - `_EU_ALL = EU_COUNTRIES` in `dutypay.py:131` (re-export)
  - `OWN_VAT_IDS_VERBRINGUNG` in `config.py:11` (Top-Level-Konstante mit SK-Kommentar)
  - `_DEFAULT_OWN_VAT_IDS` in `config.py:26` (gleicher Inhalt minus SK-Kommentar, ohne SK-Eintrag)
  - `_COUNTRY_CURRENCY` in `dutypay.py:135` vs. `COUNTRY_CURRENCIES` in `verbringung_pdf.py:65` — überlappen
    sich, sind nicht identisch (verbringung_pdf hat AT/BE/NL extra, dutypay hat US/NO/DK/HU/RO/SE)
  - `_PLATFORM_COUNTRY` in `db_jtl.py:23` (kein Pendant; OK so, lebt nur in DB-Layer)
- Beschreibung: EU-Mitgliedsländer und Country→Currency-Mappings sind
  Stammdaten, die genau einmal definiert sein müssen. Aktuell drei Quellen
  für EU-Liste, zwei für Currency-Mapping. Wenn 2027 ein neues EU-Mitglied
  dazukommt, muss man drei Stellen anfassen. Bei `OWN_VAT_IDS` ist
  bedenklich, dass die "Verbringung"-Variante explizit eine **Übermenge**
  ist (mit SK-Anmerkung) — der Unterschied verschwindet im Kommentar.
- Refactor-Vorschlag: Neues Modul `core/reference_data.py`:
  ```python
  EU_MEMBER_STATES: frozenset[str] = frozenset({...})  # 27 Länder
  COUNTRY_CURRENCY: dict[str, str] = {...}             # konsolidiert
  PLATFORM_COUNTRY: dict[str, str] = {...}             # aus db_jtl
  ```
  Alle Module importieren von dort. `OWN_VAT_IDS` zentral in `Settings`,
  `OWN_VAT_IDS_VERBRINGUNG` als Property `Settings.own_vat_ids_with_returns_only_warehouses`
  oder einfach auflösen — die SK-Sonderregel ("kein Eintrag = keine
  Registrierung") wirkt durch das Fehlen des Schlüssels, nicht durch zwei
  unterschiedliche Dicts.
- Aufwand: 1-4h
- Migrations-Relevanz: MITTEL. Im ERP wird das Tax-Engine-Modul wandern, und
  je weniger Stammdaten dabei "an drei Stellen synchron halten" sind, desto
  weniger Bugs.

#### F-4: `RawInvoiceLine`-Felder sind tote Buchhaltung
- Datei: `src/jtl2datev/core/models.py:39-60`
- Beschreibung: `RawInvoiceLine` hat 15 Felder (sku, description, quantity,
  product_group_id, position_type, jtl_tax_key_id, weight, manufacturer,
  manufacturer_country, commodity_code, long_description, unit, transport_code).
  Seit der Header-Eckdaten-Umstellung (2026-05-06) wird **`_synthetic_line`**
  in `db_jtl.py:295-309` aufgerufen, das **alle** diese Felder leer/None
  lässt. Im Repository bleibt damit pro Invoice exakt eine synthetische Line
  übrig, deren reichhaltige Felder semantisch gelogen sind (sie suggerieren
  Daten, die nicht da sind). Dutypay/DATEV/Taxually-Exporter ignorieren sie
  konsequent. `next-session.md` Punkt 1 listet das bereits als geplantes
  Cleanup. Die Konsequenz für ERP-Migration: das ERP-Schema muss diese
  Felder gar nicht erst füllen.
- Refactor-Vorschlag: `RawInvoiceLine` auf das reduzieren, was tatsächlich
  benutzt wird (`line_no`, `net`, `gross`, `vat_amount`, `vat_rate`,
  `jtl_tax_key_id`). Wenn später Position-Level-Daten zurückkehren (echte
  Mehrposten), reines Hinzufügen — aber dann mit wirklicher Befüllung.
- Aufwand: 1-4h (Tests anpassen, Pydantic-Defaults entfernen, openpyxl-XLSX-
  Verbringung-Writer prüfen)
- Migrations-Relevanz: NIEDRIG-MITTEL. Reine Hygiene; das ERP weiß nicht,
  welche Felder Schein sind.

#### F-5: Pipeline-Modul ist unterausgeprägt; Flow nur halb extrahiert
- Datei: `src/jtl2datev/core/pipeline.py` (69 Zeilen, nur `run_reconcile`)
- Beschreibung: Pipeline existiert als Konzept, enthält aber nur **eine**
  Funktion (`run_reconcile`). Die Export-Pipelines werden direkt in `cli.py`
  zusammengestellt: Repo holen, Decisions berechnen, schreiben, archivieren
  (siehe F-2). `pipeline.py` wäre der natürliche Ort für `run_datev_export`,
  `run_dutypay_export`, `run_taxually_export`, `run_verbringung_export`. Die
  CLI würde dann nur Click-Argumente entgegennehmen und die passende Pipeline-
  Funktion aufrufen. Aktuell ist `pipeline.py` faktisch ein "ReconcileService"-
  Modul mit irreführendem Namen.
- Refactor-Vorschlag: Entweder `pipeline.py` zu `reconcile_service.py`
  umbenennen, oder die anderen Export-Service-Funktionen dorthin ziehen
  (besser, siehe F-2).
- Aufwand: kombiniert mit F-2
- Migrations-Relevanz: MITTEL.

#### F-6: Settings-Coverage lückenhaft, Konstanten leben außerhalb
- Datei: `src/jtl2datev/core/config.py`
- Beschreibung: `Settings` deckt DB-Verbindung, DATEV-Mandant, OwnVAT, B-Ware-
  Strategie ab — gut. Aber:
  - DATEV-Konten-Mapping (`_DOMESTIC_MAP`, `_DEBITOR_BY_PAYMENT`) hardcoded
    in `rules.py`. Das sind Mandanten-spezifische Daten. Im ERP mit mehreren
    Mandanten muss das aus Settings/DB kommen.
  - Hard-Min-Date `_MIN_DATE = date(2024, 11, 1)` in `db_jtl.py:16` und
    nochmal in `preflight.py:16` — magic constant, zweimal definiert,
    sollte in Settings.
  - `STANDARD_VAT_RATE` (Steuersätze 2026) in `tax_engine.py:26` — wird
    sich jährlich ändern (siehe Estland-Kommentar zum 01.07.2025-Wechsel).
    Wenn historische Belege re-exportiert werden, braucht es zeitabhängige
    Sätze; aktuell ist alles "current state".
- Refactor-Vorschlag:
  ```python
  class Settings(BaseSettings):
      ...
      hard_min_invoice_date: date = date(2024, 11, 1)
      vat_rates: dict[str, Decimal] = ...   # JSON-loadable, mit period-validity
      domestic_account_map: dict[str, str] = ...  # warehouse -> account
      debitor_account_map: dict[str, int] = ...   # payment_method -> account
  ```
  `STANDARD_VAT_RATE` bekommt eine zeitabhängige Variante:
  `vat_rate_for(country, on_date) -> Decimal`. Das ist auch aus
  Tax-Korrektheits-Sicht relevant (separater Reviewer); architektonisch ist
  der Punkt: **Konfiguration vs. Stammdaten vs. Konstanten** ist nicht
  konsequent getrennt.
- Aufwand: 1-4h für die einfachen Punkte (`_MIN_DATE`, `_DOMESTIC_MAP`),
  >4h für period-validity der VAT-Sätze
- Migrations-Relevanz: HOCH. Mandanten-Mapping ist im ERP-Multi-Mandanten-
  Setup essentiell.

#### F-7: `_build_row` in datev.py macht zu viel, Audit-Tag verworren
- Datei: `src/jtl2datev/core/datev.py:289-371`
- Beschreibung: 80-Zeilen-Funktion mit 8 Keyword-Args. Mischt FX-Logik,
  EU-Spaltenlogik, Audit-Tag, Kunden-Beleginfo. `_IDX_*`-Konstanten (20+)
  am Modul-Top sind ein Code-Smell — typischer Hinweis auf "ich modelliere
  ein flaches Tupel statt ein Datenobjekt". Außerdem wird der Audit-Tag in
  Spalte `_IDX_BELEGLINK` (Beleglink) untergebracht — das ist ein Hack, den
  CLAUDE.md-Convention "vor Übergabe an den Steuerberater wieder entfernen"
  bestätigt.
- Refactor-Vorschlag: `BuchungsRow` als `dataclass` mit benannten Feldern
  und einer `to_csv_row(self) -> list[str]`-Methode. Dann verteilen sich
  die 124 Spaltenpositionen einmal an einer Stelle, und die Builder-Funktionen
  arbeiten mit Domain-Objekten. Der Audit-Tag bekommt ein eigenes Feld in
  der Row, der CSV-Writer entscheidet, ob er es in Beleglink schreibt.
- Aufwand: 1-4h
- Migrations-Relevanz: NIEDRIG (ändert nichts am Schema).

### NICE-TO-HAVE

#### F-8: `_format_decimal` / `_safe_text` / `_safe` Format-Helper dupliziert
- Stellen: `datev.py:224-258`, `dutypay.py:264-287`, `taxually.py` indirekt
  über openpyxl. Jeder Exporter hat seinen eigenen "DE-Komma"-Formatter
  und seine eigene "Semikolon-Strip"-Sanitizer-Funktion. Inhalte fast
  identisch.
- Refactor-Vorschlag: `core/format_helpers.py` mit `format_de_decimal`,
  `format_de_date`, `csv_safe_text`, `cp1252_safe_text`. Encoding-spezifika
  (`cp1252` für DATEV) bleiben in den Exportern.
- Aufwand: <1h
- Migrations-Relevanz: NIEDRIG.

#### F-9: Default-Logging auf ERROR begräbt warnings
- Datei: `src/jtl2datev/cli.py:21-29`
- Beschreibung: Default ist seit kürzlich `ERROR`. Begründung im Kommentar:
  "Bibliotheks-WARNINGs (z.B. 'Unknown platform') unterdrückt — Fallback
  ist im Code dokumentiert". Das ist riskant: `_marketplace_country_for` und
  `_warehouse_currency` (DutyPay) loggen mit WARN, wenn unbekannte Länder/
  Plattformen auftauchen — genau die Fälle, wo der Operator es wissen sollte.
  Wenn das Signal-Rauschen zu hoch ist, sollte das **per Logger-Level pro
  Modul** zurückgenommen werden, nicht global. Außerdem unterdrückt ERROR
  auch die DATEV-Export-Warnungen `"%s flagged ERROR"` und
  `"%s flagged UNKNOWN"` — die wandern stattdessen ja in den ExportReport,
  aber nicht jeder CLI-Aufrufer schaut dort hin.
- Refactor-Vorschlag: Default zurück auf WARNING, Modulen wie
  `db_jtl._marketplace_country_for` einen INFO-Log statt WARN geben (oder
  einmaligen Cache, der pro Plattform nur einmal warnt). `--quiet` für
  ERROR-only, `-v` für INFO, `-vv` für DEBUG.
- Aufwand: <1h
- Migrations-Relevanz: NIEDRIG (FastAPI hat ohnehin eigenes Logging-Setup).

#### F-10: Test-Verteilung — viele Format-Smoke-Tests, wenig Pipeline
- Beobachtung (insgesamt 367 Tests laut `grep -c "def test_"`, 418 inkl.
  parametrize laut next-session.md):
  - test_dutypay.py: 76 Tests
  - test_datev.py: 46
  - test_verbringung_pricing.py: 45
  - test_cli.py: 41 (überwiegend `--help`/Argument-Validierung-Smoke)
  - test_pipeline.py: 10 (für ein Pipeline-Modul, das `run_reconcile`
    enthält — nicht der Export-Pipelines)
  - test_reconcile.py: nur 2 Tests (für ein zentrales Modul!)
  - test_tax_engine.py: 10
  - test_rules.py: 24
- Beschreibung: Die Exporter sind sehr gut getestet (gut), aber der
  Reconcile-Vergleich hat nur 2 Unit-Tests, obwohl er das **Korrektheits-
  Gewissen** des Tools ist. CLI-Tests sind fast alle "Help-Smoke" und
  "fehlende Args werfen Fehler" — wenig Wert. Die Integration-Tests
  (`@pytest.mark.integration` in `test_db_jtl.py`) skippen ohne
  `SQL_USERNAME` automatisch — das ist OK, sollte aber in `pytest.ini`
  ein eigener Marker mit Doku sein.
- Refactor-Vorschlag: `test_reconcile.py` ausbauen (10-15 Cases pro
  Severity-Pfad), CLI-Help-Tests durch parametrisierten Smoke-Test ersetzen.
  Pipeline-Tests sollten in `test_export_runner.py` umziehen, sobald F-2
  passiert.
- Aufwand: 1-4h
- Migrations-Relevanz: MITTEL (die Tests wandern 1:1 mit, aber nur, wenn sie
  Library-Code testen, nicht CLI-Argument-Parsing).

#### F-11: `from __future__ import annotations` inkonsistent
- Beobachtung: Manche Module nutzen es (`models.py`, `rules.py`, `pipeline.py`,
  `dutypay.py`, `dutypay_delta.py`, `datev.py`, `datev_delta.py`,
  `taxually_delta.py`, `verbringung_taxually.py`, `verbringung_pdf.py`),
  andere nicht (`db_jtl.py`, `tax_engine.py`, `taxually.py`, `config.py`,
  `archive.py`, `repositories.py`, `verbringung_parser.py`,
  `verbringung_pricing.py`, `exchange_rates.py`, `preflight.py`).
- Refactor-Vorschlag: einheitlich überall hinzufügen oder per Ruff-Rule
  erzwingen. Inhaltlich kein Problem (Python 3.12), nur Konsistenz.
- Aufwand: <1h
- Migrations-Relevanz: NIEDRIG.

#### F-12: Imports innerhalb von Funktionen
- Stellen: viele in `cli.py` (jeder Command importiert seine Core-Module
  innerhalb der Funktion — vermutlich für CLI-Startup-Performance).
  Auch in `core/db_jtl.py:258` (`from datetime import datetime`),
  `archive.py`-Imports in cli statt einmal oben.
- Beschreibung: In CLI vertretbar (lazy load → schnellere `--help`-
  Antwortzeit). In Core-Modulen (`_to_date` in db_jtl.py) eher Code-Smell.
- Refactor-Vorschlag: Core-Module: alle Imports nach oben. CLI: bleibt
  bewusst lazy, aber dokumentiert das in einem Modul-Kommentar.
- Aufwand: <1h
- Migrations-Relevanz: NIEDRIG.

#### F-13: `verbringung_pdf.py` mischt Layout, Konstanten, Konvertierung
- Datei: 446 Zeilen, enthält `COUNTRY_NAMES_DE`, `COUNTRY_NAMES_EN`,
  `COUNTRY_CURRENCIES` (siehe F-3 Duplikat), Layout (`_NumberedCanvas`,
  `_build_pdf`), und Orchestrierung (`generate_proforma_pdfs`).
- Refactor-Vorschlag: Stammdaten in `core/reference_data.py`, Layout in
  `core/verbringung_pdf_layout.py`, Orchestrierung bleibt in
  `verbringung_pdf.py`. Wahrscheinlich erst nötig, wenn weitere PDF-Layouts
  dazukommen.
- Aufwand: 1-4h
- Migrations-Relevanz: NIEDRIG.

#### F-14: Error-Handling: blanket `except Exception` mit `click.echo`
- Stellen: jeder CLI-Command fängt `except Exception as exc:` und schreibt
  `f"Fehler beim ...: {exc}"`. Das ist bei einem Konsolen-Tool akzeptabel,
  schluckt aber den Stack-Trace. Bei DB-Connect-Fehlern (häufigste Ursache)
  ist die Exception-Message oft kryptisch (`pyodbc`-Mehrzeiler).
- Refactor-Vorschlag: `except Exception as exc: ... raise SystemExit(1) from exc`
  ist heute schon im Code (gut). Ergänzend: bei `--verbose` zusätzlich den
  Traceback ausgeben. Im Library-Layer (Core) wird ohnehin nichts
  geschluckt — das ist sauber gelöst.
- Aufwand: <1h
- Migrations-Relevanz: NIEDRIG (FastAPI hat eigene Exception-Handler).

## Modul-Landkarte

### Aktuell

```
cli.py (1572 LOC)
  ├─ export                ─┐
  ├─ export-delta          ─┤  alle nutzen direkt:
  ├─ export-dutypay        ─┤    Settings, make_engine, JtlInvoiceRepository
  ├─ export-dutypay-delta  ─┤    Tempfile-/Archiv-Choreographie inline
  ├─ export-taxually       ─┤    Date-Resolution-Logik wiederholt
  ├─ export-taxually-delta ─┤    Out-Path-Konvention wiederholt
  ├─ export-verbringung    ─┘  + B-Ware-Summary-Aggregator (~70 Zeilen)
  ├─ reconcile             →   pipeline.run_reconcile (gut!)
  ├─ mixed-vat-check       →   preflight.find_mixed_vat_belege
  └─ import-rates          →   exchange_rates.import_bmf_rates

core/
  ├─ repositories.py (14 LOC)        ABC, 1 Methode
  ├─ db_jtl.py (640 LOC)             SQL + Mapping + JTL-Konventionen
  ├─ tax_engine.py                   reine Logik (gut!)
  ├─ rules.py                        Konten-Mapping (Hardcoded-Tabellen)
  ├─ reconcile.py                    Compare-Logik (gut, aber unter-getestet)
  ├─ pipeline.py                     enthält NUR run_reconcile, irreführend
  ├─ preflight.py                    Mixed-VAT-SQL — hängt direkt an Engine
  ├─ datev.py / dutypay.py /         Format-Writer; Format-Spec-Konstanten
  │  taxually.py                       inline; eigene _format_decimal/_safe
  ├─ datev_delta.py / dutypay_delta /  Delta-Logik; uneinheitlich strukturiert
  │  taxually_delta.py                 (taxually_delta hat z.B. Archive-Helper
  │                                     drin, die anderen nicht)
  ├─ archive.py                      generisch (gut!)
  ├─ exchange_rates.py               JSON-Store + BMF-CSV-Import (gut!)
  └─ verbringung_*.py (4 Module)     parser/pricing/taxually/pdf — eigene
                                       Country-Currency-Tabelle, eigene Konstanten
```

### Empfohlen (nach Refactor F-1, F-2, F-3, F-5, F-6)

```
cli/
  ├─ __init__.py        (main group, version, verbose)
  ├─ _common.py         (date-resolution, archive-runner)
  ├─ export_*.py        (~30 Zeilen pro Command, delegiert an services/)
  └─ ...

core/
  ├─ repositories/      (Package)
  │   ├─ __init__.py    (ABC: InvoiceRepository, ArticlePricingRepository,
  │   │                  PreflightRepository)
  │   └─ jtl.py         (Implementierungen, ehemals db_jtl.py + verbringung_pricing)
  ├─ services/          (Package, ehemals pipeline.py erweitert)
  │   ├─ datev_export.py
  │   ├─ dutypay_export.py
  │   ├─ taxually_export.py
  │   ├─ verbringung_export.py
  │   ├─ reconcile.py   (= heutiges pipeline.run_reconcile)
  │   └─ delta.py       (gemeinsamer Delta-Algorithmus, falls extrahierbar)
  ├─ exporters/         (Format-Writer, ehemals datev.py/dutypay.py/taxually.py)
  │   ├─ datev_extf.py
  │   ├─ dutypay_csv.py
  │   ├─ taxually_xlsx.py
  │   └─ format_helpers.py  (DE-Decimal, CSV-Safe-Text, etc.)
  ├─ models.py          (RawInvoiceLine schlanker, siehe F-4)
  ├─ tax_engine.py      (unverändert)
  ├─ rules.py           (Mapping-Tabellen aus Settings beziehen, F-6)
  ├─ reference_data.py  (NEU: EU_COUNTRIES, COUNTRY_CURRENCY, PLATFORM_COUNTRY)
  ├─ config.py          (erweiterte Settings, F-6)
  ├─ archive.py         (unverändert)
  ├─ exchange_rates.py  (unverändert)
  └─ verbringung/       (Package)
      ├─ parser.py
      ├─ pricing.py
      ├─ taxually.py
      └─ pdf.py
```

Im FastAPI-Umzug entfällt `cli/` komplett, `core/services/` wird zu
`backend/api/routers/`. Zwischen Router und Service liegt nur noch ein
Pydantic-Request/Response-Schema, kein Tempfile-Boilerplate mehr.

## Geprüfte Aspekte ohne Befund

- **Framework-Reinheit von `core/`**: kein `print`, kein `click`, kein
  `sys.argv`. Logging über `logging.getLogger(__name__)` durchgehend.
  Die DB-Engine wird ausnahmslos per Konstruktor injiziert (`JtlInvoiceRepository(engine)`).
  CLAUDE.md-Regel #1 wird strikt eingehalten.
- **Pydantic-Modelle**: Alle Domain-Models sind `frozen=True`. Defaults
  konsistent (`None` für Optionals). `StrEnum` für `TaxTreatment` und
  `KindOfBusiness` — modern und richtig. `model_copy(update=...)` wird in
  `taxually_delta.py:87` genutzt — saubere Pydantic-v2-Idiomatik.
- **Iterator-Streaming**: `JtlInvoiceRepository.fetch_invoices` ist Generator,
  nutzt `conn.execution_options(stream_results=True)`. Speicherprofil bei
  großen Datumsbereichen sollte unauffällig sein.
- **SQL-Parameter-Binding**: Alle Queries in `db_jtl.py` und `preflight.py`
  nutzen `text(...)` mit `:placeholder` + `bindparam(expanding=True)` für
  IN-Listen. Kein String-Concat. (Sicherheits-Audit gehört Robustness-
  Reviewer, hier nur Architektur-Bestätigung: das DAO macht es richtig.)
- **Atomic-Writes**: `exchange_rates._atomic_write` nutzt tmp-File +
  `os.replace`. Vorbildlich.
- **Repository-Pattern strukturell**: `JtlInvoiceRepository` erbt von
  `InvoiceRepository`, `make_engine(settings)` ist Factory. Die Dependency-
  Richtung stimmt: `db_jtl` → `repositories` (Interface) → `models`. Keine
  zyklischen Importe entdeckt.
- **Delta-Logik (DATEV/DutyPay)**: Match-Key-Strategie ist explizit
  dokumentiert (Buchungstext-Token für DATEV, DocumentID für DutyPay).
  `--shift-to-period` ist sauber als optional behandelt. Architektur ok.
- **Test-Isolation**: SQLite-Engine-Fixtures in `test_verbringung_pricing.py`
  sind ein gutes Pattern (Tabellen-Namen werden in `lookup_prices` per
  Default-Argument konfigurierbar gehalten — guter Punkt für Testbarkeit).
