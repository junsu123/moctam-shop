"""Tác nhân nội dung SEO & tư vấn: bản nháp blog và FAQ từ thông tin sản phẩm ĐÃ DUYỆT.

Bộ nhớ trước, LLM sau: câu hỏi đã có FAQ đã duyệt (điểm ≥ ngưỡng, cùng loại câu hỏi) → không gọi LLM.
Mọi bản nháp gửi website đều ở trạng thái chờ duyệt, kèm nguồn tham chiếu (product_id + info_version).
"""
from __future__ import annotations

import hashlib
import logging

from .. import textnorm
from ..llm import BudgetExceeded, Llm, LlmUnavailable, parse_json_block
from ..memory import Memory, question_type
from ..store import Store
from . import enqueue

log = logging.getLogger("xuong_ai.content")

SYSTEM = (
    "Bạn là biên tập viên nội dung cho một xưởng nhỏ ở Việt Nam bán trà túi lọc, bột ngũ cốc, bột thiên nhiên và cà phê. "
    "Chỉ dùng THÔNG TIN ĐƯỢC CUNG CẤP. Không bịa số liệu, công dụng chữa bệnh, chứng nhận hay giá. "
    "Không đưa giá cụ thể vào nội dung (giá thay đổi; website hiển thị giá hiện hành). "
    "Nếu thông tin không có, hãy hướng người đọc liên hệ xưởng. Viết tiếng Việt tự nhiên, câu ngắn, giọng thân thiện. "
    "Trả lời DUY NHẤT một đối tượng JSON."
)


def _facts(p: dict) -> str:
    lines = [f"Tên: {p['name']}", f"Mô tả: {p.get('short_desc') or ''}"]
    for k, label in (("ingredients", "Thành phần"), ("usage_guide", "Cách dùng"), ("storage_guide", "Bảo quản"), ("allergens", "Dị ứng")):
        if p.get(k):
            lines.append(f"{label}: {p[k]}")
    lines.append("Quy cách: " + "; ".join(f"{s['variant_label']}" for s in p.get("skus", [])))
    return "\n".join(lines)


def blog_drafts(store: Store, llm: Llm, catalog: dict, limit: int = 2) -> dict:
    done = {r["source_ref"] for r in store.all("SELECT source_ref FROM knowledge WHERE kind = 'blog_outline'")}
    made, skipped = 0, 0
    for p in catalog.get("products", []):
        if made >= limit:
            break
        ref = f"blog:product:{p['id']}@v{p['info_version']}"
        if ref in done:
            skipped += 1
            continue
        prompt = (
            "Viết một bài blog 450–700 chữ hướng dẫn sử dụng/bảo quản và gợi ý cách thưởng thức sản phẩm dưới đây.\n"
            "HTML chỉ dùng thẻ p, h2, h3, ul, li, strong. JSON gồm: title (≤ 70 ký tự), meta_description (≤ 155 ký tự), keywords, body.\n\n"
            + _facts(p)
        )
        try:
            data = parse_json_block(llm.complete("blog_draft", SYSTEM, prompt, max_tokens=2000))
        except (BudgetExceeded, LlmUnavailable) as e:
            log.warning("Dừng soạn blog: %s", e)
            break
        except ValueError as e:
            log.warning("Phản hồi không hợp lệ cho sản phẩm %s: %s", p["id"], e)
            continue
        enqueue(store, ref, "blog", {
            "title": data.get("title", "")[:250], "meta_description": data.get("meta_description", "")[:320], "keywords": data.get("keywords", ""),
            "body": data.get("body", ""), "product_id": p["id"], "category_id": p["category_id"],
            "source_refs": [{"product_id": p["id"], "info_version": p["info_version"]}], "generated_by": llm.cfg.model,
        })
        Memory(store).add_pending("blog_outline", ref, data.get("title", p["name"]), "", "san_pham", p["category_id"], p["id"], str(p["info_version"]))
        made += 1
    return {"drafted": made, "skipped_existing": skipped}


def cluster_questions(questions: list[dict], sim: float = 0.3) -> list[dict]:
    """Gom câu hỏi gần nghĩa (BM25 chuẩn hóa; khớp hoàn toàn ≈ 0.45) để mỗi cụm chỉ soạn một FAQ."""
    clusters: list[dict] = []
    for q in sorted(questions, key=lambda x: -int(x.get("n", 1))):
        docs = {i: c["rep"] for i, c in enumerate(clusters)}
        best = textnorm.rank(q["question"], docs)[:1] if docs else []
        if best and best[0][1] >= sim:
            c = clusters[best[0][0]]
            c["n"] += int(q.get("n", 1))
            c["variants"].append(q["question"])
        else:
            clusters.append({"rep": q["question"], "n": int(q.get("n", 1)), "variants": [q["question"]]})
    return clusters


def faq_drafts(store: Store, llm: Llm, catalog: dict, threshold: float, limit: int = 5) -> dict:
    mem = Memory(store)
    stats = {"clusters": 0, "memory_hits": 0, "drafted": 0, "llm_skipped": 0}
    questions = catalog.get("unanswered_questions", [])
    clusters = cluster_questions(questions)
    stats["clusters"] = len(clusters)
    for c in clusters:
        if stats["drafted"] >= limit:
            break
        q = c["rep"]
        qt = question_type(q)
        hits = mem.search(q, kinds=("faq",), statuses=("approved", "pending"), qtype=qt)
        top = hits[0] if hits else None
        if top and top[1] >= threshold:
            # Đã có tri thức (đã duyệt hoặc đang chờ duyệt) → không gọi LLM
            mem.record_hit("faq_draft", True, top[1])
            stats["memory_hits"] += 1
            continue
        mem.record_hit("faq_draft", False, top[1] if top else None)
        ref = "faq:q:" + hashlib.sha1(textnorm.fold(q).encode()).hexdigest()[:12]
        if store.one("SELECT 1 FROM outbox WHERE client_ref = ?", (ref,)):
            continue
        # Ngữ cảnh: FAQ đã duyệt + nhãn sản phẩm liên quan nhất
        ctx_rows = mem.search(q, kinds=("faq", "label"), statuses=("approved",), limit=4)
        ctx = "\n\n".join(f"[{r['kind']}] {r['title']}\n{textnorm.redact(r['body'].split('[search] ')[0])[:800]}" for r, _ in ctx_rows)
        refs = [{"product_id": r["product_id"], "info_version": int(r["source_version"])} for r, _ in ctx_rows if r["kind"] == "label" and r["source_version"]]
        prompt = (
            f"Khách hỏi (các cách hỏi khác nhau): {'; '.join(c['variants'][:5])}\n\n"
            f"Thông tin đã duyệt của xưởng:\n{ctx or '(không có)'}\n\n"
            "Soạn MỘT câu hỏi thường gặp chuẩn và câu trả lời 2–5 câu, chỉ dựa trên thông tin trên. "
            "Nếu thông tin không đủ, câu trả lời phải mời khách liên hệ hotline/Zalo của xưởng, không phỏng đoán. "
            'JSON: {"question": ..., "answer": ..., "keywords": "từ khóa không dấu, cách nhau dấu phẩy", "sufficient": true|false}'
        )
        try:
            data = parse_json_block(llm.complete("faq_draft", SYSTEM, prompt, max_tokens=700))
        except (BudgetExceeded, LlmUnavailable) as e:
            log.warning("Dừng soạn FAQ: %s", e)
            stats["llm_skipped"] += 1
            break
        except ValueError:
            continue
        enqueue(store, ref, "faq", {
            "title": data.get("question", q)[:250], "body": data.get("answer", ""), "body_is_text": True,
            "keywords": data.get("keywords", ""), "source_refs": refs + [{"asked": c["n"], "sufficient": bool(data.get("sufficient"))}],
            "generated_by": llm.cfg.model,
        })
        mem.add_pending("faq", ref, data.get("question", q), data.get("answer", ""), qt, source_version=None, ttl_days=60)
        stats["drafted"] += 1
    return stats
