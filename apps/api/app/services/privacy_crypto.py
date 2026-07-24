from __future__ import annotations

import base64
import hashlib

from ..config import get_settings

try:  # pragma: no cover - required dependency in production/test environments
    from cryptography.fernet import Fernet  # type: ignore
except Exception as exc:  # pragma: no cover
    Fernet = None
    _FERNET_IMPORT_ERROR = exc
else:
    _FERNET_IMPORT_ERROR = None


def _key() -> bytes:
    secret = get_settings().jwt_secret.encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    if Fernet is None:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "cryptography is required for connector secret encryption"
        ) from _FERNET_IMPORT_ERROR
    return Fernet(_key())


def encrypt_value(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_value(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
