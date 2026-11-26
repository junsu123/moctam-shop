# Lệnh thường dùng (Linux/macOS/WSL). Trên Windows dùng scripts\windows\*.ps1.
.PHONY: test lint backend-test frontend-test e2e up down logs
test: backend-test frontend-test
backend-test:
	cd backend && uv sync --frozen && uv run pytest -p no:warnings
frontend-test:
	cd frontend && npm ci --no-audit --no-fund && npm run typecheck && npm run lint && npm run build
e2e:
	./e2e/run.sh
lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd frontend && npm run lint
up:
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs --tail 100 -f
