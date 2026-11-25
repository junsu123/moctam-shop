-- 003_legal_settings.sql — thông tin pháp lý của chủ website (Luật TMĐT 2025: công khai thông tin chủ quản)
-- Hiển thị ở chân trang, trang Chính sách bảo mật thông tin và Điều khoản sử dụng. Điền trong Quản trị → Cấu hình.
SET NAMES utf8mb4;

INSERT IGNORE INTO settings (`key`, `value`, updated_at) VALUES
('business_name',        '', UTC_TIMESTAMP()),
('business_reg_no',      '', UTC_TIMESTAMP()),
('business_reg_info',    '', UTC_TIMESTAMP()),
('representative',       '', UTC_TIMESTAMP()),
('privacy_email',        '', UTC_TIMESTAMP()),
('hosting_provider',     'Hostinger', UTC_TIMESTAMP()),
('server_location',      '', UTC_TIMESTAMP()),
('complaint_reply_days', '3', UTC_TIMESTAMP());
