from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_magic_link, refresh_access_token, verify_magic_link
from ..db import get_db
from ..schemas import AuthResponse, RefreshRequest, RegisterRequest, RegisterResponse, VerifyRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    token, dev_token = await create_magic_link(db, body.email)
    return RegisterResponse(dev_token=dev_token, message=f"Magic link created for {body.email}")


@router.post("/verify", response_model=AuthResponse)
async def verify(body: VerifyRequest, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await verify_magic_link(db, body.token)
    return AuthResponse(access_token=access, refresh_token=refresh, user_id=user.id)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(body: RefreshRequest):
    user, access, refresh = await refresh_access_token(body.refresh_token)
    return AuthResponse(access_token=access, refresh_token=refresh, user_id=user.id)
