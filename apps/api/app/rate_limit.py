from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from .auth import get_current_user
from .models import User

_WINDOW_SECONDS = 60
_DEFAULT_LIMIT = 60
_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


async def _check(scope: str, user_id: str, limit: int = _DEFAULT_LIMIT, window_seconds: int = _WINDOW_SECONDS) -> None:
    key = f"{scope}:{user_id}"
    now = time.time()
    bucket = _BUCKETS[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
    bucket.append(now)


def rate_limit_dependency(scope: str, limit: int = _DEFAULT_LIMIT, window_seconds: int = _WINDOW_SECONDS) -> Callable[..., object]:
    async def _dependency(
        user: User = Depends(get_current_user),
    ) -> None:
        await _check(scope, str(user.id), limit=limit, window_seconds=window_seconds)

    return _dependency
