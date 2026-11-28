"""Danh mục công cụ theo docs/AGENT_DESIGN.md §4.

Sprint 2 có 2 công cụ chạy thật, không cần tích hợp ngoài:
- `signals.read`: đọc tín hiệu nội bộ (chi phí AI, trạng thái agent, việc chờ duyệt);
- `notify.owner`: gửi báo cáo cho Owner qua Telegram (xếp vào hàng thông báo, tôn trọng giờ yên lặng).

Các công cụ còn lại đã khai báo (để Policy Engine và quyền của từng agent tham chiếu) nhưng chưa có tích hợp:
gọi sẽ nhận `NOT_CONFIGURED` (CLAUDE.md quy tắc 5). Tích hợp được thêm theo lộ trình Sprint 4–8.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core import db
from app.domain import notify
from app.tasks.tools import DelegateIn, DelegateOut, ShareIn, ShareOut, delegate, share
from app.tools.spec import ActionSpec, Handler, RetryPolicy, ToolCtx, act, register, tool

# ------------------------------------------------------------------ công cụ chạy thật


class SignalsIn(BaseModel):
    include: list[Literal["budget", "agents", "approvals"]] = Field(default=["budget", "agents", "approvals"])


class SignalsOut(BaseModel):
    at: datetime
    budget: dict[str, float] | None = None
    agents: dict[str, int] | None = None
    approvals_pending: int | None = None


async def _signals(ctx: ToolCtx, inp: SignalsIn) -> SignalsOut:
    from app.gateway.models import spend

    out = SignalsOut(at=datetime.now(UTC))
    if "budget" in inp.include:
        s = await spend(ctx.conn)
        out.budget = {k: float(s[k]) for k in ("today_usd", "allowed_today_usd", "month_usd", "month_cap_usd", "month_pct")}
    if "agents" in inp.include:
        out.agents = {r["state"]: int(r["n"]) for r in await db.all_(ctx.conn, "SELECT state, count(*) n FROM agent_status GROUP BY state")}
    if "approvals" in inp.include:
        out.approvals_pending = int(
            await db.scalar(ctx.conn, "SELECT count(*) FROM approvals WHERE status = 'pending' AND expires_at > now()") or 0
        )
    return out


class NotifyIn(BaseModel):
    text: str = Field(min_length=1, max_length=3500)
    kind: Literal["report", "alert"] = "report"
    urgent: bool = False


class NotifyOut(BaseModel):
    notification_id: int | None
    queued: bool


async def _notify(ctx: ToolCtx, inp: NotifyIn) -> NotifyOut:
    # Khóa chống trùng của lời gọi làm dedupe_key: chạy lại cùng khóa không gửi tin thứ hai
    nid = await notify.enqueue(
        ctx.conn, inp.kind, f"[{ctx.agent_key}] {inp.text}", urgent=inp.urgent, dedupe_key=f"tool:{ctx.idempotency_key}"
    )
    return NotifyOut(notification_id=nid, queued=nid is not None)


def _real(
    name: str,
    description: str,
    level: int,
    side: Literal["none", "internal", "external"],
    inp: type[BaseModel],
    out: type[BaseModel],
    handler: Handler,
) -> ActionSpec:
    return ActionSpec(
        name=name, description=description, min_level=level, side_effects=side, input_model=inp, output_model=out, handler=handler
    )


register(
    tool(
        "signals",
        "Tín hiệu nội bộ: chi phí AI, trạng thái agent, việc chờ duyệt",
        "low",
        _real("read", "Đọc tín hiệu", 1, "none", SignalsIn, SignalsOut, _signals),
        timeout_s=5,
    )
)
register(
    tool(
        "notify",
        "Báo cáo cho Owner qua Telegram (theo giờ yên lặng)",
        "low",
        _real("owner", "Gửi báo cáo/cảnh báo cho Owner", 3, "internal", NotifyIn, NotifyOut, _notify),
        timeout_s=5,
        retry=RetryPolicy(max_attempts=2),
    )
)

# ------------------------------------------------------------------ đã khai báo, chưa có tích hợp
register(
    tool(
        "site",
        "Website moctam qua API đồng bộ có khóa phạm vi",
        "medium",
        act("catalog", "Đọc sản phẩm, giá, tồn kho đã xác thực", 1, "none"),
        act("faq", "Đọc FAQ đã đăng", 1, "none"),
        act("crawl", "Quét trang của chính website", 1, "none"),
        act("page_audit", "Đo tốc độ/SEO trang (Lighthouse cục bộ)", 1, "none"),
        act("funnel_stats", "Số liệu phễu thanh toán", 1, "none"),
        act("aggregates", "Số liệu tổng hợp đơn hàng (đã ẩn danh)", 1, "none"),
        act("care_list", "Danh sách khách cần chăm sóc (chỉ customer_key)", 1, "none"),
        act("draft", "Gửi bản nháp FAQ/blog chờ duyệt", 2, "external"),
        act("publish", "Xuất bản FAQ/blog (ADR-16)", 3, "external"),  # bài rủi ro: Content Gate gắn publish_risky
        act("unpublish", "Gỡ bài đã xuất bản", 3, "external"),
    )
)
register(
    tool(
        "web",
        "Tìm kiếm và đọc trang web công khai (đọc cách ly)",
        "medium",
        act("search", "Tìm kiếm web", 1, "none", untrusted=True),
        act("fetch", "Đọc một trang (chặn mạng nội bộ)", 1, "none", untrusted=True),
    )
)
register(tool("gsc", "Google Search Console", "low", act("read", "Đọc hiển thị, click, vị trí", 1, "none")))
register(tool("ga4", "Google Analytics 4", "low", act("read", "Đọc lượt truy cập, chuyển đổi", 1, "none")))
register(
    tool(
        "task",
        "Giao việc giữa các agent (Task Engine, Sprint 4)",
        "low",
        act("create", "Tạo task con", 2, "internal"),
        _real("delegate", "Giao việc cho agent khác (có tiêu chí, ngân sách, hạn chót)", 2, "internal", DelegateIn, DelegateOut, delegate),
        act("review", "Review đầu ra của cấp dưới", 2, "internal"),
        timeout_s=10,
    )
)
register(tool("report", "Soạn báo cáo", "low", act("compose", "Soạn báo cáo cho Owner", 2, "internal")))
register(tool("analytics", "Phân tích tổng hợp", "low", act("overview", "Tổng quan KPI", 1, "none")))
register(
    tool("content_calendar", "Lịch nội dung", "low", act("read", "Xem lịch", 1, "none"), act("plan", "Đề xuất lịch đăng", 2, "internal"))
)
register(
    tool("image", "Tạo/sửa ảnh (Q-I6)", "medium", act("generate", "Tạo ảnh nháp", 2, "external"), act("edit", "Sửa ảnh", 2, "external"))
)
register(tool("video", "Tạo video (Q-I6)", "medium", act("generate", "Tạo video nháp", 2, "external")))
register(tool("brand", "Brand guidelines", "low", act("read_assets", "Đọc màu, font, logo, mẫu", 1, "none")))
register(tool("asset", "Kho tài nguyên (gắn nhãn AI tạo)", "low", act("store", "Lưu tài nguyên", 2, "internal")))
register(
    tool(
        "social",
        "Mạng xã hội qua API chính thức",
        "medium",
        act("read_metrics", "Đọc hiệu suất bài đăng", 1, "none"),
        act("public_profile_read", "Đọc hồ sơ công khai", 1, "none", untrusted=True),
    )
)
register(tool("trend", "Nghiên cứu xu hướng", "low", act("research", "Tìm xu hướng", 1, "none", untrusted=True)))
register(
    tool(
        "ads",
        "Nền tảng quảng cáo",
        "high",
        act("read_metrics", "Đọc CPA/ROAS/CAC", 1, "none"),
        act("create_draft_campaign", "Tạo chiến dịch nháp (chưa chạy)", 2, "external"),
        act("change_budget", "Đổi ngân sách chiến dịch", 3, "external", "spend_over_threshold"),
    )
)
register(
    tool(
        "support",
        "Hộp thư hỗ trợ khách (đã che dữ liệu)",
        "medium",
        act("read_inbox", "Đọc câu hỏi của khách", 1, "none", untrusted=True),
        act("draft_reply", "Soạn câu trả lời nháp", 2, "internal"),
        act("send_reply", "Gửi trả lời cho khách", 3, "external", "message_customer"),
    )
)
register(tool("crm", "CRM", "low", act("read", "Đọc khách hàng (ẩn danh)", 1, "none")))
register(
    tool(
        "lead",
        "Danh sách khách sỉ/đại lý tiềm năng",
        "medium",
        act("create", "Thêm lead (bắt buộc có nguồn)", 2, "internal"),
        act("score", "Chấm điểm lead", 2, "internal"),
        act("first_contact", "Liên hệ lần đầu", 3, "external", "contact_new_party"),
    )
)
register(
    tool(
        "partner",
        "Đối tác KOC/KOL",
        "medium",
        act("create", "Thêm đối tác tiềm năng", 2, "internal"),
        act("first_contact", "Liên hệ lần đầu", 3, "external", "contact_new_party"),
    )
)
register(
    tool(
        "experiment",
        "Thí nghiệm A/B, holdout",
        "medium",
        act("design", "Thiết kế thí nghiệm", 2, "internal"),
        act("launch_live", "Chạy thí nghiệm trên trang thật", 3, "external"),
    )
)
register(tool("sql", "Truy vấn chỉ đọc trên schema phân tích (đã ẩn danh)", "low", act("readonly", "Chạy truy vấn đọc", 1, "none")))
register(tool("python", "Sandbox tính toán (không mạng)", "low", act("sandbox", "Chạy phép tính", 1, "none")))
register(tool("finance", "Giá vốn, lợi nhuận (phạm vi owner_only)", "high", act("read", "Đọc số liệu tài chính", 1, "none")))
register(
    tool(
        "integration",
        "Tích hợp nền tảng",
        "high",
        act("status", "Tình trạng tích hợp", 1, "none"),
        act("enable", "Bật tích hợp mới hoặc cấp OAuth", 3, "external", "enable_integration"),
    )
)
register(tool("workflow", "Workflow đã duyệt", "medium", act("toggle", "Bật/tắt workflow đã duyệt", 3, "internal")))
register(tool("alerts", "Cảnh báo hệ thống", "low", act("raise", "Tạo cảnh báo kỹ thuật", 2, "internal")))
register(tool("email", "Email marketing", "high", act("send_bulk", "Gửi chiến dịch hàng loạt", 3, "external", "bulk_send")))
register(
    tool(
        "knowledge",
        "Chia sẻ kiến thức (qua thẩm định)",
        "low",
        _real("share", "Gửi ứng viên kiến thức vào hộp thẩm định", 2, "internal", ShareIn, ShareOut, share),
        timeout_s=10,
    )
)
