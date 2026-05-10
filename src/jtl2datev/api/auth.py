"""JWT-Signatur-Validierung für alle geschützten Endpoints.

Nur Signatur + sub-Claim werden geprüft. Permissions liegen in toci-erp-DB
und werden vom Aufrufer validiert — nicht hier.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from jtl2datev.api.dependencies import SettingsDep
from jtl2datev.core.config import Settings

bearer_scheme = HTTPBearer(auto_error=False)


def verify_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, SettingsDep],
) -> dict:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")
    if "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing sub claim")
    return payload


VerifyJwtDep = Annotated[dict, Depends(verify_jwt)]
