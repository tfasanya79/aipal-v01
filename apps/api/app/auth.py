import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import PyJWTError as JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_db
from .models import MagicLinkToken, User

security = HTTPBearer(auto_error=False)
settings = get_settings()


def create_access_token(user_id: uuid.UUID, email: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "email": email, "exp": expire, "typ": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(user_id: uuid.UUID, email: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_days)
    payload = {"sub": str(user_id), "email": email, "exp": expire, "typ": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def create_magic_link(db: AsyncSession, email: str) -> tuple[str, str | None]:
    email = email.strip().lower()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=1)
    db.add(MagicLinkToken(token=token, email=email, expires_at=expires))
    await db.commit()
    dev_token = token if settings.magic_link_dev_return_token or settings.aipal_env.lower() != "production" else None
    return token, dev_token


async def verify_magic_link(db: AsyncSession, token: str) -> tuple[User, str, str]:
    result = await db.execute(select(MagicLinkToken).where(MagicLinkToken.token == token))
    row = result.scalar_one_or_none()
    if not row or row.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or used token")
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Token expired")
    row.used_at = datetime.now(UTC)
    result = await db.execute(select(User).where(User.email == row.email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=row.email, wake_name="AiPal")
        db.add(user)
        await db.flush()
    await db.commit()
    await db.refresh(user)
    access = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id, user.email)
    return user, access, refresh


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("typ") == "refresh":
            raise JWTError("Refresh token cannot authenticate requests")
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def refresh_access_token(refresh_token: str) -> tuple[User, str, str]:
    try:
        payload = jwt.decode(refresh_token, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("typ") != "refresh":
            raise JWTError("Invalid token type")
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    from .db import async_session

    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        access = create_access_token(user.id, user.email)
        refresh = create_refresh_token(user.id, user.email)
        return user, access, refresh
