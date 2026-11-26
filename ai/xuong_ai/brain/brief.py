"""Báo cáo của văn phòng: bản tin mỗi sáng (Markdown), xem bộ não đang nghĩ gì, và tình hình nhân sự.

Viết bằng mẫu cố định, không gọi LLM — không tốn chi phí, không bịa số liệu.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import learning, state
from .model import GOALS, ROSTER, VERDICTS, fmt, local

WEEKDAY = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
BACKLOG_LABEL = {"faq": "FAQ", "blog": "Bài blog", "cross_sell": "Gợi ý mua kèm", "care": "Khách cần chăm sóc"}


def _sev(x: float) -> str:
    return "Cao" if x >= 0.7 else ("Vừa" if x >= 0.4 else "Thấp")


def _vnd(n: int) -> str:
    return f"{n:,.0f}".replace(",", ".") + " ₫"


def _ago(store, now):
    return fmt(now - dt.timedelta(hours=24))


def render(brain, now: dt.datetime) -> str:
    s = brain.store
    th = brain.think(now)
    facts = th["ctx"].facts
    loc = local(now)
    esc = th["escalations"]
    since = _ago(s, now)
    done = s.all("SELECT role, action, status, COUNT(*) n FROM brain_tasks WHERE started_at >= ? GROUP BY role, action, status", (since,))
    n_done = sum(r["n"] for r in done if r["status"] == "done")
    n_fail = sum(r["n"] for r in done if r["status"] == "failed")
    bl = facts.get("backlog", {})
    n_review = learning.pending_review_items(bl)
    llm = facts.get("llm", {})

    L = [f"# Bản tin văn phòng AI — {WEEKDAY[loc.weekday()]} {loc.strftime('%d/%m/%Y')}", ""]
    parts = [f"{len(esc)} việc cần anh/chị quyết" if esc else "không có việc gì cần anh/chị quyết",
             f"văn phòng đã làm {n_done} việc trong 24 giờ" + (f" ({n_fail} lỗi)" if n_fail else ""),
             f"{n_review} bản nháp chờ duyệt"]
    if llm.get("available"):
        parts.append(f"LLM hôm nay {llm.get('calls', 0)} lượt / {llm.get('cost_usd', 0):.3f} USD")
    L += ["**Tóm tắt:** " + " · ".join(parts) + ".", ""]
    if brain.cfg.brain.paused or (brain.cfg.brain.stop_file and brain.cfg.brain.stop_file.exists()):
        L += ["> ⏸ Văn phòng đang **tạm dừng**. Bỏ `paused = true` trong config.toml hoặc xóa tệp STOP để làm việc lại.", ""]

    L += ["## Cần anh/chị quyết", ""]
    if esc:
        for i, e in enumerate(esc, 1):
            L.append(f"{i}. **[{_sev(e.severity)}] {e.title}**  ")
            if e.detail:
                L.append(f"   {e.detail}")
    else:
        L.append("Không có. Văn phòng tự lo được mọi việc hiện tại.")
    L.append("")

    sales = facts.get("sales")
    if sales:
        L += ["## Tình hình bán hàng", "",
              f"- Đơn 24 giờ qua: **{sales['orders_24h']}**" + (f" (bình thường khoảng {sales['baseline_per_day']}/ngày)" if sales.get("enough_history") else ""),
              f"- 7 ngày qua: {sales['orders_7d']} đơn, {_vnd(sales['revenue_7d'])} (không tính đơn hủy)"]
        L += [f"- {n}" for n in facts.get("notes", [])]
        L.append("")

    work = [x for x in th["signals"] if x.kind != "routine"]
    L += ["## Bộ não nhận thấy", ""]
    if work:
        for x in work[:10]:
            L.append(f"- [{_sev(x.severity)}] {x.title} — _{GOALS.get(x.goal, x.goal)}_")
        if len(work) > 10:
            L.append(f"- … và {len(work) - 10} tín hiệu khác (xem `python -m xuong_ai think`)")
    else:
        L.append("- Không có khoảng trống nào cần xử lý.")
    L.append("")

    L += ["## Văn phòng đã làm (24 giờ qua)", "", "| Nhân viên | Việc | Xong | Lỗi |", "|---|---|---|---|"]
    agg: dict = {}
    for r in done:
        a = agg.setdefault((r["role"], r["action"]), [0, 0])
        a[0 if r["status"] == "done" else 1] += r["n"]
    for (role, action), (ok, bad) in sorted(agg.items()):
        L.append(f"| {ROSTER[role].title if role in ROSTER else role} | {action} | {ok} | {bad} |")
    if not agg:
        L.append("| — | (máy tắt hoặc chưa có việc) | 0 | 0 |")
    drafts = s.all("SELECT action, result FROM brain_tasks WHERE status='done' AND action IN ('faq_draft','blog_draft') AND started_at >= ? ORDER BY id", (since,))
    if drafts:
        L += ["", "Bản nháp mới gửi lên website (chờ duyệt):"]
        for r in drafts:
            d = json.loads(r["result"] or "{}")
            again = " _(soạn lại theo góp ý)_" if ":r" in (d.get("client_ref") or "") else ""
            L.append(f"- {'FAQ' if r['action'] == 'faq_draft' else 'Blog'}: {d.get('question') or d.get('title') or d.get('client_ref')}{again}")
    L.append("")

    L += ["## Đang chờ duyệt trên website", ""]
    if bl.get("known"):
        L.append(" · ".join(f"{lab}: {int(bl.get(k) or 0)}" for k, lab in BACKLOG_LABEL.items()))
        if bl.get("oldest_pending_at"):
            L.append(f"\nBản nháp chờ lâu nhất từ {bl['oldest_pending_at']} UTC.")
    else:
        L.append("Chưa lấy được số liệu (website chưa có API phản hồi hoặc chưa đồng bộ lần nào).")
    L.append("")

    held = s.all("SELECT d.task_key, d.action, d.verdict, d.why FROM brain_decisions d JOIN (SELECT task_key, MAX(id) mid FROM brain_decisions "
                 "WHERE at >= ? GROUP BY task_key) m ON m.mid = d.id WHERE d.verdict IN ('defer','block') ORDER BY d.id DESC", (since,))
    if held:
        L += ["## Việc đã hoãn hoặc chặn — và vì sao", ""]
        by_why: dict = {}
        for r in held:
            by_why.setdefault((r["verdict"], r["why"]), []).append(r["action"])
        for (v, why), acts in list(by_why.items())[:8]:
            L.append(f"- {VERDICTS[v]} {len(acts)} việc ({', '.join(sorted(set(acts)))}): {why}")
        L.append("")

    les = learning.lessons(s, now)
    L += ["## Bài học từ phản hồi của người duyệt", ""]
    L += [f"- {x}" if not x.startswith("  ") else f"  - {x.strip()}" for x in les] or ["- Chưa đủ bản nháp được duyệt để rút kinh nghiệm (cần ≥ 3 mỗi loại)."]
    L += ["", "---", "_Bản tin do văn phòng AI tự soạn từ dữ liệu cục bộ (không có thông tin cá nhân của khách). "
          "Mọi bản nháp đều chờ nhân viên duyệt trên website; văn phòng không tự xuất bản hay sửa đơn, giá, kho._", ""]
    return "\n".join(L)


def write(brain, now: dt.datetime) -> Path:
    d = brain.cfg.brain.office_dir
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{local(now).date().isoformat()}-ban-tin-van-phong.md"
    p.write_text(render(brain, now), encoding="utf-8")
    return p


# ---------------------------------------------------------------------- dòng lệnh
def format_thoughts(th: dict) -> str:
    L = ["BỘ NÃO ĐANG NGHĨ GÌ (chạy thử — không làm việc nào, không ghi gì)", ""]
    L.append(f"Tín hiệu ({len(th['signals'])}):")
    for x in th["signals"]:
        L.append(f"  [{x.severity:.2f}] {x.title}")
    L.append("")
    L.append(f"Việc cần người ({len(th['escalations'])}):")
    for e in th["escalations"]:
        L.append(f"  [{_sev(e.severity)}] {e.title}")
    L.append("")
    L.append("Quyết định:")
    groups: list[list] = []  # gộp các quyết định giống nhau (cùng việc, cùng lý do) cho dễ đọc
    for d in th["decisions"]:
        if groups and d.verdict != "assign" and (groups[-1][0].verdict, groups[-1][0].task.action, groups[-1][0].why) == (d.verdict, d.task.action, d.why):
            groups[-1].append(d)
        else:
            groups.append([d])
    for g in groups:
        d = g[0]
        n = f" ×{len(g)}" if len(g) > 1 else ""
        L.append(f"  {VERDICTS[d.verdict]:<10} {ROSTER[d.task.role].title:<20} {d.task.action + n:<14} {d.why}")
        for x in g[:3]:
            L.append(f"  {'':<10} ↳ {x.task.reason}")
        if len(g) > 3:
            L.append(f"  {'':<10} ↳ … và {len(g) - 3} việc tương tự")
    if not th["decisions"]:
        L.append("  (không có việc nào)")
    return "\n".join(L)


def format_office(brain, now: dt.datetime) -> str:
    s = brain.store
    since = _ago(s, now)
    L = ["VĂN PHÒNG AI", ""]
    paused = brain.cfg.brain.paused or (brain.cfg.brain.stop_file and brain.cfg.brain.stop_file.exists())
    L.append("Trạng thái: " + ("TẠM DỪNG" if paused else "đang làm việc"))
    last_tick = s.one("SELECT * FROM brain_ticks ORDER BY id DESC LIMIT 1")
    L.append(f"Nhịp gần nhất: {last_tick['started_at'] + ' UTC' if last_tick else 'chưa chạy'}")
    L += ["", "Nhân sự (24 giờ qua):"]
    for code, r in ROSTER.items():
        row = s.one("SELECT SUM(status='done') ok, SUM(status='failed') bad, MAX(started_at) last FROM brain_tasks WHERE role = ? AND started_at >= ?", (code, since))
        stats = f"{row['ok'] or 0} xong, {row['bad'] or 0} lỗi" if row and row["last"] else "chưa có việc"
        if code == "chu_xuong":
            stats = f"{len(state.open_escalations(s))} việc đang chờ"
        elif code == "truong_phong":
            stats = f"{s.one('SELECT COUNT(*) n FROM brain_ticks WHERE started_at >= ?', (since,))['n']} nhịp"
        L.append(f"  {r.title:<22} {stats:<20} {r.duty}")
    L += ["", "Độ tin cậy học được (90 ngày):"]
    for kind, label in learning.KIND_LABEL.items():
        rel = learning.reliability(s, kind, now)
        L.append(f"  {label:<20} {rel['mean']:.0%}  ({rel['approved']} duyệt, {rel['edited']} sửa, {rel['rejected']} từ chối)")
    esc = state.open_escalations(s)
    L += ["", f"Việc cần chủ xưởng ({len(esc)}):"]
    L += [f"  [{_sev(e['severity'])}] {e['title']} (từ {e['first_seen']} UTC)" for e in esc] or ["  (không có)"]
    return "\n".join(L)
