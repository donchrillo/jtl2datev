# Steuer- und Länder-Regeln

> Stand: 2026-05-05 — Geschäftsmodell vom Nutzer eingeholt. Steuersätze und
> Konto-Mapping noch offen (siehe TODOs).
>
> **Strategische Entscheidung 2026-05-05:** Wir bauen eine **eigene Steuer-Engine**
> und vertrauen JTLs gespeicherten Steuerschlüsseln nicht blind. Grund: Amazon
> liefert teils falsche Steuern (z.B. PL→IT Auftrag mit polnischer USt statt
> italienischer, weil Amazon den Kunden trotz ungültiger USt-IdNr. als B2B
> behandelt). JTL übernimmt diese falschen Werte, existierende Tools (Taxdoo,
> Jera) erkennen den Konflikt — wir tun das auch. JTLs Steuerinfos werden
> mitgelesen und in `core/reconcile.py` mit dem Engine-Ergebnis verglichen
> (Mismatch-Report). Die Engine ist als wiederverwendbares Modul für TOCI-ERP
> ausgelegt.

## Versandlager

Versand erfolgt aus mehreren Lägern in Europa:

| Lagerland         | Eigene USt-IdNr. | Bemerkung                            |
|-------------------|------------------|--------------------------------------|
| DE (eigenes Lager) | ja              | Hauptlager                           |
| FR (Amazon FBA)   | ja               | lokal                                |
| IT (Amazon FBA)   | ja               | lokal                                |
| ES (Amazon FBA)   | ja               | lokal                                |
| PL (Amazon FBA)   | ja               | lokal                                |
| CZ (Amazon FBA)   | ja               | lokal                                |
| UK (Amazon FBA)   | ja               | Drittland (post-Brexit)              |

**Kernregel — Lagerland → gleiches Lagerland:**
Verkauf wird **lokal** über den dortigen Steuerberater abgerechnet, **nicht über
OSS**. → Diese Umsätze müssen für DATEV separat gekennzeichnet (eigene Konten /
USt-Schlüssel) ausgewiesen werden.

## Zielmärkte

- Alle EU-Länder
- Drittländer: insb. UK, CH

## Inland — Lagerland == Zielland

- Lagerland DE → Kunde DE: deutsche USt (19 % / 7 %)
- Lagerland FR → Kunde FR: französische USt
- analog IT, ES, PL, CZ
- Lagerland UK → Kunde UK: UK-VAT (UK ist Drittland, aber Lager mit lokaler
  Registrierung)
- TODO: konkrete Sätze + Sachkonten je Land

## EU grenzüberschreitend (Lagerland != Zielland, beides EU)

- **OSS-Verfahren ist aktiv**
- B2C: USt-Satz des Bestimmungslandes, Meldung über OSS
- B2B mit gültiger USt-IdNr.: Reverse-Charge (steuerfrei i.g. Lieferung)
  - TODO: USt-IdNr.-Validierung (VIES) — JTL-seitig vorhanden?
- TODO: Konto-Mapping OSS-Erlöse je Bestimmungsland

## Drittland

- Generell: steuerfrei nach §4 Nr. 1a UStG (Ausfuhr)
- **Spezialfall UK + CH über Amazon:** Amazon agiert als Marketplace Facilitator und behält die Steuer ein.
  - **UK:** seit Brexit (HMRC VAT Notice 1003).
  - **CH:** ab 01.01.2025 (MWSTG Art. 20a, Plattformbesteuerung).
  - **Erkennungsmerkmal in der Engine:** Plattform-Prefix `amazon` + `gross == net` → `MARKETPLACE_FACILITATOR`.
  - **Buchungsausweis:** Netto = Brutto, kein USt-Ausweis, Konto 4328000.
  - Andere Plattformen (eBay/Kaufland) versenden in der Praxis nicht nach UK/CH — sollte das jemals passieren, wäre die Engine entsprechend zu erweitern.
- **UK aus EU-Lager mit fehlendem Amazon-Einbehalt:** seltener Fall (1–2 Belege/Monat aus FR/ES) — Amazon kassiert nicht, wir melden 20 % UK-VAT über die UK-Steuerregistrierung. Engine-Treatment: `EXPORT_LOCAL_VAT`, Konto 4325000.

## Rechnungsquellen (DB-Routing seit 2024-11-01)

| Marktplatz | Tabelle                  | Bemerkung                                          |
|------------|--------------------------|----------------------------------------------------|
| eBay       | `Rechnung.tRechnung`     | `cZahlungsart='eBay Managed Payments'`, `ext=0`    |
| Kaufland   | `Rechnung.tRechnung`     | `cZahlungsart='Kaufland.de'`, `ext=0`              |
| Otto       | `Rechnung.tRechnung`     | `cZahlungsart='Otto.de'`, `ext=1`, `kPlattform=8`  |
| JTL        | `Rechnung.tRechnung`     | manuelle Belege, `kPlattform=1`                    |
| Amazon (regulär) | `Rechnung.tExternerBeleg` | seit 1.11.2024 via VCS (`cHerkunft='VCS'`)   |
| Amazon (manuell korrigiert) | `Rechnung.tRechnung` | seltene Sonderfälle: User hat fehlerhaften VCS-Beleg gelöscht und in JTL neu erzeugt; `cZahlungsart='AmazonPayments'`, `ext=0`, `kPlattform` 50-65 |
| TEMU       | —                        | NICHT über dieses Tool                             |

**Stichtag:** Amazon-Belege vor 2024-11-01 lagen in `tRechnung`, danach in
`tExternerBeleg`. Datums-Untergrenze für Repository: `>= 2024-11-01`. Fokus
2026.

Code muss beide Tabellen lesen und in einheitliche `RawInvoice`-Modelle
mergen. Keine Deduplizierung nötig (Quellen sind disjunkt).

## Sonderfälle

- Differenzbesteuerung (§25a): **nicht relevant**
- Kleinunternehmer-Empfänger: TODO
- Gutschriften: TODO (Vorzeichen, Belegnummern-Konvention)
