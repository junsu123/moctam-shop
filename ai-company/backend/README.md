# Máy chủ AI Marketing Company (backend)

FastAPI, Python 3.12+, PostgreSQL + pgvector, Valkey/Redis. Thiết kế: `../docs/ARCHITECTURE.md`.

## Chạy khi phát triển

```bash
uv sync                               # cài phụ thuộc theo uv.lock
export AICO_DATABASE_URL=postgresql+psycopg://aico:aico@127.0.0.1:5432/aico
uv run alembic upgrade head           # tạo/cập nhật CSDL
uv run uvicorn app.main:app --reload  # http://127.0.0.1:8000/api/docs
```

## Kiểm thử

```bash
uv run ruff check . && uv run mypy app
AICO_TEST_DATABASE_URL=postgresql+psycopg://aico:aico@127.0.0.1:5432/aico_test uv run pytest
```

`AICO_TEST_DATABASE_URL` phải trỏ tới CSDL **riêng cho kiểm thử**, có tên chứa `test`: bài test migration xóa rồi tạo lại toàn bộ lược đồ.

## API hiện có (Sprint 0)

| Đường dẫn | Ý nghĩa |
|---|---|
| `GET /api/v1/health/live` | Tiến trình còn sống (Docker healthcheck) |
| `GET /api/v1/health/ready` | CSDL (có pgvector) và hàng đợi sẵn sàng; `503` nếu thiếu |

Mọi lỗi trả về dạng `{"error": {"code", "message", "request_id"}}`. `code` cố định cho máy đọc; `message` là tiếng Việt.
