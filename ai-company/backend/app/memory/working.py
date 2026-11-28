"""Working memory (BRAIN_SPEC §3): mục tiêu, các bước đã làm, giả thuyết, việc chờ của task đang chạy.

Nằm trong Redis khi task chạy (nhanh, tự hết hạn sau 7 ngày nếu bị bỏ dở). Đóng task thì trả bản tóm tắt để runtime
lưu vào checkpoint/episodic, rồi xóa.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

TTL_S = 7 * 24 * 3600


class WorkingMemory:
    def __init__(self, agent_key: str, task_id: str, client: aioredis.Redis | None = None) -> None:
        self.r = client or aioredis.from_url(get_settings().redis_url, decode_responses=True)
        self.key = f"aico:wm:{agent_key}:{task_id}"

    async def set(self, field: str, value: Any) -> None:
        await self.r.hset(self.key, field, json.dumps(value, ensure_ascii=False))
        await self.r.expire(self.key, TTL_S)

    async def get(self, field: str) -> Any:
        v = await self.r.hget(self.key, field)
        return None if v is None else json.loads(v)

    async def add_step(self, step: dict[str, Any]) -> int:
        n = int(await self.r.rpush(self.key + ":steps", json.dumps(step, ensure_ascii=False)))
        await self.r.expire(self.key + ":steps", TTL_S)
        return n

    async def snapshot(self) -> dict[str, Any]:
        raw: dict[str, str] = await self.r.hgetall(self.key)  # type: ignore[assignment]
        fields: dict[str, Any] = {str(k): json.loads(v) for k, v in raw.items()}
        steps = [json.loads(s) for s in await self.r.lrange(self.key + ":steps", 0, -1)]
        return {**fields, "steps": steps}

    async def close(self) -> dict[str, Any]:
        snap = await self.snapshot()
        await self.r.delete(self.key, self.key + ":steps")
        return snap
