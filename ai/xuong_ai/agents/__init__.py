"""Các tác nhân AI. Mọi đầu ra gửi lên website đều ở trạng thái chờ duyệt."""
from __future__ import annotations

import json

from ..client import SiteClient, SiteError
from ..store import Store


def enqueue(store: Store, client_ref: str, kind: str, data: dict) -> bool:
    """Đưa vào hộp thư đi; client_ref xác định → không gửi trùng."""
    cur = store.db.execute("INSERT OR IGNORE INTO outbox(client_ref, kind, payload) VALUES(?,?,?)", (client_ref, kind, json.dumps(data, ensure_ascii=False)))
    return cur.rowcount == 1


def flush_outbox(store: Store, client: SiteClient, batch: int = 50) -> dict:
    rows = store.all("SELECT * FROM outbox WHERE status = 'queued' ORDER BY created_at LIMIT ?", (batch,))
    if not rows:
        return {"sent": 0}
    items = [{"client_ref": r["client_ref"], "kind": r["kind"], "data": json.loads(r["payload"])} for r in rows]
    try:
        res = client.send_drafts(items)
    except SiteError as e:
        store.db.executemany("UPDATE outbox SET attempts = attempts + 1, result = ? WHERE client_ref = ?", [(str(e), r["client_ref"]) for r in rows])
        raise
    stats = {"sent": len(rows), "accepted": 0, "rejected": 0}
    for r in res.get("results", []):
        st = "accepted" if r.get("status") == "accepted" else "rejected"
        stats[st] += 1
        store.db.execute("UPDATE outbox SET status = ?, result = ?, attempts = attempts + 1 WHERE client_ref = ?",
                         (st, json.dumps(r, ensure_ascii=False)[:1000], r.get("client_ref")))
    return stats
