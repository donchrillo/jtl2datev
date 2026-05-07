# Q1 2026 — DATEV ERROR/UNKNOWN-Belege zur Prüfung

DATEV-Export Q1 2026 hat im März **3 Belege als ERROR** und **1 Beleg als UNKNOWN** markiert (`Belegfeld 2`). Diese Belege stehen in der Export-Datei, haben aber kein Gegenkonto — sie müssen manuell geprüft und korrekt verbucht werden.

Stand: 2026-05-07.

## Gemeinsames Muster

Alle vier Belege haben **Brutto = Netto** in Konstellationen, in denen die Engine eine steuerpflichtige Buchung erwartet. Drei Erklärungsmöglichkeiten:

1. **Tatsächlich steuerfrei** (z.B. EU-B2B-Reverse-Charge auf inländischer Plattform — bei Amazon.es/.it kommt B2B-RC-Domestic vor, wenn der Käufer mit USt-ID auftritt).
2. **Datenfehler in JTL** (Steuer fehlt fälschlicherweise auf der Position).
3. **Marketplace-Sonderfall** (z.B. eBay-Beleg mit Storno-Korrektur ohne Steuer).

Die Markierung `ERROR`/`UNKNOWN` ist absichtlich — der Steuerberater bekommt nicht stillschweigend ein steuerlich falsches Ergebnis.

## Belege

### 1. `SR202603197` — ERROR
| Feld                 | Wert                              |
|----------------------|-----------------------------------|
| Belegtyp             | Storno-Rechnungskorrektur (in `tgutschrift`) |
| kGutschrift          | 742339                            |
| Datum                | 02.03.2026                        |
| Lager                | ES                                |
| Empfänger            | ES (Domestic)                     |
| Kunde-UStID          | `B79594073` (Spanien)             |
| Externe Auftragsnr   | `404-4520158-1506758` (Amazon)    |
| Plattform            | Amazon.es                         |
| Brutto / Netto       | 60,73 € / 60,73 € (kein VAT)      |
| Buchungsseite        | H (Haben — Erlös-Korrektur)       |
| Kunde                | Jorge Crespo Dominguez            |
| Hypothese            | ES-B2B-Domestic mit Reverse-Charge — Engine erwartet bei ES-Inland 21 % MwSt, sieht aber Brutto = Netto → Mismatch. |
| Prüfung in JTL       | `cGutschriftNr = 'SR202603197'` aufrufen, Steuer und Bezugs-Rechnung prüfen. |
| Prüfung in Amazon    | Order `404-4520158-1506758` in Amazon Seller Central öffnen — ist Käufer als Geschäftskunde mit USt-ID hinterlegt? |

### 2. `SR202603225` — ERROR
| Feld                 | Wert                              |
|----------------------|-----------------------------------|
| Belegtyp             | Storno-Rechnungskorrektur (in `tgutschrift`) |
| kGutschrift          | 742367                            |
| Datum                | 02.03.2026                        |
| Lager                | IT                                |
| Empfänger            | IT (Domestic)                     |
| Kunde-UStID          | `IT02913210346` (Italien)         |
| Externe Auftragsnr   | `404-3750250-7037909` (Amazon)    |
| Plattform            | Amazon.it                         |
| Brutto / Netto       | 60,60 € / 60,60 € (kein VAT)      |
| Buchungsseite        | H (Haben — Erlös-Korrektur)       |
| Kunde                | Chiarini Andrea                   |
| Hypothese            | IT-B2B-Domestic mit Reverse-Charge — Engine erwartet bei IT-Inland 22 % MwSt. |
| Prüfung in JTL       | `cGutschriftNr = 'SR202603225'` aufrufen. |
| Prüfung in Amazon    | Order `404-3750250-7037909` — Geschäftskunde mit IT-USt-ID? |

### 3. `202650012449` — ERROR
| Feld                 | Wert                              |
|----------------------|-----------------------------------|
| Belegtyp             | Eigene Gutschrift (in `tgutschrift`) |
| kGutschrift          | 742402                            |
| Datum                | 18.03.2026                        |
| Lager                | DE                                |
| Empfänger            | DE (Domestic)                     |
| Kunde-UStID          | keine (B2C)                       |
| Externe Auftragsnr   | `M489435` (eBay)                  |
| Plattform            | Weitere Verkaufskanäle            |
| Brutto / Netto       | 9,90 € / 9,90 € (kein VAT)        |
| Buchungsseite        | H (Haben — Erlös-Korrektur)       |
| Kunde                | Schuster Steffen                  |
| Hypothese            | DE-B2C-Domestic ohne 19 % MwSt — Brutto = Netto ist hier untypisch. Möglicher Datenfehler in JTL oder Storno-Korrektur ohne Steuer-Anteil. |
| Prüfung in JTL       | `cGutschriftNr = '202650012449'` aufrufen, Bezugsrechnung prüfen — wurde dort 19 % MwSt korrekt ausgewiesen? |
| Prüfung in eBay      | Order `M489435` öffnen, Steuer-Anteil verifizieren. |

### 4. `CZ60001DNL56FI` — UNKNOWN
| Feld                 | Wert                              |
|----------------------|-----------------------------------|
| Belegtyp             | Externer Beleg (in `tExternerBeleg`) |
| kExternerBeleg       | 150152                            |
| Datum                | 09.03.2026                        |
| Lager                | CZ                                |
| Empfänger            | IT (Cross-Border-OSS)             |
| Bill-Country         | IT                                |
| Kunde-UStID          | keine (B2C)                       |
| Externe Auftragsnr   | `403-4755726-9236337` (Amazon)    |
| Plattform            | Amazon.it                         |
| Brutto / Netto       | 17,00 € / 17,00 € (kein VAT)      |
| Buchungsseite        | S (Soll — regulärer Verkauf)      |
| Kunde                | michael Amrhein                   |
| Hypothese            | OSS-Verkauf CZ-Lager → IT-Kunde sollte 22 % IT-VAT haben; Brutto = Netto → Engine kann nicht klassifizieren. Möglicherweise Beleg ohne Steuer-Position importiert (Marketplace-Daten unvollständig). |
| Prüfung in JTL       | `cBelegnr = 'CZ60001DNL56FI'` aufrufen, Positionen prüfen — fehlt eine Steuer-Position oder steht 0 % MwSt? |
| Prüfung in Amazon    | Order `403-4755726-9236337` — VAT-Anteil im Marketplace-Datensatz vorhanden? |

## Nächste Schritte

Nach manueller Prüfung:
- Wenn Steuerfreiheit korrekt: Beleg im DATEV-Stapel manuell mit korrektem Konto/BU-Schlüssel ergänzen.
- Wenn Datenfehler: in JTL Beleg korrigieren, dann Engine-Re-Export für März fahren (`jtl2datev export --from 2026-03-01 --to 2026-03-31 --out exports/datev/2026-03.csv`).
