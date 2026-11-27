"""Brain Loader: đọc thư mục bộ não, ghép mẫu phòng ban (`extends`), kiểm schema, tính hash.

- `bundle_hash`: SHA-256 của toàn bộ bundle đã chuẩn hóa (JSON sắp khóa). Đổi bất kỳ chữ nào → hash khác.
- `core_rules_hash`: SHA-256 của phần quy tắc cốt lõi = constitution + hard_rules + tool_permissions.
  Hash này phải có trong `brain_core_pins` (Owner đã chấp nhận) thì runtime mới chịu nạp (BRAIN_SPEC §9).
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.brain.schema import Bundle
from app.tools import catalog as _catalog  # noqa: F401  (đăng ký công cụ)
from app.tools import spec as tools

# Tệp trong thư mục agent → vị trí trong bundle (theo cấu trúc BRAIN_SPEC §2)
FILES: list[tuple[str, tuple[str, ...], str | None]] = [
    ("identity/profile.yaml", ("identity", "profile"), None),
    ("identity/role.yaml", ("identity", "role"), None),
    ("identity/personality.yaml", ("identity", "personality"), None),
    ("reasoning/reasoning_policy.yaml", ("reasoning", "reasoning_policy"), None),
    ("reasoning/planning_policy.yaml", ("reasoning", "planning_policy"), None),
    ("reasoning/decision_policy.yaml", ("reasoning", "decision_policy"), None),
    ("skills/skill_registry.yaml", ("skills",), "skills"),
    ("tools/tool_permissions.yaml", ("tool_permissions",), "permissions"),
    ("evaluation/performance.yaml", ("evaluation", "performance"), None),
    ("evaluation/evaluation_rules.yaml", ("evaluation", "evaluation_rules"), None),
]

MSG = {
    "missing": "thiếu trường bắt buộc",
    "extra_forbidden": "trường không được phép (gõ sai tên?)",
    "string_pattern_mismatch": "sai định dạng",
    "greater_than_equal": "nhỏ hơn mức cho phép",
    "less_than_equal": "lớn hơn mức cho phép",
    "too_short": "danh sách/chuỗi quá ngắn",
}


class BrainError(Exception):
    """Lỗi nạp bộ não, kèm danh sách vấn đề cụ thể (đường dẫn trường + lý do) để Owner/CI sửa được ngay."""

    def __init__(self, agent: str, problems: list[str], code: str = "BRAIN_INVALID") -> None:
        super().__init__(f"{agent}: " + "; ".join(problems))
        self.agent, self.problems, self.code = agent, problems, code


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def core_rules(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "constitution": bundle["constitution"],
        "hard_rules": bundle["identity"]["role"]["hard_rules"],
        "tool_permissions": bundle["tool_permissions"],
    }


@dataclass(frozen=True)
class Loaded:
    bundle: Bundle
    data: dict[str, Any]  # dạng JSON đã chuẩn hóa (lưu vào agent_brains.bundle)
    bundle_hash: str
    core_rules_hash: str


def _read(path: Path, agent: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise BrainError(agent, [f"{path.name}: YAML lỗi cú pháp ({str(e).splitlines()[0]})"]) from e


def _merge(base: Any, over: Any) -> Any:
    """Ghép sâu: dict ghép theo khóa, giá trị khác (kể cả danh sách) thì bản của agent thay bản mẫu."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = copy.deepcopy(base)
        for k, v in over.items():
            out[k] = _merge(out[k], v) if k in out else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def _set(d: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = _merge(d[path[-1]], value) if path[-1] in d else value


def _problems(e: ValidationError) -> list[str]:
    out = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "(gốc)"
        msg = MSG.get(err["type"], err["msg"].removeprefix("Value error, "))
        out.append(f"{loc}: {msg}")
    return out


def check_tools(bundle: Bundle) -> list[str]:
    """Đối chiếu quyền với Tool Registry và hiến pháp."""
    out = []
    forbidden = set(bundle.constitution.forbidden_tags)
    for p in bundle.tool_permissions:
        t = tools.get(p.tool)
        a = t.actions.get(p.action) if t else None
        if a is None:
            out.append(f"tool_permissions: công cụ {p.tool}.{p.action} không có trong Tool Registry")
            continue
        if p.level < a.min_level:
            out.append(f"tool_permissions: {p.tool}.{p.action} cấp L{p.level} thấp hơn cấp tối thiểu L{a.min_level} của hành động")
        if forbidden & set(a.tags):
            out.append(f"tool_permissions: {p.tool}.{p.action} thuộc nhóm hành động hiến pháp cấm")
    return out


def load_agent(root: Path, agent: str) -> Loaded:
    d = root / agent
    if not (d / "brain.yaml").is_file():
        raise BrainError(agent, ["không tìm thấy brain.yaml"], "BRAIN_NOT_FOUND")
    manifest = _read(d / "brain.yaml", agent) or {}
    data: dict[str, Any] = {}
    if manifest.get("extends"):
        tpl = (root / str(manifest["extends"])).resolve()
        if not tpl.is_file() or root.resolve() not in tpl.parents:
            raise BrainError(agent, [f"extends: không tìm thấy mẫu {manifest['extends']}"])
        data = _read(tpl, agent) or {}
    data = _merge(data, manifest)
    for rel, path, inner in FILES:
        f = d / rel
        if f.is_file():
            v = _read(f, agent)
            _set(data, path, (v or {}).get(inner) if inner else (v or {}))
    data.setdefault("skills", [])
    data.setdefault("tool_permissions", [])
    data["constitution"] = _read(root / "_core" / "constitution.yaml", agent)
    if data.get("agent_id") != agent:
        raise BrainError(agent, [f"agent_id trong brain.yaml ({data.get('agent_id')}) khác tên thư mục"])
    try:
        bundle = Bundle.model_validate(data)
    except ValidationError as e:
        raise BrainError(agent, _problems(e)) from e
    if probs := check_tools(bundle):
        raise BrainError(agent, probs)
    norm = bundle.model_dump(mode="json")
    return Loaded(bundle=bundle, data=norm, bundle_hash=digest(norm), core_rules_hash=digest(core_rules(norm)))


def agent_dirs(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))


def from_stored(agent: str, data: dict[str, Any]) -> Loaded:
    """Dựng lại từ bản đã lưu trong CSDL (kiểm schema lại, tính lại hash để phát hiện sửa lén trong CSDL)."""
    try:
        bundle = Bundle.model_validate(data)
    except ValidationError as e:
        raise BrainError(agent, _problems(e)) from e
    norm = bundle.model_dump(mode="json")
    return Loaded(bundle=bundle, data=norm, bundle_hash=digest(norm), core_rules_hash=digest(core_rules(norm)))


def diff(a: Any, b: Any, path: str = "") -> list[dict[str, Any]]:
    """So sánh hai bundle: danh sách {path, from, to} cho mọi chỗ khác nhau."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[dict[str, Any]] = []
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else str(k)
            if k not in a:
                out.append({"path": p, "from": None, "to": b[k]})
            elif k not in b:
                out.append({"path": p, "from": a[k], "to": None})
            else:
                out += diff(a[k], b[k], p)
        return out
    return [] if a == b else [{"path": path, "from": a, "to": b}]


def semver(v: str) -> tuple[int, int, int]:
    x, y, z = (int(p) for p in v.split("."))
    return x, y, z
