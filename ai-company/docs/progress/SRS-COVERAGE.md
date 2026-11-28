# Độ phủ SRS v1.0

Cập nhật cuối mỗi Sprint. Trạng thái: `chưa làm` · `đang làm` · `xong (test …)`.

| SRS | Nội dung | Sprint dự kiến | Trạng thái |
|---|---|---|---|
| §2.2 | Kiến trúc kỹ thuật (FastAPI, Next.js, Postgres + pgvector, Redis/Valkey, Docker Compose) | 0–1 | **xong (test_core, test_db, E2E)**: còn chờ chạy `docker compose up` trên máy Owner |
| §2.2 | LangGraph | 4 | chưa làm |
| §3 | 15 agent | 2, 4, 6, 7 | **đang làm**: 15 agent có bộ não riêng (danh tính, sứ mệnh, luật cứng, tính cách, quyền, KPI), vòng đời có kiểm chuyển trạng thái (UT-AG-01…05); chưa có hành vi (Sprint 4) |
| §4 | Bộ não riêng (bundle, phiên bản, trí nhớ 4 loại, truy hồi, RLS) | 2–3 | **xong (UT-BRAIN-01…08, UT-MEM-01…10, IT-DB-02, IT-VEC-01/02, PT-03 ở 200 nghìn mục)**: trí nhớ riêng/phòng/chung/chỉ Owner, 4 loại, RLS hai vai trò, truy hồi lai có chuẩn hóa tiếng Việt, ngân sách token, MMR, nhật ký truy hồi. Việc ghi trải nghiệm từ task thật nối ở Sprint 4 |
| §5 | Learning Engine, duyệt kiến thức | 5 | chưa làm |
| §6 | Message bus, cộng tác, giải quyết bất đồng | 4 | **đang làm (4a xong)**: 8 loại message, outbox giao ít nhất một lần, chống trùng, hộp ứng viên kiến thức (IT-A2A-01/02/04). Giải quyết bất đồng: 4c |
| §7 | Task Engine (9 trạng thái, retry, timeout, khôi phục) | 4 | **xong ở 4a**: 9 trạng thái kiểm hai lớp, phụ thuộc, hợp đồng giao việc, lease, retry giãn cách, timeout, hủy lan xuống, review, phê duyệt, checkpoint LangGraph, đối soát (UT-TASK-01…07, IT-LG-01/03, IT-REC-01/02) |
| §8 | Model Gateway (Claude + OpenAI, chi phí, dự phòng) | 1 | **xong (UT-MGW-01…08)**: chờ gọi thật bằng khóa của Owner |
| §9 | Tool Registry / Tool Gateway | 2 | chưa làm |
| §10 | Tích hợp (website, GSC, GA4, quảng cáo, sàn, Zalo…) | 4, 8 | chưa làm |
| §11 | Lược đồ CSDL | 1–5 | **đang làm**: `0001_baseline` … `0004_memory` (IT-DB-01, IT-DB-02, IT-DB-03 đạt) |
| §12 | Dashboard / Control Center | 0–8 | **đang làm**: đăng nhập 2FA, Tổng quan, Agent (5 tab, có Trí nhớ), Trí nhớ, Diễn biến (SSE), Phê duyệt, Cài đặt (Telegram, ngân sách, giờ, nhà cung cấp AI, công cụ). E2E đạt |
| ADR-15 | Telegram Gateway (thông báo, kết nối chat, giờ yên lặng) | 1, 4 | **xong phần thông báo (IT-TG-01, 04, 05)**: nút duyệt ở Sprint 4 |
| §13 | Quyền 4 cấp, phê duyệt | 2 | **xong (UT-POL-01…12, UT-TOOL-01…06)**: Policy Engine 4 cấp, hiến pháp, danh sách bắt buộc duyệt, hạn mức, taint; hàng chờ phê duyệt có digest + hạn 72 giờ; nút duyệt trên Telegram ở Sprint 4 |
| §14 | Lịch tự động, khôi phục sau khởi động lại | 4 | **xong ở 4a**: cron theo giờ VN, chạy bù một lần trong 24 giờ (IT-REC-03); giao diện lịch đăng bài: 4b |
| §15 | Bảo mật (14 yêu cầu) | 1–9 | **đang làm**: Argon2id + TOTP (chống dùng lại mã), khóa tạm, CSRF, xác thực lại, secret mã hóa phong bì, audit chuỗi băm, CSP nonce, che dữ liệu; mặc định từ chối mọi công cụ, hash quy tắc cốt lõi, changelog bộ não chỉ thêm |
| §16 | API `/api/v1` | 1–8 | **đang làm**: health, auth, agents (+chi tiết, bộ não, so sánh, rollback, lịch sử, thử truy hồi), brains/sync, tools, approvals, memory, settings, providers, overview, events (+SSE), telegram |
| §18 | Kiểm thử tự động | 0–9 | **đang làm**: CI 5 job, 130 test backend, E2E đi hết luồng Owner (thêm trí nhớ), công cụ đo PT-03 |
| §19 | 25 tiêu chí nghiệm thu | 9 | chưa làm |
| §21 | Quy trình bắt buộc cho Claude Code | 0 | **xong**: CLAUDE.md, mẫu PR có DoD, báo cáo Sprint |
