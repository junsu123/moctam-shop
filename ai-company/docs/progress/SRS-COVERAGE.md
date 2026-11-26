# Độ phủ SRS v1.0

Cập nhật cuối mỗi Sprint. Trạng thái: `chưa làm` · `đang làm` · `xong (test …)`.

| SRS | Nội dung | Sprint dự kiến | Trạng thái |
|---|---|---|---|
| §2.2 | Kiến trúc kỹ thuật (FastAPI, Next.js, Postgres + pgvector, Redis/Valkey, Docker Compose) | 0–1 | **xong (test_core, test_db, E2E)**: còn chờ chạy `docker compose up` trên máy Owner |
| §2.2 | LangGraph | 4 | chưa làm |
| §3 | 15 agent | 2, 4, 6, 7 | **đang làm**: 15 agent có trong registry, tạm dừng/chạy lại có nhật ký (test_api_control); chưa có hành vi |
| §4 | Bộ não riêng (bundle, phiên bản, trí nhớ 4 loại, truy hồi, RLS) | 2–3 | chưa làm |
| §5 | Learning Engine, duyệt kiến thức | 5 | chưa làm |
| §6 | Message bus, cộng tác, giải quyết bất đồng | 4 | chưa làm |
| §7 | Task Engine (9 trạng thái, retry, timeout, khôi phục) | 4 | chưa làm |
| §8 | Model Gateway (Claude + OpenAI, chi phí, dự phòng) | 1 | **xong (UT-MGW-01…08)**: chờ gọi thật bằng khóa của Owner |
| §9 | Tool Registry / Tool Gateway | 2 | chưa làm |
| §10 | Tích hợp (website, GSC, GA4, quảng cáo, sàn, Zalo…) | 4, 8 | chưa làm |
| §11 | Lược đồ CSDL | 1–5 | **đang làm**: `0001_baseline`, `0002_control_center` (IT-DB-01, IT-DB-03 đạt) |
| §12 | Dashboard / Control Center | 0–8 | **đang làm**: v1 có đăng nhập 2FA, Tổng quan, Agent, Diễn biến (SSE), Cài đặt (Telegram, ngân sách, giờ, nhà cung cấp AI). E2E đạt |
| ADR-15 | Telegram Gateway (thông báo, kết nối chat, giờ yên lặng) | 1, 4 | **xong phần thông báo (IT-TG-01, 04, 05)**: nút duyệt ở Sprint 4 |
| §13 | Quyền 4 cấp, phê duyệt | 2 | chưa làm |
| §14 | Lịch tự động, khôi phục sau khởi động lại | 4 | chưa làm |
| §15 | Bảo mật (14 yêu cầu) | 1–9 | **đang làm**: thêm Argon2id + TOTP, khóa tạm, CSRF, xác thực lại, secret mã hóa phong bì, audit chuỗi băm không sửa được, CSP nonce, che dữ liệu trước khi gửi LLM/Telegram |
| §16 | API `/api/v1` | 1–8 | **đang làm**: health, auth, agents, settings, providers, overview, events (+SSE), telegram |
| §18 | Kiểm thử tự động | 0–9 | **đang làm**: CI 5 job (thêm E2E Playwright), 64 test backend |
| §19 | 25 tiêu chí nghiệm thu | 9 | chưa làm |
| §21 | Quy trình bắt buộc cho Claude Code | 0 | **xong**: CLAUDE.md, mẫu PR có DoD, báo cáo Sprint |
