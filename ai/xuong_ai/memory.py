"""Bộ nhớ tri thức (SQLite + BM25) — tìm quy tắc/mẫu đã duyệt TRƯỚC khi gọi LLM (đặc tả §6).

- Điểm tương đồng chỉ là MỘT tín hiệu: còn phải khớp loại câu hỏi/nhóm sản phẩm và phiên bản nguồn còn hiệu lực.
- Tri thức mới vào trạng thái 'pending'; chỉ 'approved' được dùng để trả lời.
- Mẫu hết hạn hoặc dựa trên nguồn đã thay đổi bị chuyển 'retired'.
"""
from __future__ import annotations

import datetime as dt
import hashlib

from . import textnorm
from .store import Store

QUESTION_TYPES = {
    "giao_hang": ["giao", "ship", "phi ship", "phi giao", "van chuyen", "bao lau", "nhan hang", "mien phi"],
    "thanh_toan": ["thanh toan", "chuyen khoan", "vietqr", "qr", "cod", "tra tien", "ck"],
    "doi_tra": ["doi tra", "hoan tien", "tra hang", "loi", "hong", "doi hang"],
    "bao_quan": ["bao quan", "han dung", "de duoc", "tu lanh", "am moc"],
    "cach_dung": ["cach dung", "cach pha", "pha", "uong", "lieu luong", "hom"],
    "di_ung": ["di ung", "gluten", "dau nanh", "sua", "dau phong", "tre em", "ba bau", "me bau"],
    "uu_dai": ["voucher", "ma giam", "khuyen mai", "flash sale", "giam gia", "uu dai"],
}


def question_type(text: str) -> str:
    f = " " + textnorm.fold(text) + " "
    best, n = "khac", 0
    for qt, kws in QUESTION_TYPES.items():
        hits = sum(1 for k in kws if f" {k} " in f)
        if hits > n:
            best, n = qt, hits
    return best


class Memory:
    def __init__(self, store: Store):
        self.s = store

    # ------------------------------------------------------------ nạp tri thức đã duyệt từ website
    def refresh_from_catalog(self, catalog: dict) -> dict:
        """FAQ đã xuất bản + nhãn sản phẩm là tri thức 'approved'. Mục không còn trên website → retired."""
        seen_faq, seen_label = set(), set()
        with self.s.tx() as db:
            for f in catalog.get("published_faqs", []):
                ref = f"faq:{f['id']}"
                ver = str(f.get("version_id") or hashlib.sha1((f["question"] + f["answer"]).encode()).hexdigest()[:10])
                seen_faq.add(ref)
                self._upsert(db, "faq", ref, ver, f["question"], f["answer"], "website_faq", "approved",
                             question_type(f["question"]), f.get("category_id"), f.get("product_id"),
                             extra_search=f.get("search_text"))
            for p in catalog.get("products", []):
                ref = f"product:{p['id']}"
                seen_label.add(ref)
                body = "\n".join(x for x in [
                    f"Thành phần: {p.get('ingredients')}" if p.get("ingredients") else "",
                    f"Cách dùng: {p.get('usage_guide')}" if p.get("usage_guide") else "",
                    f"Bảo quản: {p.get('storage_guide')}" if p.get("storage_guide") else "",
                    f"Dị ứng: {p.get('allergens')}" if p.get("allergens") else "",
                    "Quy cách: " + "; ".join(s["variant_label"] for s in p.get("skus", [])),
                ] if x)
                self._upsert(db, "label", ref, str(p["info_version"]), p["name"], body, "product_label", "approved",
                             "san_pham", p["category_id"], p["id"])
            # nguồn đã gỡ / đổi
            for r in db.execute("SELECT id, kind, source_ref FROM knowledge WHERE status = 'approved' AND source IN ('website_faq','product_label')").fetchall():
                if (r["kind"] == "faq" and r["source_ref"] not in seen_faq) or (r["kind"] == "label" and r["source_ref"] not in seen_label):
                    db.execute("UPDATE knowledge SET status = 'retired', updated_at = datetime('now') WHERE id = ?", (r["id"],))
            # mẫu hết hạn
            db.execute("UPDATE knowledge SET status = 'retired' WHERE expires_at IS NOT NULL AND expires_at < datetime('now') AND status <> 'retired'")
        return {"faqs": len(seen_faq), "labels": len(seen_label)}

    def _upsert(self, db, kind, ref, ver, title, body, source, status, qtype, cat, pid, extra_search=None):
        cur = db.execute("SELECT id, source_version FROM knowledge WHERE kind = ? AND source_ref = ?", (kind, ref)).fetchone()
        text_body = body if extra_search is None else body + "\n\n" + "[search] " + extra_search
        if cur:
            if cur["source_version"] != ver:
                db.execute("UPDATE knowledge SET title=?, body=?, source_version=?, status=?, question_type=?, category_id=?, product_id=?, updated_at=datetime('now') WHERE id=?",
                           (title, text_body, ver, status, qtype, cat, pid, cur["id"]))
            elif status == "approved":
                db.execute("UPDATE knowledge SET status='approved' WHERE id=? AND status='retired'", (cur["id"],))
        else:
            db.execute("INSERT INTO knowledge(kind, question_type, category_id, product_id, title, body, source, source_ref, source_version, status) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (kind, qtype, cat, pid, title, text_body, source, ref, ver, status))

    def add_pending(self, kind: str, ref: str, title: str, body: str, qtype: str, cat=None, pid=None, source_version: str | None = None, ttl_days: int | None = None):
        exp = (dt.datetime.now(dt.UTC).replace(tzinfo=None) + dt.timedelta(days=ttl_days)).strftime("%Y-%m-%d %H:%M:%S") if ttl_days else None
        self.s.db.execute(
            "INSERT OR IGNORE INTO knowledge(kind, question_type, category_id, product_id, title, body, source, source_ref, source_version, status, expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (kind, qtype, cat, pid, title, body, "llm", ref, source_version, "pending", exp))

    # ------------------------------------------------------------ truy hồi
    def search(self, query: str, kinds=("faq",), statuses=("approved",), qtype: str | None = None, category_id=None, limit: int = 5):
        ph_k = ",".join("?" * len(kinds))
        ph_s = ",".join("?" * len(statuses))
        rows = self.s.all(f"SELECT * FROM knowledge WHERE kind IN ({ph_k}) AND status IN ({ph_s})", (*kinds, *statuses))
        if qtype and qtype != "khac":
            same = [r for r in rows if r["question_type"] in (qtype, None, "khac")]
            rows = same or rows
        if category_id:
            rows = [r for r in rows if r["category_id"] in (None, category_id)] or rows
        docs = {r["id"]: self.doc_text(r) for r in rows}
        ranked = textnorm.rank(query, docs)[:limit]
        by_id = {r["id"]: r for r in rows}
        return [(by_id[i], s) for i, s in ranked]

    @staticmethod
    def doc_text(r) -> str:
        """Giống cách website dựng tài liệu FAQ: tiêu đề ×2 + search_text."""
        body = r["body"]
        if "[search] " in body:
            return f"{r['title']} {r['title']} {body.split('[search] ', 1)[1]}"
        return f"{r['title']} {r['title']} {textnorm.fold(r['title'] + ' ' + body[:600])}"

    def record_hit(self, task: str, hit: bool, score: float | None):
        self.s.db.execute("INSERT INTO memory_hits(day, task, hit, score) VALUES(date('now'), ?, ?, ?)", (task, 1 if hit else 0, score))
