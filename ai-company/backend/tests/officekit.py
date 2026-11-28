"""Bộ dựng cho test Task Engine + runtime: model giả theo kịch bản (httpx.MockTransport), không gọi mạng thật.

Kịch bản là hàm `(agent, phase, task_title, prompt) -> dict` trả JSON mà model "trả lời"; phase là plan | compose.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

Script = Callable[[str, str, str, str], dict[str, Any] | None]
AGENT_RE = re.compile(r"\(([a-z_]+)\), thuộc phòng")
TITLE_RE = re.compile(r"^Tiêu đề: (.*)$", re.M)


def done(output: dict[str, Any] | None = None, confidence: float = 0.9, summary: str = "Viết ngay") -> dict[str, Any]:
    return {"summary": summary, "steps": [], "output": output or {"summary": "xong"}, "confidence": confidence, "claims": []}


def steps(*items: tuple[str, str, dict[str, Any]], summary: str = "Cần công cụ") -> dict[str, Any]:
    return {
        "summary": summary,
        "steps": [{"tool": t, "action": a, "input": i, "why": ""} for t, a, i in items],
        "output": None,
        "confidence": 0.8,
        "claims": [],
    }


def composed(output: dict[str, Any], confidence: float = 0.85) -> dict[str, Any]:
    return {"output": output, "confidence": confidence, "claims": []}


class FakeModel:
    def __init__(self) -> None:
        self.script: Script = lambda agent, phase, title, prompt: None
        self.calls: list[dict[str, str]] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if req.url.path.endswith("/embeddings"):  # vector giả: túi từ băm, đủ để tìm theo nghĩa giữa các câu chung từ
            import hashlib

            dims = int(body.get("dimensions") or 512)
            data = []
            for i, text in enumerate(body["input"]):
                v = [0.0] * dims
                for w in str(text).lower().split():
                    v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dims] += 1.0  # noqa: S324 — chỉ để băm trong test
                data.append({"index": i, "embedding": v if any(v) else [1.0] + [0.0] * (dims - 1)})
            return httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": 10}})
        msgs = body.get("messages") or []
        system = body.get("system") or next((m["content"] for m in msgs if m.get("role") == "system"), "")
        if isinstance(system, list):
            system = " ".join(x.get("text", "") for x in system)
        prompt = msgs[-1]["content"] if msgs else ""
        if isinstance(prompt, list):
            prompt = " ".join(x.get("text", "") for x in prompt)
        m = AGENT_RE.search(system)
        agent = m.group(1) if m else "?"
        t = TITLE_RE.search(prompt)
        title = t.group(1) if t else ""
        phase = "gate" if "bộ kiểm duyệt nội dung" in system else ("compose" if "Viết kết quả cuối" in prompt else "plan")
        self.calls.append({"agent": agent, "phase": phase, "title": title, "prompt": prompt, "system": system})
        out = self.script(agent, phase, title, prompt)
        if out is None:
            out = {"plan": done(), "compose": composed({"summary": "xong"}), "gate": {"risk": "low", "reason": "nội dung bình thường"}}[
                phase
            ]
        text = json.dumps(out, ensure_ascii=False)
        if "api.openai.com" in req.url.host:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 800, "completion_tokens": 200}}
            )
        return httpx.Response(200, json={"content": [{"type": "text", "text": text}], "usage": {"input_tokens": 800, "output_tokens": 200}})


@pytest.fixture
async def office(env: None, synced: list[object]) -> AsyncIterator[FakeModel]:
    """Bộ não đã đồng bộ, khóa nhà cung cấp đã lưu (commit), model giả; dọn pool checkpoint sau test."""
    from app.core import db
    from app.domain import store
    from app.gateway import models
    from app.tasks import engine, graph, hooks  # noqa: F401 — đăng ký xử lý phê duyệt

    async with db.engine().begin() as c:
        await store.put_secret(c, "provider.anthropic.api_key", "sk-ant-test-" + "a" * 30, "test")
        await store.put_secret(c, "provider.openai.api_key", "sk-test-" + "o" * 30, "test")
    fake = FakeModel()
    models.transport = httpx.MockTransport(fake)
    yield fake
    models.transport = None
    await graph.close()
    engine.reset_kick()
    await db.dispose()


async def make_task(**kw: Any) -> dict[str, Any]:
    from app.core import db
    from app.tasks import engine

    kw.setdefault("created_by", "user:owner")
    async with db.engine().begin() as c:
        return await engine.create(c, **kw)


async def task(tid: str) -> dict[str, Any]:
    from app.core import db
    from app.tasks import engine

    async with db.engine().connect() as c:
        return await engine.get(c, tid)


async def rows(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    from app.core import db

    async with db.engine().connect() as c:
        return [dict(r) for r in await db.all_(c, sql, params or {})]


async def drain(rounds: int = 60) -> int:
    from app.workers.agents import drain as _drain

    return await _drain("test-worker", rounds)
