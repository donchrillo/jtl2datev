# jtl2datev

Konsolen-Tool: liest Rechnungen/Gutschriften aus JTL-Datenbank, erzeugt DATEV-konformen Export.
Spätere Integration in eigenes ERP (FastAPI + React 19) — daher **Core-Library framework-agnostisch** halten.

## Harte Regeln (für jede Session)

1. **Core-Library (`src/jtl2datev/core/`) ist framework-agnostisch.** Kein `print()`, kein `click`, kein DB-Connection-String hardcoded. Logging über `logging`, Config über Pydantic-Models, DB-Session injizierbar. CLI-spezifisches gehört in `cli/`, HTTP-spezifisches in `api/`.
2. **Service-Layer (`core/services/`) ist die Schnittstelle für alle Aufrufer (CLI/API/Tests):** typed `*Request`/`*Result`-Dataclasses, typed Exceptions. Kein print/echo, kein SystemExit, kein Engine-Lifecycle, kein Archive — Orchestration ist Aufrufer-Verantwortung.
3. **DB-Layer ist swappable.** Aktuell JTL (MSSQL). Später eigenes ERP. Repository-Pattern: Interfaces in `core/repositories.py`, JTL-Implementierung in `core/db_jtl.py`.
4. **Coding delegieren.** Orchestrator (Opus 4.7) plant. Implementation läuft via `Agent`-Tool mit `subagent_type=general-purpose` und `model=sonnet`. Doku-Updates via Agent mit `model=haiku`.
5. **Kontext schlank halten.** Erledigtes aus `next-session.md` raus, nach `docs/status.md` archivieren. Detaildokus in `docs/`, nicht hier.
6. **Immer im venv arbeiten.** `source .venv/bin/activate` oder `uv run ...`. Niemals system-Python belasten.
7. **Niemals committen ohne explizite Freigabe.**

## Projektstruktur

```
src/jtl2datev/
  core/                  framework-agnostisch
    services/            Application-Layer: typed Request → Result, Exceptions
    repositories.py      ABCs (InvoiceRepository, ArticlePricingRepository)
    db_jtl.py            JTL-Implementierung der Repositories (MSSQL)
    datev.py, dutypay.py, taxually.py, ...   Domain-Writer + Reports
    tax_engine.py, rules.py, reference_data.py   Tax-Logic + Stammdaten
    pipeline.py, preflight.py, archive.py, exchange_rates.py
  cli/                   Click-Sub-Commands (dünne Wrapper über services/)
    __init__.py          main-Group + version
    _common.py           _parse_month, _resolve_date_range
    export_*.py, reconcile.py, mixed_vat_check.py, import_rates.py
  api/                   FastAPI-Skeleton (optional via [api]-Extra)
    main.py, dependencies.py
    routers/exports.py   POST /export/{datev,dutypay,taxually}
    routers/reports.py   GET /reconcile, /mixed-vat-check
docs/
  architecture.md  Design-Entscheidungen
  db-schema.md     JTL-DB-Findings (Tabellen, Joins)
  datev-format.md  DATEV-Export-Spezifikation
  dutypay-format.md, taxually-format.md, verbringung.md
  tax-rules.md     Länder-/Steuersatz-Regeln
  status.md        Archiv erledigter Arbeit
  review/          Konsolidierte Review-Reports (BLOCKER/WICHTIG-Liste)
next-session.md    Was als Nächstes ansteht (kurz halten!)
.claude/agents/    Agenten-Definitionen (coder, docs-writer)
```

**Schichten-Diagramm:**
```
cli/* (Click) ──┐
                ├─→ core/services/* ─→ core/{datev,dutypay,taxually,...}
api/* (FastAPI)─┘                  ─→ core/repositories (ABC) ─→ core/db_jtl
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
- FastAPI + uvicorn für HTTP-API (optional via `pip install jtl2datev[api]`)
- openpyxl, reportlab für Exporter
- pytest, ruff, mypy für Dev
