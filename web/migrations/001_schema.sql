-- =====================================================================
-- 001_schema.sql — Lược đồ CSDL website bán hàng (một bên bán, một kho)
-- MySQL 8.0+ / MariaDB 10.6+, InnoDB, utf8mb4. Mọi mốc thời gian lưu UTC.
-- Tiền lưu bằng số nguyên VND (BIGINT / INT UNSIGNED).
-- =====================================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ---------------------------------------------------------------------
-- HỆ THỐNG
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
  version     VARCHAR(64)  NOT NULL PRIMARY KEY,
  applied_at  DATETIME     NOT NULL,
  checksum    CHAR(64)     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE roles (
  code         VARCHAR(32)  NOT NULL PRIMARY KEY,
  name         VARCHAR(100) NOT NULL,
  permissions  TEXT         NOT NULL COMMENT 'JSON array of permission codes'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE users (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email          VARCHAR(190) NOT NULL UNIQUE,
  full_name      VARCHAR(120) NOT NULL,
  password_hash  VARCHAR(255) NOT NULL,
  role_code      VARCHAR(32)  NOT NULL,
  extra_permissions TEXT      NULL COMMENT 'JSON array, cấp thêm quyền riêng',
  is_active      TINYINT(1)   NOT NULL DEFAULT 1,
  failed_logins  INT          NOT NULL DEFAULT 0,
  locked_until   DATETIME     NULL,
  last_login_at  DATETIME     NULL,
  created_at     DATETIME     NOT NULL,
  updated_at     DATETIME     NOT NULL,
  CONSTRAINT fk_users_role FOREIGN KEY (role_code) REFERENCES roles(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE settings (
  `key`       VARCHAR(64)  NOT NULL PRIMARY KEY,
  `value`     TEXT         NOT NULL,
  updated_at  DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE audit_logs (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  actor_type   ENUM('user','system','sync') NOT NULL DEFAULT 'user',
  user_id      INT UNSIGNED NULL,
  action       VARCHAR(64)  NOT NULL,
  entity_type  VARCHAR(40)  NOT NULL,
  entity_id    VARCHAR(64)  NOT NULL,
  before_json  MEDIUMTEXT   NULL,
  after_json   MEDIUMTEXT   NULL,
  note         VARCHAR(500) NULL,
  ip           VARCHAR(45)  NULL,
  created_at   DATETIME     NOT NULL,
  KEY idx_audit_entity (entity_type, entity_id, created_at),
  KEY idx_audit_user (user_id, created_at),
  KEY idx_audit_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Khóa API cho dịch vụ Python. Chỉ lưu SHA-256 của khóa.
CREATE TABLE api_keys (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name         VARCHAR(100) NOT NULL,
  key_prefix   CHAR(8)      NOT NULL,
  key_hash     CHAR(64)     NOT NULL UNIQUE,
  scopes       VARCHAR(255) NOT NULL COMMENT 'events:read,catalog:read,drafts:write',
  is_active    TINYINT(1)   NOT NULL DEFAULT 1,
  last_used_at DATETIME     NULL,
  created_at   DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE rate_limits (
  bucket       VARCHAR(120) NOT NULL PRIMARY KEY,
  hits         INT          NOT NULL,
  window_start DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Ghi nhận tác vụ nền (hết hạn đơn, sao lưu) để giám sát (NFR-05).
CREATE TABLE job_runs (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  job         VARCHAR(64)  NOT NULL,
  status      ENUM('ok','failed') NOT NULL,
  detail      TEXT         NULL,
  started_at  DATETIME     NOT NULL,
  finished_at DATETIME     NOT NULL,
  KEY idx_job_time (job, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE error_logs (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  channel     VARCHAR(40)  NOT NULL,
  code        VARCHAR(64)  NOT NULL,
  message     VARCHAR(1000) NOT NULL,
  created_at  DATETIME     NOT NULL,
  KEY idx_err (channel, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- SẢN PHẨM
-- ---------------------------------------------------------------------
CREATE TABLE categories (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(120) NOT NULL,
  slug        VARCHAR(140) NOT NULL UNIQUE,
  description VARCHAR(500) NULL,
  repurchase_days INT UNSIGNED NULL COMMENT 'Chu kỳ mua lại tham khảo cho chăm sóc khách',
  sort_order  INT          NOT NULL DEFAULT 0,
  is_active   TINYINT(1)   NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE products (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  category_id   INT UNSIGNED NOT NULL,
  name          VARCHAR(200) NOT NULL,
  slug          VARCHAR(220) NOT NULL UNIQUE,
  short_desc    VARCHAR(500) NULL,
  description   MEDIUMTEXT   NULL COMMENT 'HTML đã lọc',
  ingredients   TEXT         NULL,
  usage_guide   TEXT         NULL,
  storage_guide TEXT         NULL,
  allergens     TEXT         NULL,
  status        ENUM('draft','active','discontinued') NOT NULL DEFAULT 'draft',
  is_featured   TINYINT(1)   NOT NULL DEFAULT 0,
  search_text   TEXT         NOT NULL COMMENT 'Tên + SKU + từ khóa, chữ thường, bỏ dấu',
  keywords      VARCHAR(500) NULL,
  info_version  INT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'Tăng khi thông tin nhãn đổi, AI dùng để vô hiệu tri thức cũ',
  created_at    DATETIME     NOT NULL,
  updated_at    DATETIME     NOT NULL,
  KEY idx_products_cat (category_id, status),
  CONSTRAINT fk_products_cat FOREIGN KEY (category_id) REFERENCES categories(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE product_images (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  product_id  INT UNSIGNED NOT NULL,
  path        VARCHAR(255) NOT NULL,
  alt         VARCHAR(200) NULL,
  sort_order  INT          NOT NULL DEFAULT 0,
  KEY idx_img_product (product_id, sort_order),
  CONSTRAINT fk_img_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Mỗi quy cách bán = một SKU duy nhất, giá riêng, tồn riêng.
CREATE TABLE skus (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  product_id    INT UNSIGNED NOT NULL,
  sku_code      VARCHAR(64)  NOT NULL UNIQUE,
  variant_label VARCHAR(120) NOT NULL COMMENT 'Ví dụ: Hộp 20 túi x 2g',
  net_weight_g  INT UNSIGNED NULL,
  price         INT UNSIGNED NOT NULL,
  status        ENUM('active','discontinued') NOT NULL DEFAULT 'active',
  sort_order    INT          NOT NULL DEFAULT 0,
  created_at    DATETIME     NOT NULL,
  updated_at    DATETIME     NOT NULL,
  KEY idx_skus_product (product_id, status),
  CONSTRAINT fk_skus_product FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE product_relations (
  id                 INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  product_id         INT UNSIGNED NOT NULL,
  related_product_id INT UNSIGNED NOT NULL,
  source             ENUM('staff','ai') NOT NULL DEFAULT 'staff',
  status             ENUM('pending','approved','rejected') NOT NULL DEFAULT 'approved',
  score              DECIMAL(6,4) NULL,
  reason             VARCHAR(300) NULL,
  sort_order         INT          NOT NULL DEFAULT 0,
  created_at         DATETIME     NOT NULL,
  reviewed_by        INT UNSIGNED NULL,
  UNIQUE KEY uq_rel (product_id, related_product_id),
  CONSTRAINT fk_rel_p FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  CONSTRAINT fk_rel_r FOREIGN KEY (related_product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- KHO — tồn khả dụng = on_hand - reserved, luôn >= 0 (CHECK + UPDATE có điều kiện)
-- ---------------------------------------------------------------------
CREATE TABLE inventory (
  sku_id     INT UNSIGNED NOT NULL PRIMARY KEY,
  on_hand    INT          NOT NULL DEFAULT 0,
  reserved   INT          NOT NULL DEFAULT 0,
  updated_at DATETIME     NOT NULL,
  CONSTRAINT chk_inv_nonneg CHECK (on_hand >= 0 AND reserved >= 0 AND on_hand >= reserved),
  CONSTRAINT fk_inv_sku FOREIGN KEY (sku_id) REFERENCES skus(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE inventory_movements (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  sku_id          INT UNSIGNED NOT NULL,
  order_id        BIGINT UNSIGNED NULL,
  type            ENUM('receive','adjust','reserve','release','ship','return_restock','return_reject') NOT NULL,
  on_hand_delta   INT          NOT NULL DEFAULT 0,
  reserved_delta  INT          NOT NULL DEFAULT 0,
  on_hand_after   INT          NOT NULL,
  reserved_after  INT          NOT NULL,
  reason          VARCHAR(300) NULL,
  transition_key  VARCHAR(80)  NULL COMMENT 'order:{id}:{from}>{to} — chống ghi trùng',
  user_id         INT UNSIGNED NULL,
  created_at      DATETIME     NOT NULL,
  KEY idx_mv_sku (sku_id, created_at),
  KEY idx_mv_order (order_id),
  UNIQUE KEY uq_mv_transition (transition_key, sku_id),
  CONSTRAINT fk_mv_sku FOREIGN KEY (sku_id) REFERENCES skus(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- VÙNG GIAO & BIỂU PHÍ
-- ---------------------------------------------------------------------
CREATE TABLE shipping_zones (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(120) NOT NULL,
  provinces   TEXT         NOT NULL COMMENT 'JSON array tên tỉnh/thành phục vụ',
  eta_text    VARCHAR(120) NULL,
  is_active   TINYINT(1)   NOT NULL DEFAULT 1,
  sort_order  INT          NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE shipping_rates (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  zone_id         INT UNSIGNED NOT NULL,
  fee             INT UNSIGNED NOT NULL,
  free_from       INT UNSIGNED NULL COMMENT 'Miễn phí khi tiền hàng sau giảm >= mức này',
  effective_from  DATETIME     NOT NULL,
  effective_to    DATETIME     NULL,
  created_at      DATETIME     NOT NULL,
  KEY idx_rate_zone (zone_id, effective_from),
  CONSTRAINT fk_rate_zone FOREIGN KEY (zone_id) REFERENCES shipping_zones(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- ƯU ĐÃI
-- ---------------------------------------------------------------------
CREATE TABLE flash_sales (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name           VARCHAR(150) NOT NULL,
  starts_at      DATETIME     NOT NULL,
  ends_at        DATETIME     NOT NULL,
  allow_voucher  TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'Dòng hàng Flash Sale có được tính vào voucher không',
  is_active      TINYINT(1)   NOT NULL DEFAULT 1,
  created_at     DATETIME     NOT NULL,
  updated_at     DATETIME     NOT NULL,
  CONSTRAINT chk_fs_time CHECK (ends_at > starts_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE flash_sale_items (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  flash_sale_id  INT UNSIGNED NOT NULL,
  sku_id         INT UNSIGNED NOT NULL,
  sale_price     INT UNSIGNED NOT NULL,
  UNIQUE KEY uq_fs_sku (flash_sale_id, sku_id),
  KEY idx_fsi_sku (sku_id),
  CONSTRAINT fk_fsi_fs FOREIGN KEY (flash_sale_id) REFERENCES flash_sales(id) ON DELETE CASCADE,
  CONSTRAINT fk_fsi_sku FOREIGN KEY (sku_id) REFERENCES skus(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE vouchers (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  code            VARCHAR(40)  NOT NULL UNIQUE,
  description     VARCHAR(200) NULL,
  amount          INT UNSIGNED NOT NULL COMMENT 'Giảm số tiền cố định',
  min_subtotal    INT UNSIGNED NOT NULL DEFAULT 0,
  scope_type      ENUM('all','category','product') NOT NULL DEFAULT 'all',
  scope_ids       TEXT         NULL COMMENT 'JSON array id danh mục/sản phẩm',
  starts_at       DATETIME     NOT NULL,
  ends_at         DATETIME     NOT NULL,
  usage_limit     INT UNSIGNED NULL COMMENT 'NULL = không giới hạn',
  reserved_count  INT UNSIGNED NOT NULL DEFAULT 0,
  used_count      INT UNSIGNED NOT NULL DEFAULT 0,
  is_active       TINYINT(1)   NOT NULL DEFAULT 1,
  created_at      DATETIME     NOT NULL,
  updated_at      DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- KHÁCH HÀNG (đặt hàng không cần tài khoản; khách nhận diện theo SĐT)
-- ---------------------------------------------------------------------
CREATE TABLE customers (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  phone              VARCHAR(20)  NOT NULL UNIQUE,
  full_name          VARCHAR(120) NOT NULL,
  customer_key       CHAR(24)     NOT NULL UNIQUE COMMENT 'Mã ẩn danh (HMAC SĐT) gửi cho Python',
  marketing_consent  TINYINT(1)   NOT NULL DEFAULT 0,
  consent_updated_at DATETIME     NULL,
  created_at         DATETIME     NOT NULL,
  updated_at         DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- ĐƠN HÀNG (bản chụp toàn bộ dữ liệu tại thời điểm đặt)
-- ---------------------------------------------------------------------
CREATE TABLE orders (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  code               VARCHAR(20)  NOT NULL UNIQUE,
  access_token       CHAR(32)     NOT NULL,
  customer_id        BIGINT UNSIGNED NOT NULL,
  status             ENUM('pending','confirmed','shipping','delivered','cancelled','returning','returned') NOT NULL DEFAULT 'pending',
  payment_method     ENUM('cod','vietqr') NOT NULL,
  payment_status     ENUM('unpaid','partial','paid','overpaid','partially_refunded','refunded') NOT NULL DEFAULT 'unpaid',
  needs_review       TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'Tác vụ hết hạn chuyển cho nhân viên',
  review_reason      VARCHAR(300) NULL,
  -- bản chụp giao hàng
  ship_name          VARCHAR(120) NOT NULL,
  ship_phone         VARCHAR(20)  NOT NULL,
  ship_province      VARCHAR(80)  NOT NULL,
  ship_address       VARCHAR(400) NOT NULL,
  ship_note          VARCHAR(400) NULL,
  zone_id            INT UNSIGNED NOT NULL,
  zone_name          VARCHAR(120) NOT NULL,
  shipping_rate_id   INT UNSIGNED NOT NULL,
  -- tiền (VND nguyên)
  goods_subtotal     INT UNSIGNED NOT NULL COMMENT 'Tiền hàng sau Flash Sale',
  voucher_id         INT UNSIGNED NULL,
  voucher_code       VARCHAR(40)  NULL,
  voucher_discount   INT UNSIGNED NOT NULL DEFAULT 0,
  shipping_fee       INT UNSIGNED NOT NULL,
  total              INT UNSIGNED NOT NULL,
  amount_received    INT UNSIGNED NOT NULL DEFAULT 0,
  amount_refunded    INT UNSIGNED NOT NULL DEFAULT 0,
  transfer_content   VARCHAR(40)  NOT NULL COMMENT 'Nội dung chuyển khoản gắn mã đơn',
  carrier_name       VARCHAR(80)  NULL,
  tracking_code      VARCHAR(80)  NULL,
  expires_at         DATETIME     NOT NULL COMMENT 'Hạn chờ xác nhận theo phương thức',
  qr_viewed_at       DATETIME     NULL,
  delivered_at       DATETIME     NULL,
  last_event_seq     BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Phiên bản đồng bộ = seq sự kiện gần nhất',
  created_at         DATETIME     NOT NULL,
  updated_at         DATETIME     NOT NULL,
  KEY idx_orders_status (status, created_at),
  KEY idx_orders_expiry (status, expires_at),
  KEY idx_orders_customer (customer_id),
  CONSTRAINT chk_order_total CHECK (total = goods_subtotal - voucher_discount + shipping_fee),
  CONSTRAINT chk_refund_cap CHECK (amount_refunded <= amount_received),
  CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers(id),
  CONSTRAINT fk_orders_voucher FOREIGN KEY (voucher_id) REFERENCES vouchers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE order_items (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id        BIGINT UNSIGNED NOT NULL,
  sku_id          INT UNSIGNED NOT NULL,
  product_id      INT UNSIGNED NOT NULL,
  category_id     INT UNSIGNED NOT NULL,
  product_name    VARCHAR(200) NOT NULL,
  sku_code        VARCHAR(64)  NOT NULL,
  variant_label   VARCHAR(120) NOT NULL,
  list_price      INT UNSIGNED NOT NULL,
  unit_price      INT UNSIGNED NOT NULL COMMENT 'Sau Flash Sale',
  flash_sale_id   INT UNSIGNED NULL,
  quantity        INT UNSIGNED NOT NULL,
  line_total      INT UNSIGNED NOT NULL,
  voucher_eligible TINYINT(1)  NOT NULL DEFAULT 1,
  qty_returned_ok      INT UNSIGNED NOT NULL DEFAULT 0,
  qty_returned_reject  INT UNSIGNED NOT NULL DEFAULT 0,
  KEY idx_oi_order (order_id),
  KEY idx_oi_sku (sku_id),
  CONSTRAINT fk_oi_order FOREIGN KEY (order_id) REFERENCES orders(id),
  CONSTRAINT fk_oi_sku FOREIGN KEY (sku_id) REFERENCES skus(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE order_status_history (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id     BIGINT UNSIGNED NOT NULL,
  from_status  VARCHAR(20)  NULL,
  to_status    VARCHAR(20)  NOT NULL,
  actor_type   ENUM('customer','user','system') NOT NULL,
  user_id      INT UNSIGNED NULL,
  reason       VARCHAR(500) NULL,
  created_at   DATETIME     NOT NULL,
  KEY idx_osh_order (order_id, created_at),
  CONSTRAINT fk_osh_order FOREIGN KEY (order_id) REFERENCES orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE voucher_usages (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  voucher_id  INT UNSIGNED NOT NULL,
  order_id    BIGINT UNSIGNED NOT NULL UNIQUE,
  amount      INT UNSIGNED NOT NULL,
  status      ENUM('reserved','used','released') NOT NULL,
  created_at  DATETIME     NOT NULL,
  updated_at  DATETIME     NOT NULL,
  KEY idx_vu_voucher (voucher_id, status),
  CONSTRAINT fk_vu_voucher FOREIGN KEY (voucher_id) REFERENCES vouchers(id),
  CONSTRAINT fk_vu_order FOREIGN KEY (order_id) REFERENCES orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Khóa gửi lại (Idempotency-Key) gắn với phiên đặt hàng.
CREATE TABLE idempotency_keys (
  id_key        VARCHAR(80)  NOT NULL PRIMARY KEY,
  session_hash  CHAR(64)     NOT NULL,
  request_hash  CHAR(64)     NOT NULL,
  order_id      BIGINT UNSIGNED NULL COMMENT 'NULL trong lúc giao dịch tạo đơn đang chạy',
  created_at    DATETIME     NOT NULL,
  KEY idx_idem_time (created_at),
  CONSTRAINT fk_idem_order FOREIGN KEY (order_id) REFERENCES orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- THANH TOÁN, SAI LỆCH, HOÀN TIỀN
-- ---------------------------------------------------------------------
CREATE TABLE payment_receipts (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id       BIGINT UNSIGNED NULL COMMENT 'NULL khi chưa khớp được đơn',
  method         ENUM('vietqr','cod','other') NOT NULL,
  source         VARCHAR(40)  NOT NULL COMMENT 'Ngân hàng/hãng vận chuyển/người giao',
  bank_txn_id    VARCHAR(80)  NOT NULL,
  amount         INT UNSIGNED NOT NULL,
  transfer_content VARCHAR(200) NULL,
  received_at    DATETIME     NOT NULL,
  recorded_by    INT UNSIGNED NOT NULL,
  note           VARCHAR(300) NULL,
  created_at     DATETIME     NOT NULL,
  UNIQUE KEY uq_receipt_txn (source, bank_txn_id),
  KEY idx_receipt_order (order_id),
  CONSTRAINT fk_receipt_order FOREIGN KEY (order_id) REFERENCES orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE payment_discrepancies (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id     BIGINT UNSIGNED NULL,
  receipt_id   BIGINT UNSIGNED NULL,
  type         ENUM('underpaid','overpaid','wrong_content','late','after_cancel','unmatched','cod_mismatch') NOT NULL,
  expected_amount INT UNSIGNED NULL,
  actual_amount   INT UNSIGNED NULL,
  status       ENUM('open','resolved') NOT NULL DEFAULT 'open',
  resolution   ENUM('accepted','refund','replacement_order','customer_topup','other') NULL,
  resolution_note VARCHAR(500) NULL,
  resolved_by  INT UNSIGNED NULL,
  resolved_at  DATETIME     NULL,
  created_at   DATETIME     NOT NULL,
  KEY idx_disc_status (status, created_at),
  KEY idx_disc_order (order_id),
  CONSTRAINT fk_disc_order FOREIGN KEY (order_id) REFERENCES orders(id),
  CONSTRAINT fk_disc_receipt FOREIGN KEY (receipt_id) REFERENCES payment_receipts(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE refunds (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id      BIGINT UNSIGNED NOT NULL,
  amount        INT UNSIGNED NOT NULL,
  reason        VARCHAR(500) NOT NULL,
  status        ENUM('pending','completed','cancelled') NOT NULL DEFAULT 'pending',
  requested_by  INT UNSIGNED NULL COMMENT 'NULL = hệ thống tạo khi hủy đơn đã thu tiền',
  approved_by   INT UNSIGNED NULL,
  refund_txn_ref VARCHAR(80) NULL,
  refunded_at   DATETIME     NULL,
  created_at    DATETIME     NOT NULL,
  updated_at    DATETIME     NOT NULL,
  KEY idx_refund_status (status),
  KEY idx_refund_order (order_id),
  CONSTRAINT fk_refund_order FOREIGN KEY (order_id) REFERENCES orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- NỘI DUNG: blog & FAQ có phiên bản, duyệt, xuất bản
-- ---------------------------------------------------------------------
CREATE TABLE contents (
  id                    INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  kind                  ENUM('blog','faq','page') NOT NULL,
  slug                  VARCHAR(220) NOT NULL,
  status                ENUM('draft','pending_review','published','unpublished') NOT NULL DEFAULT 'draft',
  source                ENUM('staff','ai') NOT NULL DEFAULT 'staff',
  category_id           INT UNSIGNED NULL,
  product_id            INT UNSIGNED NULL,
  current_version_id    INT UNSIGNED NULL,
  published_version_id  INT UNSIGNED NULL,
  -- bản xuất bản (denormalized để đọc nhanh)
  pub_title             VARCHAR(250) NULL,
  pub_meta_description  VARCHAR(320) NULL,
  pub_body              MEDIUMTEXT   NULL,
  pub_search_text       TEXT         NULL,
  cover_image           VARCHAR(255) NULL,
  published_at          DATETIME     NULL,
  created_at            DATETIME     NOT NULL,
  updated_at            DATETIME     NOT NULL,
  UNIQUE KEY uq_content_slug (kind, slug),
  KEY idx_content_status (kind, status, published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE content_versions (
  id               INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  content_id       INT UNSIGNED NOT NULL,
  version_no       INT UNSIGNED NOT NULL,
  title            VARCHAR(250) NOT NULL,
  meta_description VARCHAR(320) NULL,
  body             MEDIUMTEXT   NOT NULL,
  keywords         VARCHAR(500) NULL,
  source_refs      TEXT         NULL COMMENT 'JSON: nguồn tham chiếu (sản phẩm + info_version, tài liệu)',
  created_by       INT UNSIGNED NULL,
  created_source   ENUM('staff','ai') NOT NULL DEFAULT 'staff',
  review_note      VARCHAR(500) NULL,
  reviewed_by      INT UNSIGNED NULL,
  reviewed_at      DATETIME     NULL,
  created_at       DATETIME     NOT NULL,
  UNIQUE KEY uq_cv (content_id, version_no),
  CONSTRAINT fk_cv_content FOREIGN KEY (content_id) REFERENCES contents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- CHĂM SÓC LẠI (đề xuất từ Python, nhân viên xem xét)
-- ---------------------------------------------------------------------
CREATE TABLE care_suggestions (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  batch_id        VARCHAR(40)  NOT NULL,
  customer_id     BIGINT UNSIGNED NOT NULL,
  category_id     INT UNSIGNED NULL,
  last_order_at   DATETIME     NULL,
  due_date        DATE         NOT NULL,
  score           DECIMAL(6,4) NULL,
  reason          VARCHAR(300) NULL,
  status          ENUM('pending','contacted','skipped') NOT NULL DEFAULT 'pending',
  handled_by      INT UNSIGNED NULL,
  handled_at      DATETIME     NULL,
  created_at      DATETIME     NOT NULL,
  UNIQUE KEY uq_care (batch_id, customer_id, category_id),
  KEY idx_care_status (status, due_date),
  CONSTRAINT fk_care_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- ĐỒNG BỘ — sự kiện ghi cùng giao dịch cập nhật đơn.
-- seq được cấp từ bộ đếm sync_counter (khóa hàng) ở cuối giao dịch,
-- nên thứ tự seq trùng thứ tự commit (xem docs/THIET-KE.md §6).
-- ---------------------------------------------------------------------
CREATE TABLE sync_counter (
  id        TINYINT UNSIGNED NOT NULL PRIMARY KEY,
  last_seq  BIGINT UNSIGNED  NOT NULL
) ENGINE=InnoDB;

CREATE TABLE sync_events (
  seq          BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  event_id     CHAR(26)     NOT NULL UNIQUE,
  entity_type  VARCHAR(32)  NOT NULL,
  entity_id    BIGINT UNSIGNED NOT NULL,
  event_type   VARCHAR(48)  NOT NULL,
  payload      TEXT         NOT NULL COMMENT 'JSON tối thiểu, không có tên/SĐT/địa chỉ',
  created_at   DATETIME     NOT NULL,
  KEY idx_se_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Hộp thư bản nháp do Python gửi (để truy vết; nội dung chuyển vào bảng nghiệp vụ ở trạng thái chờ duyệt)
CREATE TABLE sync_inbox (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  api_key_id   INT UNSIGNED NOT NULL,
  client_ref   VARCHAR(80)  NOT NULL,
  kind         VARCHAR(32)  NOT NULL,
  status       ENUM('accepted','rejected') NOT NULL,
  result       VARCHAR(500) NULL,
  created_at   DATETIME     NOT NULL,
  UNIQUE KEY uq_inbox_ref (api_key_id, client_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO sync_counter (id, last_seq) VALUES (1, 0);

-- Câu hỏi chat (đã bỏ dấu, che SĐT) để phát hiện khoảng trống FAQ; không lưu danh tính khách.
CREATE TABLE chat_questions (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  question       VARCHAR(500) NOT NULL,
  source         ENUM('faq','live','label','fallback') NOT NULL,
  matched_faq_id INT UNSIGNED NULL,
  score          DECIMAL(8,4) NULL,
  created_at     DATETIME     NOT NULL,
  KEY idx_chat_src (source, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
