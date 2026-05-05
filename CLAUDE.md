# jtl2datev

Konsolen-Tool: liest Rechnungen/Gutschriften aus JTL-Datenbank, erzeugt DATEV-konformen Export.
Spätere Integration in eigenes ERP (FastAPI + React 19) — daher **Core-Library framework-agnostisch** halten.

## Harte Regeln (für jede Session)

1. **Core-Library (`src/jtl2datev/core/`) ist framework-agnostisch.** Kein `print()`, kein `click`, kein DB-Connection-String hardcoded. Logging über `logging`, Config über Pydantic-Models, DB-Session injizierbar. CLI-spezifisches gehört in `cli.py`.
2. **DB-Layer ist swappable.** Aktuell JTL (MSSQL). Später eigenes ERP. Repository-Pattern: Interfaces in `core/repositories.py`, JTL-Implementierung separat.
3. **Coding delegieren.** Orchestrator (Opus 4.7) plant. Implementation läuft via `Agent`-Tool mit `subagent_type=general-purpose` und `model=sonnet`. Doku-Updates via Agent mit `model=haiku`.
4. **Kontext schlank halten.** Erledigtes aus `next-session.md` raus, nach `docs/status.md` archivieren. Detaildokus in `docs/`, nicht hier.
5. **Immer im venv arbeiten.** `source .venv/bin/activate` oder `uv run ...`. Niemals system-Python belasten.
6. **Niemals committen ohne explizite Freigabe.**

## Projektstruktur

```
src/jtl2datev/
  core/            framework-agnostisch: db, models, rules, datev, config
  cli.py           dünner Click-Wrapper
docs/
  architecture.md  Design-Entscheidungen
  db-schema.md     JTL-DB-Findings (Tabellen, Joins)
  datev-format.md  DATEV-Export-Spezifikation
  tax-rules.md     Länder-/Steuersatz-Regeln
  status.md        Archiv erledigter Arbeit
next-session.md    Was als Nächstes ansteht (kurz halten!)
.claude/agents/    Agenten-Definitionen (coder, docs-writer)
```

## Workflow pro Session

1. `next-session.md` lesen → konkrete Aufgabe wählen.
2. Bei Bedarf relevante `docs/*.md` lesen (nicht alle).
3. Implementation an Coder-Agent delegieren (Sonnet 4.6).
4. Doku-Update an Docs-Agent delegieren (Haiku 4.5).
5. `next-session.md` aktualisieren (erledigtes raus → `status.md`).

## Tech-Stack

- Python 3.12, `uv` für venv/deps
- Pydantic v2 für Models/Config
- SQLAlchemy 2.0 + pyodbc für JTL (MSSQL)
- Click für CLI
- pytest, ruff, mypy für Dev
