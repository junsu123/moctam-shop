"""Gọi API đồng bộ của website (urllib, thử lại khi mạng gián đoạn)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class SiteError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.details = status, code, details or {}


class SiteClient:
    def __init__(self, base_url: str, read_key: str, write_key: str, timeout: float = 20.0, retries: int = 3):
        self.base, self.read_key, self.write_key, self.timeout, self.retries = base_url.rstrip("/"), read_key, write_key, timeout, retries

    def _req(self, method: str, path: str, key: str, params: dict | None = None, body=None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        last = None
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": f"Bearer {key}", "Accept": "application/json", "Content-Type": "application/json",
                "User-Agent": "xuong-ai/1.0",
            })
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode() or "{}")
            except urllib.error.HTTPError as e:
                try:
                    err = json.loads(e.read().decode()).get("error", {})
                except Exception:
                    err = {}
                if e.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(min(30, 2 ** attempt)); last = e; continue
                raise SiteError(e.code, err.get("code", "HTTP_ERROR"), err.get("message", str(e)), err.get("details")) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
                if attempt < self.retries:
                    time.sleep(min(30, 2 ** attempt)); continue
        raise SiteError(0, "NETWORK", f"Không kết nối được website: {last}")

    def events(self, after: int, limit: int = 500):
        return self._req("GET", "/api/sync/events", self.read_key, {"after": after, "limit": limit})

    def snapshot(self, after_id: int = 0, limit: int = 500):
        return self._req("GET", "/api/sync/snapshot", self.read_key, {"after_id": after_id, "limit": limit})

    def catalog(self):
        return self._req("GET", "/api/sync/catalog", self.read_key)

    def send_drafts(self, items: list[dict]):
        return self._req("POST", "/api/sync/drafts", self.write_key, body={"items": items})
