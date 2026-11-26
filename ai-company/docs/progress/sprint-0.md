# Báo cáo Sprint 0: Quyết định và khung

Thời gian: 26/11/2026. Kiến trúc v0.2 được Owner duyệt lúc 22:43. Owner ưu tiên trang quản trị trọn gói, nên Control Center có từ Sprint 1.

## Đã xong (kèm bằng chứng)

| Hạng mục | Kết quả | Kiểm chứng |
|---|---|---|
| Ghi duyệt kiến trúc, đổi kế hoạch | DECISIONS lần 5; PLAN §2–3: Control Center từ Sprint 1, lớn dần mỗi Sprint; CLAUDE.md đổi trạng thái | — |
| Backend FastAPI | `/api/v1/health/live`, `/api/v1/health/ready` (CSDL có pgvector + hàng đợi; 503 khi thiếu, không lộ chuỗi kết nối); mã lỗi ổn định `{"error": {code, message, request_id}}`; middleware request-id; log JSON tự che SĐT, email, khóa API, token Telegram, JWT; cấu hình qua biến môi trường, production bắt buộc khóa chủ ≥ 32 ký tự | **15/15 test đạt** (pytest), gồm 3 test chạy trên Postgres 16 + pgvector và Redis thật; ruff + ruff format sạch; mypy strict sạch |
| Migration | Alembic `0001_baseline`: extension `vector`, `pg_trgm`, `unaccent`; schema `langgraph`; bảng `system_meta`. Lên/xuống/lên đều đạt | `test_migration_up_down_up` (IT-DB-01) |
| Trang quản trị | Next.js 16 + TypeScript, tiếng Việt, sáng/tối, màu "trà" chung với màn hình diễn biến; trang *Trung tâm điều hành* hiện tình trạng hệ thống (tự cập nhật 5 giây); gọi backend qua cùng nguồn (rewrite) | `npm run typecheck`, `npm run build` đạt; chạy thật cùng backend + Postgres + Redis: 3 dòng "Sẵn sàng"; chụp màn hình sáng/tối/điện thoại, không lỗi console |
| Docker | Dockerfile backend (non-root, healthcheck) và frontend (standalone, non-root); `docker-compose.yml` với `db` (pgvector), `queue` (Valkey), `migrate` (chạy một lần), `backend`, `frontend`; **giới hạn RAM tổng ~2,7 GB** (trong ngân sách 6 GB); mọi cổng chỉ mở ở 127.0.0.1; thiếu biến bí mật thì báo lỗi rõ | `docker compose config` hợp lệ |
| CI | `.github/workflows/ai-company.yml`: backend (ruff, format, mypy, pytest với Postgres pgvector + Valkey), frontend (typecheck, build), compose (config + build image), quét secret (gitleaks) | Chạy trên GitHub khi mở PR |
| Mẫu PR | `.github/pull_request_template.md` có đủ checklist Definition of Done | — |
| Hướng dẫn Windows | `docs/CAI-DAT-WINDOWS.md` + 5 script PowerShell: kiểm tra máy, giới hạn WSL2 6 GB, tạo `.env` ngẫu nhiên, khởi động và mở trang, sao lưu (giữ 14 bản + chép ra ngoài). Script lưu UTF-8 có BOM + CRLF để Windows PowerShell 5.1 hiển thị đúng tiếng Việt | Xem mục "Chưa kiểm chứng" |

## Chưa kiểm chứng được trong môi trường phát triển (cần làm trên máy Owner hoặc CI)

1. **`docker compose up` thật**: môi trường phát triển bị chặn tải image từ Docker Hub, nên chưa build và chạy container được. Thay vào đó, toàn bộ thành phần đã chạy trực tiếp (backend, Next.js, Postgres 16 + pgvector, Redis) và trả kết quả đúng. Job `compose` trong CI sẽ build image thật. **Tiêu chí thoát Sprint 0 "docker compose up chạy được trên máy Owner" chờ Owner chạy `khoi-dong.ps1`.**
2. **Script PowerShell**: chưa chạy được trên Windows thật, vì môi trường không cho tải và chạy PowerShell. Script chỉ dùng lệnh có sẵn trong Windows PowerShell 5.1. Owner chạy `kiem-tra-may.ps1` đầu tiên; script này chỉ đọc, không thay đổi gì.

## Việc chuyển sang Sprint 1 (đã ghi, chưa làm)

- CSP của trang quản trị đang cho phép `'unsafe-inline'` cho script, vì Next.js chèn script nội tuyến. Sprint 1 chuyển sang CSP dùng **nonce** (middleware), kèm trang đăng nhập.
- Thêm ESLint cho frontend; thêm Playwright E2E cho trang quản trị (E2E-01).
- Kiểm thử container trong CI ngoài bước build: `docker compose up` + gọi `/health/ready`.

## Chi phí LLM trong Sprint

0 USD (chưa có lời gọi LLM nào).
