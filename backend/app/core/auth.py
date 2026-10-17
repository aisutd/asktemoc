"""
JWT gate for /api/chat.

The Next.js server mints a short-lived HS256 JWT (sub, email, name;
aud=asktemoc-api, iss=asktemoc-web) with BACKEND_JWT_SECRET. This module
requires that token on every request. It does not persist users.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    sub: str
    email: str
    name: str | None = None


def email_allowed(email: str, settings: Settings) -> bool:
    email = email.strip().lower()
    domain = settings.allowed_email_domain.strip().lower().lstrip("@")
    return email.endswith("@" + domain)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_claims(token: str, settings: Settings) -> dict:
    secret = settings.BACKEND_JWT_SECRET
    if not secret:
        raise _unauthorized("API auth is not configured")
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        audience=settings.BACKEND_JWT_AUDIENCE,
        issuer=settings.BACKEND_JWT_ISSUER,
        options={"require": ["exp", "iat", "sub", "aud", "iss"]},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    settings = get_settings()

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Missing bearer token")

    try:
        claims = _decode_claims(credentials.credentials, settings)
    except jwt.PyJWTError as e:
        raise _unauthorized(f"Invalid token: {e}") from e

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise _unauthorized("Token missing sub")

    email = claims.get("email")
    if not isinstance(email, str) or not email_allowed(email, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only @{settings.allowed_email_domain} accounts may use this API",
        )

    name = claims.get("name") if isinstance(claims.get("name"), str) else None
    return CurrentUser(sub=sub, email=email, name=name)
