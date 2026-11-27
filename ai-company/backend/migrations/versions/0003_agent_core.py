"""Agent Core: bộ não có phiên bản, ghim hash quy tắc cốt lõi, công cụ, quyền, nhật ký gọi công cụ,
quyết định của Policy Engine, hàng chờ phê duyệt; chống dùng lại mã TOTP.

Revision ID: 0003_agent_core
Revises: 0002_control_center
"""

from alembic import op

revision = "0003_agent_core"
down_revision = "0002_control_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        -- Chống dùng lại mã TOTP: lưu bước thời gian (30 giây) của mã hợp lệ gần nhất
        ALTER TABLE users ADD COLUMN totp_last_step bigint;

        -- Bộ não: mỗi lần nạp bundle có nội dung mới tạo một dòng; tối đa 1 bản active mỗi agent
        CREATE TABLE agent_brains (
          id uuid PRIMARY KEY,
          agent_key text NOT NULL REFERENCES agents(agent_key) ON DELETE CASCADE,
          brain_version text NOT NULL,
          prompt_version text NOT NULL,
          knowledge_version text NOT NULL,
          skill_version text NOT NULL,
          bundle jsonb NOT NULL,
          bundle_hash text NOT NULL,
          core_rules_hash text NOT NULL,
          state text NOT NULL CHECK (state IN ('draft','shadow','active','retired','rejected')),
          created_at timestamptz NOT NULL DEFAULT now(),
          created_by text NOT NULL,
          activated_at timestamptz,
          UNIQUE (agent_key, bundle_hash)
        );
        CREATE UNIQUE INDEX agent_brains_one_active ON agent_brains(agent_key) WHERE state = 'active';
        CREATE INDEX agent_brains_agent ON agent_brains(agent_key, created_at DESC);

        -- Changelog phiên bản bộ não (SRS §4.5): chỉ thêm, không sửa, không xóa
        CREATE TABLE agent_versions (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          at timestamptz NOT NULL DEFAULT now(),
          agent_key text NOT NULL REFERENCES agents(agent_key) ON DELETE CASCADE,
          event text NOT NULL CHECK (event IN ('bootstrap','proposed','activated','rolled_back','rejected','core_pinned')),
          component text NOT NULL,
          from_version text,
          to_version text,
          brain_id uuid REFERENCES agent_brains(id),
          previous_brain_id uuid REFERENCES agent_brains(id),
          diff jsonb NOT NULL DEFAULT '[]',
          sources jsonb NOT NULL DEFAULT '[]',
          proposed_by text NOT NULL,
          approved_by text,
          test_results jsonb NOT NULL DEFAULT '{}'
        );
        CREATE INDEX agent_versions_agent ON agent_versions(agent_key, id DESC);
        CREATE FUNCTION agent_versions_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'agent_versions chỉ được thêm, không được sửa hay xóa';
        END $$;
        CREATE TRIGGER agent_versions_no_change BEFORE UPDATE OR DELETE ON agent_versions
          FOR EACH ROW EXECUTE FUNCTION agent_versions_immutable();

        -- Hash quy tắc cốt lõi được Owner chấp nhận (constitution + hard_rules + tool_permissions).
        -- Runtime từ chối nạp bundle có hash lệch mà không có dòng ở đây.
        CREATE TABLE brain_core_pins (
          agent_key text NOT NULL REFERENCES agents(agent_key) ON DELETE CASCADE,
          core_rules_hash text NOT NULL,
          approved_by text NOT NULL,
          approved_at timestamptz NOT NULL DEFAULT now(),
          approval_id uuid,
          PRIMARY KEY (agent_key, core_rules_hash)
        );

        -- Công cụ (mã nguồn khai báo, đồng bộ vào đây để Control Center và Policy Engine đọc)
        CREATE TABLE tool_registry (
          id text PRIMARY KEY,
          description text NOT NULL,
          actions jsonb NOT NULL,            -- {action: {min_level, tags[], side_effects}}
          input_schema jsonb NOT NULL,
          output_schema jsonb NOT NULL,
          side_effects text NOT NULL CHECK (side_effects IN ('none','internal','external')),
          risk text NOT NULL CHECK (risk IN ('low','medium','high')),
          default_timeout_s real NOT NULL,
          retry_policy jsonb NOT NULL,
          available boolean NOT NULL,        -- false: chưa có tích hợp, gọi sẽ trả NOT_CONFIGURED
          updated_at timestamptz NOT NULL DEFAULT now()
        );

        -- Quyền (agent × công cụ × hành động). Lấy từ tools/tool_permissions.yaml của bộ não đang active.
        CREATE TABLE agent_permissions (
          agent_key text NOT NULL REFERENCES agents(agent_key) ON DELETE CASCADE,
          tool_id text NOT NULL,
          action text NOT NULL,
          autonomy_level smallint NOT NULL CHECK (autonomy_level BETWEEN 1 AND 4),
          limits jsonb NOT NULL DEFAULT '{}',
          requires_approval boolean NOT NULL DEFAULT false,
          granted_by text NOT NULL,
          brain_id uuid REFERENCES agent_brains(id) ON DELETE SET NULL,
          expires_at timestamptz,
          PRIMARY KEY (agent_key, tool_id, action)
        );

        CREATE TABLE approvals (
          id uuid PRIMARY KEY,
          subject_type text NOT NULL,
          subject_id text NOT NULL,
          action text NOT NULL,
          title text NOT NULL,
          summary text NOT NULL DEFAULT '',
          payload jsonb NOT NULL DEFAULT '{}',
          payload_digest text NOT NULL,
          risk text NOT NULL CHECK (risk IN ('low','medium','high')),
          requested_by text NOT NULL,
          status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','expired','cancelled')),
          decided_by text,
          decided_at timestamptz,
          decision_note text,
          created_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL
        );
        CREATE INDEX approvals_pending ON approvals(created_at DESC) WHERE status = 'pending';
        CREATE UNIQUE INDEX approvals_one_pending ON approvals(subject_type, subject_id, payload_digest) WHERE status = 'pending';

        CREATE TABLE tool_invocations (
          id uuid PRIMARY KEY,
          at timestamptz NOT NULL DEFAULT now(),
          tool_id text NOT NULL,
          action text NOT NULL,
          agent_key text NOT NULL,
          task_id text,
          idempotency_key text NOT NULL UNIQUE,
          input_digest text NOT NULL,
          status text NOT NULL CHECK (status IN ('running','succeeded','failed','denied','waiting_approval')),
          output jsonb,
          error_code text,
          error text,
          attempts int NOT NULL DEFAULT 0,
          duration_ms int,
          approval_id uuid REFERENCES approvals(id),
          finished_at timestamptz
        );
        CREATE INDEX tool_invocations_agent ON tool_invocations(agent_key, at DESC);

        -- Mỗi quyết định của Policy Engine đều ghi lại kèm lý do ("vì sao agent bị chặn")
        CREATE TABLE policy_decisions (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          at timestamptz NOT NULL DEFAULT now(),
          agent_key text NOT NULL,
          tool_id text NOT NULL,
          action text NOT NULL,
          decision text NOT NULL CHECK (decision IN ('allow','require_approval','deny')),
          rule text NOT NULL,
          reason text NOT NULL,
          context jsonb NOT NULL DEFAULT '{}'
        );
        CREATE INDEX policy_decisions_agent ON policy_decisions(agent_key, at DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS policy_decisions, tool_invocations, approvals, agent_permissions, tool_registry,
          brain_core_pins, agent_versions, agent_brains CASCADE;
        DROP FUNCTION IF EXISTS agent_versions_immutable();
        ALTER TABLE users DROP COLUMN IF EXISTS totp_last_step;
        """
    )
