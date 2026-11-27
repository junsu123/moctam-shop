"""Chuẩn hóa tiếng Việt cho tìm kiếm trí nhớ: PHẢI giống hệt `ai/xuong_ai/textnorm.py` (và web/app/src/Domain/Text.php).

Kiểm chứng bằng tests/test_memory.py::test_mem05_textnorm_parity (so từng chuỗi với bản ở ai/).
"""

from __future__ import annotations

import re
import unicodedata

_MAP = str.maketrans(
    {
        **dict.fromkeys("àáạảãâầấậẩẫăằắặẳẵ", "a"),
        **dict.fromkeys("èéẹẻẽêềếệểễ", "e"),
        **dict.fromkeys("ìíịỉĩ", "i"),
        **dict.fromkeys("òóọỏõôồốộổỗơờớợởỡ", "o"),
        **dict.fromkeys("ùúụủũưừứựửữ", "u"),
        **dict.fromkeys("ỳýỵỷỹ", "y"),
        "đ": "d",
    }
)
STOP = {"a", "ah", "oi", "la", "thi", "ma", "va", "voi", "cua", "cho", "toi", "minh", "em", "anh", "chi",
        "ban", "shop", "nhe", "nha", "vay", "the", "nao", "gi", "sao", "hay", "cac", "mot", "u", "duoc", "ad",
        "admin", "xin", "hoi", "cam", "on", "ha", "ne"}  # fmt: skip
ALIAS = {"ko": "khong", "k": "khong", "hok": "khong", "hong": "khong", "kg": "khong", "dc": "duoc",
         "sp": "san pham", "ship": "giao", "cf": "ca phe", "cafe": "ca phe", "coffee": "ca phe"}  # fmt: skip


def fold(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").lower().translate(_MAP)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> list[str]:
    f = fold(s)
    return f.split(" ") if f else []


def terms(text: str) -> list[str]:
    raw: list[str] = []
    for t in tokens(text):
        raw.extend(ALIAS.get(t, t).split(" "))
    toks = [t for t in raw if t not in STOP]
    return toks + [f"{toks[i]}_{toks[i + 1]}" for i in range(len(toks) - 1)]


def search_text(text: str) -> str:
    """Văn bản lưu để tìm: bỏ dấu, chữ thường, mở rộng viết tắt (sp → san pham) để tìm có dấu/không dấu/viết tắt đều khớp."""
    out: list[str] = []
    for t in tokens(text):
        out.extend(ALIAS.get(t, t).split(" "))
    return " ".join(out)


def query_terms(text: str) -> list[str]:
    """Từ đơn của câu hỏi (bỏ từ dừng, bỏ cặp từ ghép), giữ thứ tự, không lặp."""
    return list(dict.fromkeys(t for t in terms(text) if "_" not in t))
