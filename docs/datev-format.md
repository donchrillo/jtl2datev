# DATEV-Export-Format

> Reverse-Engineered aus dem Jera-Beispielexport
> `samples/jera/EXTF_Buchungsstapel_Belege_202603_20260407132743_1.csv`
> (März 2026, 4 807 Buchungen).

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
| 3 | WKZ Umsatz | leer (Default = EUR) |
| 7 | **Konto** | Debitor-Sammelkonto (8-stellig, s.u.) |
| 8 | **Gegenkonto** | Erlöskonto (7-stellig) |
| 9 | **BU-Schlüssel** | leer / `240` / `241` / `285` (s.u.) |
| 10 | Belegdatum | `DDMM` (s.o.) |
| 11 | Belegfeld 1 | externe Order-ID (Amazon-Order-ID, Otto/eBay-ID) |
| 12 | Belegfeld 2 | optional — z.T. eine zweite Referenz, oft leer |
| 14 | Buchungstext | `"{cRechnungsnr/cBelegnr} {Vorname Nachname}"` |
| 40 | EU-Land + UStID (Bestimmung) | bei OSS_B2C nur Land-ISO (z.B. `IT`); bei IGL_B2B Kunden-UStID (z.B. `IT05041920967`) |
| 41 | EU-Steuersatz (Bestimmung) | Zielland-Standardsatz bei OSS_B2C |
| 132 | EU-Land + UStID (Ursprung) | unsere lokale UStID, **nur wenn Lagerland ≠ DE** (z.B. `FR54820509628`, `IT00185379997`, `CZ683736606`, `PL5263144779`, `ESN2765131D`) |
| 133 | EU-Steuersatz (Ursprung) | leer |
| 87 | Veranlagungsjahr | `2026` |

Alle übrigen Spalten leer lassen.

## Debitor-Sammelkonten (8-stellig)

| Konto | Plattform / Quelle | Sample-Volumen 03/2026 |
|---|---|---|
| **10005000** | Amazon (alle Marktplätze, alle Lager) | 4 056 |
| **10011000** | Otto (`R-DE-…` / `E-DE-…`) | 299 |
| **10006000** | eigene Wawi (eBay/Kaufland) | 188 |
| **10008000** | eigene Wawi (eBay/Kaufland) | 116 |
| 10000000 | Amazon-VCS-Sonderfälle (`INV-XX-…`) | 11 |
| 10004000 / 10002000 | vereinzelt (eigene Wawi) | 4 |

> **Offene Frage:** Was unterscheidet `10006000` vs `10008000` (beide eigene-Wawi)? Vermutlich eBay vs. Kaufland — vom User bestätigen.

## Erlöskonten (Gegenkonto, 7-stellig — SKR04)

### Tabelle Engine-Treatment → Konto

| Treatment | Lagerland | Bestimmungsland | Konto | BU | Anmerkung |
|---|---|---|---|---|---|
| DOMESTIC | DE | DE | **4400000** | – | Erlöse 19% Inland |
| DOMESTIC | FR | FR | **4324000** | – | FR-lokal 20% (lokaler Steuerberater) |
| DOMESTIC | IT | IT | **4326000** | – | IT-lokal 22% |
| DOMESTIC | ES | ES | **4323000** | – | ES-lokal 21% |
| DOMESTIC | PL | PL | **4327000** | – | PL-lokal 23% |
| DOMESTIC | CZ | CZ | (TBD, kein Sample im März) | – | CZ-lokal 21% — vermutlich `4328000` oder eigenes Konto |
| DOMESTIC | GB | GB | (TBD) | – | UK-lokal 20% |
| DOMESTIC | beliebig + UStID + 0% (national reverse charge) | gleiches Land | **4126000** | – | B2B-Inland 0% — Sample mit Kunden-UStID `IT05041920967` etc. |
| OSS_B2C (DE-Lager) | DE | EU-Ausland | **4320000** | **240** | EU-Ursprung leer (DE Stammland) |
| OSS_B2C (anderes EU-Lager) | FR/IT/ES/PL/CZ/… | EU-Ausland | **4320000** | **241** | EU-Ursprung mit unserer lokalen UStID (z.B. `FR54820509628`) |
| IGL_B2B (cross-border B2B Reverse-Charge) | beliebig | EU mit Kunden-UStID | **4001000** | **285** | EU-Bestimmung mit Kunden-UStID |
| THIRD_COUNTRY | beliebig | außerhalb EU/UK/CH | **4121000** ?? | – | Sample-Belegen mit `…NL56FD`-Suffix |
| EXPORT_LOCAL_VAT (Amazon UK/CH ohne MF, gross≠net) | beliebig | GB/CH | **4325000** | – | nur 1 Sample (`DE6002P4NL56FU`) — bestätigt unseren Edge-Case |
| MARKETPLACE_FACILITATOR | beliebig | GB/CH (Amazon zieht ein) | (TBD — kein Sample im März; vermutlich `4328000`) | – | Sample-Belegen mit `…NL56FD`-Suffix, oft engl. Namen → vermutlich UK |

### Offene Konten-Fragen an User

1. **`4126000`** — was genau? Domestic-B2B 0% (national reverse charge)? Oder etwas anderes?
2. **`4121000`** — alle Amazon-VCS-Belege ohne EU-Bestimmung, ohne Satz. Drittland §4 Nr.1a? Oder Marketplace-Facilitator?
3. **`4328000`** — ausschließlich `…FD`-Suffix (Suffix-Code für UK?). Drittland UK Marketplace-Facilitator?
4. **`4325000`** — 1 Beleg `DE6002P4NL56FU` (`…FU`-Suffix) → entspricht unserem `EXPORT_LOCAL_VAT`. UK-VAT-pflichtig?
5. **`4327000`** — 10 Belege mit `INV-PL-…`-Format und EU-Bestimmung=PL/23% → PL-Lokal-Konto, korrekt?
6. **CZ-Lager-Lokal**: welches Konto? (kein Sample im März, vermutlich `4328000`?)
7. **GB-Lager-Lokal**: welches Konto? (Lager DE→Kunde DE auf 4400000; aber UK-Lager → UK-Kunde?)

### BU-Schlüssel-Differenzierung

- **BU leer** + Konto 4400000/4324000/4326000/… → Konto kodiert den Steuersatz, kein BU nötig
- **BU 240** + 4320000 → OSS B2C, Lager **DE** (Stammland, EU-Ursprung leer)
- **BU 241** + 4320000 → OSS B2C, Lager **anderes EU** (FR/IT/CZ/PL/ES — EU-Ursprung mit unserer lokalen UStID gefüllt)
- **BU 285** + 4001000 → i.g. Lieferung Reverse-Charge B2B

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

## Offene Punkte vor finaler Implementation

- [ ] User bestätigt Sachkonten-Mapping (insbesondere 4121000, 4328000, 4126000, 4325000, 4970000)
- [ ] CZ + GB DOMESTIC-Konten klären
- [ ] Differenz `10006000` vs `10008000` Debitoren
- [ ] DE-eigene UStID + alle Lager-UStIDs (DE319514546 ist die unsere — bestätigen)
- [ ] Belegfeld 2 — wann gefüllt, womit?
- [ ] Gutschriften: ist Bezugsbelegnummer in einem speziellen Feld zu setzen (DATEV Spalte „Beleg-Link")?
