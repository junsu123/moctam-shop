"""Website moctam giả cho kiểm thử E2E (chỉ dùng trong e2e/): /api/sync/catalog, /drafts, /publish, /unpublish.

Kiểm thử với website THẬT (PHP + MariaDB) nằm ở backend/tests/test_publishing.py (CI dựng bằng web/tests/it_server.sh).
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEYS = {
    "read": "xk_e2e_doc_" + "r" * 20,
    "drafts": "xk_e2e_nhap_" + "d" * 20,
    "publish": "xk_e2e_dang_" + "p" * 20,
}
PRODUCTS = [
    {
        "id": 1,
        "name": "Trà gừng mật ong",
        "category_id": 1,
        "info_version": 1,
        "skus": [{"variant_label": "Hộp 20 túi", "list_price": 65000}],
    }
]
published: dict[str, dict] = {}


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

    def _auth(self, kind: str) -> bool:
        if self.headers.get("authorization") != f"Bearer {KEYS[kind]}":
            self._json(
                403,
                {"error": {"code": "FORBIDDEN", "message": "Khóa không đúng quyền."}},
            )
            return False
        return True

    def do_GET(self) -> None:
        if self.path == "/api/sync/catalog" and self._auth("read"):
            self._json(200, {"products": PRODUCTS, "published_faqs": [], "published_blogs": []})
        elif self.path == "/__published":
            self._json(200, published)
        elif not self.path.startswith("/api/sync/catalog"):
            self._json(404, {})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        if self.path == "/api/sync/drafts" and self._auth("drafts"):
            self._json(
                200,
                {
                    "results": [
                        {
                            "client_ref": i["client_ref"],
                            "status": "accepted",
                            "result": "content:900",
                        }
                        for i in body["items"]
                    ]
                },
            )
        elif self.path == "/api/sync/publish" and self._auth("publish"):
            cid = 100 + len(published)
            published[body["client_ref"]] = {
                "content_id": cid,
                "status": "published",
                "url": "http://127.0.0.1:8083/hoi-dap.html",
            }
            self._json(200, published[body["client_ref"]])
        elif self.path == "/api/sync/unpublish" and self._auth("publish"):
            self._json(200, {"content_id": body["content_id"], "status": "unpublished"})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
