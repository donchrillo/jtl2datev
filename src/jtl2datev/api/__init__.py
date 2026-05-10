"""jtl2datev FastAPI-Skeleton.

Demonstriert die Schichten-Trennung zwischen Presentation (HTTP) und Service-
Layer (`core/services/`). Routen sind dünne Wrapper, die typed Requests an
Services delegieren und typed Results in HTTP-Responses übersetzen.

Optional installiert via `pip install jtl2datev[api]`.
Lokal starten:
    uvicorn jtl2datev.api.main:app --reload
oder via Entry-Point:
    jtl2datev-api
"""
