"""Gọi Claude hoặc OpenAI qua HTTP với hạn mức theo ngày (số lượt + chi phí). Ghi nhật ký sử dụng."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import LlmCfg
from .store import Store
from .textnorm import redact


class BudgetExceeded(Exception):
    pass


class LlmUnavailable(Exception):
    pass


class Llm:
    def __init__(self, cfg: LlmCfg, store: Store, transport=None):
        self.cfg, self.s = cfg, store
        self._transport = transport or self._http

    def usage_today(self) -> dict:
        r = self.s.one("SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd),0) AS cost FROM llm_usage WHERE day = date('now')")
        return {"calls": r["n"], "cost_usd": round(r["cost"], 4)}

    def available(self) -> bool:
        return self.cfg.provider != "none" and bool(self.cfg.api_key)

    def complete(self, task: str, system: str, user: str, max_tokens: int = 1500) -> str:
        if not self.available():
            raise LlmUnavailable("Chưa cấu hình LLM (provider/api_key).")
        u = self.usage_today()
        if u["calls"] >= self.cfg.max_calls_per_day or u["cost_usd"] >= self.cfg.max_cost_per_day_usd:
            raise BudgetExceeded(f"Đã chạm hạn mức ngày: {u}")
        system, user = redact(system), redact(user)  # không gửi SĐT/email
        try:
            text, tin, tout = self._transport(system, user, max_tokens)
            ok = 1
        except Exception:
            self._log(task, 0, 0, 0)
            raise
        cost = tin / 1e6 * self.cfg.price_in_per_mtok + tout / 1e6 * self.cfg.price_out_per_mtok
        self._log(task, tin, tout, cost, ok)
        return text

    def _log(self, task, tin, tout, cost, ok=0):
        self.s.db.execute("INSERT INTO llm_usage(day, task, provider, model, input_tokens, output_tokens, cost_usd, ok) VALUES(date('now'),?,?,?,?,?,?,?)",
                          (task, self.cfg.provider, self.cfg.model, tin, tout, cost, ok))

    def _http(self, system: str, user: str, max_tokens: int):
        if self.cfg.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": self.cfg.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            body = {"model": self.cfg.model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]}
        elif self.cfg.provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.cfg.api_key}", "content-type": "application/json"}
            body = {"model": self.cfg.model, "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        else:
            raise LlmUnavailable(self.cfg.provider)
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as r:
                d = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise LlmUnavailable(f"LLM lỗi {e.code}: {e.read()[:300]!r}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise LlmUnavailable(f"Không gọi được LLM: {e}") from None
        if self.cfg.provider == "anthropic":
            text = "".join(c.get("text", "") for c in d.get("content", []) if c.get("type") == "text")
            u = d.get("usage", {})
            return text, u.get("input_tokens", 0), u.get("output_tokens", 0)
        u = d.get("usage", {})
        return d["choices"][0]["message"]["content"], u.get("prompt_tokens", 0), u.get("completion_tokens", 0)


def parse_json_block(text: str) -> dict:
    """Lấy đối tượng JSON đầu tiên trong câu trả lời của mô hình."""
    s = text.find("{")
    e = text.rfind("}")
    if s < 0 or e <= s:
        raise ValueError("Không có JSON trong phản hồi")
    return json.loads(text[s:e + 1])
