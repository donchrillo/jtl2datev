# Amazon-Verbringungen (FBA-Lagerbewegungen)

> **Stand:** 2026-05-08  
> Dokumentiert Exports von innergemeinschaftlichen Lagerbewegungen
> (Amazon-FBA Transfers + Inbound-Lagergänge). Q1-2026 Verbringungs-SKUs: 0 unresolved (vorher 148).

## Fachlicher Hintergrund

Innergemeinschaftliche Verbringungen sind steuerfreie Lieferungen von Waren zwischen Lagerorten in verschiedenen EU-Ländern. Sie unterliegen nicht der lokalen USt des Empfänger-Landes, sondern einer Meldepflicht in der Gelangensanzeige (§ 4 Nr. 1b UStG i.V.m. § 6a Abs. 2 UStG / Art. 17 i.c.w. Art. 138 EU-Directive 2006/112/EC).

Amazon betreibt FBA-Lager in DE, PL, CZ, IT, FR, ES, GB. Waren-Transfers zwischen diesen Lagern sowie Inbound-Transporte zu neuen FBA-Lagern müssen steuerfrei abgerechnet werden.

**Datenquelle:** Amazon stellt monatlich einen Transactional Report bereit (TXT, tab-separated, ~95 Spalten), am 3. des Folgemonats erstellt, mit allen Lagerbewegungen des Berichtsmonats.

## Beleg-Kategorisierung aus dem Amazon-Report

| Transaction-Type | Bedeutung | Verbringung? | Q1-Zeilen |
|---|---|---|---|
| `FC_TRANSFER` | Lager-zu-Lager-Transfer | ✓ Ja | 3.004 |
| `INBOUND` | Eigenversand Hünxe → FBA-Lager | ✓ Ja | 15 |
| `SALE` | Verkauf an Endkunde | ✗ Nein | — |
| `REFUND` | Kundenrückgabe | ✗ Nein | — |
| `RETURN` | Retourversand zum Sender | ✗ Nein (Sonderfall) | — |
| `LIQUIDATION` | Bestandsabverkauf | ✗ Nein | — |
| `DONATION` | Spendenversand | ✗ Nein | — |

**Filter:** Nur `FC_TRANSFER` + `INBOUND` werden exportiert. Alle übrigen Transaktionstypen ignoriert.

**Rücksendungen Amazon → Hünxe (User-Lager):** Werden im Amazon-Transactional-Report grundsätzlich **nicht erfasst** — weder die automatischen Removals (alle 14 Tage) noch manuelle Rückforderungen erscheinen darin. Der `is_return_to_user`-Marker (ARRIVAL_POST_CODE = 46569) ist im Code als Vorsichtsmaßnahme vorhanden, in Q1 2026 wurde keine solche Zeile gefunden — erwartungsgemäß null Treffer.

## CLI-Spec

```
jtl2datev export-verbringung
    --report <amazon.txt>           # Pflicht: Amazon Transactional Report (TXT, tab-separated)
    --month YYYY-MM                  # Pflicht: Berichtsmonat für PFR-Nummerierung + Auto-Archive
    [--out-xlsx file.xlsx]          # Optional: Taxually-XLSX-Export. Default: Auto-Archive
    [--out-pdf-dir dir/]            # Optional: Pro-Forma-Rechnungen (PDF). Default: Auto-Archive
    [--out-missing-ek file.csv]     # Optional: Fehler-Log SKUs ohne EK-Preis. Default: Auto-Archive
    [--strict]                       # Optional: bei fehlendem Wechselkurs abbrechen (CI-Mode).
                                     # Default ohne --strict: interaktiv nachfragen + speichern.
```

**Beispiel:**
```bash
jtl2datev export-verbringung \
    --report samples/verbringungen/3871700020495.txt \
    --month 2026-01
```

**Auto-Archive (Standard, falls keine `--out-*` angegeben):**
```
exports/verbringung/<YYYY-MM>/
    ├── verbringung_<TIMESTAMP>.xlsx     # Taxually-Format (20 Spalten)
    ├── pdfs/
    │   ├── PFR26-01-0001.pdf           # Pro-Forma-Rechnung Route 1
    │   ├── PFR26-01-0002.pdf           # Pro-Forma-Rechnung Route 2
    │   └── ...
    └── missing_ek_<TIMESTAMP>.csv      # SKUs ohne EK-Preis
```

## XLSX-Export: Taxually-Format

Identisches Format wie regulärer `export-taxually`, 20 Spalten, Sheet „Your data":

| Spalte | Wert |
|---|---|
| Transaction type | `"Inventory transfer"` für `FC_TRANSFER`, `"Sales"` für `INBOUND` (mit Taxually-Convention) |
| Subject of the transaction | `"Goods"` |
| Sales channel | leer |
| VAT number | Eigene VAT-ID des Departure-Landes (aus `OWN_VAT_IDS_VERBRINGUNG`) |
| Transaction date | `depart_date` für FC_TRANSFER, `complete_date` für INBOUND (YYYY-MM-DD) |
| Invoice number | `TRANSACTION_EVENT_ID[:30]` (gekürzt für Eindeutigkeit) |
| Departure country | Lager-Land (ISO2-Code) |
| Customer's country | Zielland (ISO2-Code) |
| Currency | `"EUR"` |
| Gross amount | `qty × ek_netto` (Netto-EK × Menge, positiv, Dezimaltrennzeichen: Punkt) |
| Columns 11–20 (VAT fields, Net, Local) | leer (Taxually rechnet selbst) |

**Dezimalformat:** Punkt (englisch), nicht Komma. Zahlen roh (nicht gerundet).

## PDF-Export: Pro-Forma-Rechnung

Eine PDF pro Routen-Paar (Departure-Land → Arrival-Land) für die Berichtsperiode.

**Struktur pro PDF:**
- **Header:** ToCi-Adresse + Ausstellungsdatum (letzter Tag der Periode, z.B. 2026-01-31)
- **Beteiligter Parteien:**
  - Verkäufer: eigene Firma + VAT-ID (Departure-Land)
  - Käufer: Amazon EU / Lagerstandort + VAT-ID (Arrival-Land) — falls vorhanden
- **Fachliche Absätze:** Freitextblock zur Erklärung der steuerfreien innergemeinschaftlichen Verbringung (§4 Nr.1b. UStG i.V.m. § 6a Abs. 2 UStG / Art. 17 i.c.w. Art. 138 EU-Directive 2006/112/EC)
- **Tabelle:** Artikel-Nr., Warenbezeichnung, Menge, EK-Netto je Stk., Summe (EUR)
- **Währungs-Footer:** Summen pro Währung falls nicht-EUR-Zielland vorhanden (z.B. GBP für GB-Transfer)

**Datei-Naming:** `PFR{YY}-{MM}-{NNNN}.pdf`  
- `{YY}` = 2-stelliges Jahr (26 für 2026)
- `{MM}` = 2-stelliger Monat (01–12)
- `{NNNN}` = 4-stellige Nummer pro Route, nach alphabetischer Sortierung von `DEPARTURE_COUNTRY-ARRIVAL_COUNTRY`

**Routing-Sortierung (Q1-Beispiele):**
- `CZ-DE`, `CZ-ES`, `CZ-FR`, `CZ-IT`, `CZ-PL`, … (Routen alphabetisch nach DEP-ARR)
- Nummerierung: `0001`, `0002`, … pro Berichtsmonat

## SKU-Mapping: 6-Tier-Lookup

Amazon-`SELLER_SKU` aus dem Transactional Report werden gegen JTL-Artikel-Datenbank gemappt. Zwei neue Tiers (5 + 6) addressieren B-Ware und ASIN-Lookups — Q1-2026 jetzt 100% Coverage (0 unresolved).

**Lookup-Reihenfolge (höher = Vorrang):**

| Tier | Strategie | Quelle | matched_via | Q1-Treffer |
|------|-----------|--------|-------------|------------|
| 1 | Direct: SKU exakt in `pf_amazon_angebot_mapping.cSellerSKU` | `pf_amazon_angebot_mapping` → `tArtikel.kArtikel` | `"direct"` | 235 |
| 2 | FBA/MFN-Suffix strippen (z.B. `-FBA`, `-MFN`), dann Tier-1 | `pf_amazon_angebot_mapping` | `"fba"` | 0 |
| 3 | Direct: SKU als `tArtikel.cArtNr` (case-insensitive) | `tArtikel` | `"tArtikel-direct"` | 1 |
| 4 | amzn.gr.-Stem: sukzessiv 1–3 Dash-Segmente entfernen, dann Tier-1 | `pf_amazon_angebot_mapping` | `"amzn"` | 61 |
| 5a | B-Ware-Stem (Regex): Stem in Mapping | `pf_amazon_angebot_mapping` | `"bware-stem"` | 129 |
| 5b | B-Ware-Stem: Stem direkt in `tArtikel.cArtNr` | `tArtikel` | `"bware-stem"` | (in 129) |
| 5-fallback | B-Ware ohne Match: pauschal 0,10 € | — | `"bware-fallback"` | 27 |
| 6a | ASIN → `tArtikel.cASIN` direkt (altes Listing) | `tArtikel` | `"asin-tartikel"` | 16 |
| 6b | ASIN → `pf_amazon_angebot.cASIN1` → aktuell SKU → Mapping/tArtikel | `pf_amazon_angebot` | `"asin-angebot"` | 54 |
| — | Unresolvable | — | `None` | 0 |

**Reihenfolge-Diagramm (vereinfacht):**

```
SELLER_SKU
  ├─ Tier 1: exakt Mapping? → Treffer
  ├─ Tier 2: minus Suffix → Mapping? → Treffer
  ├─ Tier 3: tArtikel.cArtNr? → Treffer
  ├─ Tier 4: amzn.gr.-Stem-Extract → Mapping? → Treffer
  │
  ├─ [amzn.gr.* SKU erkannt?]
  │   ├─ Tier 5a: Stem-Regex → Mapping? → 10% EK (mit Audit-Flag)
  │   ├─ Tier 5b: Stem → tArtikel.cArtNr? → 10% EK (mit Audit-Flag)
  │   ├─ Tier 6: ASIN vorhanden? → tArtikel.cASIN / pf_amazon_angebot.cASIN1? → voller EK (mit Audit-Flag)
  │   └─ Fallback: → 0,10 € pauschal
  │
  └─ [nicht B-Ware]
      ├─ Tier 6a: ASIN → tArtikel.cASIN? → Treffer
      ├─ Tier 6b: ASIN → pf_amazon_angebot.cASIN1? → Treffer
      └─ Unresolved → None
```

### B-Ware-Behandlung

**SKU-Pattern:** `amzn.gr.<UNSER_SKU>-<HASH>-<SUFFIX>`  
Beispiel: `amzn.gr.2021451277-4-gLdqx3olTjVpVZOl-PO`

**Stem-Extraktion (Regex `_BWARE_RE`):**  
Hash ist 10–20 Zeichen alphanumerisch; Suffix 2 Zeichen `[A-Z0-9]`. Der Stem ist alles bis zum Hash, also `<UNSER_SKU>-<kurze_Prä>`.

**Bewertungsregel (User-bestätigt 2026-05-08):**

| Fall | Beschreibung | EK-Betrag | Flag |
|------|---|---|---|
| Tier 5a Match | Stem in `pf_amazon_angebot_mapping` → `tArtikel` gefunden | 10 % vom `fEKNetto` des Stem-Artikels (Floor 0,01 €) | `is_bware=True` |
| Tier 5b Match | Stem als `tArtikel.cArtNr` (case-insensitive) → gefunden | 10 % vom `fEKNetto` des Artikels (Floor 0,01 €) | `is_bware=True` |
| Tier 6 Match | ASIN-Lookup erfolgreich (Tier 6a/6b) | voller `fEKNetto` des aktuellen Amazon-Listings | `is_bware=True`, `bware_pricing_basis=` Stem-EK |
| Kein Match | SKU in keiner Quelle → Fallback | pauschal 0,10 € | `is_bware=True` |

**Konfiguration in `core/config.py`:**

```python
bware_pricing_strategy: Literal["ten_percent", "flat_10ct"] = "ten_percent"  # default
bware_flat_price: Decimal = Decimal("0.10")
bware_percentage: Decimal = Decimal("0.10")  # 10 %
```

**CLI-Override:**  
```bash
jtl2datev export-verbringung --report ... --month 2026-01 --bware-pricing-strategy flat_10ct
```

Bei `flat_10ct` werden Tier 5/6 komplett übersprungen; alle `amzn.gr.*`-SKUs bekommen direkt 0,10 €.

**PDF-Marker:**  
Artikel-Beschreibung bekommt Suffix `(B-Ware)` wenn `is_bware=True`.

**Output `bware_summary_<timestamp>.csv`:**  
Listet alle B-Ware-Bewegungen pro Periode zur Sichtprüfung:

| Spalte | Bedeutung |
|--------|-----------|
| `seller_sku` | Original-SKU aus Report |
| `stem` | Extrahierter Stem |
| `qty_total` | Gesamtmenge über Periode |
| `movements` | Anzahl Bewegungen |
| `ek_basis` | Basis-EK des Stem-Artikels (falls Match) |
| `ek_used` | Tatsächlich verwendeter EK (10% oder Fallback) |
| `source` | Tier-Treffer (bware-stem / asin-tartikel / asin-angebot / bware-fallback) |

**`missing_ek_*.csv`:**  
B-Ware-SKUs sind ausgeschlossen (jetzt alle bewertet).

**PricingResult-Erweiterung:**

```python
@dataclass
class PricingResult:
    matched_via: str | None
    ek_netto: Decimal
    is_bware: bool = False
    bware_pricing_basis: Decimal | None = None  # voller EK des Stem-Artikels (für Audit)
```

### ASIN-Lookup (Tier 6)

Für SKUs, die Tiers 1–4 nicht aufgelöst haben (alte SKUs früherer Amazon-Listings, deren ASIN aber noch existiert).

**Schema-Findings (verifiziert 2026-05-08):**

- `pf_amazon_angebot_fba` hat **keine** `cASIN`-Spalte → Fallout als ASIN-Lookup-Quelle
- `tArtikel.cASIN` existiert direkt → Preferred Source
- `pf_amazon_angebot` hat `cASIN1`, `cASIN2`, `cASIN3` (üblicherweise nur `cASIN1` befüllt)

**Tier 6a:** `tArtikel.cASIN = movement.asin` → kArtikel + EK

**Tier 6b:** `pf_amazon_angebot.cASIN1 = movement.asin` → aktuell zugehörige `cSellerSKU` → durch Tier-1 (mapping) + Tier-3 (tArtikel) geschickt

**Position in der Reihenfolge:**
- Bei `amzn.gr.*`-SKUs (B-Ware): nach 5a/5b, vor Bware-Fallback. Tier-6-Treffer = voller EK, `is_bware=True`.
- Bei normalen SKUs: nach Tier 1–4, vor unresolved.

**API-Erweiterung:**

```python
def lookup_prices(
    skus: list[str],
    engine: Engine,
    bware_strategy: str = "ten_percent",
    asin_by_sku: dict[str, str] | None = None,  # NEU
) -> dict[str, PricingResult]: ...
```

`asin_by_sku=None` → Tier 6 wird übersprungen (Backward-Kompatibilität). CLI baut Dict aus `MovementRow.asin` auf.

### Q1-2026-Statistik nach Tier-6-Erweiterung

| Monat | Tier 1 (direct) | Tier 2 (fba) | Tier 3 (art) | Tier 4 (amzn) | Tier 5 (bware-stem/fb) | Tier 6 (asin-t/a) | unresolved |
|-------|-------:|-------:|-------:|-------:|-------:|-------:|-------:|
| JAN | 81 | 0 | 0 | 39 | 92 (69+23) | 49 (14+35) | 0 |
| FEB | 77 | 0 | 0 | 12 | 33 (32+1) | 11 (2+9) | 0 |
| MAR | 77 | 0 | 1 | 10 | 31 (28+3) | 10 (0+10) | 0 |
| **Q1 total** | **235** | **0** | **1** | **61** | **156 (129+27)** | **70 (16+54)** | **0** |
| **% des Gesamts (523)** | **44,9%** | **0%** | **0,2%** | **11,7%** | **29,8%** | **13,4%** | **0%** |

**Vorher (nur Tier 1–4):** 148 unresolved (22 % von 673 Unique SKUs).  
**Nachher (mit Tier 5+6):** 0 unresolved (100 % Coverage).

## EK-Preis-Quelle

Pro gemap­pter SKU wird der JTL-Netto-EK gelesen:

| Feld | Quelle | Fallback |
|------|--------|----------|
| `fEKNetto` | `dbo.tArtikel.fEKNetto` (aktueller Netto-EK) | Wenn `= 0`, dann `fLetzterEK` |
| **HINWEIS** | Wenn auch Fallback `= 0`: SKU in `missing_ek_*.csv` gelistet | — |

**Beschreibung:** Aus `dbo.tArtikelBeschreibung` (Spalten `cName`, mit Filtern `kSprache=1`, `kPlattform=1` — deutsch, Amazon-Plattform).

## Konfiguration: VAT-IDs und Wechselkurse

### `OWN_VAT_IDS_VERBRINGUNG` in `core/config.py`

```python
OWN_VAT_IDS_VERBRINGUNG: dict[str, str] = {
    "DE": "DE249030238",
    "GB": "GB242492315",
    "FR": "FR54820509628",
    "IT": "IT00185379997",
    "PL": "PL5263144779",
    "CZ": "CZ683736606",
    "ES": "ESN2765131D",
    # SK: keine VAT-Registrierung
}
```

**Sonderfall SK (Slowakei):** Keine VAT-Registrierung notwendig. Das slowakische Amazon-Lager ist ein reines **Retourenlager** — Endkunden senden Retouren dorthin, die anschließend auf andere FBA-Lager verteilt werden. Es finden weder Verkäufe noch Versendungen an Endkunden ab SK statt → keine Steuerpflicht. Bei FC_TRANSFER mit Departure=SK bleibt die VAT number-Spalte im Output leer.

### Wechselkurse: BMF-Import + JSON-Storage

**Speicherung:** `data/exchange_rates.json` (gitversioniert, später migrierbar zu SQL).

**Schema:**
```json
{
  "YYYY-MM": {
    "CCY": {"value": "1,2345", "source": "BMF"|"manual"}
  }
}
```

**BMF-Datenquelle (monatlich aktualisiert):**
- URL-Muster: `https://www.bundesfinanzministerium.de/Datenportal/Daten/offene-daten/steuern-zoelle/umsatzsteuer-umrechnungskurse/datensaetze/uu-kurse-{YEAR}-csv.csv?__blob=publicationFile`
- Format: CSV, Encoding ISO-8859-1, Trennzeichen Semikolon
- Alle 48 EU/EWR-Länder + weitere Währungen (z.B. Tschechien 24,278 EUR/CZK Jan 2026)

**Import-Command:**
```bash
jtl2datev import-rates [--year YYYY] [--csv PATH]
```
Lädt oder aktualisiert Kurse aus BMF-CSV. Bestehende `source=BMF`-Werte werden überschrieben, `source=manual`-Werte bleiben erhalten (User-Input hat Vorrang).

**Interaktiver Modus (Default):**
Wenn ein Kurs für eine Route fehlt, fragt das CLI nach:
```
Wechselkurs für 2026-01 fehlt: CZK
Quelle BMF: https://www.bundesfinanzministerium.de/...
1 EUR = ? CZK (Enter zum Abbruch):
```
Eingabe wird als `source="manual"` gespeichert.

**Strict-Mode für CI/Automation:**
```bash
jtl2datev export-verbringung --report ... --month 2026-01 --strict
```
Bricht ab wenn Kurs fehlt (keine Interaktion).

**Q1-2026 BMF-Kurse (initial importiert, 116 Kurse):**

| Währung | Jan | Feb | Mär |
|---------|-----|-----|-----|
| PLN | 4,2127 | 4,2184 | 4,2715 |
| CZK | 24,278 | 24,260 | 24,438 |
| GBP | 0,86828 | 0,87032 | 0,86631 |
| (weitere: SEK, DKK, RON, HUF, USD etc.) | — | — | — |

## Kein Delta-Command

Anders als bei DATEV/DutyPay/Taxually gibt es **kein** `export-verbringung-delta`. Begründung: Amazon erstellt den Transactional Report final am 3. des Folgemonats. Nachträglich hinzukommende Transaktionen im gleichen Berichtsmonat sind ausgeschlossen — der Bericht ist ein Snapshot.

**Neurun:** Um nachgelagerte Transaktionen zu erfassen, wäre ein neuer Bericht (neuer Monat) erforderlich. Dann mit `--month` neu exportieren, nicht delta.

## Live-Run Q1-2026

Verifizierung gegen Sample-Reports aus `samples/verbringungen/`:

| Monat | Report | FC_TRANSFER | INBOUND | XLSX-Zeilen | Routen/PDFs | Unique SKUs |
|-------|--------|-------------|---------|-------------|-------------|-------------|
| JAN | 3871700020495.txt | 1.231 | 10 | 1.241 | 30 | 347 |
| FEB | 3919876020521.txt | 801 | 3 | 804 | 25 | 289 |
| MAR | 3968288020550.txt | 972 | 2 | 974 | 27 | 302 |

**Match-Kriterium:** Zeilenzahl XLSX = Zeilenzahl Report (FC_TRANSFER + INBOUND). Bestätigt 1:1.

**PDF-Verifikation:** Anzahl PDFs pro Monat = Anzahl distinct (DEPARTURE_COUNTRY, ARRIVAL_COUNTRY)-Paare. Bestätigt 1:1.

**EK-Preis-Verifikation:** 100% der gemappt­en SKUs haben EK-Netto > 0. Ungemappte SKUs gelistet in `missing_ek_*.csv` (keine Fehlerbehandlung erforderlich — Export dennoch vollständig).

## Module (implementiert 2026-05-07)

| Modul | Inhalt |
|-------|--------|
| `core/verbringung_parser.py` | Amazon-TXT-Parser (tab-separated, ~95 Spalten). Filter FC_TRANSFER + INBOUND. |
| `core/verbringung_pricing.py` | SKU-Mapping (4-Tier-Lookup), EK-Preis-Lookup, Beschreibungs-Join |
| `core/verbringung_taxually.py` | XLSX-Generator (20 Spalten, openpyxl, identisch zu Taxually-Format) |
| `core/verbringung_pdf.py` | Pro-Forma-PDF (reportlab), Header + Absätze + Tabelle + Summen |
| `cli.py` (erweitert) | `export-verbringung`-Command |

## Tests

**Test-Stand:** 418 passed, 3 skipped (nach Tier-5+6-Erweiterung).

## Offene Punkte für Nachpflege

(Keine — Q1-2026 100 % Verbringungs-SKU-Coverage erreicht.)

## Verweise

- Konfiguration: `docs/db-schema.md` (6-Tier-Lookup-Strategie, Schema `pf_amazon_angebot_mapping`, `tArtikel`, `tArtikelBeschreibung`, `pf_amazon_angebot`, B-Ware-Befunde)
- Architektur: `docs/architecture.md` (Module `verbringung_pricing.py` mit B-Ware + ASIN-Support)
- Status: `docs/status.md` (2026-05-08 — Tier 5+6: B-Ware + ASIN-Lookup)
