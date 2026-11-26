"""Đọc cấu hình TOML. Khóa API đặt trong tệp cấu hình hoặc biến môi trường, không đưa vào git."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SiteCfg:
    base_url: str
    read_key: str
    write_key: str
    timeout: float = 20.0


@dataclass
class LlmCfg:
    provider: str = "anthropic"          # anthropic | openai | none
    model: str = "claude-haiku-5-5"
    api_key: str = ""
    max_calls_per_day: int = 50
    max_cost_per_day_usd: float = 1.0
    price_in_per_mtok: float = 1.0       # USD / 1 triệu token đầu vào — cập nhật theo bảng giá nhà cung cấp
    price_out_per_mtok: float = 5.0
    timeout: float = 60.0


@dataclass
class BrainCfg:
    """Bộ não "Trưởng văn phòng": mục tiêu, nội quy và nhịp làm việc."""
    paused: bool = False                 # công tắc tạm dừng (hoặc tạo tệp STOP cạnh config.toml)
    tick_seconds: int = 60
    max_tasks_per_tick: int = 6
    max_pending_review: int = 15         # không để quá N bản nháp AI chờ nhân viên duyệt
    care_backlog_cap: int = 60           # danh sách chăm sóc còn quá N khách chưa xử lý → không gửi thêm
    human_only_question_types: list = field(default_factory=lambda: ["di_ung"])
    max_ai_attempts: int = 2             # bản nháp bị từ chối N lần → chuyển người viết
    brief_hour: int = 7                  # giờ (Việt Nam) viết bản tin văn phòng mỗi ngày
    goals: dict = field(default_factory=lambda: dict(DEFAULT_GOALS))
    daily_caps: dict = field(default_factory=lambda: dict(DEFAULT_DAILY_CAPS))
    stop_file: Path | None = None
    office_dir: Path | None = None


DEFAULT_GOALS = {          # trọng số mục tiêu: càng cao càng được ưu tiên
    "van_hanh": 1.0,       # website vận hành ổn định, dữ liệu đồng bộ kịp thời
    "tra_loi_khach": 0.8,  # khách hỏi gì cũng có câu trả lời đúng
    "giu_chan": 0.6,       # nhắc khách cũ mua lại đúng lúc
    "gia_tri_don": 0.4,    # gợi ý mua kèm
    "noi_dung_seo": 0.4,   # nội dung SEO cho sản phẩm
}

DEFAULT_DAILY_CAPS = {"faq_draft": 5, "blog_draft": 2, "care_list": 1, "crosssell": 1, "maintenance": 1}


@dataclass
class Cfg:
    site: SiteCfg
    llm: LlmCfg
    db_path: Path
    proposals_dir: Path
    faq_threshold: float = 0.10
    care_only_consented: bool = True
    care_horizon_days: int = 7
    care_overdue_days: int = 21
    crosssell_min_support: int = 2
    crosssell_max_per_product: int = 3
    blog_drafts_per_run: int = 2
    faq_drafts_per_run: int = 5
    schedule: dict = field(default_factory=dict)
    brain: BrainCfg = field(default_factory=BrainCfg)


DEFAULT_SCHEDULE = {  # phút
    "sync": 10,
    "catalog": 60,
    "feedback": 60,
    "crosssell": 24 * 60,
    "care": 24 * 60,
    "faq_drafts": 24 * 60,
    "blog_drafts": 7 * 24 * 60,
    "maintenance": 7 * 24 * 60,
}


def load(path: str | os.PathLike | None = None) -> Cfg:
    p = Path(path or os.environ.get("XUONG_AI_CONFIG", "config.toml"))
    raw = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    base = p.parent.resolve()
    s = raw.get("site", {})
    l = raw.get("llm", {})
    a = raw.get("agents", {})
    b = raw.get("brain", {})
    site = SiteCfg(
        base_url=os.environ.get("XUONG_SITE_URL", s.get("base_url", "http://127.0.0.1:8080")).rstrip("/"),
        read_key=os.environ.get("XUONG_READ_KEY", s.get("read_key", "")),
        write_key=os.environ.get("XUONG_WRITE_KEY", s.get("write_key", "")),
        timeout=float(s.get("timeout", 20)),
    )
    llm = LlmCfg(
        provider=l.get("provider", "anthropic"),
        model=l.get("model", "claude-haiku-5-5"),
        api_key=os.environ.get("XUONG_LLM_KEY", l.get("api_key", "")),
        max_calls_per_day=int(l.get("max_calls_per_day", 50)),
        max_cost_per_day_usd=float(l.get("max_cost_per_day_usd", 1.0)),
        price_in_per_mtok=float(l.get("price_in_per_mtok", 1.0)),
        price_out_per_mtok=float(l.get("price_out_per_mtok", 5.0)),
        timeout=float(l.get("timeout", 60)),
    )
    return Cfg(
        site=site,
        llm=llm,
        db_path=(base / raw.get("db_path", "data/xuong_ai.sqlite3")),
        proposals_dir=(base / raw.get("proposals_dir", "proposals")),
        faq_threshold=float(a.get("faq_threshold", 0.10)),
        care_only_consented=bool(a.get("care_only_consented", True)),
        care_horizon_days=int(a.get("care_horizon_days", 7)),
        care_overdue_days=int(a.get("care_overdue_days", 21)),
        crosssell_min_support=int(a.get("crosssell_min_support", 2)),
        crosssell_max_per_product=int(a.get("crosssell_max_per_product", 3)),
        blog_drafts_per_run=int(a.get("blog_drafts_per_run", 2)),
        faq_drafts_per_run=int(a.get("faq_drafts_per_run", 5)),
        schedule={**DEFAULT_SCHEDULE, **raw.get("schedule", {})},
        brain=BrainCfg(
            paused=bool(b.get("paused", False)),
            tick_seconds=int(b.get("tick_seconds", 60)),
            max_tasks_per_tick=int(b.get("max_tasks_per_tick", 6)),
            max_pending_review=int(b.get("max_pending_review", 15)),
            care_backlog_cap=int(b.get("care_backlog_cap", 60)),
            human_only_question_types=list(b.get("human_only_question_types", ["di_ung"])),
            max_ai_attempts=int(b.get("max_ai_attempts", 2)),
            brief_hour=int(b.get("brief_hour", 7)),
            goals={**DEFAULT_GOALS, **b.get("goals", {})},
            daily_caps={**DEFAULT_DAILY_CAPS, **b.get("daily_caps", {})},
            stop_file=base / "STOP",
            office_dir=base / b.get("office_dir", "office"),
        ),
    )
