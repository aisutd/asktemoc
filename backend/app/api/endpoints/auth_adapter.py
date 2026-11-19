"""
Auth.js database adapter, reached only from the Next.js server.

Next.js holds no database connection. These routes write the Auth.js
`users` and `accounts` tables. Callers must present a short-lived JWT
with purpose=auth-adapter.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.auth import email_allowed, require_adapter
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import Account, User

router = APIRouter(dependencies=[Depends(require_adapter)])


class UserBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    email: str
    email_verified: datetime | None = Field(default=None, alias="emailVerified")
    image: str | None = None


class UserPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    email: str | None = None
    email_verified: datetime | None = Field(default=None, alias="emailVerified")
    image: str | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    name: str | None = None
    email: str
    email_verified: datetime | None = Field(
        default=None, serialization_alias="emailVerified"
    )
    image: str | None = None


class AccountBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    userId: str
    type: str
    provider: str
    providerAccountId: str
    refresh_token: str | None = None
    access_token: str | None = None
    expires_at: int | None = None
    token_type: str | None = None
    scope: str | None = None
    id_token: str | None = None
    session_state: str | None = None


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise HTTPException(status_code=422, detail="A valid email is required")
    if not email_allowed(normalized, get_settings()):
        settings = get_settings()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only @{settings.allowed_email_domain} accounts may use this API",
        )
    return normalized


def _user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(body: UserBody, db: Session = Depends(get_db)) -> User:
    user = User(
        id=str(uuid.uuid4()),
        name=body.name,
        email=_normalize_email(body.email),
        email_verified=body.email_verified,
        image=body.image,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="User already exists") from None
    db.refresh(user)
    return user


@router.get("/users/by-email", response_model=UserResponse)
def get_user_by_email(email: str = Query(...), db: Session = Depends(get_db)) -> User:
    normalized = email.strip().lower()
    user = db.query(User).filter(User.email == normalized).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/by-account", response_model=UserResponse)
def get_user_by_account(
    provider: str = Query(...),
    providerAccountId: str = Query(...),
    db: Session = Depends(get_db),
) -> User:
    account = (
        db.query(Account)
        .options(joinedload(Account.user))
        .filter(
            Account.provider == provider,
            Account.provider_account_id == providerAccountId,
        )
        .one_or_none()
    )
    if account is None or account.user is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account.user


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db)) -> User:
    return _user_or_404(db, user_id)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: str, body: UserPatch, db: Session = Depends(get_db)) -> User:
    user = _user_or_404(db, user_id)
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates:
        user.name = updates["name"]
    if "email" in updates and updates["email"]:
        user.email = _normalize_email(updates["email"])
    if "email_verified" in updates:
        user.email_verified = updates["email_verified"]
    if "image" in updates:
        user.image = updates["image"]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="User already exists") from None
    db.refresh(user)
    return user


@router.post("/accounts", status_code=204)
def link_account(body: AccountBody, db: Session = Depends(get_db)) -> Response:
    _user_or_404(db, body.userId)
    account = Account(
        user_id=body.userId,
        type=body.type,
        provider=body.provider,
        provider_account_id=body.providerAccountId,
        refresh_token=body.refresh_token,
        access_token=body.access_token,
        expires_at=body.expires_at,
        token_type=body.token_type,
        scope=body.scope,
        id_token=body.id_token,
        session_state=body.session_state,
    )
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account already linked") from None
    return Response(status_code=204)
