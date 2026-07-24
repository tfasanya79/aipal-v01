"""Third-party integrations (v2.1+) — Spotify OAuth stub."""

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..config import get_settings
from ..db import get_db
from ..models import IntegrationToken, User

router = APIRouter(prefix="/integrations", tags=["integrations"])
settings = get_settings()

_oauth_states: dict[str, str] = {}


class SpotifyAuthResponse(BaseModel):
    authorization_url: str
    state: str


class SpotifyCallbackRequest(BaseModel):
    code: str
    state: str


class PlayMusicRequest(BaseModel):
    provider: str = "spotify"
    query: str | None = None
    playlist_id: str | None = None


@router.get("/spotify/authorize", response_model=SpotifyAuthResponse)
async def spotify_authorize(user: User = Depends(get_current_user)):
    if not settings.spotify_client_id:
        raise HTTPException(status_code=501, detail="Spotify not configured on server")
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = str(user.id)
    params = urlencode(
        {
            "client_id": settings.spotify_client_id,
            "response_type": "code",
            "redirect_uri": settings.spotify_redirect_uri,
            "scope": "user-read-playback-state streaming",
            "state": state,
        }
    )
    return SpotifyAuthResponse(
        authorization_url=f"https://accounts.spotify.com/authorize?{params}",
        state=state,
    )


@router.post("/spotify/callback")
async def spotify_callback(
    body: SpotifyCallbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    expected_user = _oauth_states.pop(body.state, None)
    if expected_user != str(user.id):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    db.add(
        IntegrationToken(
            user_id=user.id,
            provider="spotify",
            access_token=body.code,
            refresh_token=None,
        )
    )
    await db.commit()
    return {"ok": True, "provider": "spotify"}


@router.post("/play-music")
async def play_music(
    body: PlayMusicRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == user.id,
            IntegrationToken.provider == body.provider,
        )
    )
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=400, detail=f"{body.provider} not connected")
    target = body.playlist_id or body.query or "focus"
    return {
        "ok": True,
        "message": f"Would play {target} on {body.provider}",
        "deep_link": f"spotify:search:{target}",
    }
