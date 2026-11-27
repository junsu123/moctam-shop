"""Telegram Bot API giả cho kiểm thử E2E (chỉ dùng trong e2e/, không bao giờ trong production).

- /bot<TOKEN>/getMe, sendMessage, getUpdates (long-poll tối đa `timeout` giây)
- /__push  (POST JSON update) để giả lập điện thoại nhắn bot
- /__sent  (GET) để xem bot đã gửi gì
"""

from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "123456789:AAH" + "e2e" * 11
updates: list[dict] = []
sent: list[dict] = []
cond = threading.Condition()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a: object) -> None:  # yên lặng
        pass

    def _json(self, code: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self) -> None:
        if self.path == "/__sent":
            return self._json(200, sent)
        self._json(404, {"ok": False})

    def do_POST(self) -> None:
        if self.path == "/__push":
            u = self._body()
            with cond:
                u["update_id"] = len(updates) + 1
                updates.append(u)
                cond.notify_all()
            return self._json(200, {"ok": True})
        m = re.fullmatch(r"/bot([^/]+)/(\w+)", self.path)
        if not m:
            return self._json(404, {"ok": False})
        token, method = m.groups()
        if token != TOKEN:
            return self._json(401, {"ok": False, "description": "Unauthorized"})
        b = self._body()
        if method == "getMe":
            return self._json(200, {"ok": True, "result": {"id": 1, "is_bot": True, "username": "xuongtra_ai_bot"}})
        if method == "sendMessage":
            sent.append(b)
            return self._json(200, {"ok": True, "result": {"message_id": len(sent)}})
        if method == "getUpdates":
            off, wait = int(b.get("offset", 0)), min(int(b.get("timeout", 0)), 5)
            with cond:
                cond.wait_for(lambda: any(u["update_id"] >= off for u in updates), timeout=wait)
                res = [u for u in updates if u["update_id"] >= off]
            return self._json(200, {"ok": True, "result": res})
        self._json(404, {"ok": False})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
