# JTL-DB-Schema (Findings)

> JTL-Wawi-Version: **2.0**
> Offizielle Schema-Doku: https://wawi-db.jtl-software.de/tables/2.0.0.0
> und https://wawi-db.jtl-software.de/views/2.0.0.0
> (SPA, nicht von Bots crawlbar — Tabellen-Details werden iterativ via SSMS
> ermittelt und hier eingetragen.)

## Verbindung

JTL Wawi nutzt MS SQL Server. Verbindungsparameter werden aus `.env` gelesen
(Vorlage: `.env.example`), Credentials nicht im Repo.

| Variable       | Wert                  |
|----------------|-----------------------|
| `SQL_SERVER`   | `192.168.178.2`       |
| `SQL_PORT`     | `50000`               |
| `SQL_DATABASE` | `eazybusiness`        |
| `SQL_USERNAME` | (in `.env`)           |
| `SQL_PASSWORD` | (in `.env`)           |

- Auth: SQL-Login (kein Windows-Auth — passt zu Linux-Host via pyodbc).
- Erreichbar von: lokales Netz (LAN/VPN zum Server `192.168.178.2`).
- Treiber: `mssql+pyodbc` mit ODBC Driver 18 for SQL Server (TBD: ggf.
  `TrustServerCertificate=yes` nötig, da self-signed).

## Erkenntnisse JTL 2.0 (2026-05-05)

JTL 2.0 verteilt die Daten auf **Schemata** und nutzt überwiegend **Views**
statt direkter Tabellenzugriffe. Tabelle `dbo.tRechnung` ist nur ein Stub —
die fachliche Logik (Adressen, Positionen, Steuern, Buchhaltung) ist in Views
gekapselt. **Wir lesen primär aus Views**, nicht aus Basistabellen.

### Wichtigste Views für den DATEV-Export

> **Korrektur 2026-05-05:** `vBuchhaltungsuebersichtRechnung` ist nur eine
> schmale UI-Übersicht (8 Spalten: Belegnr, Beträge, Datum, Währung) — **nicht
> export-tauglich**. Primärquelle für eigene Rechnungen ist `dbo.tRechnung`
> (Header) + zugehörige Position-Tabelle + Steuerschlüssel-Joins.

| View / Tabelle                                    | Inhalt                                                          |
|---------------------------------------------------|-----------------------------------------------------------------|
| `dbo.tRechnung`                                   | **Primärquelle eigene Rechnungen** (Header, alle Routing-Felder) |
| `Rechnung.vBuchhaltungsuebersichtRechnung`        | nur Übersicht — Beträge/Status                                   |
| `Rechnung.vBuchhaltungsuebersichtRechnungPosition`| Positionen-Übersicht (mager, ohne Steuerschlüssel)              |
| `Amazon.vBuchhaltungsuebersichtAuftrag`           | Amazon-Aufträge buchhalterisch                                  |
| `Amazon.vBuchhaltungsuebersichtAuftragPosition`   |                                                                 |
| `Amazon.vBuchhaltungsuebersichtGutschrift`        | Amazon-Gutschriften                                             |
| `Amazon.vBuchhaltungsuebersichtGutschriftPosition`|                                                                 |
| `Rechnung.vExternerBelegSteuerermittlungsdaten`   | **Externe Rechnungen** (nur Amazon-VCS) — Steuerermittlung; Basisdaten in `Rechnung.tExternerBeleg*` |
| `Rechnung.vRechnung*`                             | Rechnungs-Detail-Views (Adresse, Position, Eckdaten, …)         |
| `Verkauf.vRechnungskorrekturposition`             | **Gutschriften = Rechnungskorrektur** (JTL-2.0-Bezeichnung)     |
| `Statistik.vGutschrift` / `vGutschriftPos`        | Alternative Gutschrift-Sicht                                    |

### Steuern (Schema `Steuern`)

| View                                  | Zweck                                               |
|---------------------------------------|-----------------------------------------------------|
| `Steuern.vSteuerdaten`                | Steuersätze pro Land/Klasse                         |
| `Steuern.vSteuerschluessel`           | Steuerschlüssel (DATEV-Mapping-Anker!)              |
| `Steuern.vSteuerschluesselDaten`      | Detaildaten                                         |
| `Steuern.vPositionstypSteuerschluessel` | je Positionstyp                                  |
| `Steuern.vWarengruppenSteuerschluessel` | je Warengruppe                                   |
| `Steuern.vVersandartSteuerschluessel` | je Versandart                                       |

### Verkauf / Aufträge

- `Verkauf.vAuftrag`, `vAuftragPosition`, `vAuftragRechnungsadresse`,
  `vAuftragLieferadresse`, `vAuftragZahlungsinfo` — vollständiger Auftrag
- `Verkauf.vRechnungsverwaltung`, `vRechnungsposition`
- `Verkauf.vGutschriftPosition`, `vRechnungskorrekturposition`

### Kunde

- `Kunde.lvRechnungen`, `Kunde.lvRechnungskorrekturen` (Listen-Views)
- TODO: konkrete Kundenadress-View identifizieren

### Beschaffung (Eingangsrechnungen, falls später relevant)

- `Beschaffung.lvEingangsrechnung`, `lvEingangsrechnungPos`
- nicht im aktuellen Scope (wir machen nur Ausgangsbelege)

### Korrektur 2026-05-05 (DB-Erkundung Teil 2)

Die früher hier dokumentierte ~60-Spalten-Tabelle `dbo.tRechnung` ist falsch.
Tatsächlich:

- **`dbo.tRechnung` ist ein dünner Stub** (nur 15 Spalten: `kRechnung`,
  `cRechnungsNr`, `dErstellt`, `cErloeskonto`, `cBezahlt`, `cStatus`,
  `kFirma`, `nInkassoStatus`, `dEmailversandt`, `dDruckdatum`, `nMahnstop`,
  `nZahlungsziel`, `tBestellung_kBestellung`, `tBenutzer_kBenutzer`,
  `tKunde_kKunde`). **`cErloeskonto` lebt hier!**
- **Echter Header ist `Rechnung.tRechnung`** (47 Spalten) — anderes Schema.

PK `kRechnung` ist in beiden gleich (1:1), aber Inhalte komplementär.

### Basistabelle `Rechnung.tRechnung` (47 Spalten — Header eigener + externer Rechnungen)

Alle Routing-Discriminatoren liegen hier:

| Spalte                              | Typ            | Bedeutung                                          |
|-------------------------------------|----------------|----------------------------------------------------|
| `kRechnung` (PK)                    | int            |                                                    |
| `kKunde`                            | int            | FK Kunde                                           |
| `cRechnungsnr`                      | nvarchar(50)   | Belegnummer                                        |
| `cKundennr`                         | nvarchar(30)   | Debitor-Kennung                                    |
| `nDebitorennr`                      | int            | numerische Debitor-Nr.                             |
| `cKundengruppe` / `kKundengruppe`   | nvarchar/int   |                                                    |
| `dErstellt` / `dErstelltWawi`       | datetime       |                                                    |
| `dValutadatum`                      | datetime       | Wertstellung                                       |
| `dLeistungsdatum`                   | datetime       | Leistungsdatum (DATEV-relevant!)                   |
| `cFirma` / `kFirmaHistory`          | nvarchar/int   | Mandant                                            |
| `cVersandlandISO`                   | char(2)        | **Versandland/Lager**                              |
| `cVersandlandBundeslandkuerzel`     | nvarchar(5)    |                                                    |
| `cVersandlandWaehrung` + `fVersandlandWaehrungsfaktor` | char(3)/dec |                                       |
| `cWaehrung` + `fWaehrungsfaktor`    | char(3)/dec    | Belegwährung                                       |
| `cKundeUstId`                       | nvarchar(20)   | USt-IdNr. Kunde (B2B-Indikator)                    |
| `cUstId`                            | nvarchar(25)   | Eigene verwendete USt-IdNr.                        |
| `nSteuereinstellung`                | int            | Steuerregime (s.u.)                                |
| `nSteuersonderbehandlung`           | tinyint        | Spezialfall-Flag                                   |
| `nIstExterneRechnung`               | tinyint        | 0 = eigene, 1 = extern (importiert)                |
| `nStorno` / `nIstEntwurf` / `nIstProforma` / `nArchiv` | bit |                                          |
| `nRechnungStatus` / `nStatus`       | tinyint/bit    |                                                    |
| `nZahlungszielTage` / `fSkonto` / `nSkontoInTage` | int/dec/int |                                            |
| `kPlattform`                        | int            | Marktplatz (Lookup `dbo.tPlattform`)               |
| `kShop` / `cEbayUsername`           | int / nvarchar |                                                    |
| `cExterneAuftragsnummer`            | nvarchar(50)   | Marketplace-Order-ID                               |
| `kZahlungsart` / `cZahlungsart`     | int / nvarchar |                                                    |
| `kVersandArt` / `cVersandart`       | int / nvarchar |                                                    |
| `kSprache` / `kFarbe`               | int            |                                                    |
| `nMahnstop`                         | bit            |                                                    |
| `nExistierendeRechnungDrucken`      | bit            |                                                    |
| `bRowversion`                       | timestamp      | optimistic locking                                 |

**Filter aktive Belege:** `WHERE nIstEntwurf=0 AND nIstProforma=0`
→ **`nStorno=1` wird nicht ausgefiltert.** Storno-markierte Rechnungen müssen
mitgelesen werden, weil dazu zwingend ein Gutschriftsdokument existiert/zu
existieren hat — ohne den Storno-Beleg fehlte die Hälfte der Buchung.
**`nIstExterneRechnung` ist ebenfalls KEIN Filter** — Otto trägt z.B.
`nIstExterneRechnung=1`, gehört aber genauso in den eigenen Pfad. Die einzige
Tabelle, in der nur Amazon liegt, ist `Rechnung.tExternerBeleg`.

### Verteilung (~1.16 Mio aktive Rechnungen)

- Versandländer: DE 514k, PL 327k, CZ 91k, FR 77k, IT 65k, ES 60k, GB 32k, AT 4
- Wichtige Plattformen: 31=ebay.de (eigene), 51=Amazon.de, 53=Amazon.co.uk,
  54=Amazon.fr, 56=Amazon.it, 57=Amazon.es, 60=Amazon.nl (alle extern), 8=SCX
  (Onlineshop/Kaufland)
- `nSteuereinstellung`-Werte (gesehen): `0` (Standard, ~1.15M),
  `10` (~9k), `15` (~11), `20` (~5.6k) — Bedeutung unklar (kein Lookup
  gefunden); ggf. interne JTL-Steuerzonen-IDs

**Konsequenzen fürs Repository:**
- Eigene vs. externe Rechnung über `nIstExterneRechnung`
- Lager über `cVersandlandISO` (DE/PL/CZ/FR/IT/ES/GB)
- Marktplatz über `kPlattform`-Join auf `dbo.tPlattform`
- `cErloeskonto` aus **`dbo.tRechnung`** lesen (nicht `Rechnung.tRechnung`)
- Active-Filter wie oben

### Beträge & Buchungsstatus: `Rechnung.tRechnungEckdaten` (1:1 zu kRechnung)

| Spalte                | Typ      | Bedeutung                                    |
|-----------------------|----------|----------------------------------------------|
| `kRechnung` (PK)      | int      |                                              |
| `fVkBruttoGesamt`     | decimal  | Brutto Gesamtbeleg                           |
| `fVkNettoGesamt`      | decimal  | Netto Gesamtbeleg                            |
| `fOffenerWert`        | decimal  |                                              |
| `fZahlung`            | decimal  | bereits gezahlt                              |
| `fGutschrift`         | decimal  |                                              |
| `fMahngebuehr` / `fOffeneMahngebuehr` | decimal |                                  |
| `dDruckdatum` / `dMaildatum` / `dBezahlt` / `dZahlungsziel` | datetime |                  |
| `nZahlungStatus`      | tinyint  | (0/1/2 …)                                    |
| `nRechnungTyp`        | tinyint  |                                              |
| `nIstAngemahnt` / `nMahnstufe` / `dMahndatum` |  |                                       |
| `cAuftragsnummern`    | nvarchar(200) | Komma-Liste der Quell-Aufträge          |
| `nHasRechnungskorrektur` / `nKorrigiert` | bit |                                          |

→ **Hier holen wir Brutto/Netto-Summen, nicht aus `tRechnung`.**

### Adressen: `Rechnung.tRechnungAdresse` (n:1, je Rechnung typisch 2 Zeilen)

`nTyp` ist Diskriminator: pro Rechnung existieren beide Werte (`nTyp=0` und
`nTyp=1`), je 1.167 Mio Zeilen → 1:2-Beziehung.

**Verifiziert 2026-05-05** über Vergleich mit den semantischen Views
`Rechnung.vRechnungLieferadresse` / `vRechnungRechnungsadresse`:
- `nTyp=0` = **Lieferadresse**
- `nTyp=1` = **Rechnungsadresse**

| Spalte                 | Typ           |
|------------------------|---------------|
| `kRechnung` (FK)       | int           |
| `nTyp`                 | tinyint       | 0 / 1 (s.o.)                                  |
| `cFirma`, `cAnrede`, `cTitel`, `cVorname`, `cName` | nvarchar |               |
| `cStrasse`, `cAdresszusatz`, `cPLZ`, `cOrt`, `cLand`, `cBundesland` | nvarchar |  |
| `cISO`                 | nvarchar(5)   | Land-ISO                                      |
| `cTel`, `cMobil`, `cFax`, `cMail` | nvarchar |                                       |
| `cZusatz`, `cPostID`   | nvarchar      |                                               |
| `nZolldokumenteErforderlich` | bit     |                                               |

### Position-Basistabelle: `Rechnung.tRechnungPosition` (25 Spalten)

| Spalte                        | Typ              | Bedeutung                        |
|-------------------------------|------------------|----------------------------------|
| `kRechnungPosition` (PK)      | int              |                                  |
| `kRechnung` (FK)              | int              |                                  |
| `kAuftrag` / `kAuftragPosition` | int            | Quell-Auftragsbezug              |
| `kArtikel` / `cArtNr` / `cName` / `cEinheit` / `cUnitCode` | int/nvarchar |                  |
| `fAnzahl`                     | decimal(25,13)   | Menge                            |
| `fVkNetto`                    | decimal(25,13)   | Einzelpreis netto                |
| `fVkNettoGesamt`              | decimal(14,2)    | Position netto **gerundet**      |
| `fVkBruttoGesamt`             | decimal(14,2)    | Position brutto **gerundet**     |
| `fMwSt`                       | decimal(25,13)   | **Steuersatz % (z.B. 19.0)** — kein Betrag! |
| `fRabatt`                     | decimal(25,13)   |                                  |
| `nType`                       | tinyint          | Positionstyp (1=Artikel, 2=Versand, …) |
| `kSteuerschluessel`           | int              | FK `dbo.tSteuerschluessel`       |
| `kSteuerklasse`               | int              |                                  |
| `nSort`                       | int              | Sortier-Reihenfolge              |
| `kKonfigVaterRechnungPos` / `kStuecklisteRechnungPos` | int |                            |
| `fGewicht` / `fVersandgewicht` / `fEkNetto` | decimal |                              |
| `bRowversion`                 | timestamp        |                                  |

→ **Steuerbetrag pro Position** liegt nicht hier, sondern in
`Rechnung.tRechnungPositionEckdaten`.

### Position-Eckdaten: `Rechnung.tRechnungPositionEckdaten` (1:1 zu Position)

| Spalte               | Typ      |
|----------------------|----------|
| `kRechnungPosition`  | int (PK) |
| `fVKBrutto`          | decimal  | Einzelpreis brutto                  |
| `fMwStBetrag`        | decimal  | **Steuerbetrag in EUR**             |
| `fRabattbetrag`      | decimal  |                                     |
| `fGewichtGesamt`, `fVersandgewichtGesamt` |       |                       |

### Externe Belege — Basistabellen (Schema `Rechnung`)

Bestätigt 2026-05-05:

| Tabelle                              | Bedeutung                            | Zeilen   |
|--------------------------------------|--------------------------------------|----------|
| `Rechnung.tExternerBeleg`            | Header (Marketplace-Importe)         | 156k     |
| `Rechnung.tExternerBelegEckdaten`    | Eckdaten / Beträge                   | 156k     |
| `Rechnung.tExternerBelegPosition`    | Positionen                           | 184k     |
| `Rechnung.tExternerBelegTransaktion` | Zahlungs-/Transaktionsdaten          | 156k     |

→ Echte Marketplace-Importe — **ausschließlich Amazon** (VCS-Pfad ab 2024-11-01).
Otto liegt **nicht** hier, sondern wie eBay/Kaufland in `Rechnung.tRechnung`.
`Rechnung.tRechnung.nIstExterneRechnung=1` und `tExternerBeleg` sind **getrennte
Welten** mit getrenntem Schlüsselraum (`kRechnung` vs. `kExternerBeleg`).

#### `Rechnung.tExternerBeleg` (32 Spalten — Header)

| Spalte                 | Typ              | Bedeutung                            |
|------------------------|------------------|--------------------------------------|
| `kExternerBeleg` (PK)  | int              |                                      |
| `cBelegnr`             | nvarchar(50)     | Marketplace-Belegnummer              |
| `dBelegdatumUtc` / `dErstelltWawiUtc` | datetime2 |                              |
| `nBelegtyp`            | tinyint          | **0 = Rechnung B2C (146k, pos.), 1 = Gutschrift (9.5k, neg.), 2 = Restposten-Aufkäufer-Rechnung B2B (562, pos. avg 1.51€)** — Typ 2 sind Verkäufe an Großabnehmer (mit/ohne USt-IdNr.); Steuer-Engine entscheidet via `cKaeuferUstId`+Land-Differenz. |
| `kPlattform`           | int              | Marktplatz                           |
| `kPlattformKey`        | int              |                                      |
| `kFirmaHistory` / `cFirmaUstId` | int / nvarchar(30) | Eigene Firma + UStId         |
| `cWaehrungISO` / `fWaehrungsfaktor` | nchar(3)/dec |                              |
| `cKaeuferUstId`        | nvarchar(30)     | USt-IdNr. Käufer (B2B-Indikator)     |
| Rechnungsadresse-Block: `cRAName`, `cRAAdresse1..3`, `cRAOrt`, `cRAStaat`, `cRAPostcode`, `cRALandISO` (nchar(2)), `cRATelefon`, `cRAMail` |  | direkt am Header |
| `cBezugsbelegnr`       | nvarchar(50)     | z.B. Original-Rechnung bei Gutschrift |
| `cHinweis`, `cHerkunft` | nvarchar        |                                      |
| `nDebitorenNr`         | int              |                                      |
| `kSprache`, `kBenutzer`, `kKunde`, `kZahlungsart` | int |                       |
| `nSteuereinstellung`   | tinyint          |                                      |
| `bRowversion`          | timestamp        |                                      |

**Lieferadresse + Versandland** liegen nicht hier, sondern in `tExternerBelegTransaktion`.

#### `Rechnung.tExternerBelegEckdaten` (1:1 zu Beleg, 6 Spalten)

| Spalte             | Typ          | Bedeutung                                |
|--------------------|--------------|------------------------------------------|
| `kExternerBeleg`   | int (PK)     |                                          |
| `fVkBrutto`        | decimal      | Brutto gesamt (negativ bei Gutschrift)  |
| `fVkNetto`         | decimal      | Netto gesamt                             |
| `nIstStorniert`    | bit          |                                          |
| `nFehlercode`      | int          | 0 = ok                                   |

#### `Rechnung.tExternerBelegTransaktion` (26 Spalten — Liefer-/Versandadresse + Order-ID)

| Spalte                            | Typ           | Bedeutung                          |
|-----------------------------------|---------------|------------------------------------|
| `kExternerBelegTransaktion` (PK)  | int           |                                    |
| `kExternerBeleg` (FK)             | int           |                                    |
| `nTransaktionstyp`                | tinyint       |                                    |
| `cTransaktionId` / `cBezugstransaktionId` | nvarchar |                              |
| `dTransaktionsdatumUtc` / `dExternesAuftragsdatumUtc` | datetime2 |              |
| `cExterneAuftragsnummer`          | nvarchar(50)  | Marketplace-Order-ID               |
| `cKundenAuftragsnummer`           | nvarchar(50)  |                                    |
| Lieferadresse: `cLAName`, `cLAAdresse1..3`, `cLAOrt`, `cLAStaat`, `cLAPostcode`, `cLALandISO`, `cLATelefon` |  | **Lieferland!** |
| Versandland: `cVAOrt`, `cVAStaat`, `cVAPostcode`, `cVALandISO`, `cVALandWaehrungISO`, `fVALandWaehrungsfaktor` |  | **Lager-ISO** |
| `kVersandArt`                     | int           |                                    |

→ **`cVALandISO` = Lagerland-ISO**, **`cLALandISO` = Lieferland-ISO**.
   Externe Belege haben i.d.R. genau eine Transaktion (156k:156k 1:1).

#### `Rechnung.tExternerBelegPosition` (24 Spalten)

| Spalte                          | Typ              | Bedeutung                            |
|---------------------------------|------------------|--------------------------------------|
| `kExternerBelegPosition` (PK)   | int              |                                      |
| `kExternerBelegTransaktion` (FK)| int              | join auf Transaktion → dann Beleg    |
| `kExternerBelegPositionVater`   | int              | für Bundle/Konfig                    |
| `nKindtyp`                      | tinyint          |                                      |
| `nPositionstyp`                 | tinyint          |                                      |
| `kAuftragPosition`, `kBezugRechnungPosition`, `kBezugExternerBelegPosition` | int |             |
| `cArtNr` / `kArtikel` / `cText` (nvarchar 510) / `cEinheit` |  |                              |
| `fAnzahl`                       | decimal(25,13)   |                                      |
| `fVkNetto`, `fVkBrutto`         | decimal(25,13)   | Einzelpreise (negativ bei Gutschrift)|
| `fMwStSatz`                     | decimal(25,13)   | **Satz in % (z.B. 19.0, 20.0)**       |
| `fRabattBrutto`, `fRabattNetto` | decimal          |                                      |
| `cRabatttext`                   | nvarchar(50)     |                                      |
| `fEkNetto`                      | decimal(25,13)   |                                      |
| `kExterneId`                    | bigint           |                                      |
| `kSteuerklasse`, `kSteuerschluessel` | int         | (in Praxis fast immer JTL-leer)      |

### View `Rechnung.vBuchhaltungsuebersichtRechnung` (Header-Übersicht, schmal)

| Spalte                  | Typ          |
|-------------------------|--------------|
| `kRechnung`             | int          |
| `cRechnungsnr`          | nvarchar(50) |
| `cExterneAuftragsnummer`| nvarchar(50) |
| `fVkBruttoGesamt`       | decimal      |
| `fVkNettoGesamt`        | decimal      |
| `fOffenerWert`          | decimal      |
| `dErstellt`             | datetime     |
| `cWaehrung`             | char(3)      |

→ **Nicht exportgeeignet** (zu wenig Info). Wir lesen aus `tRechnung` direkt.

### View `Steuern.vSteuerschluesselDaten`

Auch nur IDs + `nSteuertyp` — **enthält keine DATEV-Codes**.

| Spalte                | Typ |
|-----------------------|-----|
| `kWarengruppe`        | int |
| `nPositionstyp`       | int |
| `kVersandArt`         | int |
| `kSteuersatz`         | int |
| `kSteuerzone`         | int |
| `kSteuerklasse`       | int |
| `kSteuerschluessel`   | int |
| `nSteuertyp`          | int |

### Basistabelle `dbo.tSteuerschluessel` — **wichtige Erkenntnis**

12 Spalten: `kSteuerschluessel`, `cName`, `cSteuerkonto`, `cSkontokonto`,
`cBonuskonto`, `cErloeskonto`, `cAusbuchungskonto`, `cAnzahlungskonto`,
`nAnzahlung`, `nAutomatik`, `nSchluesselnummer`, `bRowversion`.

**Live in `eazybusiness` enthält die Tabelle nur 1 (in Worten: einen) Eintrag:**

| kSteuerschluessel | cName     | cSteuerkonto | cErloeskonto | nSchluesselnummer | nAutomatik |
|-------------------|-----------|--------------|--------------|-------------------|------------|
| 87                | JTL2Datev | NULL         | NULL         | 14                | 0          |

→ Konsequenz: JTLs Steuerschlüssel-/DATEV-Mapping ist hier **nicht gepflegt**.
Alle Positionen referenzieren diesen Platzhalter (`kSteuerschluessel=87` —
sichtbar in beiden Position-Tabellen). Damit ist die strategische
Entscheidung „eigene Steuer-Engine" zwingend, nicht optional. JTLs gespeicherter
Steuerschlüssel taugt nicht einmal mehr als Plausi-Referenz auf Code-Ebene
— nur die Roh-VAT-Sätze (`fMwSt` / `fMwStSatz`) und Beträge sind brauchbar.

### Sekundäre Basistabellen

- `dbo.tBestellung`, `dbo.tBestellungAttribute`, `dbo.tBestellungAttributeKey`

### Plattform-Lookup `dbo.tPlattform`

Spalten: `nPlattform` (PK), `cName`, `cID`, `cWaehrung`, `nInet`, `nTyp`.

Relevante Codes (gekürzt):

| nPlattform | cName             | Bemerkung                                  |
|-----------:|-------------------|--------------------------------------------|
| 1          | JTL-Wawi          | manuell                                    |
| 2          | Onlineshop        | eigener Webshop                            |
| 8          | Weitere Verkaufskanäle (SCX) | u.a. Kaufland (über JTL-eazyAuction)|
| 31         | ebay.de           | (eigene Rechnungen)                        |
| 38/39/42/46 | ebay.fr/.it/.es/.pl | weitere ebay-Marktplätze                |
| 51         | Amazon.de         | EUR (extern, größter Volumen-Treiber)      |
| 53         | Amazon.co.uk      | GBP                                        |
| 54         | Amazon.fr         | EUR                                        |
| 56         | Amazon.it         | EUR                                        |
| 57         | Amazon.es         | EUR                                        |
| 60         | Amazon.nl         | EUR                                        |
| 63         | Amazon.pl         | PLN                                        |

Vollständige Liste: `SELECT * FROM dbo.tPlattform ORDER BY nPlattform`.

## Gutschriften / Rechnungskorrektur (erkundet 2026-05-05)

JTL nennt Gutschriften und Rechnungskorrekturen synonym. Die Datenstruktur:

- **`Rechnung.tRechnungKorrektur`** (3 Spalten, **leer** in eazybusiness):
  nur Mapping-Tabelle `kRechnungskorrektur ↔ kRechnung ↔ kRechnungNeu`. Wird
  vermutlich nur bei „Rechnung neu erstellen"-Workflow gefüllt. **Nicht relevant
  für DATEV.**
- **`dbo.tgutschrift`** (30 Spalten, 56 634 Belege total, 2026: 270):
  echte Gutschrift-Header für eigene Belege.
- **`dbo.tGutschriftPos`** (22 Spalten, 84 018): Positionen.
- **`Verkauf.lvRechnungskorrekturverwaltung`** (73 Spalten, View): UI-Sicht
  mit eingebauten Liefer-/Rechnungsadress-Blöcken — bequem für DATEV-Repository.
- **`Verkauf.lvRechnungskorrekturposition`** (19 Spalten, View): Position-Sicht.
- Amazon-VCS-Gutschriften kommen zusätzlich über `tExternerBeleg.nBelegtyp=1`
  (bereits in `_fetch_external` als `is_credit_note=True`).

### Schlüsselspalten `dbo.tgutschrift`

| Spalte                    | Typ            | Bedeutung                                     |
|---------------------------|----------------|-----------------------------------------------|
| `kGutschrift` (PK)        | int            |                                               |
| `kRechnung`               | int (NULL)     | FK auf Original-Rechnung — in 2026 immer gesetzt |
| `kKunde`                  | int (NULL)     |                                               |
| `cGutschriftNr`           | nvarchar(50)   | Belegnummer                                   |
| `cKurzText` / `cText`     | nvarchar       | Begründung                                    |
| `fPreis`                  | decimal        | Brutto                                        |
| `fMwSt`                   | decimal        | Steuerbetrag                                  |
| `dErstellt`               | datetime       |                                               |
| `cErloeskonto`            | nvarchar(64)   | DATEV-Erlöskonto                              |
| `cWaehrung` / `fFaktor`   | nvarchar/dec   |                                               |
| `cVersandlandWaehrung` + `fVersandlandWaehrungFaktor` |  | aber **kein** `cVersandlandISO` — Lagerland muss via JOIN auf `Rechnung.tRechnung` ermittelt werden |
| `kPlattform`              | int            |                                               |
| `kRechnungsAdresse`       | int            | FK Adresse                                    |
| `cKundeUstId`             | nvarchar(20)   |                                               |
| `nIstExtern`              | tinyint        | 0=eigen, 1=extern                             |
| `nStorno` / `nStornoTyp`  | bit/tinyint    |                                               |
| `nGutschriftStatus`       | tinyint        |                                               |
| `nAnVerkaufskanalUebertragen` | bit        |                                               |
| `dDruckdatum` / `dMaildatum` | datetime    |                                               |

### Schlüsselspalten `dbo.tGutschriftPos`

| Spalte                    | Typ            | Bedeutung                                     |
|---------------------------|----------------|-----------------------------------------------|
| `kGutschriftPos` (PK)     | int            |                                               |
| `tGutschrift_kGutschrift` | int (FK)       |                                               |
| `tArtikel_kArtikel`       | int            |                                               |
| `kRechnungPosition`       | int (NULL)     | FK auf Originalposition (für Steuerübernahme!)|
| `cArtNr` / `cString`      | nvarchar       |                                               |
| `nAnzahl`                 | decimal        | Menge                                         |
| `fVKPreis`                | decimal        | Einzelpreis brutto                            |
| `fVKNetto`                | decimal        | Einzelpreis netto                             |
| `fMwSt`                   | decimal        | Steuersatz % (nicht Betrag!)                  |
| `fRabatt`                 | decimal        |                                               |
| `fVkNettoGesamt`          | decimal        |                                               |
| `fVkBruttoGesamt`         | decimal        |                                               |
| `nSort`                   | int            |                                               |

### Routing-Konsequenz für DATEV-Export

- 2026: 261 Gutschriften (Snapshot-Zählung damals mit `nStorno=0` gezogen, dieser
  Filter wird inzwischen nicht mehr angewendet). Alle haben `kRechnung`-FK
  gesetzt → Lagerland via `Rechnung.tRechnung.cVersandlandISO`-JOIN immer
  ermittelbar.
- Plattform-Verteilung 2026: Amazon (84), Otto/Kaufland via SCX (80), eBay (30),
  XML/JTL-Wawi (67).
- **Dubletten-Verdacht:** 49 Gutschriften mit `nIstExtern=1` (Amazon-Plattformen).
  Diese könnten parallel in `tExternerBeleg.nBelegtyp=1` liegen → Dedup-Logik
  oder Quell-Auswahl klären, **bevor** der Repository-Pfad implementiert wird.

## Stichtag 2024-11-01 (Amazon-Routing-Wechsel)

JTL hat zum **1. November 2024** die Ablage von Amazon-Rechnungen geändert:

- **Bis 2024-10-30:** Amazon-Rechnungen lagen in `Rechnung.tRechnung` mit
  `cZahlungsart='AmazonPayments'`. `tExternerBeleg` lief nur als Pilot
  (10-50 Belege/Monat).
- **Ab 2024-11-01:** Amazon-Rechnungen kommen über VCS direkt in
  `Rechnung.tExternerBeleg` (3-20k/Monat). `tRechnung` enthält ab da nur
  noch die wenigen Fälle, in denen der User eine fehlerhafte Amazon-Rechnung
  in `tExternerBeleg` löscht und manuell in JTL neu erzeugt.

**Konsequenz für DATEV-Export:**

- Datums-Untergrenze: `>= 2024-11-01` (Belege davor sind nicht relevant; Fokus 2026).
- Beide Quellen parallel lesen — sie sind ab 2024-11 **disjunkt** (keine
  Dubletten erwartet, da tExternerBeleg-Belege beim Löschen wirklich entfernt
  und erst dann in tRechnung neu erzeugt werden).

## Architektonische Konsequenz

Repository-Layer liest direkt aus den Basistabellen:

- **Eigene Rechnungen** (eBay, Kaufland, Otto, JTL-manuell, Amazon-Sonderfälle):
  - Header: `Rechnung.tRechnung` (Routing) + `dbo.tRechnung` (für `cErloeskonto`)
  - Summen: `Rechnung.tRechnungEckdaten`
  - Adressen: `Rechnung.tRechnungAdresse` (nTyp=0 + nTyp=1)
  - Positionen: `Rechnung.tRechnungPosition` + `tRechnungPositionEckdaten`
  - Plattform-Name: Join `dbo.tPlattform` über `kPlattform`
  - Filter: `nIstEntwurf=0 AND nIstProforma=0`. **`nStorno=1` bleibt drin** (Gutschrift muss mitgelesen werden). **Kein Filter auf `nIstExterneRechnung`** — Otto trägt zwar `=1`, gehört aber in diesen Pfad.
- **Externe Rechnungen** (nur Amazon-VCS, ab 2024-11-01):
  - Header: `Rechnung.tExternerBeleg`
  - Summen: `tExternerBelegEckdaten`
  - Liefer-/Versandadresse + Order-ID: `tExternerBelegTransaktion`
  - Positionen: `tExternerBelegPosition` (Join über kExternerBelegTransaktion)
  - Optional: View `vExternerBelegSteuerermittlungsdaten` für vorausgewertetes
    `nReverseCharge`-Flag
  - `nBelegtyp`: 0 = Rechnung B2C, 1 = Gutschrift (Beträge negativ), 2 = Restposten-Aufkäufer-Rechnung B2B
- **Gutschriften (eigene)** = JTL-Rechnungskorrektur:
  `Verkauf.vRechnungskorrekturposition` + `lvRechnungskorrekturen`
  (TBD — bisher nicht erkundet)

DATEV-Steuerschlüssel-Codes existieren in `dbo.tSteuerschluessel` **nicht
gepflegt** (1 Platzhalter-Eintrag). Eigene Steuer-Engine ist also einzige Quelle.

## Beispielqueries

```sql
-- Spalten der Buchhaltungsuebersicht-Views inspizieren
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'Rechnung'
  AND TABLE_NAME   = 'vBuchhaltungsuebersichtRechnung'
ORDER BY ORDINAL_POSITION;
```

### View `Rechnung.vBuchhaltungsuebersichtRechnungPosition`

Schmal — keine Steuer-/Länder-Info, nur Beträge:

| Spalte               | Typ          | Bedeutung                               |
|----------------------|--------------|-----------------------------------------|
| `kRechnung`          | int          | FK Header                               |
| `kRechnungPosition`  | int (PK)     |                                         |
| `cArtNr`, `cName`    | nvarchar     | Artikel                                 |
| `fAnzahl`            | decimal      | Menge                                   |
| `fVKBruttoGesamt`    | decimal      | Brutto Position                         |
| `fVKNettoGesamt`     | decimal      | Netto Position                          |
| `fMwSt`              | decimal      | MwSt-Betrag                             |
| `fRabatt`            | decimal      | Rabatt                                  |
| `nType`              | tinyint      | Positionstyp                            |

→ Kein expliziter `kSteuerschluessel` je Position! Steuerschlüssel muss über
`Steuern.vSteuerschluessel` (Routing) ermittelt werden — Inputs: Warengruppe
des Artikels, Positionstyp, Versandart, Steuersatz/-zone/-klasse. Das passiert
bei eigenen Rechnungen vermutlich in `vBuchhaltungsuebersichtRechnung*` selbst
(via interner Logik) — TBD: prüfen, ob die Header-View je Position einen Code
mitliefert.

### View `Rechnung.vExternerBelegSteuerermittlungsdaten` (externe Belege)

**Eigener Schlüsselraum** `kExternerBeleg` / `kExternerBelegPosition` —
externe Rechnungen (nur Amazon-VCS) leben **nicht** unter `kRechnung`.
`Rechnung.tRechnung.nIstExterneRechnung=1` und `tExternerBeleg` sind getrennt.

| Spalte                  | Typ           | Bedeutung                                |
|-------------------------|---------------|------------------------------------------|
| `kExternerBeleg`        | int           | PK Header                                |
| `kExternerBelegPosition`| int           | PK Position                              |
| `kFirma`                | int           | Mandant                                  |
| `cVersandlandIso`       | nchar(2)      | Lager                                    |
| `cRechnungsLandIso`     | nchar(2)      | Rechnungsadresse Land                    |
| `cRechnungBundesland`   | nvarchar(100) |                                          |
| `cLieferlandIso`        | nchar(2)      | Lieferadresse Land                       |
| `cLieferbundesLand`     | nvarchar(100) |                                          |
| `cKundeUstId`           | nvarchar(30)  |                                          |
| `nReverseCharge`        | bit           | **direkt gepflegtes Flag**               |
| `kArtikel`              | int           |                                          |
| `kWarengruppe`          | int           | Input für Steuerschlüssel-Routing        |
| `nPositionstyp`         | tinyint       |                                          |
| `fMwStSatz`             | decimal       | Steuersatz % der Position                |
| `cPosition`             | nvarchar(510) | Beschreibungstext                        |
| `cBelegnr`              | nvarchar(50)  | Externe Belegnummer                      |

Sehr nützlich: getrennt **Versand-/Rechnungs-/Lieferland** + bereits
ausgewertetes `nReverseCharge`-Flag.

### View `Steuern.vSteuerschluessel` (Routing-Tabelle)

| Spalte                              | Bedeutung                                   |
|-------------------------------------|---------------------------------------------|
| `kWarengruppe`, `nPositionstyp`, `kVersandArt` | Input-Schlüssel               |
| `kSteuersatz`, `kSteuerzone`, `kSteuerklasse`  | weitere Inputs                |
| `kSteuerschluessel`                 | Standard-Schlüssel                          |
| `kSteuerschluesselIGL`              | innergemeinschaftliche Lieferung (B2C OSS?) |
| `kSteuerschluesselUstIGL`           | USt bei IGL                                 |
| `kSteuerschluesselReverseCharge`    | EU-B2B / Drittland Reverse-Charge           |

Alles IDs — **die echten DATEV-Codes** stehen in
`Steuern.vSteuerschluesselDaten` (TODO: Struktur einlesen).

## Offene Punkte (nach Erkundung Teil 2)

1. **`nTyp` in `Rechnung.tRechnungAdresse`** — welcher Wert ist Liefer-, welcher
   Rechnungsadresse? Konvention prüfen (vermutlich `0=Liefer`, `1=Rechnung`).
2. **`nSteuereinstellung`-Werte in `Rechnung.tRechnung`** — Bedeutung von
   `0/10/15/20`. Lookup nicht in DB gefunden; ggf. JTL-Doku oder Code
   inspizieren. Für die Engine evtl. nicht zwingend nötig (wir lesen Rohfakten).
3. **Marketplace-Facilitator-Erkennung** UK/CH-Amazon: Kombination aus
   `kPlattform` (53 = Amazon.co.uk) + `cVALandISO`/`cVersandlandISO` ∈ {GB, CH}.
   Verifizieren ob Beleg-Brutto/Netto = 0 oder ob Steuer in eigenem Feld
   ausgewiesen ist.
4. **Gutschriften eigener Rechnungen** — Schema `Rechnung.tRechnungKorrektur`
   noch erkunden (Spalten + Verknüpfung zu Originalrechnung).
5. **Stornoeinträge** in `Rechnung.tRechnungStorno` — Folge-Auswirkung auf
   Buchungsexport (Storno-Gutschrift?).
