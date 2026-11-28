"""ReasoningEngine: lớp DUY NHẤT chạm vào LangGraph (ARCHITECTURE ADR-05). Muốn thay thư viện thì chỉ sửa tệp này.

- Đồ thị nhận thức dựng một lần, dùng chung cho mọi agent (`app.tasks.runtime`).
- Checkpoint lưu bằng AsyncPostgresSaver trong schema `langgraph` của cùng CSDL; `thread_id` = `tasks.id`.
- `durability="sync"`: checkpoint ghi xong rồi mới sang nút sau, nên tắt máy giữa chừng chỉ làm lại tối đa một nút.
- `execute` chạy một task đã nhận (có lease): bắt đầu mới, chạy tiếp sau sự cố, hoặc tiếp tục sau khi điều kiện chờ có kết quả.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core import db
from app.core.errors import AppError
from app.tasks import engine, runtime
from app.tasks.runtime import State

log = logging.getLogger("aico.graph")
_pool: AsyncConnectionPool | None = None
_graph: Any = None


def build(checkpointer: Any) -> Any:
    g = StateGraph(State)
    for name, fn in (
        ("load", runtime.node_load),
        ("recall", runtime.node_recall),
        ("plan", runtime.node_plan),
        ("policy", runtime.node_policy),
        ("act", runtime.node_act),
        ("wait_children", runtime.node_wait_children),
        ("compose", runtime.node_compose),
        ("verify", runtime.node_verify),
        ("route", runtime.node_route),
        ("request_review", runtime.node_request_review),
        ("await_review", runtime.node_await_review),
        ("request_approval", runtime.node_request_approval),
        ("await_approval", runtime.node_await_approval),
        ("reflect", runtime.node_reflect),
    ):
        g.add_node(name, fn)  # type: ignore[call-overload]  # nút async trả State một phần
    g.add_edge(START, "load")
    g.add_edge("load", "recall")
    g.add_edge("recall", "plan")
    g.add_edge("plan", "policy")
    g.add_conditional_edges("policy", runtime.after_policy, ["plan", "act", "verify", "reflect"])
    g.add_conditional_edges("act", runtime.after_act, ["act", "wait_children", "compose", "reflect"])
    g.add_edge("wait_children", "compose")
    g.add_edge("compose", "verify")
    g.add_conditional_edges("verify", runtime.after_verify, ["plan", "route", "reflect"])
    g.add_conditional_edges("route", runtime.after_route, ["request_review", "request_approval", "reflect"])
    g.add_edge("request_review", "await_review")
    g.add_conditional_edges("await_review", runtime.after_review, ["plan", "route", "reflect"])
    g.add_edge("request_approval", "await_approval")
    g.add_edge("await_approval", "reflect")
    g.add_edge("reflect", END)
    return g.compile(checkpointer=checkpointer)


async def setup() -> Any:
    """Mở pool kết nối của checkpointer (schema `langgraph`), tạo bảng của thư viện nếu chưa có, dựng đồ thị."""
    global _pool, _graph  # noqa: PLW0603
    if _graph is not None:
        return _graph
    _pool = AsyncConnectionPool(
        db.psycopg_url(),
        min_size=1,
        max_size=4,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row, "options": "-c search_path=langgraph"},
    )
    await _pool.open()
    saver = AsyncPostgresSaver(_pool)  # type: ignore[arg-type]
    await saver.setup()
    _graph = build(saver)
    return _graph


async def close() -> None:
    global _pool, _graph  # noqa: PLW0603
    if _pool is not None:
        await _pool.close()
    _pool, _graph = None, None


def _cfg(task_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": task_id}, "recursion_limit": 60}


def _pending_interrupt(snap: Any) -> dict[str, Any] | None:
    for t in getattr(snap, "tasks", ()) or ():
        for i in getattr(t, "interrupts", ()) or ():
            return dict(i.value)
    return None


async def state(task_id: str) -> dict[str, Any] | None:
    g = await setup()
    snap = await g.aget_state(_cfg(task_id))
    if not snap or not snap.values:
        return None
    return {"values": snap.values, "next": list(snap.next), "interrupt": _pending_interrupt(snap)}


async def _heartbeat(task_id: str, worker: str, stop: asyncio.Event) -> None:
    while not stop.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=engine.LEASE_S / 3)
        if stop.is_set():
            return
        try:
            async with db.engine().begin() as c:
                if not await engine.heartbeat(c, task_id, worker):
                    log.warning("Mất lease task %s", task_id)
                    return
        except Exception as e:  # noqa: BLE001
            log.warning("Heartbeat lỗi %s", type(e).__name__)


async def execute(task: dict[str, Any], worker: str) -> str:
    """Chạy một task đã nhận. Trả trạng thái cuối của lượt chạy này (để log/test)."""
    g = await setup()
    tid = str(task["id"])
    cfg = _cfg(tid)
    snap = await g.aget_state(cfg)
    inp: Any
    if snap and snap.values and snap.next:
        pending = _pending_interrupt(snap)
        if pending:
            async with db.engine().connect() as c:
                val = await runtime.resume_value(c, task, pending)
            if val is None:  # chưa có kết quả: trả về trạng thái chờ, không chạy đồ thị
                async with db.engine().begin() as c:
                    await engine.park(c, tid, pending["kind"], actor=f"worker:{worker}", reason="vẫn đang chờ")
                return "parked"
            inp = Command(resume=val)
        else:
            inp = None  # chạy tiếp từ checkpoint sau sự cố
    elif snap and snap.values and not snap.next:
        return await _finalize(tid, snap.values, worker)  # đồ thị đã xong nhưng chưa kịp cập nhật task
    else:
        inp = {"task_id": tid}

    stop = asyncio.Event()
    hb = asyncio.create_task(_heartbeat(tid, worker, stop))
    remaining = None
    if task.get("timeout_at"):
        remaining = max(1.0, (task["timeout_at"] - datetime.now(UTC)).total_seconds())
    try:
        await asyncio.wait_for(g.ainvoke(inp, cfg, durability="sync"), timeout=remaining)
    except TimeoutError:
        return await _fail(tid, "TIMEOUT", f"Quá thời gian cho phép ({task['timeout_s']} giây)", worker)
    except AppError as e:
        if e.code == "AGENT_PAUSED":
            async with db.engine().begin() as c:
                await db.execute(c, "UPDATE tasks SET lease_owner = NULL, lease_until = NULL WHERE id = CAST(:t AS uuid)", {"t": tid})
                await engine.log_event(c, tid, "paused", "Agent bị tạm dừng: việc sẽ chạy tiếp từ checkpoint khi agent chạy lại")
            return "paused"
        code = "LLM_FAILED" if e.code in ("LLM_FAILED", "NO_MODEL") else e.code
        return await _fail(tid, code, e.message, worker)
    except Exception as e:
        log.exception("Đồ thị task %s lỗi", tid)
        return await _fail(tid, "INTERNAL", f"Lỗi nội bộ: {type(e).__name__}", worker)
    finally:
        stop.set()
        hb.cancel()
        with contextlib.suppress(BaseException):
            await hb

    snap = await g.aget_state(cfg)
    pending = _pending_interrupt(snap)
    if pending:
        async with db.engine().begin() as c:
            if not await engine.owns(c, tid, worker):
                return "lost"
            reason = {"approval": "chờ duyệt", "review": "chờ review", "children": "chờ các việc đã giao"}[pending["kind"]]
            await engine.park(c, tid, pending["kind"], actor=f"worker:{worker}", reason=reason)
            await engine.kick()
        return "parked"
    return await _finalize(tid, snap.values, worker)


async def _fail(tid: str, code: str, msg: str, worker: str) -> str:
    async with db.engine().begin() as c:
        if not await engine.owns(c, tid, worker):
            return "lost"
        t = await engine.fail(c, tid, code, msg, actor=f"worker:{worker}")
    return str(t["status"])


async def _finalize(tid: str, values: dict[str, Any], worker: str) -> str:
    outcome = values.get("outcome") or "completed"
    async with db.engine().begin() as c:
        t = await engine.get(c, tid, lock=True)
        if t["status"] in engine.TERMINAL:
            return str(t["status"])
        if t["status"] == "IN_PROGRESS" and t["lease_owner"] not in (None, worker):
            return "lost"
        actor = f"agent:{t['assigned_agent']}"
        if outcome == "completed":
            out = values.get("output") or {}
            if t["task_type"] == "review":
                await runtime.finish_review(c, t, out)
            summary = str(out.get("summary") or out.get("title") or values.get("plan", {}).get("summary") or "")[:1000]
            await engine.complete(c, tid, out, summary, actor=actor)
            return "COMPLETED"
        if outcome == "cancelled":
            await engine.cancel(c, tid, actor=actor, reason=values.get("note") or "không được duyệt")
            return "CANCELLED"
    return await _fail(tid, values.get("outcome_code") or "FAILED", values.get("note") or "thất bại", worker)
