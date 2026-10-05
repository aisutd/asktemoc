"""
Bearer-token auth for API routes.

The Next.js server signs a short-lived HS256 JWT for the signed-in user
(sub, email, name; aud=asktemoc-api, iss=asktemoc-web) with BACKEND_JWT_SECRET.
The browser never holds this token; it only talks to the Next.js server.
"""

import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.db.models import User
from app.db.services import UserService

logger = logging.getLogger(__name__)

DEV_USER_SUB = "dev:local"
DEV_USER_EMAIL = "dev@utdallas.edu"

_bearer = HTTPBearer(auto_error=False)


def email_allowed(email: str, settings: Settings) -> bool:
    email = email.strip().lower()
    domain = settings.allowed_email_domain.strip().lower().lstrip("@")
    if email.endswith("@" + domain):
        return True
    return settings.is_development and email in settings.allowed_emails


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()

    if settings.auth_disabled:
        # Config validation guarantees ENVIRONMENT=development here.
        return UserService.upsert_user(db, DEV_USER_SUB, DEV_USER_EMAIL, "Dev User")

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Missing bearer token")

    if settings.backend_jwt_secret is None:
        logger.error("BACKEND_JWT_SECRET is not set; rejecting authenticated request")
        raise _unauthorized("API auth is not configured")

    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.backend_jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            leeway=settings.jwt_leeway_seconds,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as e:
        raise _unauthorized(f"Invalid token: {e}")

    email = claims.get("email")
    if not isinstance(email, str) or not email_allowed(email, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only @{settings.allowed_email_domain} accounts may use this API",
        )

    name = claims.get("name") if isinstance(claims.get("name"), str) else None
    return UserService.upsert_user(db, claims["sub"], email, name)
