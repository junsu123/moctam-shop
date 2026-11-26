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
    body = json.dumps({"message": {"chat": {"id": chat_id, "type": "private", "first_name": "Điện thoại Owner"}, "text": text}}).encode()
    urllib.request.urlopen(urllib.request.Request(f"{TG}/__push", body, {"content-type": "application/json"}), timeout=5)


def tg_sent() -> list[dict[str, object]]:
    with urllib.request.urlopen(f"{TG}/__sent", timeout=5) as r:
        return json.loads(r.read())


@pytest.fixture(scope="module")
def page() -> Page:
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 860}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        pg = ctx.new_page()
        pg.csp_errors = []  # type: ignore[attr-defined]
        pg.on("console", lambda m: "Content Security Policy" in m.text and pg.csp_errors.append(m.text))  # type: ignore[attr-defined]
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
    page.get_by_label("Mật khẩu (ít nhất 10 ký tự)").fill(PASSWORD)
    page.get_by_label("Nhập lại mật khẩu").fill(PASSWORD)
    page.get_by_role("button", name="Tiếp tục").click()
    expect(page.get_by_role("heading", name="Bật xác thực hai lớp")).to_be_visible()
    expect(page.locator(".qr svg")).to_be_visible()
    shot(page, "01-thiet-lap-2fa")
    page.get_by_text("Không quét được?").click()
    secret = page.locator(".secret").inner_text().strip()
    totp = pyotp.TOTP(secret)
    page.get_by_label("Mã 6 số").fill(totp.now())
    with page.expect_response(lambda r: r.url.endswith("/auth/setup/confirm")) as confirm:
        page.get_by_role("button", name="Hoàn tất").click()
    assert confirm.value.ok, confirm.value.text()
    print("set-cookie:", confirm.value.headers.get("set-cookie", "(không có)")[:80], "cookies:", [c["name"] for c in page.context.cookies()])

    # 2. Tổng quan: chỉ ra các bước còn thiếu bằng dữ liệu thật
    expect(page.get_by_role("heading", name="Tổng quan")).to_be_visible()
    expect(page.get_by_text("Còn 2 bước")).to_be_visible()
    expect(page.locator(".tile").filter(has=page.get_by_role("heading", name="Agent", exact=True)).locator(".figure")).to_have_text("15")
    shot(page, "02-tong-quan")

    # 3. Agent: tạm dừng SEO có lý do
    page.get_by_role("link", name="Agent", exact=True).click()
    row = page.locator(".agents li").filter(has_text="Từ khóa, đối thủ")
    page.once("dialog", lambda d: d.accept("Chờ Owner duyệt bộ từ khóa"))
    row.get_by_role("button", name="Tạm dừng").click()
    expect(row.locator(".tag")).to_have_text("Tạm dừng")
    expect(row).to_contain_text("Chờ Owner duyệt bộ từ khóa")
    shot(page, "03-agent")

    # 4. Diễn biến: sự kiện mới đến ngay qua SSE, không cần tải lại trang
    page.get_by_role("link", name="Diễn biến").click()
    expect(page.get_by_text("Đang cập nhật trực tiếp")).to_be_visible(timeout=10_000)
    expect(page.locator(".feed li").first).to_contain_text("tạm dừng agent")
    other = page.context.new_page()
    other.goto(BASE + "/agent")
    other.once("dialog", lambda d: d.accept("Thử luồng trực tiếp"))
    other.locator(".agents li").filter(has_text="Bài website, Facebook").get_by_role("button", name="Tạm dừng").click()
    expect(other.locator(".flash")).to_be_visible()
    other.close()
    expect(page.locator(".feed li").first).to_contain_text("content_agent", timeout=10_000)
    expect(page.locator(".feed li").first).to_contain_text("Thử luồng trực tiếp")
    shot(page, "04-dien-bien")

    # 5. Telegram: token cần xác thực lại → hộp thoại → lưu → mã kết nối → điện thoại nhắn mã → chat xuất hiện
    page.get_by_role("link", name="Cài đặt").click()
    page.get_by_label("Token do BotFather cấp").fill(TG_TOKEN)
    page.get_by_role("button", name="Kiểm tra và lưu").click()
    dlg = page.get_by_role("dialog")
    expect(dlg.get_by_role("heading", name="Xác nhận lại")).to_be_visible()
    shot(page, "05-xac-thuc-lai")
    dlg.get_by_label("Mật khẩu").fill(PASSWORD)
    dlg.get_by_label("Mã 6 số").fill(totp.now())
    dlg.get_by_role("button", name="Xác nhận").click()
    expect(page.get_by_text("Bot @xuongtra_ai_bot đã sẵn sàng")).to_be_visible()
    page.get_by_role("button", name="Tạo mã kết nối", exact=True).click()
    code = page.locator(".code-box .code").inner_text().split()[-1]
    assert re.fullmatch(r"\d{6}", code)
    shot(page, "06-ma-ket-noi")
    tg_push(5550001, f"/ketnoi {code}")
    expect(page.locator(".chats li").filter(has_text="Điện thoại Owner")).to_be_visible(timeout=15_000)
    assert any("Đã kết nối" in str(m["text"]) for m in tg_sent())
    page.get_by_role("button", name="Gửi tin thử").click()
    deadline = time.time() + 15
    while time.time() < deadline and not any("Tin thử" in str(m["text"]) for m in tg_sent()):
        time.sleep(0.5)
    assert any("Tin thử" in str(m["text"]) for m in tg_sent()), tg_sent()

    # 6. Ngân sách
    page.get_by_label("Trần mỗi tháng (USD)").fill("40")
    page.get_by_role("button", name="Lưu ngân sách").click()
    expect(page.get_by_text("Đã lưu ngân sách.")).to_be_visible()

    # 7. Khóa API (vẫn trong 5 phút xác thực lại nên không hỏi lại)
    prov = page.locator(".provider").filter(has_text="Anthropic")
    prov.get_by_label("Khóa API").fill("sk-ant-api03-" + "E" * 40 + "Z9Z9")
    prov.get_by_role("button", name="Lưu khóa").click()
    expect(prov).to_contain_text("…Z9Z9")
    expect(prov.locator(".tag")).to_have_text("Chưa kiểm tra")
    assert "EEEEEEEE" not in page.content()
    shot(page, "07-cai-dat")

    # 8. Đăng xuất, đăng nhập lại; sai mã thì báo lỗi rõ
    page.get_by_role("button", name="Đăng xuất").click()
    expect(page).to_have_url(re.compile(r"/dang-nhap$"))
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Mật khẩu").fill(PASSWORD)
    page.get_by_label("Mã 6 số trong ứng dụng xác thực").fill("000000" if totp.now() != "000000" else "111111")
    page.get_by_role("button", name="Đăng nhập").click()
    expect(page.locator("p.err")).to_contain_text("không đúng")
    shot(page, "08-dang-nhap-sai")
    page.get_by_label("Mã 6 số trong ứng dụng xác thực").fill(totp.now())
    page.get_by_role("button", name="Đăng nhập").click()
    expect(page.get_by_role("heading", name="Tổng quan")).to_be_visible()
    expect(page.get_by_text("Còn 1 bước")).to_be_visible()  # còn bấm kiểm tra khóa API
    shot(page, "09-tong-quan-sau-cai-dat")

    assert page.csp_errors == [], page.csp_errors  # type: ignore[attr-defined]
