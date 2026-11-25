-- 007_customer_account_admin.sql — Quản trị → Tài khoản khách: khóa đăng nhập, buộc đăng xuất, xóa thay khách.
-- Không thêm dữ liệu cá nhân mới (không lưu IP/thiết bị): chỉ trạng thái khóa và số phiên bản phiên đăng nhập.
SET NAMES utf8mb4;

ALTER TABLE customer_accounts
  ADD COLUMN locked_at       DATETIME     NULL COMMENT 'Đang khóa đăng nhập từ thời điểm này (NULL = không khóa)' AFTER last_login_at,
  ADD COLUMN locked_reason   VARCHAR(255) NULL AFTER locked_at,
  ADD COLUMN session_version INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Tăng lên để vô hiệu mọi phiên đăng nhập đang mở' AFTER locked_reason,
  ADD KEY idx_acct_created (created_at);

-- Nhân viên xóa tài khoản theo yêu cầu của khách (qua hotline, email…)
ALTER TABLE account_deletions
  MODIFY source ENUM('self','facebook','admin') NOT NULL;
