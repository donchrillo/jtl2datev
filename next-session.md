# Next Session

## Offene Punkte (Reihenfolge frei wählbar)

### 1. JTL-DB-Infos sammeln (Nutzer-Input nötig)
Vom Nutzer einholen und in `docs/db-schema.md` festhalten:
- DB-Server, Datenbankname, Auth (Windows/SQL), erreichbar von wo?
- Tabellen für: Rechnungen, Gutschriften, externe Rechnungen, Auftragspositionen, Kunden, Steuersätze, Lagerorte/Versandländer
- Beispiel-Queries oder Screenshots aus JTL Wawi
- Wie unterscheidet JTL Inland / EU-B2B / EU-B2C / Drittland?

### 2. DATEV-Format-Spezifikation
Vom Nutzer einholen und in `docs/datev-format.md`:
- Welches DATEV-Format genau? (vermutlich "DATEV-Format CSV" / EXTF Buchungsstapel v7.0)
- Beispiel-Export aus Jera-Tool (zum Abgleich)
- Mandantennummer, Berater, Sachkonten-Längen
- Konfigurierbare Mappings (Erlöskonten je Steuersatz/Land)

### 3. Steuer-/Länder-Regeln
In `docs/tax-rules.md`:
- Versandländer (woher wird verschickt)
- OSS-Verfahren ja/nein
- Reverse-Charge-Regeln EU-B2B
- Drittland-Logik
- Spezialfälle (z.B. Differenzbesteuerung)

### 4. Architektur-Skelett bauen (Coder-Agent, Sonnet 4.6)
Wenn 1+2 grob klar sind:
- `core/config.py` — Pydantic-Settings (DB, DATEV-Mandant, Mappings)
- `core/models.py` — Pydantic-Models für Rechnung, Position, Kunde, Steuer
- `core/repositories.py` — abstrakte Interfaces
- `core/db_jtl.py` — JTL-Implementierung (read-only)
- `core/rules.py` — Steuer-/Konten-Mapping
- `core/datev.py` — Export-Erzeugung
- `cli.py` — `jtl2datev export --from YYYY-MM-DD --to YYYY-MM-DD --out ...`

### 5. Dependencies installieren
```
uv pip install -e ".[dev]"
```

## Notizen für Orchestrator

- Vor jeder Coding-Aufgabe: Interface/Signaturen festlegen, dann an Coder-Agent delegieren.
- Nach Coding-Aufgabe: Docs-Agent fasst Änderungen in passender `docs/*.md` zusammen (kurz).
- Erledigtes hier rausnehmen, nach `docs/status.md` archivieren.
