"""Khai báo công cụ (Tool Registry). Công cụ là mã nguồn; bảng `tool_registry` chỉ là bản chiếu để Control Center
và Policy Engine đọc. Agent không có công cụ nào ghi vào registry hay quyền (SECURITY_PLAN §3.1)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection

SideEffects = Literal["none", "internal", "external"]
Risk = Literal["low", "medium", "high"]
_ORDER = {"none": 0, "internal": 1, "external": 2}

# Thẻ hành động thuộc danh sách bắt buộc người duyệt / bị cấm: định nghĩa ở brains/_core/constitution.yaml
LEVEL_NAMES = {1: "Chỉ đọc", 2: "Soạn nháp", 3: "Thực hiện", 4: "Tự động nâng cao"}


class FreeInput(BaseModel):
    """Đầu vào của công cụ chưa có tích hợp: chưa chạy được nên chưa ràng buộc chi tiết."""

    model_config = ConfigDict(extra="allow")


class FreeOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


@dataclass
class ToolCtx:
    conn: AsyncConnection  # giao dịch riêng của lời gọi; commit cùng bản ghi tool_invocations
    agent_key: str
    task_id: str | None
    idempotency_key: str
    attempt: int


Handler = Callable[[ToolCtx, Any], Awaitable[BaseModel]]
# Gắn thẻ rủi ro theo NỘI DUNG lời gọi, chạy trước Policy Engine (vd Content Gate gắn "publish_risky" → bắt buộc người duyệt)
Tagger = Callable[[AsyncConnection, Any, str, "str | None"], Awaitable[tuple[str, ...]]]


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    min_level: int  # cấp tự chủ tối thiểu: 1 đọc, 2 nháp, 3 thực hiện, 4 tự động
    side_effects: SideEffects
    tags: tuple[str, ...] = ()
    untrusted_output: bool = False  # đọc dữ liệu bên ngoài → làm "nhiễm" các bước sau (SECURITY_PLAN §4.3)
    input_model: type[BaseModel] = FreeInput
    output_model: type[BaseModel] = FreeOutput
    handler: Handler | None = None  # None: chưa có tích hợp → NOT_CONFIGURED
    tagger: Tagger | None = None


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_s: float = 0.5
    retry_on: tuple[str, ...] = ("TIMEOUT", "TRANSIENT")


@dataclass(frozen=True)
class ToolSpec:
    id: str
    description: str
    risk: Risk
    actions: dict[str, ActionSpec]
    timeout_s: float = 20.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    @property
    def side_effects(self) -> SideEffects:
        return max((a.side_effects for a in self.actions.values()), key=lambda s: _ORDER[s])

    @property
    def available(self) -> bool:
        return any(a.handler is not None for a in self.actions.values())


def act(name: str, description: str, level: int, side: SideEffects, *tags: str, untrusted: bool = False) -> ActionSpec:
    return ActionSpec(name=name, description=description, min_level=level, side_effects=side, tags=tags, untrusted_output=untrusted)


def tool(
    tid: str, description: str, risk: Risk, *actions: ActionSpec, timeout_s: float = 20.0, retry: RetryPolicy | None = None
) -> ToolSpec:
    return ToolSpec(
        id=tid, description=description, risk=risk, actions={a.name: a for a in actions}, timeout_s=timeout_s, retry=retry or RetryPolicy()
    )


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    REGISTRY[spec.id] = spec
    return spec


def get(tid: str) -> ToolSpec | None:
    return REGISTRY.get(tid)
