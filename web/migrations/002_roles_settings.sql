-- 002_roles_settings.sql — vai trò, quyền mặc định và cấu hình khởi điểm
SET NAMES utf8mb4;

INSERT INTO roles (code, name, permissions) VALUES
('admin', 'Quản trị viên', '["*"]'),
('operations', 'Nhân viên vận hành',
 '["catalog.manage","inventory.manage","shipping.manage","promo.manage","orders.view","orders.process","orders.return","payments.view","crosssell.review","care.view"]'),
('warehouse', 'Nhân viên kho',
 '["inventory.manage","orders.view","orders.process","orders.return"]'),
('reconciliation', 'Nhân viên đối soát',
 '["orders.view","payments.view","payments.reconcile","refunds.approve"]'),
('content', 'Nhân viên nội dung',
 '["content.edit","content.publish","crosssell.review"]');

-- Giá trị khởi điểm theo đặc tả §8: 15 phút báo giá, 24 giờ giữ hàng VietQR, 48 giờ chờ xác nhận COD.
INSERT INTO settings (`key`, `value`, updated_at) VALUES
('store_name',        'Xưởng Trà Mộc', UTC_TIMESTAMP()),
('store_tagline',     'Trà túi lọc, bột ngũ cốc, bột thiên nhiên & cà phê rang mộc', UTC_TIMESTAMP()),
('hotline',           '0900 000 000', UTC_TIMESTAMP()),
('zalo',              '0900000000', UTC_TIMESTAMP()),
('support_email',     'hotro@example.vn', UTC_TIMESTAMP()),
('address',           'Địa chỉ xưởng — cập nhật trong Cấu hình', UTC_TIMESTAMP()),
('quote_ttl_minutes', '15', UTC_TIMESTAMP()),
('hold_hours_vietqr', '24', UTC_TIMESTAMP()),
('hold_hours_cod',    '48', UTC_TIMESTAMP()),
('vietqr_bank_bin',   '970436', UTC_TIMESTAMP()),
('vietqr_bank_name',  'Vietcombank', UTC_TIMESTAMP()),
('vietqr_account_no', '0000000000', UTC_TIMESTAMP()),
('vietqr_account_name','XUONG TRA MOC', UTC_TIMESTAMP()),
('order_code_prefix', 'TM', UTC_TIMESTAMP()),
('sync_event_retention_days', '30', UTC_TIMESTAMP());

INSERT INTO settings (`key`, `value`, updated_at) VALUES
('chat_faq_threshold', '0.10', UTC_TIMESTAMP()),
('chat_log_days', '90', UTC_TIMESTAMP());
