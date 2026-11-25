"""Tác nhân bảo trì: soạn ĐỀ XUẤT và ca kiểm thử cho người triển khai xem xét. Không bao giờ tự sửa website."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from ..store import Store


def report(store: Store, cfg, calib: dict | None = None) -> Path:
    d = dt.date.today()
    out = Path(cfg.proposals_dir) / f"{d.isoformat()}-de-xuat-bao-tri.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    usage = store.all("SELECT day, COUNT(*) n, SUM(cost_usd) cost, SUM(ok) ok FROM llm_usage WHERE day >= date('now','-30 day') GROUP BY day ORDER BY day")
    hits = store.one("SELECT COUNT(*) n, COALESCE(SUM(hit),0) h FROM memory_hits WHERE day >= date('now','-30 day')")
    jobs = store.all("SELECT * FROM jobs ORDER BY name")
    rejected = store.all("SELECT kind, result FROM outbox WHERE status = 'rejected' ORDER BY created_at DESC LIMIT 10")
    cat = store.cache_get("catalog", {})
    unanswered = cat.get("unanswered_questions", [])[:10]

    lines = [f"# Đề xuất bảo trì — {d.strftime('%d/%m/%Y')}", "",
             "> Tệp do dịch vụ AI soạn để người phụ trách xem xét. Không có thay đổi nào được áp dụng tự động.", ""]
    lines += ["## Hiệu quả bộ nhớ và chi phí LLM (30 ngày)", ""]
    total_calls = sum(r["n"] for r in usage)
    total_cost = sum((r["cost"] or 0) for r in usage)
    rate = (hits["h"] / hits["n"] * 100) if hits["n"] else 0
    lines += [f"- Lượt gọi LLM: {total_calls}, chi phí ước tính: {total_cost:.3f} USD",
              f"- Tỷ lệ dùng lại bộ nhớ (không cần gọi LLM): {rate:.0f}% trên {hits['n']} lượt xét", ""]
    if calib:
        lines += ["## Hiệu chỉnh ngưỡng FAQ", "",
                  f"- Ngưỡng đề xuất: **{calib['recommended']}** (hiện cấu hình: {cfg.faq_threshold})",
                  f"- Độ chính xác {calib['best']['precision']:.0%}, độ phủ {calib['best']['recall']:.0%}, tỷ lệ trả lời đạt {calib['best']['accuracy']:.0%} trên {calib['n']} câu kiểm tra",
                  "- Đặt giá trị trong Quản trị → Cấu hình → *Ngưỡng khớp FAQ của chat* nếu đồng ý.", ""]
    lines += ["## Tác vụ nền", "", "| Tác vụ | Lần chạy cuối | Lỗi liên tiếp | Lỗi gần nhất |", "|---|---|---|---|"]
    lines += [f"| {j['name']} | {j['last_run'] or '-'} | {j['failures']} | {(j['last_error'] or '')[:80]} |" for j in jobs]
    if unanswered:
        lines += ["", "## Câu hỏi khách chưa có câu trả lời", "", "Đề xuất bổ sung FAQ (tác nhân FAQ sẽ soạn nháp nếu LLM được bật):", ""]
        lines += [f"- ({q['n']} lần) {q['question']}" for q in unanswered]
    if rejected:
        lines += ["", "## Bản nháp bị website từ chối", ""]
        lines += [f"- {r['kind']}: {r['result'][:160]}" for r in rejected]
    lines += ["", "## Ca kiểm thử đề xuất trước khi áp dụng thay đổi", "",
              "1. Chạy `XUONG_DB=xuong_test php tests/acceptance.php` trên môi trường thử nghiệm — tất cả ca phải ĐẠT.",
              "2. Nếu đổi ngưỡng FAQ: chạy `python -m xuong_ai calibrate` sau khi đổi và kiểm tra độ chính xác không giảm.",
              "3. Thử chat với 5 câu trong danh sách chưa trả lời ở trên; câu không có FAQ phải hiện kênh hỗ trợ.",
              "4. Sao lưu production (`php bin/backup.php`) trước khi chạy migration mới.", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
