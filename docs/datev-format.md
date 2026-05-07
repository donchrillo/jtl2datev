# DATEV-Export-Format

> Reverse-Engineered aus dem Jera-Beispielexport
> `samples/jera/EXTF_Buchungsstapel_Belege_202603_20260407132743_1.csv`
> (März 2026, 4 807 Buchungen).
> 
> Stand: 2026-05-07.

## Format-Variante

- **EXTF Buchungsstapel** (Datenkategorie 21)
- DATEV-Versionskennung: **700** (= v7.0)
- Format-Version: **12**
- Header-Erzeuger: `JE` / `JERA2DATEV`
- 134 Spalten je Buchungssatz

## Encoding & Konventionen

| Eigenschaft | Wert |
|---|---|
| Encoding | **Windows-1252 (ANSI)** |
| Zeilenumbruch | **CRLF** |
| Trennzeichen | **Semikolon** `;` |
| Dezimalzeichen | **Komma** `,` |
| Stringquoting | nicht standardmäßig — Buchungstext ohne Anführungszeichen |
| Belegdatum | `DDMM` mit *führender Null nur beim Monat*, Tag ohne. Bsp.: `203` = 02.03., `2703` = 27.03., `1003` = 10.03. |

## Header-Felder (Zeile 1)

| Feld | Wert (aus Sample) | Bedeutung |
|---|---|---|
| 1 | `EXTF` | Format |
| 2 | `700` | Versionskennung v7.0 |
| 3 | `21` | Datenkategorie Buchungsstapel |
| 4 | `Buchungsstapel` | Bezeichnung |
| 5 | `12` | Format-Version |
| 6 | `20260407132743000` | Erzeugt-Zeitstempel (Jahr-Monat-Tag-HHMMSSmmm) — Excel verstümmelt das beim Öffnen zu `2,02604E+16`, im File korrekt schreiben! |
| 7 | (leer) | importiert von |
| 8 | `JE` | Diktatkürzel |
| 9 | `JERA2DATEV` | Erzeugt von (für uns: `jtl2datev`) |
| 10 | (leer) | Importiert von |
| 11 | **`14974`** | **Mandantennummer** |
| 12 | **`10305`** | **Beraternummer** |
| 13 | `20260101` | WJ-Beginn |
| 14 | **`7`** | **Sachkonten-Länge** |
| 15 | `20260301` | Datum von |
| 16 | `20260331` | Datum bis |
| 17 | `Belege 2026/03` | Bezeichnung |
| 18 | `JE` | Diktatkürzel |
| 19 | `1` | Buchungstyp (Finanzbuchführung) |
| 20 | `0` | Rechnungslegungszweck |
| 21 | `0` | Festschreibung |
| 22 | `EUR` | Default-WKZ |

## Buchungssatz-Felder (Zeile 2 = Spaltennamen, ab Zeile 3 Daten)

Wir füllen primär:

| Spalte | Feld | Inhalt |
|---|---|---|
| 1 | Umsatz (ohne S/H) | Brutto, immer **positiv** mit Komma-Dezimaltrennzeichen (Vorzeichen über Soll/Haben) |
| 2 | Soll/Haben-Kennzeichen | `S` für Rechnungen, `H` für Gutschriften |
| 3 | WKZ Umsatz | **Bei EUR-Belegen leer; bei Fremdwährung ISO-4217-Code** (z.B. `GBP`, `PLN`, `SEK`, `CZK`). Engine befüllt aus `invoice.currency_factor`. |
| 4 | Kurs | **Bei EUR-Belegen leer; bei Fremdwährung Wechselkurs aus JTL** (`fWaehrungsfaktor`, Format: 4 Nachkommastellen, Komma als Dezimaltrenner — z.B. `0,8719`). |
| 5 | Basis-Umsatz | **Bei EUR-Belegen leer; bei Fremdwährung Original-Brutto in EUR umgerechnet** (Format: 2 Nachkommastellen, Komma — z.B. `25,53`). Beispiel: GBP-Beleg `FR500071NL56FD` mit Brutto 22,26 GBP, Kurs 0,8719 → Basis-Umsatz 25,53 EUR. |
| 6 | WKZ Basis-Umsatz | **Bei EUR-Belegen leer; bei Fremdwährung `EUR`**. |
| 7 | **Konto** | Debitor-Sammelkonto (8-stellig, s.u.) |
| 8 | **Gegenkonto** | Erlöskonto (7-stellig) |
| 9 | **BU-Schlüssel** | leer / `240` / `241` / `285` (s.u.) |
| 10 | Belegdatum | `DDMM` (s.o.) |
| 11 | Belegfeld 1 | externe Order-ID (Amazon-Order-ID, Otto/eBay-ID) **ohne `_N`-Suffix**. JTL speichert Mehrteil-Sendungen mit `_1`, `_2`, … (z.B. `406-0538474-1507531_1`), Engine schreibt nur Basis-Order-ID (z.B. `406-0538474-1507531`). Eindeutigkeit pro Beleg liegt in Buchungstext (DocumentID). |
| 12 | Belegfeld 2 | optional — z.T. eine zweite Referenz, oft leer |
| 14 | Buchungstext | `"{cRechnungsnr/cBelegnr} {Vorname Nachname}"` |
| 40 | EU-Land + UStID (Bestimmung) | bei OSS_B2C nur Land-ISO (z.B. `IT`); bei IGL_B2B Kunden-UStID (z.B. `IT05041920967`) |
| 41 | EU-Steuersatz (Bestimmung) | Zielland-Standardsatz bei OSS_B2C |
| 132 | EU-Land + UStID (Ursprung) | unsere lokale UStID, **nur wenn Lagerland ≠ DE** (z.B. `FR54820509628`, `IT00185379997`, `CZ683736606`, `PL5263144779`, `ESN2765131D`) |
| 133 | EU-Steuersatz (Ursprung) | leer |
| 87 | Veranlagungsjahr | `2026` |

Alle übrigen Spalten leer lassen.

## Debitor-Sammelkonten (8-stellig) — gemappt nach **Zahlungsart** (`cZahlungsart`)

Quelle: JTL Personenkonten-Konfiguration (Screenshot `samples/jera/Screenshot 2026-05-05 151112.png`). Default-Konto: **10000000**.

| Konto | Zahlungsart-Werte | Bemerkung |
|---|---|---|
| **10001000** | Bar, Bar bei Selbstabholung | Kasse |
| **10002000** | Überweisung, Vorkasse, vorkasse, Rechnung manuell | Vorkasse |
| **10004000** | PayPal, paypal, PayPal-Express | PayPal |
| **10005000** | AmazonPayments, amazon_payments, Amazon Payments | Amazon |
| **10006000** | eBay Rechnungskauf, eBay Managed Payments | eBay |
| **10007000** | Gewährleistung | (selten) |
| **10008000** | REAL, Kaufland, Kaufland.de | Kaufland (nicht eBay!) |
| **10009000** | rechnung_mit_klarna, Sofortbezahlen Klarna | Klarna |
| **10010000** | shopify_payments | Shopify |
| **10011000** | Otto | Otto |
| **10012000** | TEMU | (außerhalb Tool-Scope) |
| **10000000** | (Default-Fallback) | unbekannt / nicht gemappt |

**Implementierung:** Mapping fest verdrahten (oder als Settings-Override). Lookup über `cZahlungsart` mit case-insensitive Match.

## Erlöskonten (Gegenkonto, 7-stellig — SKR04)

Quelle: `samples/jera/SachkontenZuordnung.csv` (78 Mapping-Einträge, vollständig).

Schlüssel-Dimensionen: `Lager-ISO × Bestimmungs-ISO × UStID-vorhanden × Plattform`.
Sonder-Country-Codes: `DE` (DE-Lager), `EU` (jedes Nicht-DE EU-Lagerland),
`HLG` (Helgoland), `MC` (Monaco — wie FR), `XI` (Nordirland — wie EU),
`Drittl.` (alle Drittländer).

### Konten-Übersicht (vollständig)

| Konto | Bemerkung | Lager → Ziel | USt | BU |
|---|---|---|---|---|
| **4400000** | volle USt Inland | DE → DE | 19% | – |
| **4324000** | FR-lokal | FR → FR / FR → MC | 20% | – |
| **4326000** | IT-lokal | IT → IT | 22% | – |
| **4323000** | ES-lokal (B2C, UStID=nein) | ES → ES | 21% | – |
| **4327000** | PL-lokal | PL → PL | 23% | – |
| **4322000** | CZ-lokal | CZ → CZ | 21% | – |
| **4325000** | UK 20% (DE-Reg) | EU → GB / GB → EU | 20% | – |
| **4328000** | "**VAT durch Amazon**" — Marketplace-Facilitator | EU/GB → GB | 0% | – |
| **4001000** | EU → DE B2B (Reverse-Charge, wir sind Käufer) | EU → DE | 19% | **285** |
| **4125000** | IGL aus DE-Lager (mit Kunden-UStID) | DE → EU mit UStID | 0% | – |
| **4126000** | IGL aus EU-Lager (zwischen Mitgliedstaaten) | EU → EU oder EU → DE mit UStID | 0% | – |
| **4120000** | DE/EU → Helgoland steuerfrei + DE → Drittland | DE/EU → HLG / DE → Drittl. | 0% | – |
| **4121000** | EU/GB → Drittland steuerfrei | EU → Drittl. / GB → EU/Drittl. | 0% | – |
| **4320000 BU 240** | OSS B2C aus DE-Lager | DE → EU-AT/BE/BG/CY/CZ/DK/EE/ES/FI/FR/GR/HR/HU/IE/IT/LT/LU/LV/MT/NL/PL/PT/RO/SE/SI/SK/XI | je Zielland | **240** |
| **4320000 BU 241** | OSS B2C aus Nicht-DE EU-Lager | EU → AT/BE/BG/CY/CZ/DK/EE/ES/FI/FR/GR/HR/HU/IE/IT/LT/LU/LV/MT/NL/PL/PT/RO/SE/SI/SK/XI/MC | je Zielland | **241** |
| **4970000** | "DPD Schaden" Sonderfall | DE → DE | 0% | – |

### Lookup-Algorithmus für `rules.py`

```
Inputs: warehouse_country, dest_country, treatment, has_vat_id, line_vat_rate

1. Normalisiere dest: MC → für FR-Lager: bleibt MC; für DE-Lager: wie EU.
2. Drittland-Sonderfall: dest == HLG → 4120000.
3. dest == "Drittl." (außerhalb EU+GB+CH):
   - wh == DE → 4120000
   - wh in EU → 4121000
   - wh == GB → 4121000
4. dest == GB:
   - wh in EU oder GB:
     - line_vat_rate == 0 → 4328000 (MARKETPLACE_FACILITATOR)
     - sonst → 4325000 (EXPORT_LOCAL_VAT)
5. wh == dest (DOMESTIC):
   - DE → 4400000
   - FR → 4324000
   - IT → 4326000
   - ES → 4323000 (B2C; falls UStID + 0% → 4126000)
   - PL → 4327000
   - CZ → 4322000
   - GB → 4325000
6. Cross-border EU + has_vat_id (B2B Reverse-Charge):
   - wh == DE, dest in EU → 4125000
   - wh in EU, dest in EU oder DE → 4126000
   - wh in EU, dest == DE (wir sind Käufer) → 4001000 + BU 285 (Sonderfall — nur wenn JTL es so klassifiziert)
7. Cross-border EU + B2C (OSS):
   - wh == DE → 4320000 + BU 240
   - wh in EU (Nicht-DE) → 4320000 + BU 241
8. Sonderfall "DPD Schaden": JTL flagged 4970000 — wir nutzen das nicht aktiv, aber loggen wenn Engine 4970000 produziert.
```

### Engine-Treatment ↔ Sachkonto-Mapping

| Engine-Treatment | typisches Konto |
|---|---|
| `DOMESTIC` (Lager == Ziel, vat>0) | 4400000 (DE) / 4324000 (FR) / 4326000 (IT) / 4323000 (ES) / 4327000 (PL) / 4322000 (CZ) / 4325000 (GB) |
| `DOMESTIC` (Lager == Ziel, vat=0, UStID) | 4126000 (EU) |
| `OSS_B2C` aus DE-Lager | 4320000 + BU **240** |
| `OSS_B2C` aus Nicht-DE EU-Lager | 4320000 + BU **241** |
| `IGL_B2B` (DE-Lager, Kunden-UStID) | 4125000 |
| `IGL_B2B` (Nicht-DE EU-Lager, Kunden-UStID) | 4126000 |
| `IGL_B2B` (Wir kaufen B2B aus EU nach DE) | 4001000 + BU **285** |
| `THIRD_COUNTRY` (DE-Lager) | 4120000 |
| `THIRD_COUNTRY` (EU/GB-Lager) | 4121000 |
| `MARKETPLACE_FACILITATOR` (Amazon UK, gross==net) | **4328000** |
| `EXPORT_LOCAL_VAT` (UK, gross≠net) | **4325000** |
| Sonderfall DPD Schaden | 4970000 (manuell, nicht von Engine) |

## Sonderfälle

### Gutschriften / Stornos

- **Soll/Haben** invertiert (`H` statt `S`), Beträge bleiben **positiv**.
- Sample: Otto-Gutschrift `E-DE-…` und Amazon-Gutschrift (Belegtyp 1) → Konto 10005000 / Gegenkonto 4320000 BU=241, S/H=H.
- **Datenfehler-Auffangkonto: `4970000`** — wenn Jera keinen passenden Treatment-Treffer findet (z.B. Mitarbeiter-Gutschrift ohne MwSt). Sample: `202650012449 Schuster Steffen` — genau unsere bekannte Fehler-Gutschrift! Engine wirft hier weiter `error` im Reconcile, gehört nicht in den DATEV-Export ohne manuelle Korrektur.

### Datums-Format-Fallstrick

Excel öffnet `203` u.U. als Zahl (203) und entfernt führende Nullen. Beim **Schreiben** unbedingt als String mit `f"{day}{month:02d}"` — Tag **ohne** führende Null bei < 10, Monat **mit** führender Null. Quoting nicht nötig (Excel behandelt rein numerische Werte automatisch).

### Header-Zeitstempel

Spalte 6 ist `YYYYMMDDhhmmssfff`. Excel rundet auf wissenschaftliche Notation (`2,02604E+16`). Wir schreiben als String, Excel-Anzeige ist egal — DATEV liest die Datei direkt.

### EU-UStID-Spalten

- **Spalte 40** „EU-Land und UStID (Bestimmung)":
  - Bei `OSS_B2C`: nur 2-stelliger Country-Code (z.B. `IT`)
  - Bei `IGL_B2B`: vollständige UStID (z.B. `IT05041920967`)
- **Spalte 132** „EU-Land und UStID (Ursprung)":
  - Bei DE-Lager: leer
  - Bei FR/IT/ES/PL/CZ-Lager: unsere lokale UStID (`FR54820509628`, `IT00185379997`, …)
  - Diese müssen in `Settings` als Mapping `warehouse_country → own_vat_id` konfiguriert werden.

## Buchungssatz-Beispiele

```
# DE-Lager → DE-Kunde (DOMESTIC 19%)
47,6;S;;;;;10005000;4400000;;203;cbn4wjs65s;;;R-DE-249030238-2026-322 Kruse Cora;…
# = Konto Amazon-Sammeldebitor an 4400000 Erlöse 19% Inland, 47,60 € am 02.03.

# DE-Lager → IT-Kunde B2C (OSS BU 240)
30,21;S;;;;;10005000;4320000;240;903;406-2316425-1404350;;;202630260479 Michele Egidio Villa;…;IT;22;…
# = Amazon-Debitor an 4320000 OSS-Erlöse, 30,21 € am 09.03., Bestimmungsland IT 22%

# FR-Lager → IT-Kunde B2C (OSS BU 241)
30,47;S;;;;;10005000;4320000;241;303;407-7920859-3780313;;;202630260771 emanuela frosio;…;IT;22;…;FR54820509628;
# = wie oben aber Spalte 132 enthält unsere FR-UStID als Ursprung

# PL-Lager → DE-Kunde B2B (IGL Reverse-Charge BU 285)
9,9;S;;;;;10005000;4001000;285;103;302-1775111-9245150;;;DE60028UNL56FU Jennifer Schlosser;…;;;…;PL5263144779;
# = i.g. Lieferung von PL nach DE, Spalte 132 = unsere PL-UStID

# Gutschrift (Soll/Haben = H)
10,52;H;;;;;10005000;4320000;241;103;171-8477686-7023502;;;DE600098NL56FQ manolo illana abril;…
# = identisches Konto-Schema wie Original, nur S/H invertiert
```

## Zusammenfassung — was wir brauchen für `datev.py`

1. **Settings** erweitern um:
   - `datev_mandantennr: int = 14974`
   - `datev_beraternr: int = 10305`
   - `datev_wj_start: date = 2026-01-01`
   - `datev_skr_account_length: int = 7`
   - `own_vat_ids: dict[str, str]` — Lagerland → UStID (`{"DE": "DE319514546", "FR": "FR54820509628", "IT": "IT00185379997", "ES": "ESN2765131D", "PL": "PL5263144779", "CZ": "CZ683736606", "GB": ?}`)
2. **`rules.py`** mit Mapping-Tabelle Treatment+Lagerland → (Konto, BU)
3. **`datev.py`**: EXTF-CSV-Writer mit Header + Datenzeilen, Windows-1252-Encoding.

## CLI-Flags für Validierung

### `--compare-to <jera.csv>`

Lädt Referenz-Export, indiziert nach Belegnummer (erstes Whitespace-separated Token in Buchungstext). 
Buchungen mit (Konto, BU)-Abweichung bekommen "X" in Belegfeld 2. 
Belege außerhalb der Referenz-Periode werden nicht markiert. 
**Default:** deaktiviert.

### `--audit`

Schreibt Engine-Regel-Tag (z.B. `OSS241-CZ-AT`, `IGL-DE-FR`, `MF-GB-FR`, `DOM-DE-19`, `DOM-RC-IT`, `THIRD-EU-DE-CH`, `EXP-GB-ES`, `ERROR`, `UNKNOWN`) in Spalte 20 „Beleglink". 
Vor Übergabe an Steuerberater entfernen. 
**Default:** deaktiviert.

**Tag-Schema:**
- `DOM-{wh}-{rate}` – Domestic (z.B. `DOM-DE-19`, `DOM-IT-22`)
- `DOM-RC-{wh}` – Domestic Reverse-Charge (vat=0 + vat_id)
- `OSS240-DE-{dest}` – OSS aus DE-Lager
- `OSS241-{wh}-{dest}` – OSS aus EU-Lager (≠ DE)
- `OSS285-{wh}-DE` – OSS EU-Lager → DE
- `IGL-{wh}-{dest}` – IGL B2B
- `MF-GB-{wh}` – Marketplace-Facilitator UK (Amazon)
- `EXP-GB-{wh}` – UK mit lokaler VAT-Pflicht (nicht MF)
- `THIRD-EU-{wh}-{dest}` – Drittland aus EU-Lager
- `THIRD-DE-{dest}` – Drittland aus DE-Lager
- `ERROR` / `UNKNOWN` – Marker für skippte Belege (kein Treatment, Fehler in Rohfakten)

## CLI / Workflow

Standardablauf für Monats-Export:

```bash
# 1. Vorprüfung: gemischte Steuersätze
jtl2datev mixed-vat-check --month YYYY-MM

# 2. Reconciliation (Engine ↔ JTL)
jtl2datev reconcile --month YYYY-MM

# 3. Hauptexport (archiviert automatisch unter exports/datev/<YYYY-MM>/)
jtl2datev export --month YYYY-MM

# 4. Delta-Export (falls nachgelagerte Belege)
jtl2datev export-delta --month YYYY-MM
```

DATEV-Archive: `exports/datev/<YYYY-MM>.csv` (aktueller Stand), `exports/datev/<YYYY-MM>/<timestamp>.csv` (Baseline für Delta-Vergleich).

## Sondervorgänge

### Bundle-Master Self-Reference

`kStuecklisteRechnungPos = kRechnungPosition` markiert die Master-Position (nicht `NULL`).
SQL-Filter berücksichtigt dies und schließt Master-Positionen von Gesamtverarbeitung aus
(werden nur als Platzhalter gezählt; Positionen selbst kommen via `kStuecklisteRechnungPos`-Join).

### Stornierte Belege bleiben drin

`nIstStorniert=1` → Beleg wird NICHT ausgefiltert. Stornierung erfolgt durch eine separate
Storno-Gutschrift-Zeile (`nBelegtyp=1`), die den Original-Beleg gegenbucht. Dies sichert
vollständige Audit-Trail für Steuerberater.

### Temu (`cExterneAuftragsnummer LIKE 'PO%'`) — ausgeschlossen

Ende 2025 wurde Temu testweise importiert, dann vom Steuerberater zurückgerollt.
Die `PO-…`-Bestellnummern bleiben in der DB, dürfen aber nicht in den DATEV-Export.
Filter im SQL-Layer für `_SQL_OWN` und `_SQL_CREDIT_NOTES`:
`cExterneAuftragsnummer NOT LIKE 'PO%'`. Sammelgutschriften (`SR202602…`) gegen
diese Original-Rechnungen werden über den JOIN ebenfalls ausgefiltert.

### Amazon Italien VCS-IDU (`cHerkunft='VCS-IDU'`) — bleibt drin

Italien-spezifischer Sonderfall: bei Bargeld-/Kassen-Verkäufen erstellt Amazon
keine Rechnung, bei späterer Erstattung fehlt der Erstattungsbeleg. Diese
Erstattungen importiert JTL als „VCS-IDU"-Belege (`XRK-…` Gutschriften,
`XRE-…` Rechnungen), die der User in JTL manuell vervollständigt.
**Geld ist geflossen → muss in DATEV.**

Jera erfasst sie inkonsistent (~213 Belege total, alle Amazon.it, in keinem
der drei Q1-Jera-Exporte enthalten). Engine nimmt sie alle. Bei künftigen
Jera-Vergleichen bewusst ignorieren — die Differenz hier ist Jera-Bug.

### Jera-Phase-out (ab April 2026)

Jera-Schnittstelle ist nach JTL-Software-Update inkompatibel, Lizenzen
ausgelaufen, keine Updates mehr verfügbar. Ab April 2026 ist `jtl2datev` die
**einzige** Quelle für DATEV-Exporte. Vergleichsbasis fehlt — Engine-Logik
muss dann eigenständig validiert sein.

## Offene Punkte vor finaler Implementation

- [x] ~~Sachkonten-Mapping bestätigt~~ (vollständig in `samples/jera/SachkontenZuordnung.csv` dokumentiert)
- [x] ~~Debitor-Mapping~~ (Screenshot zeigt: Mapping nach `cZahlungsart`)
- [ ] **Lager-UStIDs vollständig** (aus den Sample-Belegen: `FR54820509628`, `IT00185379997`, `CZ683736606`, `PL5263144779`, `ESN2765131D`; DE-UStID erschien als `DE319514546`; **GB-UStID fehlt noch**)
- [ ] **Belegfeld 2** — wann gefüllt, womit? In Sample meist leer; bei Amazon manchmal 8-stellige Zahl (`11212135` etc.) — vermutlich JTL-interner Auftrags-Key. Prüfen.
- [ ] **`4970000` "DPD Schaden"** — wann triggert das in Praxis? Unsere Fehler-Gutschrift `202650012449` würde Engine als error flaggen, nicht in Export schreiben. Ok für jetzt.
- [ ] **Header-Zeitstempel-Format** im File-Sample steht `2,02604E+16` — Jera schreibt also nicht-quoted und Excel verstümmelt's bei Anzeige. Beim Schreiben als 17-stelliger Integer-String exportieren (`YYYYMMDDhhmmssfff`).
- [ ] **DutyPay-Format** (`samples/jera/DutyPay-Sale-2026-MAR.csv`) — separates OSS-Format, später angehen.
