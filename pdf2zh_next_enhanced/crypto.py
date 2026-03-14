from __future__ import annotations

import base64
from pathlib import Path

from cryptography.fernet import Fernet

from .paths import ENCRYPTION_KEY_PATH
from .paths import ensure_data_dirs


def _load_key(key_path: Path | None = None) -> bytes:
    key_path = key_path or ENCRYPTION_KEY_PATH
    ensure_data_dirs()
    if not key_path.exists():
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        return key
    return key_path.read_bytes().strip()


def get_cipher() -> Fernet:
    return Fernet(_load_key())


def encrypt_text(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    token = get_cipher().encrypt(value.encode("utf-8"))
    return base64.urlsafe_b64encode(token).decode("ascii")


def decrypt_text(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    token = base64.urlsafe_b64decode(value.encode("ascii"))
    return get_cipher().decrypt(token).decode("utf-8")
