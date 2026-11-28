"""Tự kiểm tra TẤT ĐỊNH của runtime (BRAIN_SPEC §4): đúng/sai, không phải điểm chất lượng.

Tiêu chí thành công dạng có cấu trúc kiểm được bằng mã; tiêu chí dạng câu chữ (`manual`) được ghi lại cho người review.
Góp ý của người duyệt có thể kèm kiểm tra (vd "meta description phải có tên sản phẩm" → `contains`), lưu trong trí nhớ trải
nghiệm và được áp lại cho những lần sau (AC-BRAIN-01 bước 3c).
"""

from __future__ import annotations

from typing import Any

from app.memory.textnorm import fold


def _get(out: dict[str, Any], field: str | None) -> Any:
    cur: Any = out
    for part in (field or "").split("."):
        if not part:
            continue
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list | tuple):
        return " ".join(_text(x) for x in v)
    if isinstance(v, dict):
        return " ".join(_text(x) for x in v.values())
    return str(v)


def _resolve(text: str | list[str] | None, inputs: dict[str, Any]) -> list[str]:
    """`{input.product_name}` trong tiêu chí lấy giá trị từ đầu vào của task."""
    items = text if isinstance(text, list) else [text or ""]
    out = []
    for t in items:
        if t.startswith("{input.") and t.endswith("}"):
            t = _text(_get(inputs, t[7:-1]))
        if t:
            out.append(t)
    return out


def check(output: dict[str, Any], criteria: list[Any], inputs: dict[str, Any] | None = None) -> tuple[list[str], list[str]]:
    """Trả (vấn đề, tiêu chí cần người kiểm). Không có vấn đề = đạt."""
    problems: list[str] = []
    manual: list[str] = []
    inputs = inputs or {}
    if not isinstance(output, dict) or not output:
        return ["đầu ra rỗng"], manual
    for c in criteria:
        if isinstance(c, str):
            manual.append(c)
            continue
        if not isinstance(c, dict):
            continue
        t, f = c.get("type"), c.get("field")
        v = _get(output, f)
        label = c.get("description") or ""
        if t == "manual":
            manual.append(label or str(c))
        elif t == "required_fields":
            miss = [x for x in c.get("fields") or ([f] if f else []) if _get(output, x) in (None, "", [], {})]
            if miss:
                problems.append("thiếu trường: " + ", ".join(miss))
        elif t == "max_len":
            if len(_text(v)) > int(c.get("n") or 0):
                problems.append(f"'{f}' dài {len(_text(v))} ký tự, tối đa {c.get('n')}")
        elif t == "min_len":
            if len(_text(v)) < int(c.get("n") or 0):
                problems.append(f"'{f}' ngắn quá ({len(_text(v))} ký tự, tối thiểu {c.get('n')})")
        elif t == "contains":
            hay = fold(_text(v))
            for needle in _resolve(c.get("text"), inputs):
                if fold(needle) not in hay:
                    problems.append(f"'{f}' phải có \"{needle}\"" + (f" ({label})" if label else ""))
        elif t == "not_contains":
            hay = fold(_text(v if f else output))
            for needle in _resolve(c.get("text"), inputs):
                if fold(needle) in hay:
                    problems.append(f'không được có "{needle}"' + (f" trong '{f}'" if f else ""))
        elif t == "field_in":
            if v not in (c.get("values") or []):
                problems.append(f"'{f}' phải là một trong {c.get('values')}")
        elif t == "min_items":
            if not isinstance(v, list) or len(v) < int(c.get("n") or 0):
                problems.append(f"'{f}' cần ít nhất {c.get('n')} mục")
    return problems, manual
