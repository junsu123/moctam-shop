"""Task Engine, Message Bus, lịch tự động (SRS §6, §7, §14; DATABASE_SCHEMA §6, §7; ARCHITECTURE ADR-04, ADR-05).

- `tasks`: 9 trạng thái SRS; lease + `FOR UPDATE SKIP LOCKED` làm hàng đợi bền (sống qua tắt máy); khóa phiên bản `version`.
  Chuyển trạng thái được kiểm trong mã (`app.tasks.engine`) VÀ bằng trigger (lớp thứ hai).
- `task_logs`: từng bước của task; phát NOTIFY cho màn hình Diễn biến.
- `agent_messages`: đúng schema SRS §6.1 + các trường của AGENT_DESIGN §5; đồng thời là outbox (giao ít nhất một lần).
- `knowledge_candidates`: hộp ứng viên kiến thức (`knowledge_sharing` vào đây, không ghi thẳng vào trí nhớ). Sprint 5 mở rộng.
- `schedules`: lịch cron cấu hình được, chạy bù khi máy bật lại.
- Checkpoint LangGraph nằm trong schema riêng `langgraph`, do thư viện tự tạo bảng (`app.tasks.graph.setup`).

Revision ID: 0005_tasks
Revises: 0004_memory
"""

from alembic import op

revision = "0005_tasks"
down_revision = "0004_memory"
branch_labels = None
depends_on = None

STATUSES = "'CREATED','PENDING','ASSIGNED','IN_PROGRESS','WAITING_REVIEW','WAITING_APPROVAL','COMPLETED','FAILED','CANCELLED'"
MSG_TYPES = (
    "'task_request','task_response','knowledge_sharing','research_result','review_request','approval_request','error_report',"
    "'performance_report'"
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS langgraph")
    op.execute(
        f"""
        CREATE TABLE tasks (
          id uuid PRIMARY KEY,
          parent_id uuid REFERENCES tasks(id),
          root_id uuid NOT NULL,
          depth int NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 4),
          title text NOT NULL CHECK (length(title) BETWEEN 3 AND 300),
          description text NOT NULL DEFAULT '',
          task_type text NOT NULL DEFAULT 'generic',
          created_by text NOT NULL,                      -- principal: user:<id>, agent:<key>, system:scheduler
          assigned_agent text REFERENCES agents(agent_key),
          priority smallint NOT NULL DEFAULT 2 CHECK (priority BETWEEN 0 AND 3),  -- 0 khẩn, 1 cao, 2 thường, 3 thấp
          deadline timestamptz,
          input_data jsonb NOT NULL DEFAULT '{{}}',
          output_data jsonb,
          success_criteria jsonb NOT NULL DEFAULT '[]',
          status text NOT NULL DEFAULT 'CREATED' CHECK (status IN ({STATUSES})),
          requires_review boolean NOT NULL DEFAULT false,
          reviewer text,                                 -- principal duyệt nội bộ (vd agent:marketing_director)
          requires_approval boolean NOT NULL DEFAULT false,
          autonomy_max smallint NOT NULL DEFAULT 2 CHECK (autonomy_max BETWEEN 1 AND 4),
          budget_usd numeric(10,4) NOT NULL DEFAULT 0.5 CHECK (budget_usd >= 0),
          spent_usd numeric(12,6) NOT NULL DEFAULT 0,
          brain_id uuid REFERENCES agent_brains(id),     -- bộ não ghim lúc tạo task
          graph_key text NOT NULL DEFAULT 'cognitive',
          graph_node text,
          wait_kind text,                                -- approval | review | children (khi đồ thị dừng chờ)
          attempt int NOT NULL DEFAULT 1,
          max_attempts int NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
          not_before timestamptz,
          lease_owner text,
          lease_until timestamptz,
          idempotency_key text UNIQUE,
          timeout_s int NOT NULL DEFAULT 1800 CHECK (timeout_s BETWEEN 30 AND 86400),
          timeout_at timestamptz,
          error_code text,
          error text,
          result_summary text,
          version int NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          started_at timestamptz,
          finished_at timestamptz
        );
        CREATE INDEX tasks_runnable ON tasks(status, lease_until, priority, created_at);
        CREATE INDEX tasks_agent ON tasks(assigned_agent, status);
        CREATE INDEX tasks_parent ON tasks(parent_id);
        CREATE INDEX tasks_root ON tasks(root_id);
        CREATE INDEX tasks_recent ON tasks(updated_at DESC);

        -- Lớp thứ hai: chuyển trạng thái sai thì CSDL từ chối (lớp một ở app.tasks.engine.ALLOWED)
        CREATE FUNCTION task_transition_check() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE ok boolean;
        BEGIN
          IF NEW.status = OLD.status THEN RETURN NEW; END IF;
          ok := CASE OLD.status
            WHEN 'CREATED' THEN NEW.status IN ('PENDING','CANCELLED')
            WHEN 'PENDING' THEN NEW.status IN ('ASSIGNED','CANCELLED')
            WHEN 'ASSIGNED' THEN NEW.status IN ('IN_PROGRESS','PENDING','CANCELLED')
            WHEN 'IN_PROGRESS' THEN NEW.status IN ('PENDING','WAITING_REVIEW','WAITING_APPROVAL','COMPLETED','FAILED','CANCELLED')
            WHEN 'WAITING_REVIEW' THEN NEW.status IN ('IN_PROGRESS','WAITING_APPROVAL','COMPLETED','CANCELLED')
            WHEN 'WAITING_APPROVAL' THEN NEW.status IN ('IN_PROGRESS','COMPLETED','CANCELLED')
            WHEN 'FAILED' THEN NEW.status IN ('PENDING','CANCELLED')
            ELSE false
          END;
          IF NOT ok THEN
            RAISE EXCEPTION 'TASK_TRANSITION_INVALID: % -> %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER task_transition BEFORE UPDATE OF status ON tasks FOR EACH ROW EXECUTE FUNCTION task_transition_check();

        CREATE TABLE task_dependencies (
          task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
          depends_on uuid NOT NULL,                      -- có thể chưa tồn tại (task con do Message Bus tạo sau)
          PRIMARY KEY (task_id, depends_on),
          CHECK (task_id <> depends_on)
        );
        CREATE INDEX task_dependencies_on ON task_dependencies(depends_on);

        CREATE TABLE task_logs (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
          at timestamptz NOT NULL DEFAULT now(),
          agent_key text,
          event text NOT NULL,
          node text,
          step_no int,
          text text NOT NULL,
          data jsonb NOT NULL DEFAULT '{{}}'
        );
        CREATE INDEX task_logs_task ON task_logs(task_id, id);
        CREATE INDEX task_logs_recent ON task_logs(id DESC);
        CREATE FUNCTION task_log_notify() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_notify('aico_events', json_build_object('source','task','id',NEW.id)::text);
          RETURN NEW;
        END $$;
        CREATE TRIGGER task_log_after_insert AFTER INSERT ON task_logs FOR EACH ROW EXECUTE FUNCTION task_log_notify();

        CREATE TABLE task_reviews (
          id uuid PRIMARY KEY,
          task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
          round int NOT NULL,
          reviewer text NOT NULL,
          verdict text NOT NULL CHECK (verdict IN ('approve','request_changes','reject')),
          notes text,
          rubric_scores jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (task_id, round)
        );

        CREATE TABLE agent_messages (
          id uuid PRIMARY KEY,
          message_type text NOT NULL CHECK (message_type IN ({MSG_TYPES})),
          sender text NOT NULL,
          receiver text NOT NULL,
          task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
          conversation_id uuid,
          correlation_id uuid,
          priority smallint NOT NULL DEFAULT 2,
          payload jsonb NOT NULL,
          trust text NOT NULL DEFAULT 'internal' CHECK (trust IN ('internal','untrusted')),
          idempotency_key text NOT NULL UNIQUE,
          status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','delivered','failed','expired')),
          attempts int NOT NULL DEFAULT 0,
          last_error text,
          not_before timestamptz,
          expires_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          delivered_at timestamptz
        );
        CREATE INDEX agent_messages_queue ON agent_messages(status, not_before, created_at) WHERE status = 'queued';
        CREATE INDEX agent_messages_receiver ON agent_messages(receiver, created_at DESC);
        CREATE INDEX agent_messages_task ON agent_messages(task_id);

        CREATE TABLE knowledge_candidates (
          id uuid PRIMARY KEY,
          proposed_by text NOT NULL,
          target_scope text NOT NULL CHECK (target_scope ~ '^(agent:[a-z0-9_]+|dept:[a-z0-9_]+|company)$'),
          title text NOT NULL,
          claim text NOT NULL,
          evidence jsonb NOT NULL DEFAULT '[]',
          trust text NOT NULL DEFAULT 'internal',
          source_message_id uuid UNIQUE REFERENCES agent_messages(id) ON DELETE SET NULL,
          status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected','duplicate')),
          created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE schedules (
          id uuid PRIMARY KEY,
          name text NOT NULL UNIQUE,
          agent_key text NOT NULL REFERENCES agents(agent_key),
          cron text NOT NULL,
          timezone text NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
          task_template jsonb NOT NULL,
          enabled boolean NOT NULL DEFAULT true,
          catch_up_hours int NOT NULL DEFAULT 24 CHECK (catch_up_hours BETWEEN 0 AND 168),
          last_run_at timestamptz,
          next_run_at timestamptz,
          created_by text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        """  # noqa: S608 — chỉ chèn hằng số STATUSES/MSG_TYPES
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS schedules, knowledge_candidates, agent_messages, task_reviews, task_logs, task_dependencies, tasks CASCADE;
        DROP FUNCTION IF EXISTS task_transition_check();
        DROP FUNCTION IF EXISTS task_log_notify();
        DROP SCHEMA IF EXISTS langgraph CASCADE;
        """
    )
