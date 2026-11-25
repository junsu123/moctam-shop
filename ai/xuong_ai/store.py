"""SQLite cục bộ: trạng thái đồng bộ, đơn tối thiểu, hàng đợi tác vụ, bộ nhớ tri thức, nhật ký LLM."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processed_events (event_id TEXT PRIMARY KEY, seq INTEGER NOT NULL, applied_at TEXT NOT NULL DEFAULT (datetime('now')));
-- Đơn ở dạng tối thiểu: KHÔNG có tên, SĐT, địa chỉ (giới hạn theo mục đích)
CREATE TABLE IF NOT EXISTS orders (
  order_id INTEGER PRIMARY KEY, code TEXT, status TEXT, payment_method TEXT, payment_status TEXT,
  customer_key TEXT, marketing_consent INTEGER, zone_id INTEGER, goods_subtotal INTEGER, total INTEGER,
  voucher_code TEXT, created_at TEXT, delivered_at TEXT, version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_key);
CREATE TABLE IF NOT EXISTS order_items (
  order_id INTEGER NOT NULL, sku_id INTEGER NOT NULL, product_id INTEGER NOT NULL, category_id INTEGER NOT NULL,
  qty INTEGER NOT NULL, unit_price INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
CREATE TABLE IF NOT EXISTS products (product_id INTEGER PRIMARY KEY, category_id INTEGER, status TEXT, info_version INTEGER, version INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS catalog_cache (key TEXT PRIMARY KEY, json TEXT NOT NULL, fetched_at TEXT NOT NULL DEFAULT (datetime('now')));

-- Bộ nhớ tri thức: quy tắc/mẫu đã duyệt + bản nháp chờ duyệt
CREATE TABLE IF NOT EXISTS knowledge (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,              -- faq | label | blog_outline | rule
  question_type TEXT,              -- giao_hang | thanh_toan | doi_tra | bao_quan | cach_dung | di_ung | san_pham | khac
  category_id INTEGER, product_id INTEGER,
  title TEXT NOT NULL, body TEXT NOT NULL,
  source TEXT NOT NULL,            -- website_faq | product_label | llm | staff
  source_ref TEXT,                 -- vd 'faq:12@v34', 'product:5@v3'
  source_version TEXT,
  status TEXT NOT NULL,            -- approved | pending | retired
  expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(kind, source_ref)
);
CREATE TABLE IF NOT EXISTS jobs (name TEXT PRIMARY KEY, last_run TEXT, next_run TEXT, failures INTEGER NOT NULL DEFAULT 0, last_error TEXT, last_result TEXT);
CREATE TABLE IF NOT EXISTS outbox (client_ref TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', result TEXT, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS llm_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, task TEXT, provider TEXT, model TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, ok INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS memory_hits (id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, task TEXT, hit INTEGER NOT NULL, score REAL);
"""


class Store:
    def __init__(self, path: Path | str):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    @contextmanager
    def tx(self):
        """Giao dịch nguyên khối: lỗi → hoàn tác toàn bộ."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def get(self, key: str, default: str | None = None) -> str | None:
        r = self.db.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else default

    def set(self, key: str, value) -> None:
        self.db.execute("INSERT INTO sync_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))

    def cache_put(self, key: str, obj) -> None:
        self.db.execute("INSERT INTO catalog_cache(key, json) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET json = excluded.json, fetched_at = datetime('now')", (key, json.dumps(obj, ensure_ascii=False)))

    def cache_get(self, key: str, default=None):
        r = self.db.execute("SELECT json FROM catalog_cache WHERE key = ?", (key,)).fetchone()
        return json.loads(r["json"]) if r else default

    def all(self, sql: str, params=()) -> list[sqlite3.Row]:
        return self.db.execute(sql, params).fetchall()

    def one(self, sql: str, params=()):
        return self.db.execute(sql, params).fetchone()
