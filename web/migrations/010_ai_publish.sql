-- 010_ai_publish.sql — AI tự xuất bản FAQ/blog qua khóa riêng `content:publish` (ADR-16 của ai-company).
-- Website là lớp chặn CUỐI: chỉ nội dung AI mới, đúng giờ cho phép, trong hạn mức ngày ĐẾM Ở WEBSITE, có audit, gỡ được ngay.
SET NAMES utf8mb4;

ALTER TABLE contents
  ADD COLUMN published_by ENUM('staff','ai') NULL COMMENT 'Ai bấm xuất bản lần gần nhất (NULL = chưa xuất bản)' AFTER published_at;

UPDATE contents SET published_by = 'staff' WHERE published_at IS NOT NULL;

CREATE TABLE ai_publications (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  api_key_id      INT UNSIGNED NOT NULL,
  client_ref      VARCHAR(80)  NOT NULL,
  content_id      INT UNSIGNED NOT NULL,
  kind            ENUM('blog','faq') NOT NULL,
  published_at    DATETIME     NOT NULL,
  unpublished_at  DATETIME     NULL,
  unpublish_reason VARCHAR(500) NULL,
  UNIQUE KEY uq_aipub_ref (api_key_id, client_ref),
  KEY idx_aipub_day (kind, published_at),
  KEY idx_aipub_content (content_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Hạn mức an toàn phía website (bằng mức cao nhất của giai đoạn 3; lịch thật ở dịch vụ Python thấp hơn)
INSERT IGNORE INTO settings (`key`, `value`, updated_at) VALUES
('ai_publish_enabled',     '1',     UTC_TIMESTAMP()),
('ai_publish_limit_faq',   '3',     UTC_TIMESTAMP()),
('ai_publish_limit_blog',  '1',     UTC_TIMESTAMP()),
('ai_publish_hours',       '07:00-21:30', UTC_TIMESTAMP());
