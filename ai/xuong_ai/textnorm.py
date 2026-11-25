"""Chuẩn hóa tiếng Việt và BM25 chuẩn hóa — PHẢI giống hệt web/app/src/Domain/Bm25.php và Text.php.

Nhờ đó ngưỡng hiệu chỉnh ở đây dùng được trực tiếp cho chat trên website.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

_MAP = str.maketrans({
    **{c: "a" for c in "àáạảãâầấậẩẫăằắặẳẵ"},
    **{c: "e" for c in "èéẹẻẽêềếệểễ"},
    **{c: "i" for c in "ìíịỉĩ"},
    **{c: "o" for c in "òóọỏõôồốộổỗơờớợởỡ"},
    **{c: "u" for c in "ùúụủũưừứựửữ"},
    **{c: "y" for c in "ỳýỵỷỹ"},
    "đ": "d",
})

K1 = 1.2
B = 0.75
STOP = {"a", "ah", "oi", "la", "thi", "ma", "va", "voi", "cua", "cho", "toi", "minh", "em", "anh", "chi",
        "ban", "shop", "nhe", "nha", "vay", "the", "nao", "gi", "sao", "hay", "cac", "mot", "u", "duoc", "ad",
        "admin", "xin", "hoi", "cam", "on", "ha", "ne"}
ALIAS = {"ko": "khong", "k": "khong", "hok": "khong", "hong": "khong", "kg": "khong", "dc": "duoc",
         "sp": "san pham", "ship": "giao", "cf": "ca phe", "cafe": "ca phe", "coffee": "ca phe"}


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


def rank(query: str, docs: dict) -> list[tuple[object, float]]:
    """Trả [(id, điểm chuẩn hóa 0..1)] giảm dần; chỉ tài liệu có điểm > 0."""
    q = list(dict.fromkeys(terms(query)))  # unique, giữ thứ tự
    if not q or not docs:
        return []
    tfs, df, total_len = {}, Counter(), 0
    for did, text in docs.items():
        ts = terms(text)
        tf = Counter(ts)
        tfs[did] = (tf, len(ts))
        total_len += len(ts)
        df.update(tf.keys())
    n = len(docs)
    avg = max(1.0, total_len / n)
    idf = {t: math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5)) for t in q}
    mx = sum(idf[t] * (K1 + 1) for t in q)
    out = []
    for did, (tf, ln) in tfs.items():
        s = 0.0
        for t in q:
            f = tf.get(t, 0)
            if f:
                s += idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * ln / avg))
        if s > 0:
            out.append((did, s / mx if mx > 0 else 0.0))
    out.sort(key=lambda x: -x[1])
    return out


_PHONE = re.compile(r"(\+?84|0)\d{9}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def redact(s: str) -> str:
    """Loại SĐT/email trước khi gửi bất kỳ nội dung nào cho LLM."""
    return _EMAIL.sub("[email]", _PHONE.sub("[sđt]", s or ""))
