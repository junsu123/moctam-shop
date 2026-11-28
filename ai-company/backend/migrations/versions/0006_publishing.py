"""Tự xuất bản FAQ/blog (ARCHITECTURE ADR-16) + nút Telegram có chữ ký (SECURITY_PLAN §3.4).

- `publish_queue`: bài đã qua Content Gate + review (+ Owner duyệt nếu là chủ đề chỉ-người-duyệt), chờ đúng khung giờ của
  lịch đăng; lên website, bị chặn khi kiểm lại trước giờ đăng, hoặc bị gỡ. Khóa chống trùng = khóa của lời gọi công cụ.
- `telegram_buttons`: mỗi nút một mã ngẫu nhiên gắn hành động + đối tượng + digest nội dung + hạn dùng, ký HMAC, dùng một lần.
- `telegram_prompts`: chat đang được hỏi "góp ý cho bài…" (tin nhắn tiếp theo của chat đó là góp ý).
- `notifications.buttons`: nút đính kèm tin (chỉ gửi cho chat có quyền duyệt).

Revision ID: 0006_publishing
Revises: 0005_tasks
"""

from alembic import op

revision = "0006_publishing"
down_revision = "0005_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE publish_queue (
          id uuid PRIMARY KEY,
          task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
          agent_key text NOT NULL,
          kind text NOT NULL CHECK (kind IN ('faq','blog')),
          title text NOT NULL,
          body text NOT NULL,
          meta_description text,
          keywords text,
          product_id int,
          category_id int,
          source_refs jsonb NOT NULL DEFAULT '[]',
          status text NOT NULL CHECK (status IN ('scheduled','publishing','published','blocked','retracted','cancelled','failed')),
          slot_at timestamptz,
          attempts int NOT NULL DEFAULT 0,
          last_error text,
          gate jsonb NOT NULL DEFAULT '{}',
          approval_id uuid REFERENCES approvals(id),
          invocation_key text NOT NULL UNIQUE,
          content_id int,
          url text,
          published_at timestamptz,
          retracted_at timestamptz,
          retracted_by text,
          retract_reason text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX publish_queue_due ON publish_queue(status, slot_at);
        CREATE INDEX publish_queue_recent ON publish_queue(created_at DESC);

        CREATE TABLE telegram_buttons (
          token text PRIMARY KEY,
          action text NOT NULL CHECK (action IN ('approve','reject','unpublish','feedback')),
          subject_type text NOT NULL,
          subject_id text NOT NULL,
          digest text NOT NULL,
          chat_id bigint NOT NULL,
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          used_result text,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX telegram_buttons_subject ON telegram_buttons(subject_type, subject_id);

        CREATE TABLE telegram_prompts (
          chat_id bigint PRIMARY KEY,
          kind text NOT NULL,
          subject_type text NOT NULL,
          subject_id text NOT NULL,
          expires_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        );

        ALTER TABLE notifications ADD COLUMN buttons jsonb;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE notifications DROP COLUMN IF EXISTS buttons;
        DROP TABLE IF EXISTS telegram_prompts, telegram_buttons, publish_queue;
        """
    )
