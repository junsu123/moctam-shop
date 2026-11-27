"""UUIDv7: sắp theo thời gian, giữ chỉ mục gọn (DATABASE_SCHEMA §1). Python 3.12 chưa có sẵn uuid7."""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80  # 48 bit thời gian (ms)
    value |= 0x7 << 76  # phiên bản 7
    value |= ((rand >> 62) & 0xFFF) << 64  # 12 bit ngẫu nhiên
    value |= 0b10 << 62  # biến thể RFC 9562
    value |= rand & ((1 << 62) - 1)  # 62 bit ngẫu nhiên
    return uuid.UUID(int=value)
