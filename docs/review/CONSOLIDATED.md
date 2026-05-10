# Konsolidierter Review-Report

> Datum: 2026-05-09
> Konsolidiert aus: `tax-correctness.md`, `architecture.md`, `robustness.md`
> Branch: main, Commit: 3c332a7

## Executive Summary

Drei unabhängige Opus-Reviewer haben den Code aus den Perspektiven Tax-Compliance, Architektur und Robustheit untersucht. Die Reports kommen zu konsistenten Schlussfolgerungen:

- **Steuerlogik solide**, aber zwei BLOCKER (Marketplace-Facilitator-Erkennung lückenhaft, RO-Stichtag verifizierungsbedürftig) und ein kritischer Punkt zur SK-Strategie.
- **Architektur fundamental clean**, aber strukturelle Erosion durch CLI-Wachstum und Stammdaten-Duplikation. Repository-Pattern ist ein Skelett.
- **Robustheit gut bei SQL/Encoding (DATEV-Pfad)**, aber **drei ernste IO-Lücken**: nicht-atomare DATEV-Exports, Auto-Archive-Race, DutyPay sanitisiert keine Newlines/Tabs.

**Übergreifende Top-3-Prioritäten:**

1. **Atomic Writes für DATEV + Auto-Archive-Race** (Robustness F-1, F-2) — direkter Datenkorruption-Risiko bei Strg+C oder parallelen Runs. Doppel-Buchungs-Risiko über Delta-Pipeline.
2. **Marketplace-Facilitator-Logik** (Tax F-2, F-3) — eBay UK und Schweiz ab 2025 nicht erkannt, `gross==net`-Trigger ohne £135-Schwelle.
3. **DB-Connection-Lifecycle** (Robustness F-4, F-5, F-6) — Passwort-Leak-Risiko in Stack-Traces, kein pool_pre_ping erklärt heutigen 15s-Hang, kein engine.dispose().

Die Architektur-Refactorings (cli.py-Aufteilung, Repository-Erweiterung, reference_data.py) sind keine BLOCKER, aber strategisch wichtig **vor** der ERP-Migration.

## Cross-Cutting-Erkenntnisse

Mehrere Findings tauchen aus verschiedenen Perspektiven auf — das stärkt die Befunde:

| Thema | Tax | Arch | Robust |
|---|---|---|---|
| Stammdaten-Duplikation (EU-Liste, Country-Currency, OWN_VAT_IDS) | F-19 (SK) | **F-3** | — |
| `STANDARD_VAT_RATE` ohne Period-Validity | **F-7** | F-6 | — |
| `currency_factor=0` Fallback | — | — | **F-9** |
| CLI-Boilerplate vs. Service-Layer | — | **F-2** | F-6 (engine-lifecycle) |
| Default-Logging unterdrückt Warnings | — | F-9 | — |
| Tests für Reconcile-Severity unter-getestet | F-13 | **F-10** | F-16 |

## Master-Priorisierung (alle BLOCKER + WICHTIG-Findings)

### BLOCKER (zwingend vor Q2-Meldung)

| # | Quelle | Titel | Datei | Aufwand |
|---|---|---|---|---|
| **B-1** | Robust F-1 | Atomic Writes für DATEV-Export | `core/datev.py:389` | 1-4h |
| **B-2** | Robust F-2 | Auto-Archive-Race (Microsecond-TS + Collision-Suffix) | `core/archive.py:38,72` | <1h |
| **B-3** | Robust F-3 | DutyPay `_safe()` strippt keine Newlines/Tabs | `core/dutypay.py:284` | <1h |
| **B-4** | Robust F-4 | DB-Passwort kann in Stack-Traces landen | `core/config.py:82-90` | 1-4h |
| **B-5** | Tax F-1 | RO-21%-Stichtag verifizieren | `core/tax_engine.py:50` | <1h (Klärung) |
| **B-6** | Tax F-2 | MF-Erkennung für eBay UK + Schweiz ab 2025 | `core/tax_engine.py:144-168` | 1-4h |
| **B-7** | Tax F-3 | `gross==net`-MF-Trigger fragil (£135-Schwelle) | `core/tax_engine.py:154` | 1-4h |
| **B-8** | Tax F-4 | SRK-Logik ohne Cross-Check zur Master-RK | `core/db_jtl.py:587-617` | 1-4h |
| **B-9** | Arch F-1 | Repository-Interface zu schmal für ERP-Swap | `core/repositories.py` | 1-4h |

**Summe BLOCKER-Aufwand: ~1-2 Tage** (B-9 ist groß, kann aufgeschoben werden bis ERP-Migration näher rückt; alle anderen sollten in den nächsten 2 Sprints).

### WICHTIG

| # | Quelle | Titel | Aufwand |
|---|---|---|---|
| W-1 | Tax F-5 | XI (Nordirland) in Taxually-VAT-ID-Logik fehlt | <1h |
| W-2 | Tax F-7 | `STANDARD_VAT_RATE` ohne historisches Period-Mapping | 1-4h |
| W-3 | Tax F-8 | `looks_like_valid_vat_id` ohne Längen-/Prüfziffer-/VIES-Check | >4h |
| W-4 | Tax F-9 | DOMESTIC + vat_id + 0% bucht §13b blind (für DE-eCommerce falsch) | 1-4h |
| W-5 | Tax F-10 | DutyPay `is_credit_note` vs. Vorzeichen-Check | <1h |
| W-6 | Tax F-11 | Verbringungs-PDF: §10 Abs.4 UStG-Hinweis im Footer | 1-4h |
| W-7 | Tax F-12 | §16 Abs.6-Hinweis (Monatsmittel) im Verbringungs-PDF | <1h |
| W-8 | Tax F-13 | Reconcile: Cent-Toleranz für Rounding | <1h |
| W-9 | Robust F-5 | `pool_pre_ping`, `pool_recycle`, ODBC-Timeouts | 1-4h |
| W-10 | Robust F-6 | `engine.dispose()` / Context-Manager | 1-4h |
| W-11 | Robust F-7 | BMF-CSV-Encoding-Detection | 1-4h |
| W-12 | Robust F-8 | Amazon-Report-Encoding-Detection | 1-4h |
| W-13 | Robust F-9 | `currency_factor=0` Silent-Fallback | 1-4h |
| W-14 | Robust F-10 | `--month YYYY-M` Validierung strikt | <1h |
| W-15 | Robust F-12 | Connection-Sharing in `lookup_prices` | 1-4h |
| W-16 | Arch F-2 | CLI in `cli/`-Package + Service-Layer | groß (1-2 Tage) |
| W-17 | Arch F-3 | `core/reference_data.py` (EU/Currency/Platform) | 1-4h |
| W-18 | Arch F-4 | `RawInvoiceLine`-Cleanup | 1-4h |
| W-19 | Arch F-5 | `pipeline.py` umbenennen oder ausbauen | mit W-16 |
| W-20 | Arch F-6 | Settings-Coverage (`_DOMESTIC_MAP`, `_MIN_DATE`, VAT-Rates) | 1-4h |
| W-21 | Arch F-7 | DATEV `_build_row` → `BuchungsRow`-Dataclass | 1-4h |

## Empfohlene Umsetzungsreihenfolge

### Sprint A — IO-Sicherheit (1 Tag)

Quick Wins mit großem Risiko-Reduktions-Impact, alle kompatibel:

1. **B-2** Microsecond-Timestamps in archive.py (<1h)
2. **B-3** DutyPay `_safe()` mit Newline/Tab-Strip (<1h)
3. **B-1** Atomic Writes für DATEV via tempfile+rename (1-4h)
4. **W-9** `pool_pre_ping=True`, `pool_recycle=1800`, ODBC-Timeout (1-4h)
5. **B-4** `URL.create()` statt String-Bau für Connection-URL (1-4h)

→ Nach Sprint A: keine korrupten Dateien mehr möglich, kein Passwort-Leak, kein 15s-Hang. Datenintegrität für Q2-Meldung gesichert.

### Sprint B — Steuer-Korrektheit (2-3 Tage)

Vor der nächsten Marketplace-Meldung mit UK-/CH-Belegen:

1. **B-5** Mit StB klären: RO-Stichtag 01.08.2025 vs 01.01.2026 (User-Aufgabe)
2. **B-6** MF-Erkennung erweitern (eBay UK alle Plattformen, CH ab 01.01.2025)
3. **B-7** `gross==net`-Trigger sekundieren (Marketplace-Order-ID + £135-Schwelle)
4. **W-1** XI in Taxually-VAT-ID-Logik
5. **W-4** DOMESTIC + vat_id + 0% mit DE-Sonderfall (kein automatisches §13b)
6. **W-8** Cent-Toleranz im Reconcile
7. **W-13** `currency_factor=0` ERROR statt Silent-Fallback
8. **B-8** SRK-Cross-Check zur Master-RK (kann nach hinten rutschen wenn keine SRK in April)

### Sprint C — Architektur-Hygiene (2-3 Tage, vor ERP-Migration)

Strukturell wichtig, aber nicht akut:

1. **W-17** `core/reference_data.py` zentralisieren (1-4h, Quick Win)
2. **W-18** `RawInvoiceLine`-Cleanup (1-4h, war eh in next-session.md geplant)
3. **W-20** Settings-Coverage erweitern (1-4h)
4. **B-9** + **W-16** + **W-19**: CLI-Aufteilung + Service-Layer + Repository-Erweiterung (groß, 1-2 Tage)
5. **W-21** DATEV `BuchungsRow`-Dataclass (1-4h)

### Sprint D — Compliance-Polish (parallel oder später)

1. **W-2** Period-Validity für VAT-Rates (1-4h, schmerzhaft erst bei Re-Exports älterer Monate)
2. **W-3** VAT-ID-Validierung mit VIES-Cache (>4h, langfristig)
3. **W-6, W-7** Verbringungs-PDF-Hinweise (Steuerbergater-Klärung)
4. **W-11, W-12** Encoding-Detection für externe CSVs/TSVs
5. **W-14** `--month` Strikt-Regex
6. **W-10, W-15** Engine-Lifecycle / Connection-Sharing

## Konflikte zwischen Reviewern

Keine inhaltlichen Konflikte. Der Architekt empfiehlt Default-Logging zurück auf WARNING (F-9), der User hat das gestern Abend bewusst auf ERROR umgestellt — pragmatischer Mittelweg: in Sprint A `make_engine` aufräumen, dann sind die "Unknown platform"-WARNINGs eh seltener. Das Logging-Default kann dann entspannt nach WARNING zurück.

## Aufgaben für den User (nicht Code)

- **B-5** (RO-Stichtag): Steuerberater fragen oder im Online-Datenportal des BMF nachprüfen, ab welchem Datum 21% gilt. Ein einziger Belegfall in Q3/Q4 2025 reicht zur Verifikation.
- **W-6, W-7** (Verbringungs-PDF-Footer): Steuerberater-Freigabe für Bewertungsmethode B-Ware (10% Listenpreis, Floor 0,01 €, Fallback 0,10 €) dokumentieren, dann im PDF-Footer zitieren.
- **F-19 SK-Sonderfall**: Periodisch prüfen, ob Belege mit `warehouse_country=SK AND treatment IN (DOMESTIC, OSS_B2C)` auftauchen. Falls ja: SK-Registrierung erwägen.

## Geprüft und in Ordnung (Auswahl, alle drei Reviewer)

- 27 EU-Mitgliedstaaten in `EU_COUNTRIES` korrekt
- 26 von 27 VAT-Standardsätzen verifiziert (außer RO mit Verifikations-Bedarf)
- DATEV-EXTF-Format spec-konform (124 Spalten, Format 12, v7.0, cp1252, CRLF)
- Fremdwährungs-Felder (WKZ Umsatz/Kurs/Basis-Umsatz) korrekt
- DutyPay-Sign-Konvention via `abs()`+Refund-Wrapper double-negation-sicher
- Pro-Forma-PDFs zitieren §4 Nr.1b UStG i.V.m. §6a Abs.2 UStG korrekt
- Alle SQL-Queries parametrisiert (kein f-string-Injection-Risiko)
- DB strikt SELECT-only (keine DDL/INSERT/UPDATE/DELETE)
- Pydantic-Models `frozen=True`, durchgängig
- DATEV-CSV-Encoding-Sanitizer (cp1252+errors=replace, ;/\n/\r-Strip, 60-Zeichen-Limit) solide
- `exchange_rates.json` atomic-write korrekt
- BMF-Monatsmittelkurse §16 Abs.6 UStG-konform
- `core/` ist tatsächlich framework-agnostisch (kein print, kein click, kein sys.argv)
- Iterator-Streaming für große Datumsbereiche aktiv
- Repository-Pattern strukturell korrekt (DI über Konstruktor)

## Nächste Schritte

1. Diesen Bericht morgen früh durchgehen und Sprint A freigeben.
2. Sprint A komplett vor Q2-Meldung umsetzen.
3. Sprint B mit Steuerberater-Abstimmung für die User-Aufgaben verzahnen.
4. Sprint C terminieren in Abhängigkeit vom ERP-Migrations-Zeitplan.
5. Sprint D als laufende Hygiene-Aufgaben in `next-session.md` aufnehmen.

Die drei Detail-Reports (`tax-correctness.md`, `architecture.md`, `robustness.md`) bleiben als Referenz bestehen — dieser Bericht ist die Zusammenfassung mit Master-Priorität.
