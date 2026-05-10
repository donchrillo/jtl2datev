# DutyPay-Export-Format

> Spezifikation für OSS-Meldungsdatei (Mehrwertsteuermeldungen).
> Basiert auf Reverse-Engineering der Jera-Outputs (`samples/jera/DutyPay-SALE-2026-*.csv`) und DATEV-Pflichtfeld-Spec.
> Stand: 2026-05-07.

## Überblick & Scope

DutyPay ist die Schnittstelle für digitale OSS-Meldungen in der EU. Das Format wird für Umsatzsteuer-Meldungen bei grenzüberschreitenden Verkäufen genutzt.

## DATEV-Pflichtfeld-Profile

DATEV definiert vier **Meldungsprofile** mit unterschiedlichen Feldanforderungen:

1. **Umsatzsteuermeldungen** (reine OSS) — **Unser Use Case**
2. Umsatzsteuermeldungen + SAF-T + Intrastat (erweitert für Stat. Inlandsmeldung; nicht für uns)
3. Umsatzsteuermeldungen + Intrastat (ohne SAF-T; nicht für uns)
4. Umsatzsteuermeldungen + SAF-T (ohne Intrastat; nicht für uns)

Profile 2–4 sind **out of scope**: Sie wurden früher als Vollkunden-Pakete angeboten; für JTL-Wawi-Belege ist nur **Profil 1** (OSS) implementiert. Felder wie `CommodityCode`, `ItemWeight`, `TransportCode` sind nur für Intrastat/SAF-T relevant.

**Breite Befüllung:** Das Exportformat wird bewusst **breit** befüllt — alle Auslandsverkäufe (B2C OSS, B2B Reverse-Charge, Export, Refunds) landen in einer Datei. DutyPay sortiert intern nach OSS-relevanten Kriterien, nicht wir.

**Granularität:** 1 Zeile pro Belegdokument. `MarketZoneGross`/`MarketZoneNet` enthalten die Summe über alle Belegpositionen (Versand-/Verpackungs-Positionen mit 0 € fließen damit transparent ein). Begründung: Profil 1 (OSS) verlangt keine artikelweise Auflösung; Sample-Analyse Q1 2026 zeigt 0 Belege mit gemischten VAT-Sätzen pro Dokument, daher kein Informationsverlust.

## Datei-Format

| Eigenschaft | Wert |
|---|---|
| **Encoding** | UTF-8 (BOM optional) |
| **Zeilenumbruch** | LF oder CRLF |
| **Trennzeichen** | Semikolon `;` |
| **Dezimalzeichen** | Komma `,` |
| **Stringquoting** | Keine (einfache Werte) — Felder mit Semikolon/Zeilenumbruch escapen via Verdopplung oder Anführungszeichen (Standard CSV) |
| **Datumsformat** | `DD.MM.YYYY` |
| **Header-Zeile** | Ja (Zeile 1) |
| **Dateiname-Konvention** | `DutyPay-SALE-YYYY-MMM.csv` (z.B. `DutyPay-SALE-2026-JAN.csv`) |

## Spalten-Referenz

**98 Spalten insgesamt.** Tabelle mit Spalte | Typ | Beispielwert | Belegung % (aus Samples geschätzt) | Quelle | Notizen:

| Spalte | Typ | Beispiel | Belegung | Quelle | Notizen | OSS-Pflicht |
|---|---|---|---|---|---|---|
| Positions-Nr. | int | `1` | 100% | seq | Fortlaufende Nummer je Position innerhalb Datei | Pflicht |
| **KindOfBusiness** | enum | `SALE`, `REFUND`, `B2B`, `EXPORT`, `B2B-REFUND`, `EXPORT-REFUND` | 100% | Regel-Engine (s.u.) | Entscheidungsbaum nach Lager/Ziel/Kundentyp | Pflicht |
| **TransactionID** | nvarchar | `406-0538474-1507531` oder `cbn4wjs65s` | 100% | `cExterneAuftragsnummer` ohne `_N`-Suffix | **Marketplace-Order-ID (Amazon, Otto, etc.) ohne Mehrteil-Suffix.** JTL speichert Mehrteil-Marketplace-Sendungen mit `_1`, `_2`, etc. (z.B. `406-0538474-1507531_1`), Engine schreibt nur die Basis-Order-ID (z.B. `406-0538474-1507531`). Ermöglicht Suche im JTL-Frontend und Join mit DATEV-Export (gleiche ID dort in Belegfeld 1). Eindeutigkeit pro Beleg liegt in DocumentID. | Optional |
| **DocumentID** | nvarchar | `R-DE-249030238-2026-1` | 100% | JTL Belegnummer (eindeutig) | Eindeutiger Beleg-Key für Grouping. Eigene Rechnungsnummern haben kein Buchstaben-Prefix → Excel kann auf reine Ziffernfolgen mit Wissenschaftsnotation reagieren. | Pflicht |
| **ReportingPeriod** | nvarchar | `2026-JAN` | 100% | Belegdatum Monat | Format: `YYYY-MMM` (JAN/FEB/MAR…/DEC). Siehe Datumsregel (Sektion unten). | Bedingt |
| **DepartureDate** | date | `02.01.2026` | 100% | JTL `dErstellt` / `dBelegdatumUtc` | Versand-/Beleg-Datum. Mind. 1 von {ReportingPeriod, DepartureDate, ArrivalDate} erforderlich. | Bedingt |
| **ArrivalDate** | date | `02.01.2026` | 100% | JTL `dErstellt` / `dBelegdatumUtc` | praktisch = DepartureDate. Mind. 1 Datum erforderlich. | Bedingt |
| **DocumentDate** | date | `02.01.2026` | 100% | JTL `dErstellt` | Rechnungsdatum | Pflicht |
| **VatZone** | ISO-2 | `DE`, `FR`, `IT`, `PL`, `CZ`, `ES`, `GB`, `CH` | 100% | abgeleitet: Lagerland (SourceZone) | Das Lagerland — physischer Versandort. **LEER bei B2B / B2B-RC / Export / Export-RC / FC_Transfer / Inbound / Outbound / Purchase-* / Commingling-Buy-RC.** | Bedingt |
| **VATRate** | decimal % | `19` | ~40% (nur bei B2C/Inland) | abgeleitet | Steuersatz des VatZone. Leer bei B2B (Reverse-Charge). **LEER bei B2B / B2B-RC / Export / Export-RC / FC_Transfer / Inbound / Outbound / Purchase-* / Commingling-Buy-RC.** | Bedingt |
| **VATAmount** | decimal EUR | leer im Sample | <1% | abgeleitet | Steuerbetrag. Praktisch immer leer (DutyPay rechnet selbst) | Optional |
| **SourceZone** | ISO-2 | `DE`, `FR`, `IT`, `PL`, `CZ`, `ES`, `GB` | 100% | JTL `cVersandlandISO` | Lagerland (physischer Versandort) | Pflicht |
| **SourceZoneZip** | nvarchar | `38899` | ~40% | JTL Lagerort-PLZ | postleitzahl des Lagers — praktisch oft leer | Optional |
| **SourceZoneVatID** | nvarchar | `DE249030238` | ~50% | JTL `cUstId` (Eigene USt-IdNr. des Lagers) | Unsere lokale USt-IdNr. des Lagers. **(Pflicht) bei PURCHASE / PURCHASE-REFUND / PURCHASE-CROSSBORDER / COMMINGLING-BUY / COMMINGLING-BUY-RC.** Leer bei B2C SALE. | Bedingt |
| **SourceZoneVatRate** | decimal % | `19`, `20`, `21`, `22`, `23` | ~50% | abgeleitet | Steuersatz des Lagers (z.B. für Domestic oder bei B2B zur Verifikation) | Optional |
| **SourceZoneCurrencyCode** | ISO-4217 | `EUR`, `PLN`, `CZK` | ~50% | Lager-Land → ISO-4217 Lookup-Tabelle | **Aus dem Lagerland abgeleitet** (nicht aus der Beleg-Währung). EU-Lager → EUR; CZ → CZK; PL → PLN; SE → SEK; GB → GBP; etc. | Pflicht |
| **SourceZoneGross** | decimal | leer im Sample | <1% | abgeleitet | Brutto im Lagerland — praktisch nie gefüllt | Optional |
| **SourceZoneNet** | decimal | leer im Sample | <1% | abgeleitet | Netto im Lagerland — praktisch nie gefüllt | Optional |
| **TargetZone** | ISO-2 | `DE`, `IT`, `FR`, `BE`, `CH` | 100% | JTL Lieferadress-Land | Bestimmungsland (Kundenadresse) | Pflicht |
| **TargetZoneZip** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TargetZoneVatID** | nvarchar | `IT05041920967`, `ATU49548100`, leer | ~30% | JTL `cKundeUstId` | **(Pflicht) bei B2B / B2B-REFUND** mit Reverse-Charge. B2C/OSS: leer. | Bedingt |
| **TargetZoneVatRate** | decimal % | `19`, `20`, `22`, `23`, `24` | ~60% | abgeleitet | Steuersatz des Bestimmungslandes. Leer bei B2B Reverse-Charge (0%). | Optional |
| **TargetZoneCurrencyCode** | ISO-4217 | `EUR`, `GBP`, `SEK`, etc. | ~60% | Empfänger-Land → ISO-4217 Lookup-Tabelle | **Aus dem Empfänger-Land abgeleitet** (nicht aus der Beleg-Währung). EU-Empfänger in EUR-Zone → EUR; UK-Empfänger → GBP; etc. | Pflicht |
| **TargetZoneGross** | decimal | leer im Sample | <1% | abgeleitet | Brutto im Zielland — praktisch nie gefüllt | Optional |
| **TargetZoneNet** | decimal | leer im Sample | <1% | abgeleitet | Netto im Zielland — praktisch nie gefüllt | Optional |
| **MarketZone** | ISO-2 | `DE`, `IT`, `FR`, `PL`, `CZ`, `ES`, `GB` | 100% | Plattform-Land Mapping | **Marktplatz-Registrierungsland aus `marketplace_country`** (abgeleitet von `kPlattform` über Mapping in `core/db_jtl.py`). 10 Amazon-Sites: `Amazon.de`→DE, `Amazon.fr`→FR, `Amazon.it`→IT, `Amazon.es`→ES, `Amazon.com.be`→BE, `Amazon.nl`→NL, `Amazon.se`→SE, `Amazon.pl`→PL, `Amazon.co.uk`→GB. Generisches `Amazon` und unbekannte Plattformen: Fallback Lager-Land. *Verifizierung:* MarketZone ist pro DocumentID konstant (13387/13388 Belege bestätigt). | Pflicht |
| **MarketZoneCurrencyCode** | ISO-4217 | `EUR`, `PLN`, `GBP`, `SEK`, `CZK` | 100% | MarketZone-Land → ISO-4217 | **Aus dem MarketZone-Land abgeleitet** (nicht aus der Beleg-Währung). | Pflicht |
| **MarketZoneGross** | decimal | `19,95`, `202,00`, `-16,22` | 100% | JTL Beleg-Aggregat | **Beleg-Brutto** (Summe über alle Positionen) — Vorzeichen: negativ bei REFUND/B2B-REFUND/EXPORT-REFUND. **Mind. 1 Betrag** (Source/Target/MarketZone Gross/Net) erforderlich. | Bedingt |
| **MarketZoneNet** | decimal | `16,76`, `202,00`, `-13,63` | 100% | JTL Beleg-Aggregat | **Beleg-Netto** (Summe über alle Positionen) — Vorzeichen: negativ bei REFUND. **Mind. 1 Betrag** erforderlich. | Bedingt |
| **ItemID** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **ItemName** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **ItemDescription** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **CommodityCode** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **ItemQuantity** | decimal | `1` | 100% | konstant | Konstant `1` (Pflicht-konform für B2B/Export laut Spec; tatsächliche Stückzahl ist für reine OSS irrelevant) | Bedingt |
| **ItemUnit** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **ItemSalesPrice** | decimal | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **ItemPurchasePrice** | decimal | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **ItemCurrencyCode** | ISO-4217 | `EUR` | 100% | JTL Belegwährung | Währung des Rechnungsbetrags | Optional |
| **ItemWeight** | decimal | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransportCode** | int | `5` | 100% | konstant `5` | Versandart-Kennung. Konstant für Profil 1. | Optional |
| **ItemManufacturer** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **ItemManufacturerZone** | ISO-2 | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **MPN** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **Brand** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **GTIN** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **ASIN** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **ISBN** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **UPC** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **JAN** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TPCompanyName** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **PostingDateInvoice** | date | `02.01.2026` | 100% | JTL `dErstellt` | Buchungsdatum (= DocumentDate) | Optional |
| **TransactionPartner Form Of Address** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner First Name** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner Placeholder 1** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner Family Name** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner Placeholder 2** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner Tax-ID** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner Street** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner House Number** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner Additional Address** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner ZIP** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner City** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner Region** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **TransactionPartner Country IsoCode** | ISO-2 | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Company Name** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Form Of Address** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress First Name** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Placeholder 1** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Family Name** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Placeholder 2** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Placeholder 3** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Street** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress House Number** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Additional Address** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress ZIP** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress City** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Region** | nvarchar | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **BillingAddress Country ISOCode** | ISO-2 | (leer) | 0% | — | leer (Profil 1 / Invoice-Granularität) | Optional |
| **Incoterms** | nvarchar | `DDP` | ~6% | abgeleitet | Lieferbedingung. Wert `DDP` ⇔ `KindOfBusiness ∈ {B2B, EXPORT, B2B-REFUND, EXPORT-REFUND}`; sonst leer. | Optional |
| **TAX_REPORTING_SCHEME** | nvarchar | `UK_VOEC-IMPORT` | ~0,3% | abgeleitet | Wert `UK_VOEC-IMPORT` ⇔ `KindOfBusiness ∈ {EXPORT, EXPORT-REFUND}` UND `TargetZone == GB`. Sonst leer. (UK Marketplace Import-Schema) | Optional |
| **TAX_COLLECTION_RESPONSIBILITY** | nvarchar | `MARKETPLACE`, leer | ~1,6% | abgeleitet | Wert `MARKETPLACE` ⇔ `KindOfBusiness ∈ {EXPORT, EXPORT-REFUND}` UND Beleg ist Marktplatz-Verkauf (externe Order-ID aus JTL). Sonst leer. | Optional |
| **Placeholder 4–20** | — | leer | 0% | — | **Reserveplatzhalter — nicht befüllen** | Optional |

## `KindOfBusiness`-Entscheidungstabelle

Die Engine muss für jede Position den korrekten Wert ermitteln:

| Bedingung | `KindOfBusiness` | Beispiel | Merkmale |
|---|---|---|---|
| **Lagerland == Zielland, beliebige Währung** | `SALE` | DE→DE | Inlandverkauf, volle USt des Landes |
| **Lagerland != Zielland, EU, Kunden-USt-IdNr. vorhanden & gültig, Rechnung (nicht Gutschrift)** | `B2B` | DE→IT, Kunden-USt vorhanden | Reverse-Charge (EU-Lieferung), 0% USt|
| **Lagerland != Zielland, Drittland (nicht EU+GB+CH), Rechnung** | `EXPORT` | DE→CH, DE→TR | Ausfuhr steuerfrei |
| **Lagerland != Zielland, EU, B2C (kein Kunden-USt oder ungültig), Rechnung** | `SALE` (nicht explizit) | DE→IT, Kunde Privatperson | OSS-Verfahren (Steuersatz des Ziellands) — Samples zeigen: diese werden als `SALE` markiert **wenn Lagerland = Zielland**, ansonsten `SALE` auch grenzüberschreitend |
| **Beleg = Gutschrift, Lagerland == Zielland** | `REFUND` | DE→DE, negative Beträge | Storno/Rückgabe |
| **Beleg = Gutschrift, Lagerland != Zielland, EU, mit Kunden-USt** | `B2B-REFUND` | Storno zu B2B | Gutschrift zu Reverse-Charge-Position |
| **Beleg = Gutschrift, Drittland** | `EXPORT-REFUND` | Storno zu Export | Gutschrift zu Ausfuhr |

**Verifizierung aus Samples:**
- **`SALE`**: JAN/FEB/MAR 95%+ (alles DE→DE, Inlandverkäufe, `KindOfBusiness=SALE`)
- **`B2B`**: Erkennbar an `TargetZoneVatID` gefüllt, `TargetZoneVatRate=0%`, Reverse-Charge-Info
- **`EXPORT`**: `TargetZone ∈ {CH, GB, TR}` (Drittländer), `KindOfBusiness=EXPORT`, oft `TAX_COLLECTION_RESPONSIBILITY=MARKETPLACE`
- **`REFUND`**: Erkennbar an negativem `MarketZoneGross` und `MarketZoneNet`
- **`B2B-REFUND`, `EXPORT-REFUND`**: Wenige Beispiele in Samples, gleiche Vorzeichen-Regel wie REFUND

**Zugleich befüllte Felder:** `EXPORT` + `TargetZone=GB` → `TAX_REPORTING_SCHEME=UK_VOEC-IMPORT`. `EXPORT` + externe Order-ID → `TAX_COLLECTION_RESPONSIBILITY=MARKETPLACE`.

## Weitere KindOfBusiness-Werte (nicht implementiert)

DATEV definiert zusätzliche Werte, die wir aktuell **nicht abbilden** (out of scope für JTL-Wawi-Belege):

| KindOfBusiness | Beschreibung | Grund: Out of Scope |
|---|---|---|
| `SERVICE` | Dienstleistung für Kunden erbracht | Warenkonto (nicht für JTL-Wawi relevant) |
| `RETURN` | Rücksendung der Ware (Warenbewegung ohne Steuerwirkung) | Lagerverwaltungs-Tool (kommt später, Amazon-basiert) |
| `FC_TRANSFER` | Warenbewegung zwischen Versandlagern | Lagerverwaltungs-Tool |
| `INBOUND` | Händler liefert Ware ins Versandlager | Lagerverwaltungs-Tool (Empfang) |
| `OUTBOUND` | Warenuntergang oder Entnahme aus Versandlager | Lagerverwaltungs-Tool (Ausgang) |
| `IMPORT` | Einfuhr von Waren (Einfuhrumsatzsteuerpflichtig) | Einkauf-Tool (separates System) |
| `IMPORT-POSTPONED` | Zurückgestellte Einfuhr (nicht sofort steuerpflichtig) | Einkauf-Tool |
| `SAMPLE` | Mustersendungen und Geschenke (kostenlos) | Nicht in JTL-Standardprozessen |
| `PURCHASE` | Einkauf innerhalb eines Landes | Einkauf-Tool (Vendor-Invoices) |
| `PURCHASE-CROSSBORDER` | Grenzüberschreitender Einkauf | Einkauf-Tool |
| `COMMINGLING-BUY` | Amazon Commingling mit Steuerbetrag > 0 | Amazon-Report-Tool (Einkauf) |
| `COMMINGLING-BUY-RC` | Amazon Commingling mit Steuerbetrag = 0 | Amazon-Report-Tool |

**Implementierte Werte (OSS-Meldung):** `SALE`, `REFUND`, `B2B`, `B2B-REFUND`, `EXPORT`, `EXPORT-REFUND`.

## Refund-Handling

**Vorzeichen-Regel:** Gutschriften (Refunds, Stornos) sind **negativ** in beiden `MarketZoneGross` und `MarketZoneNet`.

**Sonderfall: Storno einer Rechnungskorrektur (SRK):**
Belegnummern mit Prefix `SRK` (z.B. `SRK202450012113`) kennzeichnen das Storno einer Rechnungskorrektur (=Gutschrift). Ökonomisch ist das eine **Rückgängigmachung der Gutschrift**, daher wird SRK als **SALE mit positivem Vorzeichen** behandelt (nicht als REFUND). Beispiel: Kunde 11067353, fälschliche Rechnungskorrektur wird via SRK storniert → DutyPay erfasst das als Erlös.

**Beispiel aus MAR-Sample (Zeile 809, DocumentID `DE60009ANL56FQ`):**
```
KindOfBusiness;...;MarketZoneGross;MarketZoneNet;...;VatZone
REFUND;...;-10,9;-9,08;...;FR
```

Lager = `DE`, Ziel = `FR`, aber `VatZone=FR` (Steuerzone ist Frankreich, weil ursprüngliche SALE zu FR ging, Refund kommt auch von FR-Adresse). Beträge negativ.

## Beträge: MarketZone vs. Source/Target

**Kernregel nach DATEV-Spec:**
- `SourceZoneGross/Net` (Spalten 17/18) und `TargetZoneGross/Net` (Spalten 24/25) sind **technisch Pflichtfelder** für Betrags-Validierung
- **Praktische Befüllung (Samples & Jera):** < 1% tatsächlich befüllt — DutyPay/Jera füllt diese intern

**Jera-Konvention (seit Jahren produktiv):**
- `MarketZoneGross/Net` (Spalten 28/29) werden als **Hauptbetrags-Felder** genutzt
- Diese sind **nicht Teil der DATEV-Pflichtfeld-Liste**, sondern Jera-Eigenbau
- DutyPay akzeptiert und verarbeitet diesen Ansatz

**Unser Engine:**
- Befüllt **nur MarketZone[Gross/Net]** (Positionale Beträge in Belegwährung)
- Lässt `SourceZone[Gross/Net]` und `TargetZone[Gross/Net]` leer
- **Konformität:** Kompatibel mit Jera-Output, DutyPay validiert korrekt

**Zukunftsoptionen:**
- Optional: Source/Target-Beträge zusätzlich befüllen für strikte DATEV-Konformität
- Aktuell nicht nötig, da DutyPay-Akzeptanz seit Jahren bestätigt

## Zone-Felder – Semantik

| Feld-Gruppe | Befüllung (aus Samples) | Bedeutung |
|---|---|---|
| **SourceZone** | immer | Physischer Versandort (Lagerland) |
| **SourceZoneVatID** | ~50%: bei B2B, OSS-Cross-Border | Unsere UStID des Lagers — leer bei reinem B2C SALE |
| **SourceZoneVatRate** | ~50% gefüllt | Steuersatz des Lagers (zur Validierung) |
| **SourceZone[Gross/Net]** | praktisch immer leer (<1%) | Betrag im Lagerland — **nicht befüllen** (Jera-Konvention) |
| **TargetZone** | immer | Kundenadresse-Land (Bestimmungsland) |
| **TargetZoneVatID** | ~30%: nur bei B2B mit USt-IdNr. | Kunden-USt (Reverse-Charge-Indikator) |
| **TargetZoneVatRate** | ~60%: bei B2C/OSS, 0% bei B2B | Steuersatz des Ziellands |
| **TargetZone[Gross/Net]** | praktisch immer leer (<1%) | Betrag im Zielland — **nicht befüllen** (Jera-Konvention) |
| **MarketZone** | immer | Marktplatz-Registrierungsland (oft = Lagerland oder DE) |
| **MarketZone[Gross/Net]** | immer | **Positionale Brutto/Netto in Belegwährung** — mit Vorzeichen (negativ = Refund) — **primäre Beträge** |

**Interpretation:** DutyPay nutzt `SourceZone` / `TargetZone` / `MarketZone` zur Klassifizierung; die echten Beträge kommen in `MarketZone[Gross/Net]`.

## Artikel-Stammdaten-Felder

**Im aktuellen Profil 1 (OSS-Meldung) sind alle Artikel-Stamm-Felder leer,** da die Granularität auf Belegeben liegt und OSS-Meldungen keine artikelweise Auflösung verlangen. Dies deckt sich mit der Q1-2026-Sample-Analyse: 0 Belege mit gemischten VAT-Sätzen pro Dokument.

Folgende Felder waren in Jera-Samples zu referenziellen Zwecken dokumentiert und bleiben für evtl. erweiterte Profile 2/4 (mit Intrastat/SAF-T) relevant:

## Adressfelder – TransactionPartner vs. BillingAddress

**Im aktuellen Profil 1 (OSS-Meldung) sind alle Adressfelder leer,** da OSS-Meldungen keine Adress-Details verlangen.

Die folgende Tabelle ist eine Referenz für evtl. erweiterte Profile 2/4 (mit SAF-T/Intrastat), wo Adressen relevant sind:

| Aspekt | TransactionPartner | BillingAddress | Quelle JTL |
|---|---|---|---|
| **Bedeutung** | Lieferadresse (wo wird geliefert) | Rechnungsadresse (Vertragspartner) | `tRechnungAdresse.nTyp: 0=Liefer, 1=Rechnung` |
| **Nutzung in DutyPay (Profile 2/4)** | primär (für `TargetZone` / `TargetZoneZip`) | sekundär (für Audit/Compliance) | |
| **Land (IsoCode)** | = `TargetZone` | oft = `TargetZone`, kann abweichen (B2B Konzernstrukturen) | |

## Abgeleitete Felder – Regeln

Vier Felder werden vollständig aus anderen Daten berechnet. Folgende Tabelle fasst die Logik zusammen:

| Feld | Bedingung | Wert | Belegung | Hintergrund |
|---|---|---|---|---|
| **TAX_REPORTING_SCHEME** | `KindOfBusiness ∈ {EXPORT, EXPORT-REFUND}` UND `TargetZone == GB` | `UK_VOEC-IMPORT` | ~0,3% | UK Marketplace Import-Schema (DAC7/IOSS/VOEC) |
| | sonst | (leer) | ~99,7% | |
| **TAX_COLLECTION_RESPONSIBILITY** | `KindOfBusiness ∈ {EXPORT, EXPORT-REFUND}` UND Marktplatz-Verkauf | `MARKETPLACE` | ~1,6% | Marktplatz (z.B. Amazon) hat Steuer eingezogen; erkennbar an externer Order-ID in JTL |
| | sonst | (leer) | ~98,4% | |
| **Incoterms** | `KindOfBusiness ∈ {B2B, EXPORT, B2B-REFUND, EXPORT-REFUND}` | `DDP` | ~6% | Delivered Duty Paid (Ausfuhren) |
| | sonst | (leer) | ~94% | Nicht relevant für reine Inlandverkäufe |
| **MarketZone** | `KindOfBusiness ∈ {SALE, REFUND}` | `TargetZone` (Kundenland) | — | Marktplatz folgt Kundenstandort |
| | `KindOfBusiness ∈ {B2B, EXPORT, B2B-REFUND, EXPORT-REFUND}` | `SourceZone` (Lagerland) | 100% | Marktplatz folgt physischem Versandort |

**Verifizierung aus Sample-Analyse (14.975 Zeilen):**
- `MarketZone` ist pro DocumentID konstant (13.387 von 13.388 Belege bestätigt; 1 Ausreißer war Excel-Datenfehler)
- `TAX_REPORTING_SCHEME=UK_VOEC-IMPORT`: 39 Zeilen (Exporte nach GB via Marktplatz)
- `TAX_COLLECTION_RESPONSIBILITY=MARKETPLACE`: 236 Zeilen (Marktplatz-Steuereinkassierung)
- `Incoterms=DDP`: 920 Zeilen (alle Ausfuhren und B2B)

## Bekannte Edge Cases & Anomalien

### 1. GTIN-Daten in Jera-Samples
**Faktisch nicht befüllt.** Alle GITNs, MPNs, Brands, ISBNs sind 0 Zeilen. ASIN kommt 29-mal vor (Standard-Format wie `B06XRHDQWS`, kein Excel-Quoting nötig). **Regel für Implementation:** Spalten leer lassen. Falls JTL-Stamm GTIN/MPN liefert: als reinen String schreiben, **nicht** mit `="..."`-Excel-Quoting (Jera-Format nutzt das nicht).

### 2. Negative Beträge bei REFUND
Alle `KindOfBusiness=REFUND` / `B2B-REFUND` / `EXPORT-REFUND` zeigen **negative Brutto/Netto** in `MarketZone[Gross/Net]`. Vorzeichen ist Teil des Datensatzes, nicht der `KindOfBusiness`-Markierung.

### 3. `SourceZone[Gross/Net]` und `TargetZone[Gross/Net]` — nie befüllt
Auch in den Jera-Samples praktisch 0% befüllt. **Regel:** Nicht befüllen, DutyPay rechnet intern.

### 4. ItemUnit — praktisch nie befüllt
`ItemQuantity` ist immer gesetzt, `ItemUnit` fast nie. Standard: Mengeneinheit blank lassen oder "stk".

### 5. VatZone vs. TargetZone — nicht verwechseln
`VatZone` ist das Steuerelement (wo Steuer anfällt), `TargetZone` ist das Lieferland. Bei Inland-Refunds (DE→DE) sind beide `DE`. Bei Cross-Border-Refund (Lager PL, Ziel DE, aber urspr. Sale zu FR) kann `VatZone ≠ TargetZone`.

### 6. TAX_COLLECTION_RESPONSIBILITY — Seller-Edge-Case
Im Sample 1 Zeile mit `KindOfBusiness=SALE` + `TAX_REPORTING_SCHEME=UK_VOEC-IMPORT` (Wert: `SELLER`). Diese Kombination ist widersprüchig und wird vorerst **nicht implementiert**. Clarification mit User abhängig von Häufigkeit in Live-Daten.

## PO-Prefix-Belege (Temu-Pilot, eingestellt)

Temu-Belege (Pilot Ende 2025, zurückgerollt) tragen externe Auftragsnummern mit Präfix `PO-` (z.B. `PO-123456789`). Sie sind **DE→DE B2C** und damit OSS-irrelevant, erscheinen aber im DutyPay-Output — analog zu Jera. Der frühere DATEV-Filter wurde am 2026-05-10 entfernt (keine neuen Temu-Belege seit Januar 2026). DutyPay-Verhalten ist unverändert: PO-Belege werden weiterhin mitgeführt.

## Stand 2026-05-06 — Header-Umstellung + Bug-Fixes

**Versandkosten-Bug gefixt:**
- Externe Amazon-Belege mit Versandkosten-Position wurden vorher fälschlich gefiltert, weil der `kExternerBelegPositionVater IS NULL`-Filter diese mit echten Bundle-Children verwechselte.
- Header-Beträge (`tExternerBelegEckdaten`) sind die garantierte Wahrheit — 100% Coverage, 100% Match mit Σ aller Positionen (verifiziert Q1 2026).
- Beispiel korrigiert: `DE6000SGNL56FU` jetzt korrekt 33,51 € (Header inkl. Versand) vs. alter Jera-Sample 29,52 € (ohne Versand).

**VAT-Rate-Format-Bug gefixt:**
- `_vat_rate_str()` in `dutypay.py`: `Decimal('20').normalize()` lieferte `'2E+1'` (scientific notation).
- Fix: `format(rate, 'f')` + manuelles Trailing-Zero-Trim → `'20'` statt `'2E+1'`.

**Q1 2026 Smoke-Run nach Umstellung (DutyPay):**
- JAN: 5285 Belege, Σ Brutto Engine 92.473 € vs. Jera 94.381 € (Δ −1908 €, 10 ≠-Brutto-Belege).
- FEB: 3865 Belege, Σ Brutto Engine 79.344 € vs. Jera 79.773 € (Δ −429 €, 11 ≠-Brutto).
- **MAR: 4807 Belege, Σ Brutto Engine 98.535 € vs. Jera 98.535 € (Δ −0,03 €, 0 ≠-Brutto).**
- Engine-Ausgabe ist Obermenge der Jera-Belege; JAN/FEB Δ entspricht dokumentierter Engine-vs-Jera-Drift (nicht durch Umstellung neu eingeführt).

**Verifikation gegen Live-Daten:**

Nach Sample-Analyse sind folgende Punkte **verifiziert**, könnten aber bei Live-Daten abweichen:

- **MarketZone-Heuristik (`SALE/REFUND` → TargetZone, sonst SourceZone):** Gegen Live-Belege abgleichen, falls Diff > 1%.
- **Marktplatz-Erkennung (externe Order-ID):** Quellfeld in JTL prüfen — aus `RawInvoice.source` (`jtl_external` = External-Marktplatz).
- **TAX_COLLECTION_RESPONSIBILITY=SELLER-Edge-Case:** Nur 1 Zeile im Sample; unklar ob reproduzierbar. Falls Häufigkeit steigt: Regel verfeinern.

## Implementierungs-Prüfliste für `core/dutypay.py`

- [x] CSV-Writer mit UTF-8, Semikolon-Trennzeichen, Dezimalkomma
- [x] Header-Zeile schreiben (98 Spalten)
- [x] Eine Zeile pro Belegdokument (Beträge aggregiert)
- [x] `KindOfBusiness` via Entscheidungsbaum (Lager/Ziel/USt-IdNr./Belegtyp)
- [x] Datumsformat `DD.MM.YYYY`
- [x] Negative Beträge bei Refunds
- [x] Lager-USt-IdNr. korrekt zuschalten (SourceZoneVatID bei B2B/Cross-Border)
- [x] Placeholders leer lassen (4–20)
- [x] Artikel-/Adressfelder leer (Profil 1 / Invoice-Granularität)

## Workflow: Archiv & Delta-Meldungen

### Automatische Archivierung

Jeder Aufruf von `jtl2datev export-dutypay --month YYYY-MM` archiviert die erzeugte CSV automatisch unter:

```
<export_archive_root>/dutypay/<YYYY-MM>/<YYYY-MM-DD_HH-MM-SS>.csv
```

`export_archive_root` kommt aus `Settings` (`JTL2DATEV_EXPORT_ARCHIVE_ROOT` in `.env`), Default `exports/` relativ zum CWD. Das Verzeichnis wird automatisch angelegt. Timestamp = lokale Zeit.

Der optionale `--out PATH` schreibt die Datei zusätzlich an einen frei wählbaren Pfad (z.B. für direkten Upload).

### Delta-Export: Nachträglich eingespielte Belege

OSS-Meldefrist ist der 6. des Folgemonats. Belege, die nach dem Erstexport noch in JTL eingebucht werden (z.B. verspätete Amazon-Synchronisation), müssen im Folgemonat separat nachgemeldet werden.

```bash
jtl2datev export-dutypay-delta --month YYYY-MM [--baseline FILE] [--shift-to-period YYYY-MM] [--out FILE]
```

**Ablauf:**

1. Baseline ermitteln: `--baseline FILE` oder letzter archivierter Vollexport für den Monat (lexikalisch neueste Datei in `<archive_root>/dutypay/<YYYY-MM>/`).
2. Frischen Vollexport aus JTL erzeugen.
3. Frischen Vollexport archivieren (als neue Baseline für die nächste Delta-Berechnung).
4. Diff: neue und geänderte `DocumentID`s → Delta-Zeilen.
5. Delta-CSV schreiben (Positions-Nr. ab 1 durchnummeriert).
6. Delta archivieren unter `<archive_root>/dutypay/<YYYY-MM>/deltas/<timestamp>.csv`.
7. Optional: Delta zusätzlich nach `--out` kopieren.

Geänderte Belege werden per `logging.INFO` gemeldet. Fehlt eine Baseline, bricht der Befehl mit einer klaren Fehlermeldung ab.

### Folgemonats-Nachmeldung: `--shift-to-period`

```bash
jtl2datev export-dutypay-delta --month 2026-02 --shift-to-period 2026-03 --out delta-fuer-maerz.csv
```

Nur wenn `--shift-to-period YYYY-MM` explizit gesetzt ist, werden in der **Delta-Output-CSV** (nicht in der Archivkopie!) folgende Felder überschrieben:

| Feld | Wert |
|---|---|
| `ReportingPeriod` | `YYYY-MMM` (z.B. `2026-MAR`) |
| `DepartureDate` | `01.MM.YYYY` (1. des Zielmonats) |
| `ArrivalDate` | `01.MM.YYYY` |
| `DocumentDate` | `01.MM.YYYY` |
| `PostingDateInvoice` | **unverändert** (interner Bezug auf Original-Beleg) |

Zweck: Die so erzeugte Delta-CSV kann direkt als Nachmeldung für den Folgemonat in DutyPay hochgeladen werden — ohne manuelle Nachbearbeitung in Excel.
