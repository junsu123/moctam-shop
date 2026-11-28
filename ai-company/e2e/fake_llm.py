"""Nhà cung cấp AI giả cho kiểm thử E2E (chỉ dùng trong e2e/, không bao giờ trong production).

Trả lời như Anthropic /v1/messages và OpenAI /chat/completions, nội dung theo kịch bản đơn giản:
- lập kế hoạch: viết kết quả ngay (không dùng công cụ);
- nếu trong đề bài có góp ý của Owner: kết quả có câu "Đơn đặt trước 15 giờ được gửi sáng hôm sau".
"""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

calls: list[dict] = []


def answer(system: str, prompt: str) -> dict:
    title = (re.search(r"^Tiêu đề: (.*)$", prompt, re.M) or [None, ""])[1]
    if "Góp ý của Owner" in prompt:
        text = "Xưởng chưa giao trong ngày. Đơn đặt trước 15 giờ được gửi sáng hôm sau."
    else:
        text = "Xưởng chưa giao trong ngày ạ."
    out = {"title": title, "answer": text}
    if "Viết kết quả cuối" in prompt:
        return {"output": out, "confidence": 0.9, "claims": []}
    return {"summary": "Viết câu trả lời ngắn, thân thiện", "steps": [], "output": out, "confidence": 0.9, "claims": []}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a: object) -> None:
        pass

    def _json(self, code: int, body: object) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/__calls":
            return self._json(200, calls)
        self._json(404, {})

    def do_POST(self) -> None:
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        msgs = body.get("messages") or []
        system = body.get("system") or next((m["content"] for m in msgs if m.get("role") == "system"), "")
        prompt = msgs[-1]["content"] if msgs else ""
        calls.append({"path": self.path, "model": body.get("model")})
        text = json.dumps(answer(system, prompt), ensure_ascii=False)
        if self.path.endswith("/v1/messages"):
            return self._json(200, {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": 900, "output_tokens": 150}})
        if self.path.endswith("/chat/completions"):
            return self._json(200, {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 900, "completion_tokens": 150}})
        self._json(404, {"error": "không hỗ trợ"})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
