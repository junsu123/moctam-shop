# Báo cáo Sprint 1: Foundation + Control Center v1

Thời gian: 26/11/2026. Owner duyệt "Sprint 1" sau Sprint 0 (PR #8).

Sprint này dựng phần nền mà mọi agent sẽ dùng:
- đăng nhập 2 lớp cho Owner;
- nhật ký không sửa được;
- kho bí mật mã hóa;
- Model Gateway có trần ngân sách;
- Telegram Gateway.

Trang quản trị cũng đã dùng được, có các phần: Tổng quan, Agent, Diễn biến, Cài đặt.

## Đã xong (kèm bằng chứng)

**Migration `0002_control_center`**
- Bảng:
  - `users`, `user_sessions`;
  - `audit_logs` (chuỗi băm SHA-256, trigger chặn UPDATE/DELETE/TRUNCATE, `pg_notify` cho SSE);
  - `secrets` (mã hóa phong bì AES-GCM);
  - `settings`;
  - `agents` (15 agent) + `agent_status`;
  - `provider_registry`, `model_registry` (giá tra 26/11/2026; Opus tắt), `model_profiles`, `model_usage`;
  - `telegram_chats`, `telegram_link_codes`;
  - `notifications` (outbox) + `notification_deliveries`.
- Kiểm chứng: IT-DB-01 (lên/xuống/lên), IT-DB-03 (sửa nhật ký bị chặn, sửa lén khi tắt trigger vẫn bị `verify_chain` phát hiện).

**Đăng nhập**
- Mã thiết lập dùng một lần, 30 phút (`python -m app.cli setup-token`; `khoi-dong.ps1` tự in ra và mở trang thiết lập). Sau đó tạo Owner, quét QR TOTP, rồi nhập mã để kích hoạt.
- Mật khẩu Argon2id, tối thiểu 10 ký tự.
- Phiên làm việc:
  - cookie HttpOnly + SameSite=Strict, sống 12 giờ, hết hạn sau 2 giờ không dùng;
  - mọi thao tác ghi đều cần `X-CSRF-Token`.
- Sai 5 lần thì khóa 15 phút. Bộ đếm ghi bằng giao dịch riêng nên không bị rollback.
- Thông báo lỗi giống nhau dù sai email hay sai mật khẩu, thời gian kiểm tra cũng như nhau.
- Xác thực lại (mật khẩu + mã 2FA, có hiệu lực 5 phút) cho các thao tác: đổi token Telegram, khóa API, tạo chat được duyệt việc.
- Thiết lập dở dang (tải lại trang giữa bước 1 và 2) làm lại được bằng cùng mã thiết lập; tài khoản chưa nhập mã TOTP không tính là đã thiết lập. Lỗi này lộ ra khi CI chạy E2E lần đầu.
- Kiểm chứng: `test_api_auth.py` (15 test).

**API Control Center**
- Agent: danh sách, tạm dừng/chạy lại (có lý do), tạm dừng tất cả. Mọi thao tác đều ghi nhật ký.
- Ngân sách, giờ làm việc: có kiểm tra dữ liệu, nhật ký ghi giá trị cũ và mới.
- Nhà cung cấp AI: lưu khóa (chỉ trả 4 ký tự cuối), nút kiểm tra kết nối.
- Tổng quan.
- Diễn biến: danh sách và luồng SSE qua `LISTEN aico_events`. Luồng kiểm phiên bằng kết nối ngắn rồi trả lại pool ngay, không giữ chỗ.
- Kiểm chứng: `test_api_control.py` (6 test, gồm cả test SSE thật qua NOTIFY).

**Model Gateway**
- Agent chỉ gọi theo *hồ sơ* (`cheap`, `writer_vi`, …). Dùng adapter Anthropic Messages và OpenAI Chat Completions.
- Nhà cung cấp chính trả 429/5xx/timeout thì chuyển sang model dự phòng khác nhà cung cấp.
- Kiểm trần **trước khi gọi** (tháng, ngày, được tiêu thêm từ phần ngày trước còn dư).
- Cảnh báo 80% gửi một lần mỗi tháng. Hết trần thì báo khẩn qua Telegram.
- Che SĐT, email, khóa API trước khi gửi ra ngoài.
- Đầu ra có cấu trúc được kiểm theo schema, sửa tối đa 1 lần.
- Agent đang tạm dừng không gọi được AI.
- Sổ chi phí ghi bằng kết nối riêng, nên vẫn còn khi việc của agent lỗi và rollback.
- Kiểm chứng: UT-MGW-01…08 (`test_gateway.py`, 13 test, nhà cung cấp giả).

**Telegram Gateway**
- Bot API qua httpx: `getMe`, `sendMessage`, `getUpdates` long-poll.
- Token được kiểm bằng `getMe` trước khi lưu, rồi lưu mã hóa.
- Kết nối chat bằng `/ketnoi 123456`: mã băm, 10 phút, dùng một lần.
- Chat lạ bị bỏ qua, không trả lời, nhật ký ghi một lần.
- Từng chat chọn được loại tin nhận.
- Giờ yên lặng chỉ cho tin khẩn đi qua.
- Gửi lỗi thì thử lại tối đa 5 lần. Mọi tin gửi đi đều đã che dữ liệu nhạy cảm.
- Worker `telegram` (~60 MB) chạy trong Compose, tự nhận token mới trong 5 giây, không cần khởi động lại.
- Kiểm chứng: IT-TG-01, 04, 05 (`test_telegram.py`, 9 test, Bot API giả).

**Trang quản trị**
- Các trang:
  - `/thiet-lap`, `/dang-nhap`;
  - Tổng quan: tự chỉ ra các bước còn thiếu, chi phí hôm nay/tháng có vạch cảnh báo, agent, hệ thống, Telegram, 6 diễn biến mới nhất;
  - Agent: nhóm theo phòng ban;
  - Diễn biến: trực tiếp qua SSE, lọc theo loại, nhóm theo ngày;
  - Cài đặt: Telegram, ngân sách, giờ, nhà cung cấp AI.
- Hộp "Xác nhận lại" bật lên khi máy chủ đòi xác thực lại, rồi tự chạy lại thao tác.
- **CSP dùng nonce** qua `proxy.ts`, bỏ `'unsafe-inline'`; không còn style inline.
- Chưa đăng nhập thì chuyển về trang đăng nhập ngay ở proxy.
- Kiểm chứng: `npm run typecheck`, `npm run lint` (ESLint mới thêm), `npm run build` đều đạt.

**E2E (Playwright, Chromium)**
- `e2e/run.sh` dựng CSDL sạch, chạy backend, worker, Bot Telegram giả và frontend bản build.
- Đi hết luồng:
  1. thiết lập 2FA;
  2. tạm dừng agent có lý do;
  3. Diễn biến nhận sự kiện từ tab khác không cần tải lại;
  4. lưu token (qua hộp xác nhận lại);
  5. mã kết nối → "điện thoại" nhắn mã → chat hiện ra;
  6. gửi tin thử tới bot;
  7. ngân sách;
  8. khóa API (không lộ ra trang);
  9. đăng xuất, đăng nhập sai, rồi đăng nhập đúng.
- Kiểm thêm: không có lỗi CSP trong console.
- Kết quả: **1/1 đạt**, 9 ảnh chụp.

**CI**
- Thêm `npm run lint` và job `e2e` (Postgres pgvector + Valkey, tải lên ảnh chụp/log).

**Compose**
- Thêm dịch vụ `telegram` (128 MB). Tổng giới hạn RAM ~2,8 GB.

Tổng: **65 test backend đạt** (ruff, ruff format, mypy strict sạch), **1 test E2E đạt**.

## Chuẩn hóa giao diện (27/11/2026, theo yêu cầu Owner)

Owner yêu cầu giao diện giống các bản thương mại, màn hình nhiều phần thì chuyển sang tab.

- **Khung trang**:
  - thanh bên tối có icon;
  - thanh trên có đường dẫn, trạng thái hệ thống (kiểm mỗi 30 giây) và menu người dùng (đăng xuất nằm trong menu).
- **Bộ thành phần dùng chung** (`components/ui/`):
  - tab;
  - thẻ, thẻ số liệu;
  - nhãn trạng thái, bảng, trạng thái trống;
  - hộp xác nhận (thay `window.prompt/confirm` của trình duyệt), thông báo nổi;
  - công tắc.
- **Phông Be Vietnam Pro** (thiết kế cho tiếng Việt). Phông tự chứa trong bản build: không gọi Google Fonts, CSP vẫn chỉ `'self'`. Icon dùng `lucide-react` (ISC).
- **Tab**, lưu trên URL `?tab=…` (tải lại trang hay gửi link vẫn mở đúng tab; dùng được bằng phím mũi tên):
  - Cài đặt: Telegram, Ngân sách AI, Giờ làm việc, Nhà cung cấp AI;
  - Agent: Tất cả, Điều hành, Marketing, Kinh doanh, Tăng trưởng, Công nghệ & Dữ liệu (có đếm số), kèm bảng và ô tìm agent;
  - Diễn biến: Tất cả, Thao tác, Tin Telegram (có đếm số), dạng bảng nhóm theo ngày.
- **Tổng quan**:
  - danh sách bước thiết lập có đánh dấu đã xong;
  - 4 thẻ số liệu;
  - hoạt động gần đây, tình trạng hệ thống, nhà cung cấp AI.
- **E2E** đi lại toàn bộ luồng trên giao diện mới. Kiểm thêm:
  - chuyển tab, tab nằm trên URL, tải lại vẫn giữ tab;
  - ô tìm agent;
  - màn hình điện thoại 390 px.
- Kết quả: 1/1 đạt, 12 ảnh chụp.

## Lệch so với kế hoạch (ghi trung thực)

| Kế hoạch | Thực tế | Lý do / xử lý |
|---|---|---|
| Telegram dùng aiogram (PLAN §5) | httpx gọi thẳng Bot API | Chỉ cần 3 phương thức. Ít RAM, dễ giả lập khi test. Ghi vào DECISIONS (ghi chú kỹ thuật Sprint 1). |
| OpenTelemetry trong Sprint 1 | **Chưa làm**, chuyển sang Sprint 2 | Hiện đã có log JSON (che dữ liệu) + request-id + `model_usage`. OTel có ích nhất khi có worker agent (Sprint 2). |
| IT-TG-02/03 (nút duyệt ký HMAC, hết hạn, dùng lại) | Chuyển sang Sprint 4 | Nút duyệt gắn với hàng chờ phê duyệt + LangGraph `interrupt`. Bảng `telegram_chats.can_approve` đã có sẵn. |
| "Gọi thật Claude và OpenAI qua gateway" | **Chưa kiểm chứng ở đây** | Môi trường phát triển không có khóa API và bị chặn mạng ra ngoài. Owner bấm *Cài đặt → Nhà cung cấp AI → Kiểm tra kết nối* (khoảng 20 token, chưa tới 0,0001 USD). |
| "Owner nhận tin Telegram đầu tiên" | Chờ máy Owner | E2E đã chạy với Bot API giả. Trên máy thật: dán token, tạo mã, nhắn `/ketnoi`, bấm *Gửi tin thử*. |
| TypeScript | Ghim **6.0** (thay 7.0) | `typescript-eslint` chưa hỗ trợ TS 7. Đổi lại khi họ hỗ trợ. |

## Việc chuyển sang Sprint sau (đã ghi, chưa làm)

- OpenTelemetry (Sprint 2).
- Chống dùng lại mã TOTP trong cùng 30 giây. Hiện một mã còn hiệu lực dùng được nhiều lần trong cửa sổ ±30 giây, rủi ro thấp vì trang chỉ mở ở 127.0.0.1 (Sprint 2).
- Sửa ngưỡng/tên hồ sơ model trên giao diện (registry hiện chỉ đọc trên trang). Thêm biểu đồ chi phí theo agent (Sprint 2, cùng trang từng agent).
- Kiểm thử container trong CI (`docker compose up` + `/health/ready`). Vẫn còn từ Sprint 0.
- Chạy `khoi-dong.ps1` thật trên Windows: chưa kiểm chứng được (như Sprint 0).

## Owner làm gì để dùng

1. Chạy `scripts\windows\khoi-dong.ps1`. Lần đầu cửa sổ sẽ in **mã thiết lập** và mở http://127.0.0.1:3000/thiet-lap.
2. Tạo tài khoản, quét QR bằng Google/Microsoft Authenticator.
3. Trang Tổng quan chỉ ra các bước còn lại:
   - dán khóa API rồi bấm *Kiểm tra kết nối*;
   - dán token bot Telegram, bấm *Tạo mã kết nối*, nhắn `/ketnoi xxxxxx` cho bot, rồi bấm *Gửi tin thử*.

## Chi phí LLM trong Sprint

0 USD. Mọi test đều dùng nhà cung cấp giả, chưa có lời gọi thật.
