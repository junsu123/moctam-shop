"""E2E Control Center v1 (Playwright, Chromium): đi đúng đường Owner sẽ đi lần đầu.

Thiết lập → Tổng quan → tạm dừng agent → Diễn biến cập nhật trực tiếp → Telegram (token, mã kết nối, tin thử)
→ ngân sách → khóa API (hộp xác thực lại) → đăng xuất/đăng nhập. Ảnh chụp lưu ở e2e/screenshots/.
Chạy bằng ./run.sh (dựng sẵn máy chủ).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

import pyotp
import pytest
from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("AICO_E2E_URL", "http://127.0.0.1:3000")
TG = "http://127.0.0.1:8081"
TG_TOKEN = "123456789:AAH" + "e2e" * 11
SHOTS = Path(__file__).parent / "screenshots"
EMAIL, PASSWORD = "chu.xuong@xuongtramoc.vn", "tra-moc-mat-khau-2026"


class Codes:
    """Mã TOTP chưa dùng: máy chủ từ chối dùng lại mã của bước 30 giây đã dùng, nên mỗi lần lấy bước kế tiếp (chờ nếu cần)."""

    def __init__(self, secret: str) -> None:
        self.totp, self.last = pyotp.TOTP(secret), 0

    def fresh(self) -> str:
        now = int(time.time() // 30)
        step = max(now, self.last + 1)
        if step > now + 1:
            time.sleep((step - 1) * 30 - time.time() + 0.5)
        self.last = step
        return str(self.totp.at(step * 30))


def shot(page: Page, name: str) -> None:
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def setup_token() -> str:
    out = subprocess.run(
        ["uv", "run", "python", "-m", "app.cli", "setup-token"],
        cwd=os.environ["AICO_E2E_BACKEND_DIR"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    m = re.search(r"Mã thiết lập: (\S+)", out)
    assert m, out
    return m.group(1)


def tg_push(chat_id: int, text: str) -> None:
    body = json.dumps(
        {
            "message": {
                "chat": {
                    "id": chat_id,
                    "type": "private",
                    "first_name": "Điện thoại Owner",
                },
                "text": text,
            }
        }
    ).encode()
    urllib.request.urlopen(
        urllib.request.Request(f"{TG}/__push", body, {"content-type": "application/json"}),
        timeout=5,
    )


def tg_sent() -> list[dict[str, object]]:
    with urllib.request.urlopen(f"{TG}/__sent", timeout=5) as r:
        return json.loads(r.read())


@pytest.fixture(scope="module")
def page() -> Page:
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(
            viewport={"width": 1280, "height": 860},
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        pg = ctx.new_page()
        pg.csp_errors = []  # type: ignore[attr-defined]
        pg.on(
            "console",
            lambda m: "Content Security Policy" in m.text and pg.csp_errors.append(m.text),
        )  # type: ignore[attr-defined]
        yield pg
        b.close()


def test_control_center_first_run(page: Page) -> None:
    # 1. Lần đầu: chưa có cookie → đăng nhập → chưa có Owner → thiết lập
    resp = page.goto(BASE + "/")
    assert resp is not None
    expect(page).to_have_url(re.compile(r"/thiet-lap$"))
    csp = page.evaluate("() => document.querySelector('script[nonce]') !== null")
    assert csp, "script của Next phải mang nonce CSP"
    page.get_by_label("Mã thiết lập").fill(setup_token())
    page.get_by_label("Tên hiển thị").fill("Chủ xưởng")
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Mật khẩu", exact=True).fill(PASSWORD)
    page.get_by_label("Nhập lại mật khẩu").fill(PASSWORD)
    page.get_by_role("button", name="Tiếp tục").click()
    expect(page.get_by_role("heading", name="Bật xác thực hai lớp")).to_be_visible()
    expect(page.locator(".qr svg")).to_be_visible()
    shot(page, "01-thiet-lap-2fa")
    page.get_by_text("Không quét được?").click()
    secret = page.locator(".secret").inner_text().strip()
    totp = Codes(secret)
    page.get_by_label("Mã 6 số").fill(totp.fresh())
    with page.expect_response(lambda r: r.url.endswith("/auth/setup/confirm")) as confirm:
        page.get_by_role("button", name="Hoàn tất").click()
    assert confirm.value.ok, confirm.value.text()

    # 2. Tổng quan: danh sách việc thiết lập tính từ dữ liệu thật
    expect(page.get_by_role("heading", name="Tổng quan")).to_be_visible()
    expect(page.get_by_role("heading", name="Thiết lập ban đầu: còn 4 bước")).to_be_visible()
    expect(page.get_by_role("region", name="Agent", exact=True)).to_contain_text("15")
    shot(page, "02-tong-quan")

    # 3. Agent: tab theo phòng ban, tạm dừng SEO có lý do qua hộp xác nhận
    page.get_by_role("link", name="Agent", exact=True).click()
    page.get_by_role("tab", name=re.compile("^Marketing")).click()
    expect(page).to_have_url(re.compile(r"/agent\?tab=marketing$"))
    expect(page.locator("tbody tr")).to_have_count(6)
    row = page.locator("tr[data-agent=seo_agent]")
    row.get_by_role("button", name="Tạm dừng").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_role("textbox").fill("Chờ Owner duyệt bộ từ khóa")
    shot(page, "03a-agent-xac-nhan")
    dlg.get_by_role("button", name="Tạm dừng").click()
    expect(row.locator(".badge")).to_have_text("Tạm dừng")
    expect(row).to_contain_text("Chờ Owner duyệt bộ từ khóa")
    expect(page.locator(".toast").filter(has_text="Đã tạm dừng SEO")).to_be_visible()
    page.get_by_role("tab", name=re.compile("^Tất cả")).click()
    expect(page.locator("tbody tr")).to_have_count(15)
    page.get_by_label("Tìm agent").fill("quảng cáo")
    expect(page.locator("tbody tr")).to_have_count(1)
    page.get_by_label("Tìm agent").fill("")
    shot(page, "03-agent")

    # 3b. Trang từng agent: hồ sơ, bộ não, quyền công cụ, lịch sử (Sprint 2)
    page.get_by_role("link", name="SEO", exact=True).click()
    expect(page.get_by_role("heading", name="SEO", exact=True)).to_be_visible()
    expect(page.get_by_text("Đưa các trang của Xưởng Trà Mộc lên đúng ý định tìm kiếm")).to_be_visible()
    expect(page.get_by_text("Không bịa số liệu tìm kiếm")).to_be_visible()
    shot(page, "03b-agent-ho-so")
    page.get_by_role("tab", name="Bộ não").click()
    expect(page.get_by_role("heading", name="Bộ não đang chạy: v1.0.0")).to_be_visible()
    expect(page.locator(".badge").filter(has_text="Toàn vẹn")).to_be_visible()
    expect(page.locator("tr[data-brain='1.0.0'] .badge")).to_have_text("Đang chạy")
    shot(page, "03c-agent-bo-nao")
    page.get_by_role("tab", name=re.compile("^Quyền công cụ")).click()
    expect(page.locator("tr[data-perm='site.publish']")).to_contain_text("L3 Thực hiện")
    expect(page.locator("tr[data-perm='site.publish']")).to_contain_text("2 lần/ngày")
    shot(page, "03d-agent-quyen")
    page.get_by_role("tab", name="Lịch sử").click()
    expect(page.get_by_text("Nạp lần đầu: v1.0.0")).to_be_visible()

    # 4. Diễn biến: sự kiện mới đến ngay qua SSE, không cần tải lại trang
    page.get_by_role("link", name="Diễn biến").click()
    expect(page.get_by_text("Đang cập nhật trực tiếp")).to_be_visible(timeout=10_000)
    first = page.locator("table.feed tbody tr:not(.day)").first
    expect(first).to_contain_text("tạm dừng agent")
    other = page.context.new_page()
    other.goto(BASE + "/agent")
    other.locator("tr[data-agent=content_agent]").get_by_role("button", name="Tạm dừng").click()
    other.get_by_role("dialog").get_by_role("textbox").fill("Thử luồng trực tiếp")
    other.get_by_role("dialog").get_by_role("button", name="Tạm dừng").click()
    expect(other.locator(".toast")).to_be_visible()
    other.close()
    expect(first).to_contain_text("content_agent", timeout=10_000)
    expect(first).to_contain_text("Thử luồng trực tiếp")
    page.get_by_role("tab", name=re.compile("^Thao tác")).click()
    expect(page).to_have_url(re.compile(r"tab=audit$"))
    shot(page, "04-dien-bien")

    # 5. Cài đặt → tab Telegram: token cần xác thực lại → lưu → mã kết nối → điện thoại nhắn mã → chat xuất hiện
    page.get_by_role("link", name="Cài đặt").click()
    expect(page.get_by_role("tab", name="Telegram")).to_have_attribute("aria-selected", "true")
    page.get_by_label("Token do BotFather cấp").fill(TG_TOKEN)
    page.get_by_role("button", name="Kiểm tra và lưu").click()
    dlg = page.get_by_role("dialog")
    expect(dlg.get_by_role("heading", name="Xác nhận lại")).to_be_visible()
    shot(page, "05-xac-thuc-lai")
    dlg.get_by_label("Mật khẩu").fill(PASSWORD)
    dlg.get_by_label("Mã 6 số").fill(totp.fresh())
    dlg.get_by_role("button", name="Xác nhận").click()
    expect(page.locator(".toast").filter(has_text="Bot @xuongtra_ai_bot đã sẵn sàng")).to_be_visible()
    page.get_by_role("button", name="Tạo mã kết nối", exact=True).click()
    code = page.locator(".code-panel .code").inner_text().split()[-1]
    assert re.fullmatch(r"\d{6}", code)
    tg_push(5550001, f"/ketnoi {code}")
    expect(page.locator("table.chats tbody tr").filter(has_text="Điện thoại Owner")).to_be_visible(timeout=15_000)
    assert any("Đã kết nối" in str(m["text"]) for m in tg_sent())
    shot(page, "06-cai-dat-telegram")
    page.get_by_role("button", name="Gửi tin thử").click()
    deadline = time.time() + 15
    while time.time() < deadline and not any("Tin thử" in str(m["text"]) for m in tg_sent()):
        time.sleep(0.5)
    assert any("Tin thử" in str(m["text"]) for m in tg_sent()), tg_sent()

    # 6. Tab Ngân sách AI
    page.get_by_role("tab", name="Ngân sách AI").click()
    expect(page).to_have_url(re.compile(r"tab=ngan-sach$"))
    page.get_by_label("Trần mỗi tháng (USD)").fill("40")
    page.get_by_role("button", name="Lưu ngân sách").click()
    expect(page.locator(".toast").filter(has_text="Đã lưu ngân sách.")).to_be_visible()
    shot(page, "07-cai-dat-ngan-sach")

    # 7. Tab Giờ làm việc (tải lại trang vẫn đúng tab)
    page.get_by_role("tab", name="Giờ làm việc").click()
    expect(page).to_have_url(re.compile(r"tab=gio$"))
    page.reload()
    expect(page.get_by_role("tab", name="Giờ làm việc")).to_have_attribute("aria-selected", "true")
    expect(page.get_by_label("Telegram im lặng từ")).to_have_value("22:00")

    # 8. Tab Nhà cung cấp AI: lưu khóa (vẫn trong 5 phút xác thực lại nên không hỏi lại)
    page.get_by_role("tab", name="Nhà cung cấp AI").click()
    prov = page.get_by_role("region", name="Anthropic (Claude)")
    prov.get_by_label("Khóa API").fill("sk-ant-api03-" + "E" * 40 + "Z9Z9")
    prov.get_by_role("button", name="Lưu khóa").click()
    expect(prov).to_contain_text("…Z9Z9")
    expect(prov.locator(".card-head .badge")).to_have_text("Chưa kiểm tra")
    assert "EEEEEEEE" not in page.content()
    shot(page, "08-cai-dat-nha-cung-cap")

    # 8b. Phê duyệt: agent xin chạy thí nghiệm trên trang thật (luôn cần duyệt) → Owner từ chối kèm góp ý
    subprocess.run(
        ["uv", "run", "python", str(Path(__file__).parent / "make_approval.py")],
        cwd=os.environ["AICO_E2E_BACKEND_DIR"],
        check=True,
        capture_output=True,
    )
    page.get_by_role("link", name="Tổng quan").click()
    expect(page.get_by_text("1 việc đang chờ anh/chị duyệt.")).to_be_visible()
    page.goto(BASE + "/phe-duyet")
    expect(page.locator(".sb-count")).to_have_text("1")
    card = page.get_by_role("region", name="Giám đốc Tăng trưởng muốn: chạy thí nghiệm trên trang thật")
    expect(card).to_contain_text("Rủi ro vừa")
    expect(card).to_contain_text("nút mua to hơn")
    shot(page, "08b-phe-duyet")
    card.get_by_role("button", name="Từ chối").click()
    page.get_by_role("dialog").get_by_role("textbox").fill("Chưa đủ lượt truy cập để kết luận")
    page.get_by_role("dialog").get_by_role("button", name="Từ chối").click()
    expect(page.get_by_text("Không có việc nào chờ duyệt.")).to_be_visible()
    page.get_by_role("tab", name=re.compile("^Đã xử lý")).click()
    expect(page.get_by_role("region", name="Giám đốc Tăng trưởng muốn: chạy thí nghiệm trên trang thật")).to_contain_text("Chưa đủ lượt truy cập")
    page.goto(BASE + "/cai-dat?tab=cong-cu")
    expect(page.locator("tr[data-tool='signals']")).to_contain_text("Đã kết nối")
    expect(page.locator("tr[data-tool='ads']")).to_contain_text("Chưa kết nối")
    shot(page, "08c-cong-cu")

    # 8c. Trí nhớ (Sprint 3): Owner thêm kiến thức chung; agent truy hồi được bằng câu không dấu, có giải thích điểm
    page.get_by_role("link", name="Trí nhớ").click()
    expect(page.get_by_text("Chưa có mục nào")).to_be_visible()
    expect(page.get_by_text("Chưa bật")).to_be_visible()  # chưa có khóa OpenAI thật: chỉ tìm theo từ khóa
    page.get_by_role("button", name="Thêm kiến thức").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("Nhóm").select_option("policy")
    dlg.get_by_label("Tiêu đề").fill("Chính sách giao hàng")
    dlg.get_by_label("Nội dung").fill("Xưởng không giao trong ngày; đơn đặt trước 15 giờ được gửi ngay sáng hôm sau.")
    shot(page, "08d-them-kien-thuc")
    dlg.get_by_role("button", name="Lưu vào trí nhớ").click()
    expect(page.locator(".toast").filter(has_text="Đã thêm vào trí nhớ.")).to_be_visible()
    row = page.locator(".mem-list li").filter(has_text="Chính sách giao hàng")
    expect(row).to_contain_text("Kiến thức")
    expect(page.get_by_role("tab", name=re.compile("^Kiến thức chung"))).to_contain_text("1")
    row.locator(".mem-head").click()
    expect(row.locator(".mem-content")).to_contain_text("đơn đặt trước 15 giờ")
    shot(page, "08e-tri-nho")
    page.goto(BASE + "/agent/customer_agent?tab=tri-nho")
    page.get_by_placeholder("Ví dụ: viết bài trà gừng mật ong cho mùa đông").fill("sp co giao trong ngay ko")
    page.get_by_role("button", name="Thử truy hồi").click()
    hit = page.locator(".hits li").first
    expect(hit).to_contain_text("Chính sách giao hàng")
    expect(hit).to_contain_text("Từ khóa hạng 1")
    expect(page.locator(".preview")).to_contain_text("chỉ tìm theo từ khóa")
    shot(page, "08f-thu-truy-hoi")

    # 8g. Việc (Sprint 4a): Owner giao việc có review → agent làm thật qua đồ thị (AI giả) → yêu cầu sửa → agent sửa theo góp ý → duyệt
    page.get_by_role("link", name="Việc").click()
    expect(page.get_by_text("Không có việc nào đang chạy")).to_be_visible()
    page.get_by_role("button", name="Giao việc").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("Giao cho").select_option("customer_agent")
    dlg.get_by_label("Việc cần làm").fill("Trả lời khách hỏi có giao trong ngày không")
    dlg.get_by_label("Thế nào là xong (mỗi dòng một ý)").fill("thân thiện\nnói rõ giờ chốt đơn")
    dlg.get_by_label("Tôi xem lại trước khi xong (review)").check()
    shot(page, "08g-giao-viec")
    dlg.get_by_role("button", name="Giao việc").click()
    expect(page).to_have_url(re.compile(r"/viec/[0-9a-f-]{36}$"))
    expect(page.get_by_role("heading", name="Anh/chị review (vòng 1)")).to_be_visible(timeout=30_000)
    expect(page.locator(".output").first).to_contain_text("chưa giao trong ngày")
    page.get_by_label(re.compile("^Góp ý")).fill("Nói rõ giờ chốt đơn là 15 giờ")
    page.get_by_role("button", name="Yêu cầu sửa").click()
    expect(page.get_by_role("heading", name="Anh/chị review (vòng 2)")).to_be_visible(timeout=30_000)
    expect(page.locator(".output").first).to_contain_text("15 giờ")
    page.get_by_role("button", name="Duyệt").click()
    expect(page.locator(".task-summary")).to_contain_text("Xong", timeout=30_000)
    expect(page.locator(".timeline")).to_contain_text("Owner yêu cầu sửa (vòng 1): Nói rõ giờ chốt đơn là 15 giờ")
    expect(page.locator(".timeline")).to_contain_text("Ghi trải nghiệm vào trí nhớ riêng")
    shot(page, "08h-viec-xong")
    page.goto(BASE + "/dien-bien?tab=van-phong")
    desk = page.locator(".desk").filter(has=page.get_by_role("link", name=re.compile("Chăm sóc khách")))
    expect(desk).to_contain_text("1 xong trong 24 giờ")
    shot(page, "08i-van-phong")
    page.goto(BASE + "/agent/customer_agent?tab=tri-nho")
    expect(page.locator(".mem-list")).to_contain_text("Bài học: Trả lời khách hỏi có giao trong ngày không")

    # 8j. Xuất bản (Sprint 4b): kết nối website (giả) → giao FAQ có đăng → Giám đốc Marketing review → vào lịch đăng 11:30
    page.goto(BASE + "/cai-dat?tab=website")
    page.get_by_role("textbox", name="Địa chỉ").fill("http://127.0.0.1:8083")
    page.get_by_role("button", name="Lưu", exact=True).click()
    expect(page.locator(".toast").filter(has_text="Đã lưu địa chỉ website.")).to_be_visible()
    for label, key in (
        ("Khóa đọc", "xk_e2e_doc_" + "r" * 20),
        ("Khóa gửi bản nháp", "xk_e2e_nhap_" + "d" * 20),
        ("Khóa xuất bản", "xk_e2e_dang_" + "p" * 20),
    ):
        form = page.get_by_role("form", name=label)
        form.get_by_label("Khóa API").fill(key)
        form.get_by_role("button", name="Lưu khóa").click()
        expect(page.get_by_role("region", name=re.compile("^" + label))).to_contain_text("Đã có khóa")
    assert "rrrrrrrrrrrrrrrr" not in page.content()
    page.get_by_role("button", name="Kiểm tra kết nối").click()
    expect(page.locator(".toast").filter(has_text="Kết nối tốt: 1 sản phẩm")).to_be_visible()
    shot(page, "08j-website")
    page.goto(BASE + "/agent")  # Nội dung bị tạm dừng ở bước 4: cho chạy lại để nhận việc viết FAQ
    page.locator("tr[data-agent=content_agent]").get_by_role("button", name="Chạy lại").click()
    expect(page.locator(".toast").filter(has_text="Nội dung đã chạy lại.")).to_be_visible()
    page.goto(BASE + "/viec")
    page.get_by_role("button", name="Giao việc").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("Giao cho").select_option("content_agent")
    dlg.get_by_label("Loại việc").select_option("faq")
    dlg.get_by_label("Việc cần làm").fill("Viết FAQ: xưởng có giao trong ngày không")
    dlg.get_by_role("button", name="Giao việc").click()
    expect(page).to_have_url(re.compile(r"/viec/[0-9a-f-]{36}$"))
    expect(page.locator(".task-summary")).to_contain_text("Xong", timeout=45_000)
    expect(page.locator(".timeline")).to_contain_text("duyệt (vòng 1)")  # Giám đốc Marketing review trước khi vào lịch
    expect(page.locator(".timeline")).to_contain_text("Đã xếp lịch đăng lúc 11:30")
    page.get_by_role("link", name="Xuất bản").click()
    item = page.locator(".pub-item").first
    expect(item).to_contain_text("Xưởng có giao hàng trong ngày không?")
    expect(item).to_contain_text("Chờ giờ đăng")
    expect(item).to_contain_text("11:30")
    shot(page, "08k-xuat-ban")
    page.get_by_role("tab", name="Content Gate").click()
    page.get_by_label("Tiêu đề", exact=True).fill("Trà gừng chữa cảm")
    page.get_by_label("Nội dung", exact=True).fill("Uống trà gừng mỗi ngày giúp chữa bệnh cảm cúm, cam kết 100% khỏi.")
    page.get_by_role("button", name="Thử", exact=True).click()
    expect(page.locator(".gate-result")).to_contain_text("Bị chặn, không tự đăng")
    expect(page.locator(".gate-result")).to_contain_text("chữa bệnh")
    shot(page, "08l-content-gate")
    page.get_by_role("button", name="Tạm dừng xuất bản").click()
    page.get_by_role("dialog").get_by_role("button", name="Tạm dừng").click()
    expect(page.get_by_text("Tự xuất bản đang tạm dừng")).to_be_visible()
    page.get_by_role("button", name="Cho chạy lại").click()
    expect(page.get_by_text("Tự xuất bản đang tạm dừng")).to_be_hidden()

    # 9. Đăng xuất qua menu người dùng, đăng nhập lại; sai mã thì báo lỗi rõ
    page.locator(".menu-btn").click()
    page.get_by_role("menuitem", name="Đăng xuất").click()
    expect(page).to_have_url(re.compile(r"/dang-nhap$"))
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Mật khẩu").fill(PASSWORD)
    page.get_by_label("Mã xác thực 6 số").fill("000000")
    page.get_by_role("button", name="Đăng nhập").click()
    expect(page.locator(".alert.danger")).to_contain_text("không đúng")
    shot(page, "09-dang-nhap-sai")
    page.get_by_label("Mã xác thực 6 số").fill(totp.fresh())
    page.get_by_role("button", name="Đăng nhập").click()
    expect(page.get_by_role("heading", name="Thiết lập ban đầu: còn 1 bước")).to_be_visible()  # còn kiểm tra khóa API
    shot(page, "10-tong-quan-sau-cai-dat")

    # 10. Màn hình hẹp (điện thoại) vẫn dùng được
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("link", name="Cài đặt").click()
    expect(page.get_by_role("tab", name="Telegram")).to_be_visible()
    expect(page.get_by_role("region", name="Bot Telegram")).to_be_visible()
    shot(page, "11-dien-thoai")

    assert page.csp_errors == [], page.csp_errors  # type: ignore[attr-defined]
