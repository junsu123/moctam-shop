"""Khái niệm của văn phòng AI: mục tiêu, nhân sự, tín hiệu, việc, việc cần người, quyết định."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

FMT = "%Y-%m-%d %H:%M:%S"
VN = dt.timezone(dt.timedelta(hours=7))  # Việt Nam không đổi giờ mùa hè → không cần tzdata (Windows)

GOALS = {
    "van_hanh": "Website vận hành ổn định, dữ liệu đồng bộ kịp thời",
    "tra_loi_khach": "Khách hỏi gì cũng có câu trả lời đúng",
    "giu_chan": "Nhắc khách cũ mua lại đúng lúc",
    "gia_tri_don": "Tăng giá trị đơn bằng gợi ý mua kèm",
    "noi_dung_seo": "Mỗi sản phẩm có nội dung SEO cập nhật",
}


@dataclass(frozen=True)
class Role:
    code: str
    title: str
    duty: str
    uses_llm: bool = False


ROSTER: dict[str, Role] = {r.code: r for r in [
    Role("truong_phong", "Trưởng văn phòng", "Quan sát website, cân nhắc ưu tiên, giao việc, rút kinh nghiệm, viết bản tin"),
    Role("thu_ky", "Thư ký dữ liệu", "Đồng bộ đơn, danh mục và kết quả duyệt; gửi bản nháp lên website"),
    Role("tu_van", "Tư vấn viên", "Soạn FAQ cho câu hỏi khách chưa có câu trả lời", uses_llm=True),
    Role("bien_tap", "Biên tập SEO", "Soạn bài blog từ thông tin nhãn đã duyệt", uses_llm=True),
    Role("cham_soc", "Chăm sóc khách", "Lập danh sách khách đến kỳ mua lại (chỉ khách đã đồng ý)"),
    Role("phan_tich", "Phân tích bán hàng", "Tìm cặp sản phẩm hay được mua cùng nhau"),
    Role("ky_thuat", "Kỹ thuật bảo trì", "Hiệu chỉnh ngưỡng chat, báo cáo sức khỏe hệ thống"),
    Role("chu_xuong", "Chủ xưởng / nhân viên", "Người quyết những việc AI không được tự làm"),
]}

VERDICTS = {
    "assign": "Giao việc",
    "defer": "Hoãn",
    "block": "Chặn",
    "skip": "Bỏ qua",
}


@dataclass
class Signal:
    """Điều bộ não nhận thấy. severity 0..1."""
    key: str
    kind: str
    goal: str
    severity: float
    title: str
    evidence: dict = field(default_factory=dict)


@dataclass
class Escalation:
    """Việc cần người: AI không được (hoặc không nên) tự làm."""
    key: str
    goal: str
    severity: float
    title: str
    detail: str = ""


@dataclass
class Task:
    key: str
    action: str
    role: str
    goal: str
    severity: float
    reason: str
    params: dict = field(default_factory=dict)
    needs_site: bool = True
    llm_calls: int = 0
    drafts: int = 0          # số mục sẽ chờ nhân viên duyệt
    review_kind: str | None = None
    score: float = 0.0
    why_score: str = ""


@dataclass
class Decision:
    task: Task
    verdict: str             # assign | defer | block | skip
    why: str


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def fmt(t: dt.datetime) -> str:
    return t.strftime(FMT)


def parse(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.strptime(s[:19], FMT)
    except ValueError:
        return dt.datetime.fromisoformat(s[:10])


def local(t: dt.datetime) -> dt.datetime:
    """UTC (naive) → giờ Việt Nam (naive)."""
    return (t.replace(tzinfo=dt.UTC)).astimezone(VN).replace(tzinfo=None)
