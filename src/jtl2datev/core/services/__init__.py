"""Service-Layer: orchestriert Repository + Domain-Logik + Writer.

Services nehmen typed Requests (frozen dataclasses), geben typed Results
zurück und werfen typed Exceptions. **Keine** I/O-Seiteneffekte außerhalb
der explizit angegebenen Output-Pfade — kein print/echo, kein SystemExit.

Aufrufer (CLI, FastAPI, Tests) sind verantwortlich für:
- Engine-Lifecycle (managed_engine bzw. DI)
- Default-Pfad-Auflösung (z. B. exports/datev/YYYY-MM.csv)
- Archivierung via core.archive (Service archiviert nicht selbst)
- Human-readable Output-Formatierung (CLI-Echo vs. HTTP-Response)
- Exception-zu-Exit-Code-Mapping
"""
