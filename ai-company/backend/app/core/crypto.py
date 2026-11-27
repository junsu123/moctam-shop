"""Mã hóa phong bì cho secret (SECURITY_PLAN §2.4–5).

- Khóa chủ (AICO_MASTER_KEY, ≥ 32 ký tự) → KEK bằng HKDF-SHA256.
- Mỗi secret có một khóa dữ liệu (DEK) ngẫu nhiên 256 bit; giá trị mã hóa AES-256-GCM bằng DEK;
  DEK được "bọc" bằng KEK. Tên secret là dữ liệu xác thực kèm (AAD), nên không tráo bản mã giữa các secret được.
- Giá trị gốc không bao giờ được trả qua API, ghi log hay đưa vào ngữ cảnh LLM.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings
from app.core.errors import AppError

KEY_VERSION = 1


@dataclass(frozen=True)
class Sealed:
    ciphertext: bytes
    wrapped_key: bytes
    key_version: int


def _kek(master: str | None = None) -> bytes:
    if master is None:
        mk = get_settings().master_key
        if mk is None or len(mk.get_secret_value()) < 32:
            raise AppError("MASTER_KEY_MISSING", "Chưa cấu hình AICO_MASTER_KEY (≥ 32 ký tự) nên không lưu được thông tin bí mật.", 503)
        master = mk.get_secret_value()
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"aico-kek", info=f"v{KEY_VERSION}".encode())
    return hkdf.derive(master.encode())


def seal(name: str, plaintext: str, master: str | None = None) -> Sealed:
    dek = AESGCM.generate_key(bit_length=256)
    n1, n2 = os.urandom(12), os.urandom(12)
    ct = n1 + AESGCM(dek).encrypt(n1, plaintext.encode(), name.encode())
    wrapped = n2 + AESGCM(_kek(master)).encrypt(n2, dek, b"dek:" + name.encode())
    return Sealed(ct, wrapped, KEY_VERSION)


def unseal(name: str, s: Sealed, master: str | None = None) -> str:
    dek = AESGCM(_kek(master)).decrypt(s.wrapped_key[:12], s.wrapped_key[12:], b"dek:" + name.encode())
    return AESGCM(dek).decrypt(s.ciphertext[:12], s.ciphertext[12:], name.encode()).decode()
