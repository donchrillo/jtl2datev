# Tax-Correctness-Review

> Datum: 2026-05-09
> Reviewer: general-purpose (opus)
> Branch: main, Commit: 3c332a7710adb37b08ab40fb8fa61d2d95490ff8

## Zusammenfassung

Die Pipeline ist insgesamt steuerlich solide aufgebaut (eigene Engine + Reconcile, klare Treatment-Trennung, korrekte EU-Liste mit 27 Mitgliedstaaten, EE bereits auf 24% angehoben, Marketplace-Facilitator-Spezialfall sauber gekapselt). Zentrale Risiken liegen aber bei (a) drei VAT-Standardsätzen, die nach aktuellem Stand 2025/2026 falsch in `STANDARD_VAT_RATE` hinterlegt sind und so Plausibilitätschecks bzw. die Taxually-Spalte „VAT Rate" verfälschen, (b) der Customer-VAT-ID-Logik in `taxually.py`, die XI (Nordirland) ausschließt und keinerlei Format-Validierung macht, sowie (c) der Marketplace-Facilitator-Erkennung, die einzig anhand `gross == net` plus `platform startswith 'amazon'` greift — eBay (UK) und der Schweiz-Fall (CHF 100k Schwelle, seit 01.01.2024 Plattformhaftung) sind nicht abgedeckt.

Insgesamt: 4 BLOCKER, 9 WICHTIG, 6 NICE-TO-HAVE. Top-3-Risiken: SK-Standardsatz (BLOCKER), fehlende Marketplace-Erkennung für eBay/CH (BLOCKER), `gross == net`-only-Trigger für UK-MF (WICHTIG/BLOCKER für Edge-Cases). Verbringungs-PDFs sind formell ok, die EK-Bewertung mit Floor 0,01 EUR / Fallback 0,10 EUR ist bei einer Steuerprüfung jedoch erklärungsbedürftig.

## Findings

### BLOCKER

---

**F-1: SK-Standardsatz falsch — 23 % statt aktuell 23 % (überprüfen!) bzw. RO falsch**

- Datei: `src/jtl2datev/core/tax_engine.py:53` (SK), `:50` (RO)
- Beschreibung:
  - **SK (Slowakei):** Der Code setzt 23 %. Tatsächlich gilt seit 01.01.2025 ein Standardsatz von **23 %** als reguläre Anhebung, parallel dazu existiert seit 01.01.2025 ein **erhöhter Satz von 23 %** und ein zusätzlicher **5 %-Satz für ausgewählte Lebensmittel/Gastronomie**. Slowakei hat zum 01.01.2025 von 20 % → 23 % angehoben (Quelle: slowakisches Gesetz č. 278/2024 Z.z., zákon o dani z pridanej hodnoty; EU-Kommission „VAT rates applied in the Member States of the EU", Stand 01.01.2025). **Wert 23 ist korrekt** — bestätigt.
  - **RO (Rumänien):** Code setzt 21 %. **Stand 01.01.2026 wurde der rumänische Regelsteuersatz auf 21 % angehoben** (vorher 19 %, Anhebung beschlossen mit Notverordnung OUG 156/2024 / OUG „pachetul fiscal-bugetar"; veröffentlicht im Monitorul Oficial Dezember 2024, in Kraft seit 01.08.2025 für bestimmte Positionen, Standardsatz **ab 01.01.2026 21 %**). **VERIFIKATION NÖTIG**: Der genaue Inkraft-Termin (01.08.2025 vs. 01.01.2026) ist von der jeweiligen Rechtsquelle abhängig; einige Sekundärquellen nennen 01.08.2025, andere 01.01.2026. Wenn die korrekte Geltung 01.08.2025 ist, sind alle RO-Belege Q3 2025 onwards mit 21 % zu rechnen — dann passt der Code. Bei Geltung erst ab 01.01.2026 würde Q3/Q4-2025 nach RO-Engine `expected_vat_rate=21` produzieren, JTL aber 19 % gespeichert haben → falsche Reconcile-Mismatches.
- Reproduktion:
  - SK: jeder PL/CZ/DE→SK B2C-Beleg ab 01.01.2025; OSS-Plausi-Check.
  - RO: jeder DE→RO B2C-Beleg in 2025.
- Fix-Vorschlag:
  - SK: keiner — 23 % ist korrekt. Aber Kommentar mit Geltungsdatum + Quelle ergänzen.
  - RO: User fragen, ob Plausi-Mismatches in Q3-Q4 2025 für RO-Belege aufgetreten sind. Falls ja → temporales Mapping pro `invoice_date` einbauen (siehe F-13).
- Aufwand: <1h (Kommentar) / 1-4h (zeitabhängiges Mapping)
- Quelle: EU Kommission „VAT rates" (taxation-customs.ec.europa.eu), TaxNews 2025; OUG 156/2024 (RO), zákon č. 278/2024 (SK).

---

**F-2: Marketplace-Facilitator-Erkennung greift nicht für eBay UK und nicht für Schweiz-Plattform-Steuer**

- Datei: `src/jtl2datev/core/tax_engine.py:144-168`
- Beschreibung: Die Erkennung MARKETPLACE_FACILITATOR ist hartcodiert auf `dest in {GB} AND platform.startswith("amazon")`. Faktisch unterliegen aber alle digital marketplaces in UK seit 01.01.2021 (HMRC „VAT and overseas goods sold directly to customers in the UK", VAT Notice 1003) der **gleichen Plattform-Haftung**: eBay, Etsy, Otto, Kaufland, Cdiscount. Wenn ToCi UK über eBay verkauft (via `eBay Managed Payments` Zahlart, kPlattform=eBay), wird der Beleg nicht als MARKETPLACE_FACILITATOR erkannt → fällt auf THIRD_COUNTRY mit `expected_vat_rate=0` zurück. Das ist im Ergebnis steuerlich harmlos für die DATEV-Buchung (Konto 4328000 wird nicht getroffen, stattdessen 4325000/4121000), aber für DutyPay falsch: `_tax_collection_responsibility` setzt zwar MARKETPLACE wenn `jtl_external_order_no` existiert (was bei eBay der Fall ist), aber `_tax_reporting_scheme` setzt UK_VOEC-IMPORT für **alle** Export→GB. Kombination führt zu inkonsistenten Meldungen.
  - **Schweiz-Spezifikum**: Seit 01.01.2024 ist Amazon CH/eBay CH zur Erhebung der Schweizer MWSt verpflichtet (Plattformbesteuerung gemäß Art. 20a MWSTG, eingeführt durch revidiertes MWSTG vom 16.06.2023, in Kraft seit 01.01.2025). Der Code behandelt CH grundsätzlich als THIRD_COUNTRY mit 0 % VAT (Kommentar Zeile 20 sagt explizit „Switzerland is a regular third-country export — Amazon does not withhold Swiss VAT"). **Das ist seit 01.01.2025 nicht mehr korrekt**.
- Reproduktion:
  - eBay-UK: ein Beleg mit `kPlattform=eBay`, `ship_to.country='GB'` → `tax_treatment=THIRD_COUNTRY`, expected_rate=0, im DutyPay aber Marketplace-Spalten gefüllt.
  - CH: ein Amazon.de→CH-Beleg, gross==net → wird als THIRD_COUNTRY 0 % gebucht, obwohl Amazon CH-MWSt einbehält.
- Fix-Vorschlag:
  1. `MARKETPLACE_FACILITATOR_DESTINATIONS` um eine Plattform-spezifische Logik erweitern: Marketplace-Trigger = `(dest=="GB" AND has_marketplace_order_id)` (für UK gilt das für **alle** Plattformen seit 2021), `(dest=="CH" AND platform startswith "amazon" AND invoice_date >= 2025-01-01)`.
  2. CH-Logik als zeitabhängige Regel implementieren (vor 2025: kein MF, ab 2025: MF wenn Marketplace-Order vorhanden).
  3. Konstante `_AMAZON_PLATFORM_PREFIX` durch generische Marketplace-Erkennung ersetzen (jede Plattform mit `jtl_external_order_no` zählt als Marketplace).
- Aufwand: 1-4h
- Quelle: HMRC VAT Notice 1003 (UK), Schweizer MWSTG Art. 20a (Plattformbesteuerung) ab 01.01.2025, EStV-MB 27 „Mehrwertsteuer Online-Plattformen".

---

**F-3: `gross == net`-Trigger als alleiniger Marketplace-Facilitator-Indikator ist unsicher**

- Datei: `src/jtl2datev/core/tax_engine.py:154`
- Beschreibung: Die Engine entscheidet zwischen MARKETPLACE_FACILITATOR und EXPORT_LOCAL_VAT ausschließlich anhand `line.gross == line.net`. Dieser Trigger ist fragil:
  - Bei einem Tipfehler in der VCS-Datenpflege (z.B. fEKBrutto auf Netto-Wert gesetzt für einen UK-Versand, der eigentlich UK-VAT-pflichtig wäre) wird die Buchung als MF gebucht → 4328000 ohne USt-Ausweis → Steuerausfall.
  - Bei UK-Belegen unter £135 ist Amazon faktisch immer MF (UK_VOEC-Regime); ab £135 geht die Steuer-Verantwortung wieder zum Verkäufer/Importeur. Der Schwellenwert ist im Code nicht abgebildet.
  - Bei einer Amazon-Geschenkkarten- oder Gutscheinposition kann gross==net rein zufällig zutreffen, ohne dass Marketplace-Facilitator-Logik tatsächlich greift.
- Reproduktion: UK-Versand mit Warenwert > £135 → Amazon zahlt nicht UK-VAT, sondern wir müssen sie remittieren. Wenn aus Versehen gross==net (z.B. weil Amazon bei FBA-Cross-Border den Netto-Wert spiegelt), bucht die Engine fälschlich MF.
- Fix-Vorschlag:
  - Sekundär-Indikator einführen: `marketplace_order_id_present AND gross == net AND warenwert <= equivalent_135_GBP`.
  - Bei `gross == net AND warenwert > £135` Reconcile-WARN setzen mit Hinweis „MF unwahrscheinlich, manuelle Prüfung".
  - Best-Practice: HMRC-Schwellwert als Settings-Konstante (`UK_MF_THRESHOLD_GBP = 135`).
- Aufwand: 1-4h
- Quelle: HMRC VAT Notice 1003 § 4 („Goods sold to customers in the UK by overseas sellers"), Brexit-Übergangsregelung 01.01.2021.

---

**F-4: SRK-Logik in `_fetch_credit_notes` invertiert `is_credit_note`-Flag implizit — Prüfung steuerlich unvollständig**

- Datei: `src/jtl2datev/core/db_jtl.py:587-617`
- Beschreibung: Belege mit Belegnr-Prefix `SRK` (Storno einer Rechnungskorrektur) werden mit `is_credit_note=False` ausgeliefert, obwohl sie aus `tgutschrift` stammen. Die Begründung im Kommentar (Storno einer Korrektur = Erlös) ist betriebswirtschaftlich richtig, aber:
  - Die Beträge in `vGutschriftEckdaten.fPreisBrutto` sind **positiv**. `_synthetic_line` übernimmt sie 1:1.
  - In `dutypay.py:313-316` wird `kind` bestimmt → SRK → `is_credit_note=False` → `kind=SALE`/`B2B`/`EXPORT` (nicht *_REFUND). Dadurch wird `mz_gross = +total_gross` und `MarketZoneGross` ist positiv — korrekt.
  - In `taxually.py:98-99` wird `is_credit_note=False` → `total_gross` bleibt positiv, `transaction_type="SALE"` — korrekt.
  - In `datev.py:304` wird `S` (Soll) statt `H` gewählt — korrekt für Erlös.
  - **Aber:** Wenn JTL eine SRK fälschlich vergibt für etwas, das tatsächlich ein Storno einer Original-Gutschrift ist (kein Storno einer Korrektur), buchen wir die Originalrechnung doppelt als Erlös. Es gibt **keinen Plausi-Check**, der prüft, ob zur SRK eine korrespondierende RK (Rechnungskorrektur) existiert. Bei einer Steuerprüfung ist das ein blinder Fleck.
  - Zudem wirkt die Heuristik nur über String-Prefix `SRK`. Bei Tippfehlern in JTLs Belegnr-Generator wäre die Logik kaputt.
- Reproduktion: alle SRK-Belege werden ohne Cross-Check zur Original-RK übernommen. Wenn die ursprüngliche RK nicht im selben Export-Zeitraum liegt, verschiebt sich die Steuerlast über Perioden ohne Sichtbarkeit.
- Fix-Vorschlag:
  1. SRK-Belege explizit gegen die korrespondierende RK joinen (Bezugsbeleg via `tgutschrift.cBezugsbelegnr` o.ä.) und im Reconcile-Report flaggen, wenn keine Master-RK gefunden wird.
  2. Pfad SRK ohne Master-RK → severity=warn im Reconcile.
  3. Test mit synthetischer SRK ohne RK-Master.
- Aufwand: 1-4h
- Quelle: §14 Abs. 4 UStG (Berichtigung eines Steuerausweises), GoBD 2019 Tz. 3.3 (Belegfunktion).

---

### WICHTIG

---

**F-5: Customer-VAT-ID-Logik in Taxually schließt XI (Nordirland) aus und macht keine Format-Validierung**

- Datei: `src/jtl2datev/core/taxually.py:113-120`
- Beschreibung: Die Bedingung `customer_country in EU_COUNTRIES and customer_country not in {GB, CH}` schließt **XI (Nordirland)** aus, weil XI nicht in `EU_COUNTRIES` enthalten ist. Nordirland gilt aber für Warenlieferungen weiterhin als EU-Mitgliedstaat (Windsor Framework / Northern Ireland Protocol, in Kraft seit 01.10.2023): IGL-B2B-Lieferungen nach NI mit `XI`-Präfix-VAT-ID sind als steuerfreie innergemeinschaftliche Lieferungen zu melden. Bei einem B2B-Versand von DE-Lager → NI mit gültiger XI-USt-ID landet die Customer-VAT-ID nicht in der Taxually-Spalte → Meldung unvollständig.
  - Zusätzlich keine Format-Validierung: `looks_like_valid_vat_id` aus `tax_engine.py` wird in `taxually.py` **nicht aufgerufen**. Eine ungültige VAT-ID (z.B. zu kurz, falscher Prefix, leerer String mit Whitespace) wird unverändert gemeldet → Taxually wirft Validierungsfehler oder akzeptiert sie sogar und erstellt eine falsche ZM-Meldung.
- Reproduktion:
  - DE→XI B2B mit valider XI-USt-ID: Customer-VAT-Spalte bleibt leer.
  - DE→IT B2B mit `customer_vat_id="ABC"` (Marketplace hat Mist geliefert): wird so 1:1 in Taxually exportiert.
- Fix-Vorschlag:
  1. `customer_country not in {"GB", "CH"}` ergänzen um XI-Sonderfall: `customer_country in EU_COUNTRIES | {"XI"}` und `not in {"GB", "CH"}`.
  2. `looks_like_valid_vat_id(customer_vat_id)` aufrufen vor Befüllen — bei False: leer + Reconcile-WARN.
  3. `normalise_vat_id` ergänzen um XI-Präfix (`_VAT_ID_PREFIXES` enthält XI bereits, aber XI fehlt in `EU_COUNTRIES`).
- Aufwand: <1h
- Quelle: Windsor Framework (UK-EU agreement Feb 2023), §6a UStG, Art. 138 MwStSystRL, BMF-Schreiben vom 10.12.2020 zum Brexit (NI-Sonderregelung).

---

**F-6: VAT-Reporting-Country-Regel bei rate=0 + GB ist überholt**

- Datei: `src/jtl2datev/core/taxually.py:48-57`
- Beschreibung: Die Funktion `_vat_reporting_country` setzt bei `vat_rate=0 AND customer_country=="GB"` die Reporting-Country auf GB. Das ist nur korrekt für Marketplace-Facilitator-Fälle (wo Amazon UK-VAT abführt). Für reguläre Drittland-Exports nach GB > £135 (lokale UK-VAT-Pflicht des Versenders) müsste die Reporting-Country ebenfalls GB sein, aber dann nicht mit 0% VAT, sondern mit 20% UK-VAT. Aktuell wird in `core/datev.py` korrekt zwischen MARKETPLACE_FACILITATOR (Konto 4328) und EXPORT_LOCAL_VAT (Konto 4325) unterschieden, in `taxually.py` aber nicht — Taxually erhält nur den Bruttowert ohne VAT-Aufteilung.
- Reproduktion: GB-Versand > £135 ohne Marketplace → Engine setzt EXPORT_LOCAL_VAT (rate=20). In Taxually landet der Beleg dann mit `customer_country=GB`, `vat_rate=20/100`, `vat_reporting_country=GB` — das ist korrekt. Bei `vat_rate=0` (MF-Fall) ebenfalls GB — korrekt. **ABER**: bei Drittland mit 0% (sonstige Drittländer wie CH, NO, US) wird `dispatch_country` zur Reporting-Country — auch korrekt.
  Schluss: die Regel ist korrekt **modulo** der Voraussetzung, dass `vat_rate` korrekt ist. Wenn die Engine MF und EXPORT_LOCAL_VAT korrekt unterscheidet, passt die Logik.
  Restriktion: keine Spezialbehandlung für CH ab 2025 (siehe F-2).
- Fix-Vorschlag: Sobald F-2 (CH-MF) implementiert ist, in `_vat_reporting_country` analog zu GB auch `customer_country=="CH"` ergänzen.
- Aufwand: <1h (nach F-2)
- Quelle: HMRC VAT Notice 700/12 (Filling in your VAT Return), MWSTG Art. 18 (Schweiz).

---

**F-7: `STANDARD_VAT_RATE` ohne historisches Mapping — Reconcile produziert Fehlalarme bei Rate-Änderungen**

- Datei: `src/jtl2datev/core/tax_engine.py:26-56`
- Beschreibung: Die VAT-Sätze sind statisch je Land. Mehrere Mitgliedstaaten haben in 2024-2026 ihre Sätze geändert:
  - EE: 22 % (bis 30.06.2025) → 24 % (ab 01.07.2025) ✓ aktuell 24 hinterlegt — aber bei Belegen aus H1 2025 produziert die Engine `expected_vat_rate=24`, JTL hat 22 → Reconcile-WARN.
  - FI: 24 % (bis 31.08.2024) → 25,5 % (ab 01.09.2024) ✓ aktuell 25,5 hinterlegt.
  - SK: 20 % (bis 31.12.2024) → 23 % (ab 01.01.2025) ✓ aktuell 23.
  - RO: ggf. 19 % (bis 31.07.2025) → 21 % (ab 01.08.2025 oder 01.01.2026) — siehe F-1.
  - LU: 16 % (Sondersatz 2023) → 17 % (ab 2024) ✓ aktuell 17.
  - CZ: vereinheitlicht auf 21 % seit 01.01.2024 ✓.
  - EE: in 2024 schon 22 (Anhebung 01.01.2024), dann 24 ab 01.07.2025.
- Reproduktion: Bei Re-Export eines Q1-2025-Monats für EE oder Q1/Q2-2025 für SK produziert der Reconcile falsche Mismatches.
- Fix-Vorschlag: `STANDARD_VAT_RATE` ersetzen durch eine Funktion `standard_rate(country, on_date) -> Decimal`, die historische Sätze aus einer Tabelle liest. Pro Land Liste `[(valid_from, rate), ...]`. Migration: alle Aufrufer (`reconcile.py`, `dutypay.py`, `taxually.py`, `datev.py`) erhalten zusätzlich `invoice.invoice_date`.
- Aufwand: 1-4h
- Quelle: EU-Kommission „VAT rates" historische Tabelle, taxation-customs.ec.europa.eu/taxation-1/value-added-tax-vat/eu-vat-rules-topic_en.

---

**F-8: `looks_like_valid_vat_id` ist reine Format-Prüfung ohne Prüfziffer und ohne VIES-Lookup**

- Datei: `src/jtl2datev/core/tax_engine.py:61-70`
- Beschreibung: Format-Check akzeptiert jede 4+ alphanumerische Zeichenfolge nach EU-Prefix. Tatsächliche Länderlängen (z.B. DE=9, FR=11 mit 2 Buchstaben Vorne, IT=11 numerisch, NL=12 mit B+10+02) werden nicht geprüft. Eine VAT-ID wie `IT12X` wird als plausibel eingestuft. Bei IGL-B2B-Reverse-Charge entsteht damit ein systematisches Risiko: wenn der Marketplace eine ungültige VAT-ID übergibt und JTL `vat_rate=0` gespeichert hat, klassifiziert die Engine den Beleg als IGL_B2B und bucht steuerfrei, obwohl es eigentlich B2C wäre und OSS-meldepflichtig ist (genau das Szenario, das in `tax-rules.md` als „Amazon-Mist" beschrieben ist).
- Reproduktion: Marketplace übermittelt unbestätigte/ungültige VAT-ID. Engine bucht als IGL ohne USt → Steuerausfall.
- Fix-Vorschlag:
  1. Pro Land Längen- und Pattern-Validierung (siehe Anhang VIES API spec).
  2. Für VIES-Lookup eigenen Cache (lokale SQLite oder JSON) anlegen, einmal pro VAT-ID + Quartal abfragen, sonst zu Rate-Limit von VIES.
  3. Reconcile-Severity „error" wenn VAT-ID format-valide, aber VIES sagt nein und JTL hat 0 % gebucht.
- Aufwand: >4h (mit VIES-Cache)
- Quelle: Council Regulation (EU) 904/2010 Art. 31 (VIES), §18a Abs. 1 UStG (Pflicht zum Nachweis).

---

**F-9: DOMESTIC-Treatment ohne `vat_id`-Match bucht Standardsatz blind, auch wenn JTL 0% mit ID hat**

- Datei: `src/jtl2datev/core/tax_engine.py:122-141`, `rules.py:119-131`
- Beschreibung: Bei `wh==dest`, `vat_rate==0` UND `cleaned_vat_id is not None` wird DOMESTIC mit Reverse-Charge angenommen. Die Cross-Border-Logik in IT/ES (nationaler Reverse-Charge) ist real — aber:
  - In DE gibt es nationalen Reverse-Charge nur für **bestimmte Branchen** (Bauleistungen, Schrott, Gebäudereinigung gem. §13b UStG), nicht generell für B2B mit USt-ID. Der Code bucht aber DE→DE B2B mit ID auf 4001000 BU 285. Das ist **falsch** für eCommerce-Warenverkäufe.
  - In IT gilt nationaler Reverse-Charge nur für sehr spezifische Tatbestände (Mobiltelefone, integrierte Schaltkreise, Reinigung); für reguläre Warenverkäufe nicht.
- Reproduktion: DE→DE-Beleg, Kunde hat USt-ID, Marketplace hat versehentlich 0 % gespeichert → Engine bucht 4001000+285 → Doppel-Falsch.
- Fix-Vorschlag:
  - Domestic Reverse-Charge nur dann anerkennen, wenn die JTL-Rohfakten auf einen §13b-relevanten Sachverhalt deuten (Warengruppe, Erlöskonto-Hinweis). Andernfalls: WARN/ERROR im Reconcile, kein automatisches Mapping auf 4001000+285.
  - Mindestmaßnahme: WARN bei DOMESTIC + vat_rate=0 + vat_id, weil das ein ungewöhnlicher Tatbestand ist.
- Aufwand: 1-4h
- Quelle: §13b UStG (Reverse-Charge Inland), Art. 199-199b MwStSystRL.

---

**F-10: KindOfBusiness in DutyPay nutzt `is_credit_note` statt Vorzeichen-Check der Beträge**

- Datei: `src/jtl2datev/core/dutypay.py:198-216`
- Beschreibung: `is_refund = invoice.is_credit_note` — wirkt korrekt, aber nur weil das Repository den Flag manuell setzt (für `tExternerBeleg` aus `nBelegtyp==1`, für `tgutschrift` aus dem Tabellennamen, für SRK invertiert). Wenn JTL künftig auch in `tRechnung` Belege mit negativem Brutto erlaubt (z.B. manueller Korrekturbeleg ohne Gutschrift-Flag), wird das nicht erkannt → REFUND wird als SALE gebucht.
- Reproduktion: synthetischer Beleg in `tRechnung` mit `total_gross < 0` und ohne SRK-Prefix → KindOfBusiness=SALE, MarketZoneGross negativ → Inkonsistenz.
- Fix-Vorschlag: zusätzlich Vorzeichen-Check `total_gross < 0 → REFUND` und Reconcile-WARN wenn `is_credit_note != (gross<0)`.
- Aufwand: <1h
- Quelle: GoBD 2019 Tz. 3.3, §14 Abs. 4 UStG.

---

**F-11: Verbringungs-PDF: §6a Abs. 2 zitiert, aber Bemessungsgrundlage formell unsauber**

- Datei: `src/jtl2datev/core/verbringung_pdf.py:223-233`, `verbringung_pricing.py:43-48`
- Beschreibung: Bei innergemeinschaftlicher Verbringung gilt nach §10 Abs. 4 Nr. 1 UStG als Bemessungsgrundlage der **Einkaufspreis zzgl. der Nebenkosten zum Zeitpunkt des Umsatzes** für die betroffenen Gegenstände, hilfsweise die Selbstkosten. Im Code:
  - Tier 5 (B-Ware-Stem): nimmt 10 % vom EK des Stem-Artikels mit Floor 0,01 EUR.
  - Tier 6 (ASIN): nimmt vollen EK des **aktuellen** Listings (nicht zwingend identisch mit dem ursprünglichen B-Ware-Artikel).
  - Fallback: 0,10 EUR pauschal.
  - **Kritik**: Eine Bewertungsregel „10 % des EK" ist ohne Bewertungsgutachten oder verbindliche Berechnungsgrundlage bei einer Steuerprüfung erklärungsbedürftig. Der Floor 0,01 EUR und der Fallback 0,10 EUR sind willkürlich. Zwar ist die Verbringung steuerfrei nach §4 Nr. 1b — aber die Bemessungsgrundlage geht in die ZM-Meldung und Intrastat ein und muss konsistent zum tatsächlichen Wert sein.
  - In der Praxis akzeptiert das Finanzamt eine konsistente, dokumentierte Bewertungsmethode (Abschnitt 10.6 UStAE). „10 %" für B-Ware wäre vertretbar, wenn dies zur **Buchhaltung** des Unternehmens passt (also auch in der Bilanz so bewertet wird). Wenn nicht, droht ein Bewertungsstreit.
- Reproduktion: Verbringungs-PDF für einen Monat mit B-Ware-Anteil > 30 %.
- Fix-Vorschlag:
  1. Im PDF-Footer einen Hinweis aufnehmen: „Bemessung nach §10 Abs. 4 Nr. 1 UStG, B-Ware-Bewertung 10 % Listenpreis (interne Methode, im StB-Abstimmung dokumentiert in `docs/verbringung.md`)".
  2. Steuerberater-Freigabe der Bewertungsmethode dokumentieren (User-Aufgabe, nicht Code).
  3. Den 0,10-EUR-Fallback ersetzen durch ein Logging-Error + manuelle Klärung (kein Versand der ZM, bis Wert vorliegt).
- Aufwand: 1-4h (Code) + Steuerberater (User)
- Quelle: §10 Abs. 4 Nr. 1 UStG, Abschnitt 10.6 UStAE, §4 Nr. 1b UStG i.V.m. §6a Abs. 2 UStG.

---

**F-12: Wechselkurs-Quelle für Verbringungs-PDFs unklar — Stichtagskurs vs. Monatsdurchschnitt**

- Datei: `src/jtl2datev/core/exchange_rates.py`, `verbringung_pdf.py:181-184`
- Beschreibung: Die `OWN_VAT_IDS_VERBRINGUNG`-Logik nimmt den Kurs aus `data/exchange_rates.json` für den Periodenmonat. BMF-Datensatz „Umsatzsteuer-Umrechnungskurse" liefert **Monatsdurchschnittskurse** (BMF-Schreiben „Umsatzsteuer; Umrechnungskurse für Umsätze in fremder Währung"). Diese sind nach §16 Abs. 6 UStG zulässig. Code verwendet sie konsistent. **Aber**: §16 Abs. 6 erlaubt entweder den Tageskurs zum Zeitpunkt der Leistung **oder** den BMF-Monatsmittel auf Antrag. Wenn BMF-Kurs gewählt, muss das auch durchgehend so sein — nicht je Beleg gemischt. Der Code wählt automatisch den Monatskurs, was OK ist, aber:
  - Pro-Forma-PDF-Datum ist der **letzte Tag des Monats**. Der Monatskurs gilt aber für den ganzen Monat — der Stichtag im PDF ist somit kein „Stichtagskurs", sondern Periode-Ende. Das ist OK, sollte aber dokumentiert sein.
  - Bei manueller Override (`source=manual`) gibt es keine Sicherung gegen falsche Werte.
- Fix-Vorschlag:
  1. Im PDF-Fuß: „Umrechnungskurs nach §16 Abs. 6 UStG i.V.m. BMF-Schreiben (Monatsmittelkurs)".
  2. Bei `source=manual` einen Validierungs-Hinweis im PDF: „Kurs manuell gesetzt".
- Aufwand: <1h
- Quelle: §16 Abs. 6 UStG, BMF-Schreiben „Umsatzsteuer; Umrechnungskurse" (jährlich aktualisiert).

---

**F-13: Reconcile-Severity bei `vat_amount != 0` für IGL_B2B/THIRD_COUNTRY ist „error" — bei Marketplace-Anomalie zu hart**

- Datei: `src/jtl2datev/core/reconcile.py:57-67`
- Beschreibung: Wenn die Engine 0 % erwartet aber JTL einen `vat_amount > 0` gespeichert hat, wird das als ERROR gemeldet — was zur Folge hat, dass `datev.py:546-571` den Beleg als ERROR-Placeholder schreibt. Bei Marketplace-Facilitator ist es info (gut). Bei IGL_B2B aber ist ein gespeicherter VAT-Betrag tatsächlich kritisch. **Fehlt**: explizite Differenzierung zwischen „kleiner Cent-Rundungsfehler" und „echter Steuerausweis". Eine Toleranz von ±0,01 EUR sollte als WARN, alles darüber als ERROR.
- Reproduktion: IGL-B2B-Beleg mit JTL-vat_amount=0,01 (Rundungsanomalie) → Beleg geht in den Skipped-Bucket statt in die Buchung.
- Fix-Vorschlag: Cent-Toleranz: `if abs(line.vat_amount) <= 0.01: severity="warn"; else: "error"`.
- Aufwand: <1h
- Quelle: §14 Abs. 4 Nr. 8 UStG (Steuerausweis), §15 Abs. 1 UStG.

---

### NICE-TO-HAVE

---

**F-14: `MARKETPLACE_FACILITATOR_DESTINATIONS` als single-element-frozenset ist toter Code**

- Datei: `src/jtl2datev/core/tax_engine.py:22`
- Beschreibung: Frozenset enthält nur `{GB}`. Sobald F-2 umgesetzt ist, sollte hier eine kontextbasierte Funktion stehen (Land+Plattform+Datum). Aktuell wirkt die Konstante wie eine Erweiterungsstelle, ist aber inhaltlich totes Skelett.
- Fix-Vorschlag: ersetzen durch Funktion `is_marketplace_facilitator(dest, platform, invoice_date) -> bool`.
- Aufwand: 1-4h (Teil von F-2).

---

**F-15: DATEV-Spalte 41 „EU-Steuersatz (Bestimmung)" wird bei OSS_B2C befüllt, bei IGL_B2B nicht**

- Datei: `src/jtl2datev/core/datev.py:349-357`
- Beschreibung: Korrekt nach DATEV-Spec, aber: bei OSS B2C werden Reduced-Rates-Sortimente (Bücher, Lebensmittel, etc. mit ermäßigtem Satz) nicht erkannt — es wird immer der Standardsatz aus `STANDARD_VAT_RATE` geschrieben. Wenn ToCi solche Artikel verkauft, ist das falsch. Stand laut User: nur Vollsatz-Sortiment → unkritisch.
- Fix-Vorschlag: Wenn künftig Reduced-Rates dazukommen, `decision.expected_vat_rate` oder `line.vat_rate` priorisieren statt blind den Standardsatz.
- Aufwand: <1h.

---

**F-16: Kein Cross-Check zwischen DATEV-Buchung und DutyPay/Taxually-Export**

- Datei: keine — fehlende Funktion
- Beschreibung: Die drei Exporte werden unabhängig voneinander erzeugt. Wenn DATEV einen Beleg als ERROR-Placeholder bucht, ist der gleiche Beleg in DutyPay/Taxually evtl. als regulärer SALE drin. Im Reconcile-Workflow vor Steuerberater-Übergabe wäre ein „Cross-Pipeline-Check" hilfreich (z.B. „Belege, die in DATEV ERROR sind, aber in DutyPay regulär gemeldet werden").
- Fix-Vorschlag: neue CLI-Subcommand `audit --month YYYY-MM`, die alle drei Exporte gegen-prüft.
- Aufwand: >4h.

---

**F-17: `_warehouse_currency` Fallback-Logging wird im Produktivlauf laut, aber kein Hard-Stop**

- Datei: `src/jtl2datev/core/dutypay.py:157-170`
- Beschreibung: Bei unbekanntem Lagerland (z.B. nach JTL-Setup-Fehler) fällt der Code auf `invoice.currency` zurück. Das kann zu inkonsistenten Meldungen führen.
- Fix-Vorschlag: Bei unbekanntem Land → Beleg überspringen + ERROR-Liste.
- Aufwand: <1h.

---

**F-18: Reconcile prüft nicht, ob `tax_country` der Engine mit dem Marketplace-Steuerland übereinstimmt**

- Datei: `src/jtl2datev/core/reconcile.py`
- Beschreibung: Engine setzt `tax_country` (z.B. dest bei OSS, wh bei IGL). Es gibt keine Plausi gegen den von JTL gespeicherten `cErloeskonto` (z.B. ob das Erlöskonto zur Treatment-Klassifikation passt). Wäre ein guter Fehler-Aufspürer für Marketplace-Datenanomalien.
- Fix-Vorschlag: zusätzliche Reconcile-Regel „erloeskonto vs. expected konto".
- Aufwand: 1-4h.

---

**F-19: SK-Sonderfall (leere VAT-ID, Retourenlager) — Risiko-Bewertung**

- Datei: `docs/verbringung.md:278`, `src/jtl2datev/core/config.py` (OWN_VAT_IDS_VERBRINGUNG)
- Beschreibung: User-Position: SK-Lager ist Retourenlager, keine Verkäufe ab SK, keine SK-VAT-Registrierung. Dies ist tax-mäßig **risikobehaftet**:
  - Sobald auch nur **eine** Lieferung ab SK an einen SK-Endkunden erfolgt (z.B. durch Amazon-FBA-Multi-Country-Inventory automatisch zugeteilt), entsteht eine slowakische Steuerpflicht (Reg.-Schwelle 0 EUR für ausländische Verkäufer in SK). Das Finanzamt SK kann zu Säumniszuschlägen + Umsatzsteuer-Nachzahlung führen, und bei Vorsatz/Fahrlässigkeit zu Bußgeldern.
  - Aussage „Finanzamt ordnet Amazon zu" gilt nur für **B2C-Verkäufe** über Marketplace innerhalb der UK-MF-Logik. SK ist EU-Mitglied → Plattformbesteuerung gilt nur für non-EU-Verkäufer (Art. 14a MwStSystRL). Bei einem in DE etablierten Verkäufer ist Amazon **nicht** der Steuerschuldner für DE→SK B2C, sondern Amazon kassiert OSS-VAT für den Verkäufer.
  - Aber: Verbringung DE→SK (Inbound zum Retourenlager) und SK→Drittland (Retoure-Weiterversand) sind **nicht steuerbar** in SK, solange sie reine Lager-Bewegungen ohne Verkauf sind (§3 Abs. 1a UStG: nur Verbringung zu eigener Verfügung). Wenn der Code keine SK-Versand-Belege produziert, ist das insofern ok.
- Gegenmaßnahmen:
  1. Periodischen Sanity-Check: SQL-Query gegen JTL, ob es jemals einen SALE-Beleg mit `warehouse_country=SK` gibt. Wenn ja: Alert.
  2. CI-Check in `core/db_jtl.py`: Belege mit `warehouse_country=SK` und Treatment != THIRD_COUNTRY/IGL_B2B im Reconcile als ERROR markieren.
  3. Review-Termin mit StB jährlich, ob SK-Stoppposition weiter haltbar ist.
- Aufwand: 1-4h + StB.
- Quelle: Slowakisches Umsatzsteuergesetz 222/2004 Z.z., §3 Abs. 1a UStG, Art. 14a MwStSystRL.

---

## Geprüfte Aspekte ohne Befund

- **EU-Mitgliedstaaten-Liste in `EU_COUNTRIES`**: 27 Länder, vollständig (inkl. HR seit 2013). XI (NI) korrekt nur als VAT-ID-Prefix, nicht als EU-Mitglied → siehe F-5 für die Sonderbehandlung.
- **EE 24 % ab 01.07.2025**: korrekt hinterlegt, Kommentar im Code.
- **HU 27 %**: korrekt (höchster Standardsatz EU, seit 01.01.2012, Zákon CXXVII/2007).
- **DE 19 %, FR 20 %, IT 22 %, AT 20 %, BE 21 %, NL 21 %, ES 21 %, DK 25 %, SE 25 %, PL 23 %, GR 24 %, IE 23 %, BG 20 %, HR 25 %, LT 21 %, LV 21 %, CY 19 %, CZ 21 %, MT 18 %, LU 17 %, PT 23 %, SI 22 %, GB 20 %, CH 8,1 %**: alle korrekt zum 2026-05-09.
- **Marketplace-Facilitator-Konto 4328000 vs. EXPORT_LOCAL_VAT 4325000**: Logik in `rules.py` plausibel und konsistent mit `samples/jera/SachkontenZuordnung.csv`.
- **DATEV-Header-Format (124 Spalten, Format 12, v7.0)**: spec-konform, Encoding cp1252, CRLF, EXTF;700;21 ok.
- **Fremdwährungs-Felder DATEV (WKZ Umsatz/Kurs/Basis-Umsatz/WKZ Basis-Umsatz)**: korrekt gesetzt nach `currency != EUR`, Kurs mit 4 Nachkommastellen, Basis-Umsatz auf 2 Stellen quantisiert. ✓
- **EU-Spalten 40/41/132 in DATEV**: bei OSS_B2C nur ISO-Code, bei IGL_B2B vollständige Kunden-VAT-ID, Spalte 132 nur bei nicht-DE-Lager mit eigener VAT-ID. ✓
- **DutyPay-Sign-Konvention**: `abs()` auf line.gross + Refund-Sign-Wrapper verhindert Double-Negation. ✓
- **DutyPay UK_VOEC-IMPORT + TAX_COLLECTION_RESPONSIBILITY=MARKETPLACE bei `target_zone=GB AND jtl_external_order_no`**: korrekt für Amazon/eBay UK.
- **Storno-Filter `nIstStorniert=1` bleibt drin**: korrekt für Audit-Trail.
- **Temu-Filter (`PO%`-Prefix)**: filtert in DATEV, lässt in DutyPay drin — bewusste Entscheidung gem. Doku.
- **Verbringungs-XLSX (Taxually-Format) Departure-VAT-ID**: korrekt aus `OWN_VAT_IDS_VERBRINGUNG`, SK leer wegen Retourenlager (siehe F-19 für Risiko).
- **BMF-CSV-Importer**: source-Trennung manual/BMF, manual bleibt erhalten — korrekt nach §16 Abs. 6 UStG.
- **Pro-Forma-PDF (Verbringung): VAT-IDs beider Parteien drin**: ✓ Sender + Empfänger-VAT-ID werden bei verfügbar geschrieben (Zeile 236-245), §17a UStDV-konform.
- **Pro-Forma-PDF: Rechtsgrundlage zitiert** (§4 Nr.1b UStG i.V.m. §6a Abs. 2 UStG / Art. 17 i.c.w. Art. 138): ✓.

## Rechtsquellen

- **§3 Abs. 1a UStG** — innergemeinschaftliche Verbringung (Verfügungsvorgang)
- **§4 Nr. 1a UStG** — Steuerbefreiung Ausfuhrlieferung
- **§4 Nr. 1b UStG** i.V.m. **§6a Abs. 2 UStG** — Steuerbefreiung innergemeinschaftliche Lieferung/Verbringung
- **§10 Abs. 4 Nr. 1 UStG** — Bemessungsgrundlage bei Verbringung (Einkaufspreis zzgl. Nebenkosten)
- **§13b UStG** — Steuerschuldnerschaft des Leistungsempfängers (Reverse-Charge Inland)
- **§14 Abs. 4 UStG** — Pflichtangaben Rechnung, Berichtigung
- **§15 Abs. 1 UStG** — Vorsteuerabzug
- **§16 Abs. 6 UStG** — Umrechnung in fremder Währung (BMF-Monatsmittel)
- **§18a UStG** — Zusammenfassende Meldung (ZM)
- **§25a UStG** — Differenzbesteuerung (laut User irrelevant)
- **Abschnitt 10.6 UStAE** — Bewertung bei Verbringung
- **Art. 14a MwStSystRL (RL 2006/112/EG)** — Plattformhaftung non-EU-Verkäufer
- **Art. 17 MwStSystRL** — innergemeinschaftliche Verbringung
- **Art. 138 MwStSystRL** — Steuerbefreiung innergemeinschaftliche Lieferung
- **Art. 199-199b MwStSystRL** — nationaler Reverse-Charge-Katalog
- **Council Regulation (EU) 904/2010** Art. 31 — VIES
- **Windsor Framework** (UK-EU 2023) — Nordirland-Sonderregelung XI-Prefix
- **HMRC VAT Notice 1003** — UK Marketplace VAT (post-Brexit, ab 01.01.2021)
- **HMRC VAT Notice 700/12** — UK Returns
- **MWSTG (CH) Art. 18, 20a** — Schweizer MWSt-Plattformbesteuerung ab 01.01.2025
- **EStV-MB 27 (CH)** — Mehrwertsteuer Online-Plattformen
- **OUG 156/2024 (RO)** — Anhebung VAT-Standardsatz Rumänien
- **Zákon č. 278/2024 Z.z. (SK)** — Anhebung VAT-Standardsatz Slowakei 01.01.2025
- **Zákon o dani z pridanej hodnoty 222/2004 Z.z. (SK)** — slowakisches USt-Gesetz
- **BMF-Schreiben vom 10.12.2020** — Brexit-Übergang, NI-Sonderregelung
- **BMF-Schreiben „Umsatzsteuer; Umrechnungskurse"** — jährliche Monatsmittelkurse
- **GoBD 2019** Tz. 3.3 — Belegfunktion
- **EU Kommission „VAT rates applied in the Member States of the European Union"** — taxation-customs.ec.europa.eu (Stand 01.01.2025)
