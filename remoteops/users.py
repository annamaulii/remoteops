import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from remoteops.config import settings
from remoteops.database import get_session
from remoteops.models import AuthToken, User

router = APIRouter(tags=["users"])
SessionDependency = Annotated[Session, Depends(get_session)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
password_hash = PasswordHash.recommended()


class UserCreate(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: Annotated[str, Field(min_length=1, max_length=512)]


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetResponse(BaseModel):
    detail: str


class PasswordResetConfirm(BaseModel):
    token: Annotated[str, Field(min_length=1, max_length=512)]
    new_password: Annotated[str, Field(min_length=8, max_length=128)]


RESET_RESPONSE = "If that email exists, password reset instructions will be sent."


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(user_id: UUID) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=30)
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def hash_auth_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_auth_token(
    session: Session, user: User, purpose: str, expires_at: datetime
) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        AuthToken(
            user_id=user.id,
            token_hash=hash_auth_token(token),
            purpose=purpose,
            expires_at=expires_at,
        )
    )
    return token


def create_refresh_token(session: Session, user: User) -> str:
    return create_auth_token(
        session,
        user,
        "refresh",
        datetime.now(UTC) + timedelta(days=30),
    )


def create_password_reset_token(session: Session, user: User) -> str:
    session.execute(
        delete(AuthToken).where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == "password_reset",
        )
    )
    return create_auth_token(
        session,
        user,
        "password_reset",
        datetime.now(UTC) + timedelta(minutes=30),
    )


def get_valid_auth_token(
    session: Session, token: str, purpose: str
) -> AuthToken | None:
    auth_token = session.scalar(
        select(AuthToken)
        .where(
            AuthToken.token_hash == hash_auth_token(token),
            AuthToken.purpose == purpose,
        )
        .with_for_update()
    )
    if auth_token is None:
        return None
    if auth_token.expires_at <= datetime.now(UTC):
        session.delete(auth_token)
        return None
    return auth_token


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDependency
) -> User:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
        )
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthorized() from None

    user = session.get(User, user_id)
    if user is None:
        raise unauthorized()
    return user


@router.post(
    "/users/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Email already registered"}},
)
def register_user(data: UserCreate, session: SessionDependency) -> User:
    user = User(
        email=str(data.email).lower(),
        password_hash=password_hash.hash(data.password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from None

    session.refresh(user)
    return user


@router.post("/auth/login", response_model=Token)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDependency,
) -> Token:
    email = form.username.lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None or not password_hash.verify(form.password, user.password_hash):
        raise unauthorized()
    refresh_token = create_refresh_token(session, user)
    session.commit()
    return Token(access_token=create_access_token(user.id), refresh_token=refresh_token)


@router.post("/auth/refresh", response_model=Token)
def refresh_access_token(
    data: RefreshTokenRequest,
    session: SessionDependency,
) -> Token:
    auth_token = get_valid_auth_token(session, data.refresh_token, "refresh")
    if auth_token is None:
        session.commit()
        raise unauthorized()

    user = session.get(User, auth_token.user_id)
    if user is None:
        session.delete(auth_token)
        session.commit()
        raise unauthorized()

    session.delete(auth_token)
    refresh_token = create_refresh_token(session, user)
    session.commit()
    return Token(access_token=create_access_token(user.id), refresh_token=refresh_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshTokenRequest, session: SessionDependency) -> Response:
    auth_token = session.scalar(
        select(AuthToken)
        .where(
            AuthToken.token_hash == hash_auth_token(data.refresh_token),
            AuthToken.purpose == "refresh",
        )
        .with_for_update()
    )
    if auth_token is not None:
        session.delete(auth_token)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/password-reset/request",
    response_model=PasswordResetResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    data: PasswordResetRequest, session: SessionDependency
) -> PasswordResetResponse:
    user = session.scalar(select(User).where(User.email == str(data.email).lower()))
    if user is not None:
        create_password_reset_token(session, user)
        session.commit()
    return PasswordResetResponse(detail=RESET_RESPONSE)


@router.post(
    "/auth/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
)
def confirm_password_reset(
    data: PasswordResetConfirm, session: SessionDependency
) -> Response:
    auth_token = get_valid_auth_token(session, data.token, "password_reset")
    if auth_token is None:
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        )

    user = session.get(User, auth_token.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        )

    user.password_hash = password_hash.hash(data.new_password)
    session.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/me", response_model=UserRead)
def read_current_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return user
