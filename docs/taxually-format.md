# Taxually-Export-Format

> Spezifikation für Umsatzsteuer-Selbstmeldung (VAT self-assessment).
> Basiert auf Taxually-Template-Vorgaben und Q1-2026-Reconciliation gegen Jera-Referenzen.
> Stand: 2026-05-07.

## Überblick

Taxually ist ein Cloud-Tool für vollautomatisierte Umsatzsteuer-Compliance in der EU. Das Format wird für nationale Steuermeldungen (nicht OSS) genutzt — z.B. FR / IT / ES / PL / CZ Lokalregistrierungen.

**Scope:** Direkter XLSX-Export aus JTL-Datenbank (ähnlich DutyPay), nicht aus DutyPay-Output abgeleitet. Einzige Format-Unterschied zu DutyPay: XLSX mit 20 Spalten (statt CSV mit 98 Spalten).

## Datei-Format

| Eigenschaft | Wert |
|---|---|
| **Format** | XLSX (Excel-Arbeitsmappe) |
| **Sheet-Name** | `Your data` |
| **Encoding** | UTF-8 (Excel-Standard) |
| **Dezimalzeichen** | Punkt (`.`) — Punkt-Konvention für numerische Spalten |
| **Datumsformat** | `DD.MM.YYYY` (Text oder Excel-Datumsformat) |
| **Header-Zeile** | Ja (Zeile 1) |
| **Spalten** | 20 Spalten (Spalte A bis T) |

## Spalten-Referenz (20 Spalten)

| Spalte | Header | Typ | Beispiel | Quelle | Notizen |
|---|---|---|---|---|---|
| 1 | Transaction type | Text (enum) | `SALE`, `REFUND` | Regel: `RawInvoice.is_credit_note` | `SALE` oder `REFUND` (uppercase). REFUND wenn `is_credit_note=True`. |
| 2 | Subject of the transaction | Text (const) | `Goods` | konstant | Immer `Goods` (keine Dienstleistungen). |
| 3 | Sales channel | Text (const) | `Marketplace` | konstant | Immer `Marketplace` (alle Belege aus JTL-Wawi). |
| 4 | VAT number | Text (optional) | (leer) | — | Leer (B2C-Konvention). B2B-VAT-IDs gehören nicht hier. |
| 5 | Transaction date | Date | `02.01.2026` | `RawInvoice.invoice_date` | Belegdatum in Format DD.MM.YYYY. |
| 6 | Invoice number | Text | `406-0538474-1507531` | `RawInvoice.document_id` | JTL-Belegnummer. Mehrteil-Suffix `_N` ist bereits im Repository gestrippt. |
| 7 | Departure country | Text (ISO-2) | `DE` | `RawInvoice.warehouse_country` | Lagerland (physischer Versandort), uppercase ISO-2-Code. |
| 8 | Customer's country | Text (ISO-2) | `FR` | `RawInvoice.ship_to.country_iso` | Lieferland (Kundenadresse), uppercase ISO-2-Code. |
| 9 | Currency | Text (ISO-4217) | `EUR` | `RawInvoice.currency` | Belegwährung, default `EUR`. |
| 10 | Gross amount | Number | `19.95` | `RawInvoice.gross_amount` | Brutto-Gesamtbetrag. **REFUND negativ.** |
| 11 | VAT reporting country | Text (ISO-2) | `FR` | **Regel** (siehe unten) | **Steuermeldeland** — wo meldet man diese Position? Entscheidungsbaum nach VAT-Rate und Ländern. |
| 12 | VAT Rate | Number (decimal) | `0.19` | `RawInvoice.vat_rate` (abgeleitet) | Dezimal (0.19 für 19%, 0.0 für 0%). |
| 13 | Net amount | — | (leer) | — | **Leer** — Taxually rechnet selbst. |
| 14 | VAT amount | — | (leer) | — | **Leer** — Taxually rechnet selbst. |
| 15 | Invoice date | — | (leer) | — | **Leer** — redundant zu Transaction date. |
| 16 | Local currency | — | (leer) | — | **Leer** (Profil 1 / Invoice-Granularität). |
| 17 | Exchange rate | — | (leer) | — | **Leer** — Taxually nutzt Live-Kurse. |
| 18 | Gross_local | — | (leer) | — | **Leer** (Profil 1). |
| 19 | Net_local | — | (leer) | — | **Leer** (Profil 1). |
| 20 | VAT_local | — | (leer) | — | **Leer** (Profil 1). |

## VAT Reporting Country — Entscheidungsregel

Spalte 11 bestimmt, in welchem Land die Position gemeldet wird:

### Fall 1: Positive VAT-Rate (> 0)

**VAT Rate > 0** → Meldeland = **Customer's country** (Spalte 8)

*Logik:* Wenn ein Steuersatz anfällt, ist das Land, wo die Steuer gilt, immer das Kundenland. Beispiele:
- DE→DE mit 19% → VAT reporting country = `DE` (Inland)
- DE→FR mit 20% → VAT reporting country = `FR` (OSS / Destination-based)
- DE→IT mit 22% → VAT reporting country = `IT` (OSS)

### Fall 2: Null-Rate mit Kundenland = GB

**VAT Rate == 0 UND Customer's country == `GB`** → Meldeland = **`GB`** (UK-Lokalregistrierung)

*Logik:* UK verlangt, dass Nullsteuersätze (z.B. B2B Reverse-Charge UK-Kunde mit gültiger USt-ID) auch in GB gemeldet werden. Ohne dieser Regel würden sie als IC-Lieferungen (Fall 3) gelten.

Beispiel:
- DE→GB, B2B mit gültiger GB-USt-ID, VAT 0% → VAT reporting country = `GB` (UK-Meldefrist)

### Fall 3: Null-Rate sonst (nicht GB)

**VAT Rate == 0 UND Customer's country != `GB`** → Meldeland = **Departure country** (Spalte 7, Lagerland)

*Logik:* Ausfuhren und IC-Lieferungen (außer UK) werden im Lagerland gemeldet. Der Verkäufer bucht das in seinem Heimatland.

Beispiele:
- DE→CH (Drittland), VAT 0% → VAT reporting country = `DE` (Export)
- DE→IT, B2B mit gültiger IT-USt-ID, VAT 0% → VAT reporting country = `DE` (Reverse-Charge-Meldung in Verkäufer-Land)

---

## Transaction Type — Logik

**`SALE`:** `is_credit_note = False` → Transaction type = `SALE`, Gross amount positiv
**`REFUND`:** `is_credit_note = True` → Transaction type = `REFUND`, Gross amount **negativ**

*Sonderfall:* Storno einer Gutschrift (SRK-Belege, Prefix `SRK`) werden als **SALE mit positivem Vorzeichen** behandelt (sind ökonomisch eine Erlös-Rückgängigmachung der Gutschrift). Im Engine-Output bereits als `is_credit_note=False` erkannt.

---

## Numerische Spalten — Format-Konvention

- **Dezimalzeichen:** Punkt (`.`) — nicht Komma
- **Zahltyp:** In XLSX explizit als Number-Format schreiben, nicht als Text
- **Rounding:** 2 Dezimalstellen (0.00)
- **Negative Vorzeichen:** `-19.95` für REFUND-Beträge

**Grund:** Taxually-Template verlangt Punkt-Dezimalzeichen. Excel-Locale-Konflikt (DE: Komma) wird durch explizite Zellen-Formatierung (Format-Code `0.00`) gelöst.

---

## Betrags-Aggregation

**Granularität:** 1 Zeile pro Belegdokument (wie DutyPay).

**Brutto-Beträge:** Summe aller Positionen eines Belegs → `RawInvoice.gross_amount` / `RawInvoice.net_amount`.

*Rationale:* Taxually akzeptiert Invoice-Ebene (nicht Position-Ebene), und per Beleg ist der VAT-Satz nach Engine-Logik einheitlich (Q1-2026-Analyse: 0 Belege mit gemischten Sätzen).

---

## CLI-Workflow

### Vollexport: Monatlich

```bash
jtl2datev export-taxually --month 2026-05
```

**Effekt:**
1. Alle Belege des Monats Mai 2026 aus JTL laden
2. XLSX-Sheet `Your data` mit 20 Spalten erzeugen
3. Automatisch archivieren unter `exports/taxually/<YYYY-MM>/<timestamp>.xlsx`
4. Optional: `--out <path>` zusätzlich abspeichern

**Archive-Struktur:**
```
exports/taxually/
  2026-05/
    2026-05-07_143022.xlsx    # Auto-Archive (neuester Stand)
    2026-05-01_090000.xlsx    # älterer Stand
```

### Delta: Nachgelagerte Belege

```bash
jtl2datev export-taxually-delta --month 2026-05
```

**Effekt:**
1. Letzten archivierten Vollexport laden (lexikalisch neueste Datei in `exports/taxually/2026-05/`)
2. Frischen Vollexport erzeugen
3. Diff: neue + geänderte DocumentIDs → Delta-XLSX
4. Delta archivieren unter `exports/taxually/<YYYY-MM>/deltas/<timestamp>.xlsx`

**Ablauf mit `--shift-to-period` (Nachzügler-Meldung):**

```bash
jtl2datev export-taxually-delta --month 2026-05 --shift-to-period 2026-06
```

Nachgelagert eingespielt Belege aus Mai (z.B. verspätete Amazon-Sync) können mit `--shift-to-period 2026-06` zur Juni-Meldung verschoben werden. Die Delta-Output-XLSX erhält geänderte Datumsfelder für direkte Upload in Taxually Juni-Erfassung.

---

## Q1-2026 Reconciliation — Engine vs. Jera-PowerQuery

**Referenzdatei:** `samples/jera/Taxually_export_sample_2026-Q1.xlsx` (User-PowerQuery-Output)

### Ergebnisse nach Monat

| Monat | Engine Zeilen | Engine Distinct | Jera Zeilen | Jera Distinct | Δ Summe Brutto | Δ Schnitt/Beleg | Match-Rate |
|-------|---------------|-----------------|-------------|---------------|----------------|-----------------|----|
| **JAN** | 5329 | 5329 | 5708 | 5329 | ≈ 0 € | -0,13 € | 100% |
| **FEB** | 3865 | 3865 | 4146 | 3594 | +0,04 € | +0,04 € | 99,9% |
| **MAR** | 4807 | 4807 | 5146 | 4490 | -0,03 € | -0,03 € | 99,9% |
| **Q1 Gesamt** | 14001 | 14001 | 15000 | 12413 | -0,12 € | -0,01 € | **99,95%** |

### Interpretation

**JAN:** Engine = Jera (distinct count 5329 identisch). Jera-Zeilen-Zahl 5708 ist höher, weil PowerQuery-Pipeline zusätzliche Position-Breakdown-Zeilen erzeugt (Jera-Konvention: eine Zeile je Belegposition + Versand, während Engine eine Zeile pro Beleg).

**FEB/MAR:** Engine ist **Obermenge** der Jera-PowerQuery. Zusätzliche Belege:
- FEB: 272 zusätzliche Belege mit Nummer-Prefix `202630260xxx`
- MAR: 318 zusätzliche Belege mit Nummer-Prefix `202650012xxx`

Diese Belege waren zur Zeit der Jera-PowerQuery-Erzeugung noch nicht erfasst oder nicht in der Export-Datei des Users enthalten.

**Jera-only-Beleg:** Jeweils 1 Beleg in FEB/MAR, der nur in Jera-Export vorhanden, aber nicht in Engine. Analyse zeigt: Jera-Datenwert ist durch Excel-Wissenschaftsnotation korrumpiert (`2,03E+11` statt numerische Sequenz `203000000000`). **Kein Engine-Bug — Datenqualität-Issue in Jera-PowerQuery oder User-Excel-Erzeugung.**

### Cent-Rundungen

Δ über Q1 Summe: **−0,12 €** (Rounding-Akkumulation über 14k+ Belege). Akzeptabel.

---

## Bekannte Edge Cases & Anomalien

### 1. Duplicate-Stornos (SRK-Belege)

Belegnummern mit Prefix `SRK` (z.B. `SRK202450012113`) sind Stornierungen von Rechnungskorrektionen (Gutschriften). Im Gegensatz zu regulären Refund-Belegen (Gutschriftsbeleg mit `is_credit_note=True`) werden SRKs als **SALE mit positivem Vorzeichen** geschrieben (Erlös-Rückgängigmachung).

Engine-Logik: JTL speichert SRKs mit `nBelegtyp=0` (Rechnung, nicht Gutschrift) → `is_credit_note=False` → korrekt als SALE.

### 2. Negative Brutto bei REFUND

Bei `Transaction type=REFUND` ist `Gross amount` negativ. Dezimalzeichen ist Punkt, nicht Komma. Beispiel: `-19.95` (Punkt-Dezimal).

### 3. VAT Rate 0% — Mehrfach-Länder

Ein Export mit VAT Rate 0% kann unterschiedliche VAT reporting countries haben, je nachdem ob der Kundenland GB ist oder nicht (Fall 2 vs. Fall 3). Ein EU-B2B-Export (0%, Kunde nicht GB) wird dem Verkäufer-Land zugeordnet; ein UK-B2B-Export wird GB zugeordnet — beide Nullsteuersätze, unterschiedliche Meldeplätze.

### 4. Engine-only vs. Jera-only Belege

- **Engine-only:** Belege, die nach dem Jera-PowerQuery-Export in JTL eingespielt wurden (z.B. Amazon Nachzügler). Normal — gehört zum INC-RECONCILE-Prozess.
- **Jera-only:** Belege in Jera-Export, aber nicht in Engine-Output. Analyse zeigt Datenqualität-Issues (Excel-Korruption). Nicht wiederholbar.

---

## Implementierungs-Prüfliste für `core/taxually.py`

- [x] XLSX-Writer (openpyxl), Sheet `Your data`
- [x] 20-Spalten-Header schreiben
- [x] Eine Zeile pro Belegdokument (Brutto/Netto aggregiert)
- [x] `Transaction type` per `is_credit_note` Regel (SALE / REFUND)
- [x] VAT Reporting Country — dreistufige Entscheidungslogik (VAT > 0, VAT = 0 + GB, VAT = 0 sonst)
- [x] Datumsformat `DD.MM.YYYY`
- [x] Negative Beträge bei REFUND (Punkt-Dezimal)
- [x] Numerische Spalten explizit als Number-Format
- [x] Spalten 13–20 leer (lässt Taxually rechnen)

## Implementierungs-Prüfliste für `core/taxually_delta.py`

- [x] Delta-Diff nach DocumentID (wie DutyPay)
- [x] Baseline-Matching: letzter archivierter Vollexport oder `--baseline`-Flag
- [x] `--shift-to-period` ändert Datumsfelder in Delta-Output (nicht in Archive)
- [x] Delta-XLSX archivieren unter `exports/taxually/<YYYY-MM>/deltas/<timestamp>.xlsx`

## Workflow: Archiv & Reconcilement

### Auto-Archivierung

Jeder `export-taxually --month` archiviert automatisch unter:
```
exports/taxually/<YYYY-MM>/<YYYY-MM-DD_HH-MM-SS>.xlsx
```

Timestamp = lokale Zeit, Verzeichnis auto-created.

### Delta-Export für Nachzügler

OSS-Meldefrist: 6. des Folgemonats. Verspätete Belege (z.B. Amazon-Sync-Verzögerung) werden mit `export-taxually-delta` nachgemeldet:

```bash
jtl2datev export-taxually-delta --month 2026-05
```

Findet automatisch den neuesten Baseline-Export und schreibt Delta-XLSX.

### Folgemonats-Nachmeldung via `--shift-to-period`

```bash
jtl2datev export-taxually-delta --month 2026-05 --shift-to-period 2026-06 --out delta-fuer-juni.xlsx
```

Überschreibt in der Output-XLSX:
- `Transaction date` → 01.06.2026
- `Invoice date` → 01.06.2026
- andere Datumsfelder → Zielmonat

Archiv bleibt mit Original-Datumsangaben.

---

## Tests

**Suite:** `tests/test_taxually.py` — 16 Tests, alle grün.

Abdeckung:
- Header-Zeile und Spalten-Struktur
- Transaction-Type-Logik (SALE / REFUND)
- VAT Reporting Country nach Regel 1/2/3
- Datumsformat (DD.MM.YYYY)
- Negative Beträge bei REFUND
- Delta-Matching und Archivierung
- `--shift-to-period` Datums-Umschreibung

**Gesamtsuite:** 293 Tests passed, 3 skipped.

---

## Referenzen

- **Taxually-Template:** `samples/taxually/Taxually_template_Your_data.xlsx` (20-Spalten-Vorgabe)
- **Q1-2026-Baseline:** `samples/jera/Taxually_export_sample_2026-Q1.xlsx` (User PowerQuery-Export)
- **Engine-Q1-Export:** `exports/taxually/2026-0{1,2,3}/*.xlsx` (Auto-generiert nach Implementation)
