-- 005_customer_accounts.sql — đăng nhập TÙY CHỌN của khách bằng Google / Facebook.
-- Khách vẫn đặt hàng không cần tài khoản. Tài khoản chỉ để xem lại đơn, điền sẵn thông tin, quản lý nhận tin.
SET NAMES utf8mb4;

CREATE TABLE customer_accounts (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email          VARCHAR(190) NULL COMMENT 'Email đã xác minh từ nhà cung cấp (có thể trống với Facebook)',
  display_name   VARCHAR(120) NOT NULL,
  ship_name      VARCHAR(120) NULL,
  ship_phone     VARCHAR(20)  NULL,
  ship_province  VARCHAR(80)  NULL,
  ship_address   VARCHAR(400) NULL,
  last_login_at  DATETIME     NULL,
  created_at     DATETIME     NOT NULL,
  updated_at     DATETIME     NOT NULL,
  KEY idx_acct_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE account_identities (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  account_id     BIGINT UNSIGNED NOT NULL,
  provider       ENUM('google','facebook') NOT NULL,
  provider_uid   VARCHAR(191) NOT NULL COMMENT 'Google sub / Facebook app-scoped user id',
  email          VARCHAR(190) NULL,
  email_verified TINYINT(1)   NOT NULL DEFAULT 0,
  created_at     DATETIME     NOT NULL,
  last_login_at  DATETIME     NULL,
  UNIQUE KEY uq_identity (provider, provider_uid),
  KEY idx_ident_account (account_id),
  CONSTRAINT fk_ident_account FOREIGN KEY (account_id) REFERENCES customer_accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Yêu cầu xóa dữ liệu (tự xóa tài khoản hoặc từ Facebook) — mã xác nhận để tra trạng thái
CREATE TABLE account_deletions (
  confirmation_code CHAR(16)  NOT NULL PRIMARY KEY,
  source         ENUM('self','facebook') NOT NULL,
  status         ENUM('completed','not_found') NOT NULL,
  requested_at   DATETIME     NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE orders
  ADD COLUMN account_id BIGINT UNSIGNED NULL AFTER customer_id,
  ADD KEY idx_orders_account (account_id, created_at),
  ADD CONSTRAINT fk_orders_account FOREIGN KEY (account_id) REFERENCES customer_accounts(id) ON DELETE SET NULL;
