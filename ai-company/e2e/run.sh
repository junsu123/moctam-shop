#!/usr/bin/env bash
# Kiểm thử E2E trang quản trị: dựng CSDL e2e sạch, chạy backend + worker Telegram + Telegram giả + frontend (bản build),
# rồi chạy Playwright. Cần Postgres (pgvector) và Redis đang chạy; biến AICO_E2E_DATABASE_URL trỏ tới CSDL có tên chứa "e2e".
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
: "${AICO_E2E_DATABASE_URL:?đặt AICO_E2E_DATABASE_URL, ví dụ postgresql+psycopg://aico:aico@127.0.0.1/aico_e2e}"
: "${AICO_E2E_REDIS_URL:=redis://127.0.0.1:6379/0}"
case "${AICO_E2E_DATABASE_URL##*/}" in *e2e*) ;; *) echo "CSDL phải có tên chứa e2e"; exit 2 ;; esac

export AICO_DATABASE_URL="$AICO_E2E_DATABASE_URL" AICO_REDIS_URL="$AICO_E2E_REDIS_URL" AICO_ENV=test
export AICO_MASTER_KEY="e2e-master-key-$(printf 'x%.0s' {1..32})" AICO_TELEGRAM_API_BASE="http://127.0.0.1:8081"
LOGS="$HERE/logs"; mkdir -p "$LOGS"
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

cd "$ROOT/backend"
uv run alembic downgrade base >/dev/null 2>&1 || true
uv run alembic upgrade head
python3 "$HERE/fake_telegram.py" 8081 >"$LOGS/telegram-fake.log" 2>&1 & pids+=($!)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 >"$LOGS/backend.log" 2>&1 & pids+=($!)
uv run python -m app.workers.telegram >"$LOGS/worker.log" 2>&1 & pids+=($!)
cd "$ROOT/frontend"
[ -d .next ] || AICO_BACKEND_URL=http://127.0.0.1:8000 npm run build
npx next start -p 3000 -H 127.0.0.1 >"$LOGS/frontend.log" 2>&1 & pids+=($!)

for url in http://127.0.0.1:8000/api/v1/health/live http://127.0.0.1:3000/dang-nhap; do
  for _ in $(seq 60); do curl -fsS -o /dev/null "$url" && break; sleep 1; done
done

cd "$HERE"
AICO_E2E_BACKEND_DIR="$ROOT/backend" python3 -m pytest -q -p no:cacheprovider test_control_center.py "$@"
