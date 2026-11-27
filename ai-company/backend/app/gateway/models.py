"""Model Gateway (SRS §8, ARCHITECTURE ADR-06).

Agent chỉ gọi theo *hồ sơ* (cheap, writer_vi, reasoning_mid, …). Gateway lo phần còn lại:
- chọn model theo registry, có model dự phòng khác nhà cung cấp;
- kiểm ngân sách TRƯỚC khi gọi: trần tháng, trần ngày (được tiêu thêm tới mức tối đa một ngày nếu tháng còn dư);
- che SĐT/email/khóa trước khi gửi ra ngoài (nhà cung cấp `may_receive_pii = false`);
- ghi từng lời gọi (token, chi phí, độ trễ, lỗi) vào `model_usage`;
- kiểm đầu ra có cấu trúc theo schema Pydantic, cho sửa một lần;
- cảnh báo Telegram một lần mỗi tháng khi chi phí chạm ngưỡng (mặc định 80%).
Khóa API lấy từ kho secret đã mã hóa; không bao giờ xuất hiện trong log hay lỗi trả ra.

Sổ chi phí (`model_usage`) và cảnh báo được ghi bằng **kết nối riêng, commit ngay**: lời gọi đã tốn tiền thì
vẫn phải có trong sổ kể cả khi việc của agent sau đó lỗi và giao dịch chính bị rollback.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.errors import AppError
from app.core.logging import redact
from app.core.telemetry import tracer
from app.domain import notify, store

log = logging.getLogger("aico.gateway")
VN = ZoneInfo("Asia/Ho_Chi_Minh")
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
transport: httpx.AsyncBaseTransport | None = None  # kiểm thử thay bằng MockTransport


class ProviderError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


@dataclass
class Model:
    id: str
    name: str
    provider: str
    kind: str
    base_url: str
    secret_name: str | None
    may_receive_pii: bool
    price_in: float
    price_out: float


class LlmResult(BaseModel):
    text: str
    data: Any = None
    model_id: str
    profile: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    fallback_used: bool = False


MODEL_SQL = (
    "SELECT m.id, m.model_name AS name, p.id AS provider, p.kind, p.base_url, p.secret_name, p.may_receive_pii, "
    "m.price_in_per_mtok AS price_in, m.price_out_per_mtok AS price_out FROM model_registry m JOIN provider_registry p ON p.id = m.provider_id "
    "WHERE m.id = :id AND m.enabled AND p.enabled"
)


async def _model(conn: AsyncConnection, mid: str | None) -> Model | None:
    if not mid:
        return None
    r = await db.one(conn, MODEL_SQL, {"id": mid})
    if r is None:
        return None
    d = dict(r)
    d["price_in"], d["price_out"] = float(d["price_in"]), float(d["price_out"])
    return Model(**d)


def cost(m: Model, tin: int, tout: int) -> float:
    return round(tin * m.price_in / 1e6 + tout * m.price_out / 1e6, 8)


# ------------------------------------------------------------------ ngân sách
async def spend(conn: AsyncConnection) -> dict[str, Any]:
    """Chi phí hôm nay / tháng này (theo giờ Việt Nam) và mức còn được tiêu hôm nay."""
    b = await store.get_setting(conn, "budget")
    assert isinstance(b, store.Budget)
    now = datetime.now(VN)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month0 = day0.replace(day=1)
    today = float(await db.scalar(conn, "SELECT COALESCE(SUM(cost_usd), 0) FROM model_usage WHERE at >= :d", {"d": day0}) or 0)
    month = float(await db.scalar(conn, "SELECT COALESCE(SUM(cost_usd), 0) FROM model_usage WHERE at >= :m", {"m": month0}) or 0)
    # Được tiêu thêm hôm nay nếu các ngày trước tiêu ít hơn định mức (tối đa day_burst_usd)
    surplus = max(0.0, b.day_usd * (now.day - 1) - (month - today))
    allowed_today = min(b.day_burst_usd, b.day_usd + surplus)
    return {
        "today_usd": round(today, 4),
        "month_usd": round(month, 4),
        "day_cap_usd": b.day_usd,
        "allowed_today_usd": round(allowed_today, 4),
        "month_cap_usd": b.month_usd,
        "alert_pct": b.alert_pct,
        "month_pct": round(100 * month / b.month_usd, 1) if b.month_usd else 0.0,
    }


async def _committed(sql: str, params: dict[str, Any]) -> None:
    async with db.engine().begin() as c:
        await db.execute(c, sql, params)


async def _notify_committed(text: str, dedupe_key: str) -> None:
    async with db.engine().begin() as c:
        await notify.enqueue(c, "alert", text, urgent=True, dedupe_key=dedupe_key)


async def _check_budget(
    conn: AsyncConnection, m: Model, est: float, profile: str | None, agent_key: str | None, purpose: str
) -> dict[str, Any]:
    s = await spend(conn)
    reason = None
    if s["month_usd"] + est > s["month_cap_usd"]:
        reason = f"Đã dùng {s['month_usd']:.2f}/{s['month_cap_usd']:.2f} USD của tháng."
    elif s["today_usd"] + est > s["allowed_today_usd"]:
        reason = f"Đã dùng {s['today_usd']:.2f}/{s['allowed_today_usd']:.2f} USD được phép hôm nay."
    if reason:
        await _record(m, profile, agent_key, None, purpose, 0, 0, 0, False, "BUDGET_EXCEEDED", None)
        day = datetime.now(VN).strftime("%Y-%m-%d")
        await _notify_committed(
            f"⛔ Hết ngân sách LLM: {reason} Các việc cần AI tạm dừng tới khi sang ngày/tháng mới hoặc anh/chị nâng trần.",
            f"budget_block:{day}",
        )
        raise AppError("BUDGET_EXCEEDED", "Đã hết ngân sách LLM. " + reason, 429)
    return s


async def _maybe_alert(conn: AsyncConnection) -> None:
    s = await spend(conn)
    if s["month_cap_usd"] and s["month_pct"] >= s["alert_pct"]:
        month = datetime.now(VN).strftime("%Y-%m")
        await _notify_committed(
            f"⚠️ Chi phí LLM tháng {month} đã đạt {s['month_pct']:.0f}% trần ({s['month_usd']:.2f}/{s['month_cap_usd']:.2f} USD).",
            f"budget_alert:{month}",
        )


# ------------------------------------------------------------------ gọi nhà cung cấp
async def _call(m: Model, key: str, system: str, prompt: str, max_tokens: int) -> tuple[str, int, int]:
    async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport) as c:
        try:
            if m.kind == "anthropic":
                r = await c.post(
                    m.base_url.rstrip("/") + "/v1/messages",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": m.name, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": prompt}]},
                )
            elif m.kind == "openai_compat":
                r = await c.post(
                    m.base_url.rstrip("/") + "/chat/completions",
                    headers={"authorization": f"Bearer {key}", "content-type": "application/json"},
                    json={
                        "model": m.name,
                        "max_completion_tokens": max_tokens,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    },
                )
            else:
                raise ProviderError("PROVIDER_UNSUPPORTED", f"Chưa hỗ trợ loại nhà cung cấp {m.kind}")
        except httpx.TimeoutException as e:
            raise ProviderError("TIMEOUT", "Hết thời gian chờ nhà cung cấp") from e
        except httpx.HTTPError as e:
            raise ProviderError("NETWORK", f"Lỗi mạng: {type(e).__name__}") from e
    if r.status_code in (401, 403):
        raise ProviderError("API_KEY_INVALID", f"Khóa API bị từ chối (HTTP {r.status_code})")
    if r.status_code == 429:
        raise ProviderError("RATE_LIMITED", "Nhà cung cấp giới hạn tần suất (HTTP 429)")
    if r.status_code >= 500:
        raise ProviderError("PROVIDER_DOWN", f"Nhà cung cấp lỗi (HTTP {r.status_code})")
    if r.status_code >= 400:
        raise ProviderError("BAD_REQUEST", f"Yêu cầu bị từ chối (HTTP {r.status_code}): {redact(r.text)[:200]}")
    d = r.json()
    if m.kind == "anthropic":
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        u = d.get("usage", {})
        return text, int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
    text = d["choices"][0]["message"].get("content") or ""
    u = d.get("usage", {})
    return text, int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))


async def _record(
    m: Model,
    profile: str | None,
    agent_key: str | None,
    task_id: str | None,
    purpose: str,
    tin: int,
    tout: int,
    ms: int,
    ok: bool,
    err: str | None,
    fallback_of: str | None,
) -> float:
    c = cost(m, tin, tout) if ok else 0.0
    await _committed(
        "INSERT INTO model_usage(model_id, profile, agent_key, task_id, purpose, tokens_in, tokens_out, cost_usd, latency_ms, ok, error_code, fallback_of) "
        "VALUES (:m, :p, :a, :t, :pu, :ti, :to, :c, :ms, :ok, :e, :f)",
        {
            "m": m.id,
            "p": profile,
            "a": agent_key,
            "t": task_id,
            "pu": purpose[:100],
            "ti": tin,
            "to": tout,
            "c": c,
            "ms": ms,
            "ok": ok,
            "e": err,
            "f": fallback_of,
        },
    )
    return c


def _parse_json(text: str) -> Any:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    start = min((i for i in (t.find("{"), t.find("[")) if i >= 0), default=-1)
    return json.loads(t[start:] if start > 0 else t)


async def _complete(
    conn: AsyncConnection,
    profile: str,
    system: str,
    prompt: str,
    *,
    agent_key: str | None = None,
    task_id: str | None = None,
    purpose: str = "",
    max_tokens: int = 1024,
    schema: type[BaseModel] | None = None,
) -> LlmResult:
    if agent_key:
        st = await db.scalar(
            conn, "SELECT s.state FROM agent_status s JOIN agents a ON a.id = s.agent_id WHERE a.agent_key = :k", {"k": agent_key}
        )
        if st == "paused":
            raise AppError("AGENT_PAUSED", "Agent đang tạm dừng.", 409)
    prof = await db.one(conn, "SELECT model_id, fallback_model_id FROM model_profiles WHERE profile = :p", {"p": profile})
    if prof is None:
        raise AppError("PROFILE_UNKNOWN", f"Không có hồ sơ model '{profile}'.", 400)
    candidates = [m for m in [await _model(conn, prof["model_id"]), await _model(conn, prof["fallback_model_id"])] if m]
    if not candidates:
        raise AppError("NO_MODEL", f"Hồ sơ '{profile}' không có model nào đang bật.", 503)
    if schema is not None:
        system = (
            system
            + "\n\nChỉ trả về JSON hợp lệ theo schema sau, không thêm chữ nào khác:\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        )

    errors: list[str] = []
    for i, m in enumerate(candidates):
        sys_out, prompt_out = (system, prompt) if m.may_receive_pii else (redact(system), redact(prompt))
        est = cost(m, (len(sys_out) + len(prompt_out)) // 3, max_tokens)
        await _check_budget(conn, m, est, profile, agent_key, purpose)
        key = await store.get_secret(conn, m.secret_name) if m.secret_name else None
        if not key:
            errors.append(f"{m.provider}: chưa có khóa API")
            continue
        t0 = time.perf_counter()
        try:
            text, tin, tout = await _call(m, key, sys_out, prompt_out, max_tokens)
        except ProviderError as e:
            await _record(
                m,
                profile,
                agent_key,
                task_id,
                purpose,
                0,
                0,
                round((time.perf_counter() - t0) * 1000),
                False,
                e.code,
                candidates[0].id if i else None,
            )
            errors.append(f"{m.provider}: {e.detail}")
            log.warning("LLM %s lỗi %s", m.id, e.code)
            continue
        ms = round((time.perf_counter() - t0) * 1000)
        c = await _record(m, profile, agent_key, task_id, purpose, tin, tout, ms, True, None, candidates[0].id if i else None)
        res = LlmResult(
            text=text, model_id=m.id, profile=profile, tokens_in=tin, tokens_out=tout, cost_usd=c, latency_ms=ms, fallback_used=i > 0
        )
        if schema is not None:
            try:
                res.data = schema.model_validate(_parse_json(text))
            except (ValueError, ValidationError) as e:
                fix = prompt_out + f"\n\nCâu trả lời trước không hợp lệ ({str(e)[:300]}). Trả lời lại, chỉ JSON đúng schema."
                try:
                    text2, tin2, tout2 = await _call(m, key, sys_out, fix, max_tokens)
                except ProviderError as e2:
                    raise AppError("LLM_FAILED", f"Lỗi khi nhờ model sửa định dạng: {e2.detail}", 502) from e2
                c += await _record(m, profile, agent_key, task_id, purpose + ":repair", tin2, tout2, 0, True, None, None)
                try:
                    res.data = schema.model_validate(_parse_json(text2))
                except (ValueError, ValidationError) as e2:
                    raise AppError("LLM_BAD_OUTPUT", "Model trả về dữ liệu không đúng định dạng sau 2 lần.", 502) from e2
                res.text, res.tokens_in, res.tokens_out, res.cost_usd = text2, tin + tin2, tout + tout2, round(c, 8)
        await _maybe_alert(conn)
        return res
    raise AppError("LLM_FAILED", "Không gọi được model nào: " + "; ".join(errors), 502)


async def complete(conn: AsyncConnection, profile: str, system: str, prompt: str, **kw: Any) -> LlmResult:
    """Gọi model theo hồ sơ (xem `_complete`), trong một span OpenTelemetry (không ghi nội dung prompt vào trace)."""
    with tracer.start_as_current_span(
        "llm.complete", attributes={"aico.profile": profile, "aico.agent": kw.get("agent_key") or ""}
    ) as span:
        r = await _complete(conn, profile, system, prompt, **kw)
        span.set_attributes(
            {
                "aico.model": r.model_id,
                "aico.tokens_in": r.tokens_in,
                "aico.tokens_out": r.tokens_out,
                "aico.cost_usd": r.cost_usd,
                "aico.fallback": r.fallback_used,
            }
        )
        return r


async def ping_provider(conn: AsyncConnection, pid: str) -> dict[str, Any]:
    """Kiểm tra khóa API bằng một lời gọi rất nhỏ tới model rẻ nhất của nhà cung cấp."""
    mid = await db.scalar(
        conn, "SELECT id FROM model_registry WHERE provider_id = :p AND enabled ORDER BY price_out_per_mtok LIMIT 1", {"p": pid}
    )
    m = await _model(conn, mid)
    if m is None:
        return {"ok": False, "detail": "Không có model nào đang bật", "at": datetime.now(UTC)}
    key = await store.get_secret(conn, m.secret_name) if m.secret_name else None
    if not key:
        return {"ok": False, "detail": "Chưa nhập khóa API", "at": datetime.now(UTC)}
    await _check_budget(conn, m, cost(m, 30, 8), None, None, "provider_test")
    t0 = time.perf_counter()
    try:
        text, tin, tout = await _call(m, key, "Bạn là bộ kiểm tra kết nối.", "Trả lời đúng một chữ: OK", 8)
    except ProviderError as e:
        await _record(m, None, None, None, "provider_test", 0, 0, round((time.perf_counter() - t0) * 1000), False, e.code, None)
        return {"ok": False, "detail": e.detail, "at": datetime.now(UTC)}
    ms = round((time.perf_counter() - t0) * 1000)
    c = await _record(m, None, None, None, "provider_test", tin, tout, ms, True, None, None)
    return {"ok": True, "detail": f"{m.name} trả lời sau {ms} ms (chi phí {c:.6f} USD)", "at": datetime.now(UTC)}
