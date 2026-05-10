# Robustness-Review

> Datum: 2026-05-09  
> Reviewer: general-purpose (opus)  
> Branch: main, Commit: 3c332a7710adb37b08ab40fb8fa61d2d95490ff8

## Zusammenfassung

Das Tool ist solide auf Tax-Korrektheit hin gebaut: SQL ist durchgehend parametrisiert (kein f-string-Injection-Risiko), DATEV-CSV verwendet `_to_cp1252(..., errors="replace")` plus Semikolon-Stripping (CSV-Sicher), und der DutyPay/Taxually-Pfad arbeitet mit UTF-8. Die größeren Risiken liegen jedoch nicht in der Logik, sondern in der **Lebenszyklus-/IO-Schicht**: Connection-Pool ohne Pre-Ping/Recycle (erklärt den 15s-Hang), Output-Files werden nicht atomar geschrieben (`.csv` wird `open("w")`-truncated bevor gepuffert geschrieben → Crash/Strg+C produziert truncierte Dateien, die als gültige Baseline für nächsten Delta-Lauf gelten), und die Auto-Archive verwendet sekundengenaue Timestamps (parallele Runs überschreiben sich). Encoding ist im DATEV-Pfad korrekt abgefangen, aber im DutyPay-Pfad wird `;` zwar gestrippt, **`\n`/`\r`/Tabs nicht** — das kann CSV-Zeilen sprengen, sobald JTL irgendwo eine mehrzeilige Adresse durchreicht.

**Top-3 Risiken**: 1) Nicht-atomare Exports + Auto-Archive ohne Schutz vor parallelen Läufen (Datenkorruption von Baselines möglich), 2) DutyPay/Taxually-Inputs sanitisieren `\n`/`\r` nicht (CSV-Row-Sprengung möglich, wenn JTL-Daten Newlines enthalten), 3) Connection-Pool ohne pool_pre_ping/timeout → bei Netz-Glitch hängen Exports unbestimmte Zeit, ohne Retry-Logik.

## Top-3 kritische Risiken

1. **Korrupte Baselines durch nicht-atomares Schreiben.** `write_extf_buchungsstapel` öffnet das Ziel direkt mit `out_path.open("w", ...)`. Strg+C, Disk-Full, ODBC-Disconnect oder unbehandelte Exception mitten im Loop hinterlassen eine teilweise geschriebene CSV. `archive_export` kopiert anschließend (im DATEV-Fall direkt; im DutyPay-/Taxually-Fall über tempfile, dort ist es OK) die Datei in den Archivbaum. Nächster `export-delta`-Lauf nimmt die truncierte Datei als Baseline → Delta enthält zigtausend "neue" Belege, doppelt verbucht. Wahrscheinlichkeit hoch (Strg+C kommt vor), Impact: sehr hoch (Doppel-Buchung).

2. **Newline-/Tab-Sprengung der DutyPay-/Taxually-CSV.** `_safe()` in `dutypay.py` ersetzt nur `;`, nicht `\n`, `\r`, `\t`. `csv.writer` mit `QUOTE_MINIMAL` quotet zwar Zellen mit `\n`, aber wenn jemand das File später Zeilen-weise einliest (z.B. `dutypay_delta.compute_delta` via `csv.DictReader`, der mit Quoting umgehen kann — OK) oder DutyPay selbst zeilenweise parst, geht es kaputt. Taxually-XLSX ist robuster (Excel-Strings dürfen Newlines enthalten). Wahrscheinlichkeit mittel (Adressen mit Zeilenumbruch sind in JTL üblich).

3. **DB-Connection-Lifecycle.** `make_engine()` setzt nur `fast_executemany`, keinen Pool-Konfig (kein `pool_pre_ping`, kein `pool_recycle`, kein `connect_args={"timeout": …}` für ODBC, kein `connect_args={"login_timeout": …}`). Beim heutigen 15s-Hang konnten Sie nicht klar erkennen, ob Login, TCP oder Query hing. Bei abgelaufenen Connections im Pool fliegt der erste Query mit OperationalError — kein Retry. Mittlere Wahrscheinlichkeit, hoher Impact (Steuermeldung verzögert).

## Findings

### BLOCKER

- **F-1: Nicht-atomares Schreiben von DATEV-/DutyPay-/Taxually-Files**
- `src/jtl2datev/core/datev.py:389`, `src/jtl2datev/core/dutypay.py:489`, `src/jtl2datev/core/taxually.py:158` (wb.save direkt), `src/jtl2datev/core/verbringung_taxually.py:119`
- Reproduktion: `jtl2datev export --month 2026-04` starten, nach 30s Strg+C. Datei `exports/datev/2026-04.csv` existiert, ist gekürzt. `archive_export` wird zwar nicht mehr erreicht (im DATEV-Pfad), aber der Operator könnte die Datei manuell weiterverwenden. Kritischer: bei `export-dutypay` wird zuerst in tempfile gepuffert (gut!), aber im DATEV-Pfad nicht. Bei nachfolgendem `export-delta` wird unter Umständen die korrupte Datei als Baseline gewählt, da `latest_archive` nur lexikographisch sortiert.
- Aktuelles Verhalten: Truncierte Datei bleibt liegen, kein Marker dass sie kaputt ist.
- Empfohlenes Verhalten: Gleiches Pattern wie `exchange_rates._atomic_write` — in `<path>.tmp` schreiben, am Ende `os.replace`. Bei Exception im `with`-Block: tmp-File löschen.
- Fix: `datev.write_extf_buchungsstapel` analog zu `cli.export_dutypay_cmd` umstellen — in tempfile schreiben, dann `shutil.move` ans Ziel. Alternative: Context-Manager `_atomic_open(path)` nutzen, der bei sauberer Schließung umbenennt, sonst aufräumt.
- Aufwand: 1-4h

- **F-2: Auto-Archive Race-Condition (gleiche Sekunde = Überschreibung)**
- `src/jtl2datev/core/archive.py:38` (`archive_export`), `:72` (`archive_delta`)
- Reproduktion: Zwei Terminals, beide `jtl2datev export --month 2026-04` simultan starten. Beide Runs landen mit Wahrscheinlichkeit > 0 in derselben Sekunde im Archive — der zweite überschreibt (`shutil.copy2` ohne `exist_ok`-Check) den ersten. Subtiler: Der erste Run wird *vor* der Archivierung mit etwas anderem Inhalt fertig, der zweite Run schreibt direkt darüber.
- Aktuelles Verhalten: `dest_dir / f"{ts}.csv"` wird stumm überschrieben.
- Empfohlenes Verhalten: PID + Hash anhängen oder `os.O_EXCL`-äquivalent (`open(..., "x")`) und im Konfliktfall `_2`/`_3` suffix anhängen. Mindestens microsecond-Genauigkeit (`%Y-%m-%d_%H-%M-%S-%f`).
- Fix: `ts = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S-%f")`, plus optional file-lock auf `<archive_root>/<kind>/<period>/.lock` während der Operation.
- Aufwand: <1h

- **F-3: Newlines/Tabs in DutyPay-CSV-Zellen werden nicht entfernt**
- `src/jtl2datev/core/dutypay.py:284` (`_safe`)
- Reproduktion: JTL-Beleg mit Adresse "Hauptstraße 5\nWohnung 3" — Feld kommt aus DB → wird via `_safe()` durchgereicht → `csv.writer` quotet zwar, aber sobald irgendein Schritt dazwischen `splitlines()` macht (DutyPay-Side oder unser Delta-Loader), wandert eine Zeile in die nächste. Aktuell wird `bill_to.street` in DutyPay nicht ausgeben (alle BillingAddress-Felder leer), aber `_safe()` ist auch der Sanitizer für `transaction_id`, `invoice_no`, `target_vat_id`. Wenn JTL je VAT-IDs mit `\r\n` aus PowerShell-Imports zurückgibt, fliegt es.
- Aktuelles Verhalten: nur `;` ersetzt durch space, Zeilenumbrüche bleiben.
- Empfohlenes Verhalten: analog zu `datev._safe_text` `\n` und `\r` entfernen; Tab-Zeichen (kann CSV nicht verkraften, sobald Tab-Delimiter-Konsumenten dranhängen) ebenfalls.
- Fix:
  ```python
  def _safe(val: str | None) -> str:
      if not val:
          return ""
      return val.replace(";", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ").strip()
  ```
- Aufwand: <1h

- **F-4: SQL-Connection-URL kann mit Passwort in Stack-Traces landen**
- `src/jtl2datev/core/config.py:82-90`, `src/jtl2datev/core/db_jtl.py:640`
- Reproduktion: `make_engine(settings)` baut die URL. Wenn `create_engine` fehlschlägt (z.B. Treiber nicht gefunden), enthält der `ArgumentError`-Text die volle URL inklusive Passwort. SQLAlchemy maskiert das in `repr(engine.url)` → `***`, aber der String, den wir reingeben, nicht. CLI fängt mit `except Exception as exc: click.echo(f"Fehler: {exc}")` (`cli.py:1017, 1170, 794` etc.) — beim Verbose-Logging wird das in `--verbose` durchgereicht. Heute haben wir's selbst gesehen; nicht hypothetisch.
- Aktuelles Verhalten: Passwort kann in stderr/Logs landen.
- Empfohlenes Verhalten: Verwende `sqlalchemy.engine.URL.create(...)` mit benannten Komponenten (kein String-Bau) — SQLAlchemy maskiert dann automatisch in Fehlern. Außerdem im CLI: `except Exception as exc: click.echo(f"Fehler: {type(exc).__name__}")` und volltext nur bei `--verbose`. Logging-Konfig: `logging.Filter` auf den `engine`-Logger der das Passwort scrubbed.
- Fix:
  ```python
  from sqlalchemy.engine import URL
  url = URL.create(
      "mssql+pyodbc",
      username=settings.sql_username,
      password=pw,
      host=settings.sql_server,
      port=settings.sql_port,
      database=settings.sql_database,
      query={"driver": "ODBC Driver 18 for SQL Server", "TrustServerCertificate": "yes", "Encrypt": "yes"},
  )
  return create_engine(url, fast_executemany=True)
  ```
- Aufwand: 1-4h (inkl. Test, dass URL-Repr maskiert ist)

### WICHTIG

- **F-5: Connection-Pool ohne Pre-Ping / Recycle / Timeouts (15s-Hang heute)**
- `src/jtl2datev/core/db_jtl.py:637-640`
- Reproduktion: VPN/MSSQL kurz weg, Pool hat noch alte Connections cached → erster Query 15-60s blockiert.
- Aktuelles Verhalten: `create_engine(url, fast_executemany=True)` — Defaults: kein pre_ping, pool_recycle=-1, kein login_timeout/query_timeout.
- Empfohlenes Verhalten: `pool_pre_ping=True`, `pool_recycle=1800`, ODBC-Timeouts in der Connection-String (`Connect Timeout=10` als Query-Parameter, oder via `connect_args={"timeout": 10}`).
- Fix:
  ```python
  create_engine(
      url,
      fast_executemany=True,
      pool_pre_ping=True,
      pool_recycle=1800,
      connect_args={"timeout": 10},  # ODBC login timeout
  )
  ```
  Zusätzlich Query-Timeout via `conn.execution_options(stream_results=True, ..., timeout=300)` — jede `_fetch_*` Methode setzt sowieso schon execution_options.
- Aufwand: 1-4h (inkl. Test mit simuliertem Outage)

- **F-6: Engine-Lifecycle: Engines werden nie disposed → Connection-Leak bei wiederholten CLI-Aufrufen**
- `src/jtl2datev/cli.py:128, 269, 418, 629, 771, 907, 1167, 1395`
- Reproduktion: In einem Wrapper-Skript 10× hintereinander `jtl2datev export --month X`. Pro Run wird ein Engine-Objekt erzeugt, aber nie `engine.dispose()` aufgerufen. Bei kurzlebigem CLI-Prozess egal (OS reaped), bei späterer Web-Integration (Plan: FastAPI) wird das zur Leck-Quelle.
- Aktuelles Verhalten: kein dispose, kein context-manager.
- Empfohlenes Verhalten: Faktor `make_engine` als ContextManager, oder `try/finally: engine.dispose()` im CLI.
- Fix: Helper `with managed_engine(settings) as engine: ...` oder konsequent `try: ... finally: engine.dispose()`.
- Aufwand: 1-4h

- **F-7: BMF-CSV-Encoding hartcodiert auf ISO-8859-1**
- `src/jtl2datev/core/exchange_rates.py:115`
- Reproduktion: BMF wechselt — wie alle deutschen Behörden langfristig — auf UTF-8. Decoder schluckt das stillschweigend (ISO-8859-1 dekodiert jedes Byte), aber Mojibake bei Umlauten ("März" → "MÃ¤rz") führt zu nicht-erkanntem Monat → Spalte wird ignoriert → still falsche Importe.
- Aktuelles Verhalten: Spalte still verworfen, kein Fehler.
- Empfohlenes Verhalten: Encoding-Sniffing (BOM erkennen, dann UTF-8 versuchen, fallback ISO-8859-1) **oder** mindestens einen Sanity-Check: nach Parsen mindestens 4 Monatsspalten erwartet, sonst Fehler.
- Fix: Try-UTF-8-first, dann ISO-8859-1, plus Assert auf erwartete Spaltenzahl.
- Aufwand: 1-4h

- **F-8: Amazon-Report `utf-8-sig`: bei BOM-losem oder anderem Encoding stiller Datenverlust**
- `src/jtl2datev/core/verbringung_parser.py:62`
- Reproduktion: Amazon liefert mal eine TSV mit cp1252 (gelegentlicher Bug bei Region "EU"); `utf-8-sig` schmeißt UnicodeDecodeError. Aber: keine try/except — Operator sieht generischen Stack-Trace ohne Hinweis. Außerdem bei UTF-16-Little-Endian (was Amazon tatsächlich auch schon mal macht, bei deutschem Excel-Export) komplett unleserlich.
- Aktuelles Verhalten: UnicodeDecodeError durchgereicht, vom CLI als generisches `Fehler: ...`.
- Empfohlenes Verhalten: Encoding-Detection mit `chardet`/`charset-normalizer` (chardet ist transitive Abhängigkeit vermutlich schon vorhanden), oder mindestens fallback auf cp1252 + clearer Error-Message.
- Aufwand: 1-4h

- **F-9: Decimal-Overflow / Division durch 0 bei `currency_factor=0`**
- `src/jtl2datev/core/datev.py:308-319` (DATEV behandelt es korrekt mit Warning), `src/jtl2datev/core/db_jtl.py:395, 496, 609` (`_decimal(row["currency_factor"]) or Decimal("1")`)
- Reproduktion: JTL-Bug → currency_factor=0 in DB. `_decimal(0) or Decimal("1")` → `Decimal("1")` (weil `Decimal("0")` falsy ist), das ist ein **Silent-Recover**, der den Beleg in EUR umrechnet, obwohl er FX ist. DATEV-Pfad warnt zwar, aber DutyPay-Pfad nicht (`dutypay.py` greift nirgends auf currency_factor zu — das ist OK, weil DutyPay nur Currency-Code braucht, nicht den Faktor; trotzdem ist das `or Decimal("1")` ein Footgun).
- Aktuelles Verhalten: stiller Fallback auf 1.0 → falsche FX-Beträge im Export.
- Empfohlenes Verhalten: Wenn `currency != "EUR"` und `currency_factor` 0/None: Beleg als ERROR markieren, nicht stillschweigend auf 1 setzen.
- Fix: In `_fetch_*` explizit prüfen: `cf = _decimal(row["currency_factor"])`, falls `cf == 0` und currency != EUR → Warnung loggen, Beleg überspringen oder mit Marker exportieren.
- Aufwand: 1-4h

- **F-10: Pydantic-Validierung der CLI-`--month` zu spät / inkonsistent**
- `src/jtl2datev/cli.py:163-170`
- Reproduktion: `--month 2026-4` (single-digit) → `int("4")=4`, accepted, aber `_month_date_range` baut `dt.date(2026, 4, 1)` → Auto-Archive nutzt aber `month_str` als Dirname → archiviert unter `2026-4` nicht `2026-04`. Zwei verschiedene Ordner für denselben Monat. Wahrscheinlichkeit niedrig aber realistisch (Operator-Tippfehler).
- Aktuelles Verhalten: Akzeptiert "2026-4", landet im falschen Archiv-Ordner.
- Empfohlenes Verhalten: Strikt `re.fullmatch(r"\d{4}-\d{2}", month_str)` validieren.
- Aufwand: <1h

- **F-11: Strg+C beim Verbringung-Export hinterlässt tempfile-Leichen außerhalb von tempfile-NamedTemporary-Pfaden**
- `src/jtl2datev/cli.py:1410-1417`, `:1457-1461`
- Reproduktion: Im Verbringung-Pfad wird XLSX in tempfile, dann `shutil.copy2` → `effective_xlsx`. Bei Strg+C zwischen `format_verbringung_xlsx` und `shutil.copy2`: das tempfile wird per `try/finally` aufgeräumt (gut). Aber `effective_xlsx` ist parent-mkdir'd, und beim **nächsten** Run kann ein altes `verbringung_<oldts>.xlsx` daneben liegen (anderer Timestamp). Operator-Verwirrung. Außerdem: `effective_missing_ek.parent.mkdir(...)` wird nur ausgeführt wenn `missing_rows` truthy — bei leerer missing-Liste wird trotzdem in der Konsole ein Default-Pfad genannt, der nie geschrieben wurde.
- Aufwand: <1h

- **F-12: SQL-Connection: jeder `_fetch_*` öffnet eigene Connection statt Sharing**
- `src/jtl2datev/core/db_jtl.py:334, 438, 536` und `verbringung_pricing.py:230, 253, 303, 332, 362, 384, 481, 514`
- Reproduktion: Großer Run holt Pool-Connection 3× (own/external/credit_notes) statt 1× über einen `Session`-Scope. Bei Pool size=5 (default) noch egal, aber bei Web-Integration mit max_pool=20 und parallelen Calls → Pool starvation. **Aktuell kein BLOCKER**, aber der Lookup in `verbringung_pricing` hat bis zu 9 separate `engine.connect()` für **denselben** Aufruf — das ist messbar.
- Empfohlenes Verhalten: `with engine.connect() as conn:` einmal um die ganze `lookup_prices`-Funktion legen, dann alle Tier-Funktionen `conn` als Parameter.
- Aufwand: 1-4h

### NICE-TO-HAVE

- **F-13: `_BWARE_RE` matcht case-sensitive auf Hash-Teil**
- `src/jtl2datev/core/verbringung_pricing.py:44`
- Pattern `[A-Za-z0-9]{10,20}` plus Suffix `[A-Z0-9]{2}` — wenn Amazon je das Suffix in Lowercase liefert (sie haben das zu Marketplace-IDs schon variiert), Stem nicht matched, Fallback auf 0.10. Marginal.
- Aufwand: <1h

- **F-14: `derive_vat_rate` quantisiert auf 2 dp, was bei extremen Daten Rate verfälschen kann**
- `src/jtl2datev/core/db_jtl.py:275-292`
- Wenn JTL net=0.01, gross=0.02 → raw=100% → kein known_rate within 0.5% → `Decimal("100.00")` als rate. Wandert ins Engine. Wahrscheinlichkeit minimal (Belege mit 1-Cent-Beträgen sind selten und werden meist eh als Rundung erkannt).
- Aufwand: <1h

- **F-15: `archive.latest_archive` nutzt lexikographische Sortierung**
- `src/jtl2datev/core/archive.py:57`
- Funktioniert nur weil ts-Format `%Y-%m-%d_%H-%M-%S` lexikographisch=chronologisch ist. Wenn jemand mal manuell eine Datei `manual.csv` reinlegt, wird die fälschlich als latest gewählt, weil "manual" > "2026-..." in ASCII.
- Empfohlenes Verhalten: regex auf das ts-Format und `mtime` als Tiebreaker.
- Aufwand: <1h

- **F-16: Tests fehlen für Unicode-Edge-Cases**
- `tests/test_datev.py` testet keinen Beleg mit Emojis/CJK/Newlines im Buchungstext, kein `test_dutypay.py` mit `\n` in Adressen, kein `test_verbringung_parser` mit cp1252-encodiertem Report.
- Empfohlenes Verhalten: Hinzufügen — pro Format ein Test mit "Müller / 田中 🎉" als customer_name, mit `\n` in street, mit currency_factor=0.
- Aufwand: 1-4h

- **F-17: `compute_delta`-Loader liest Baseline komplett in den Speicher**
- `src/jtl2datev/core/dutypay_delta.py:31`, `datev_delta.py:47`
- Bei aktuell 14k Belegen kein Problem (~5MB), bei 50k+ wird's spürbar. Streaming wäre nicer, ist aber kein BLOCKER.
- Aufwand: >4h

- **F-18: PDF-Generierung mit reportlab default Helvetica unterstützt keine CJK / Emoji**
- `src/jtl2datev/core/verbringung_pdf.py`
- Wenn Operator je einen Artikel mit Emoji-Description hat, rendert reportlab ein "□". Stört bei Verbringungen kaum (Sender = wir selbst), aber sollte bewusst sein.
- Aufwand: 1-4h (TTF-Font-Embedding) — derzeit kein praktischer Bedarf.

- **F-19: `_safe_text` in DATEV ersetzt `;` durch space, aber `_to_cp1252` mit `errors="replace"` macht alle nicht-encodbaren Zeichen zu `?`**
- `src/jtl2datev/core/datev.py:240, 247`
- Konsistent, aber: Operator weiß nicht, **welche** Zeichen ersetzt wurden. Bei "Müller 北京" → "M?ller ??". DATEV akzeptiert das, aber für Audit/Reklamation hilft Logging.
- Empfohlenes Verhalten: Wenn `errors="replace"` etwas verändert hat, einmal pro Beleg WARN loggen.
- Aufwand: <1h

- **F-20: `parse_amazon_report` int-Cast für QTY ohne Schutz**
- `src/jtl2datev/core/verbringung_parser.py:82`
- `int(raw.get("QTY", "0").strip() or "0")` — wenn Amazon je `"1.0"` liefert → ValueError, kein Catch. Pro-aktiv Decimal→int.
- Aufwand: <1h

- **F-21: `parse_amazon_report` mit `qty=0` werden mitgenommen**
- `src/jtl2datev/core/verbringung_parser.py:82`
- Movement mit qty=0 erzeugt PDF-Zeile mit 0,00 EUR — semantisch sinnfrei, sollte gefiltert/geloggt werden.
- Aufwand: <1h

- **F-22: `_make_extf_header` hat `f"Belege {date_from.strftime('%Y/%m')}"` — Slash im Bezeichnungsfeld in Position 16; CSV-trennt mit `;` daher OK, aber DATEV-Spec verbietet Slashes in dem Feld**
- `src/jtl2datev/core/datev.py:275`
- Funktioniert mit unserem Importeur, aber nicht spec-konform.
- Aufwand: <1h

## Threat-Model für die wichtigsten Datenflüsse

```
JTL-MSSQL  ──[SELECT]──>  Repository  ──[Pydantic models]──>  Engine  ──[CSV/XLSX/PDF]──>  Tax-Authority
   ▲                          ▲                                                            ▲
   │ read-only ✓              │ NULL-handling, type-coercion                               │ encoding-traps
   │ (no DDL,                 │ ↑ F-9: cf=0 silently → 1                                  │ ↑ F-3, F-19
   │  no writes)              │ ↑ F-10: month-format
   │                          │
   │ ↑ F-4: pw in URL         │
   │ ↑ F-5: no pre-ping       │
   │ ↑ F-12: no shared conn   │
   ▼                          ▼
   Postman/Network            Disk
   ↑ F-5/15s-hang             ↑ F-1: non-atomic write
                              ↑ F-2: archive race
                              ↑ F-15: latest_archive lexsort
```

| Datenfluss | Bedrohung | Heute mitigiert? | Empfehlung |
|---|---|---|---|
| JTL-DB → Repo | Connection-loss mid-stream | Nein (kein retry, kein checkpoint) | tenacity-Retry um `_fetch_*`, Pre-Ping |
| Repo → Engine | NULL warehouse_country | Ja (skip + warn) | OK |
| Repo → Engine | currency_factor=0 | Teilweise (DATEV warnt, übernimmt 1) | F-9: hart abbrechen / als ERROR markieren |
| Engine → CSV (DATEV) | Encoding-Bomb | Ja (`errors="replace"` + `;`-Strip + `\n`-Strip) | F-19: zumindest loggen |
| Engine → CSV (DutyPay) | Encoding-Bomb | Teilweise (`;`-Strip) | F-3: `\n`/`\r`/`\t` ergänzen |
| CSV-File → Disk | Crash mid-write | Nein (DATEV direkt) | F-1: tmp+rename |
| Disk → Archive | Race in Sekunde | Nein | F-2: microsecond + collision-suffix |
| Archive → Delta | Korrupte Baseline | Nein | F-1 lösen, plus Hash-Check vor Delta |
| BMF-Web → JSON | Encoding/Layout-Wechsel | Teilweise | F-7: Sanity-Check Spaltenzahl |
| Amazon-TSV → Parser | Encoding-Wechsel | Nein | F-8: Auto-Detect |
| User-CLI → Engine | Pfad-Injection | Click validiert exists/dir_okay ✓ | OK |
| User-CLI → SQL | (nur --month → date) | Click DateTime ✓, F-10 nur month-format laxe | F-10: regex |
| Settings → Engine | PW in Stack-Trace | Nein | F-4: URL.create + scrub |

## Encoding-Edge-Cases

| Quelle | Behandlung | Robustheit | Risiko |
|---|---|---|---|
| MSSQL nvarchar → str | pyodbc default UTF-16 → Py-str | Hoch | Keine Auffälligkeit |
| DATEV-CSV write | cp1252, errors=replace, ;/\n/\r-Strip, 60-Zeichen-Limit | Hoch | F-19: kein Audit-Log der Replaces |
| DutyPay-CSV write | utf-8, nur ;-Strip | **Mittel** | F-3: \n/\r/\t fehlen |
| Taxually-XLSX write | openpyxl handhabt UTF-8 nativ | Hoch | F-18: PDF-Subroute hat Glyph-Problem |
| BMF-CSV read | iso-8859-1 hart | Niedrig | F-7: kaputt sobald BMF UTF-8 macht |
| Amazon-TSV read | utf-8-sig hart | Niedrig | F-8: anderes Encoding = Crash |
| DATEV-CSV read (compare-to) | cp1252 hart | Hoch | OK (eigenes Format) |
| exchange_rates.json | UTF-8 atomic | Sehr hoch | OK |
| PDF-render | Helvetica builtin | Niedrig | F-18: kein CJK/Emoji |

## Geprüfte Aspekte ohne Befund

- **SQL-Injection** in `db_jtl.py`, `preflight.py`, `verbringung_pricing.py`: alle WHERE-Klauseln verwenden `text()` mit `:param`-Binding bzw. `bindparam(..., expanding=True)`. Keine f-string-Konstruktion mit User-/DB-Werten gefunden. Die `mapping_table` / `artikel_table`-Parameter in `verbringung_pricing.lookup_prices` sind formal eine Code-Injection-Vector (`.format()` setzt sie direkt in den SQL-String), werden aber **nur intern und in Tests** mit konstanten Strings gefüllt — kein User-Pfad. Sollte als `Literal` oder Allowlist annotiert werden, ist aber kein BLOCKER.
- **JTL-DB write**: einzig `engine.connect()` plus `text(SELECT ...)`. Keine `INSERT`/`UPDATE`/`DELETE`/`EXEC`/`MERGE`. `execution_options(stream_results=True)` ist read-affirming.
- **Pydantic-Validation an Boundaries**: Models sind `frozen=True`, ConfigDict konsistent. CLI nutzt `click.DateTime` und `click.Path(exists=True)` — gut.
- **DATEV-CSV-Sicherheit**: `_safe_text` und `_sanitize_buchungstext` filtern `;`, `\n`, `\r` und encoden cp1252. 60-Zeichen-Limit fürs Buchungsfeld respektiert. CSV-writer mit QUOTE_MINIMAL — robust gegen einfache Quotes.
- **Atomares Schreiben in `exchange_rates.set_rate`**: tmp + `os.replace` — gut.
- **DutyPay/Taxually-Tempfile-Pattern in CLI**: `cli.export_dutypay_cmd`, `export_taxually_cmd` schreiben über tempfile, dann `shutil.copy2` ans Ziel — atomar genug. Nur DATEV-Pfad (`export_cmd` ohne tempfile) ist nicht so abgesichert.
- **Sensitive Daten in regulären Logs**: keine direkten `logger.info(password=...)`-Aufrufe. PII (Kundennamen, Adressen) wandert in Buchungstexte, aber nicht in Standard-Logs (nur in WARN-Pfaden mit Belegnummer + Kontext). Kein logger.info dumped einen ganzen RawInvoice — gut.
- **Postgres/MSSQL-spezifische Quoting**: alle Bezeichner sind static, Schema-Prefix `Rechnung.` und `dbo.` korrekt.
- **Pickle/eval/exec/subprocess**: keine Vorkommen im core/.
- **Click-Path-Validation**: `click.Path(exists=True, dir_okay=False)` für Input-Files (compare-to, baseline, report, csv) — Ja.

