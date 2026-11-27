# Độ phủ SRS v1.0

Cập nhật cuối mỗi Sprint. Trạng thái: `chưa làm` · `đang làm` · `xong (test …)`.

| SRS | Nội dung | Sprint dự kiến | Trạng thái |
|---|---|---|---|
| §2.2 | Kiến trúc kỹ thuật (FastAPI, Next.js, Postgres + pgvector, Redis/Valkey, Docker Compose) | 0–1 | **đang làm**: khung chạy được (test_core, test_db; build frontend) |
| §2.2 | LangGraph | 4 | chưa làm |
| §3 | 15 agent | 2, 4, 6, 7 | chưa làm |
| §4 | Bộ não riêng (bundle, phiên bản, trí nhớ 4 loại, truy hồi, RLS) | 2–3 | chưa làm |
| §5 | Learning Engine, duyệt kiến thức | 5 | chưa làm |
| §6 | Message bus, cộng tác, giải quyết bất đồng | 4 | chưa làm |
| §7 | Task Engine (9 trạng thái, retry, timeout, khôi phục) | 4 | chưa làm |
| §8 | Model Gateway (Claude + OpenAI, chi phí, dự phòng) | 1 | chưa làm |
| §9 | Tool Registry / Tool Gateway | 2 | chưa làm |
| §10 | Tích hợp (website, GSC, GA4, quảng cáo, sàn, Zalo…) | 4, 8 | chưa làm |
| §11 | Lược đồ CSDL | 1–5 | **đang làm**: migration nền `0001_baseline` (IT-DB-01 đạt) |
| §12 | Dashboard / Control Center | 0–8 | **đang làm**: trang Trung tâm điều hành + tình trạng hệ thống |
| §13 | Quyền 4 cấp, phê duyệt | 2 | chưa làm |
| §14 | Lịch tự động, khôi phục sau khởi động lại | 4 | chưa làm |
| §15 | Bảo mật (14 yêu cầu) | 1–9 | **đang làm**: log che dữ liệu, mã lỗi không lộ chi tiết, cổng chỉ 127.0.0.1, khóa chủ bắt buộc ở production, container non-root, quét secret trong CI |
| §16 | API `/api/v1` | 1–8 | **đang làm**: `/health/live`, `/health/ready` |
| §18 | Kiểm thử tự động | 0–9 | **đang làm**: CI 4 job |
| §19 | 25 tiêu chí nghiệm thu | 9 | chưa làm |
| §21 | Quy trình bắt buộc cho Claude Code | 0 | **xong**: CLAUDE.md, mẫu PR có DoD, báo cáo Sprint |
