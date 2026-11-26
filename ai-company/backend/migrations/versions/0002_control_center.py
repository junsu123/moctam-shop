"""Control Center v1: người dùng + phiên, audit chuỗi băm (chỉ thêm), secret mã hóa, cài đặt, agent registry,
Model Gateway (nhà cung cấp, model, hồ sơ, nhật ký dùng), Telegram (chat, mã kết nối, thông báo).

Revision ID: 0002_control_center
Revises: 0001_baseline
"""

from alembic import op

revision = "0002_control_center"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

# 15 agent theo docs/AGENT_DESIGN.md (đây là cấu hình tổ chức, không phải dữ liệu giả)
AGENTS = [
    ("ai_ceo", "AI CEO", "executive", "executive", None, "Phân tích mục tiêu, lập chiến lược, phân công, theo dõi và báo cáo Owner"),
    ("marketing_director", "Giám đốc Marketing", "marketing", "director", "ai_ceo", "Chia việc marketing, review đầu ra, lịch nội dung"),
    ("sales_director", "Giám đốc Kinh doanh", "sales", "director", "ai_ceo", "Chia việc bán hàng, review lead và đối tác, giữ chân khách"),
    ("growth_director", "Giám đốc Tăng trưởng", "growth", "director", "ai_ceo", "Thiết kế thí nghiệm, tối ưu chuyển đổi, kiểm chứng bài học"),
    ("seo_agent", "SEO", "marketing", "specialist", "marketing_director", "Từ khóa, đối thủ, kế hoạch SEO, bản nháp bài, theo dõi Search Console"),
    ("content_agent", "Nội dung", "marketing", "specialist", "marketing_director", "Bài website, Facebook, kịch bản TikTok/livestream, email, lịch nội dung"),
    ("social_agent", "Mạng xã hội", "marketing", "specialist", "marketing_director", "Xu hướng, lịch đăng, hiệu suất và tương tác mạng xã hội"),
    ("ads_agent", "Quảng cáo", "marketing", "specialist", "marketing_director", "Phân tích chiến dịch, đề xuất ngân sách, bản nháp chiến dịch"),
    ("creative_agent", "Thiết kế", "marketing", "specialist", "marketing_director", "Banner, ảnh sản phẩm, poster, video theo brand guidelines"),
    ("customer_agent", "Chăm sóc khách", "sales", "specialist", "sales_director", "Soạn trả lời khách, tư vấn sản phẩm, đề xuất chăm sóc khách cũ"),
    ("affiliate_agent", "Đối tác/KOC", "sales", "specialist", "sales_director", "Tìm KOC/KOL, đánh giá độ phù hợp, theo dõi hiệu quả đối tác"),
    ("sales_intelligence", "Tìm khách sỉ", "sales", "specialist", "sales_director", "Tìm khách sỉ, đại lý, nghiên cứu đối thủ, chấm điểm lead"),
    ("web_cro_agent", "Tối ưu chuyển đổi", "technology", "specialist", "growth_director", "Phân tích trang, phễu thanh toán, đề xuất A/B"),
    ("data_analyst", "Phân tích dữ liệu", "technology", "specialist", "growth_director", "Doanh thu, chi phí, KPI, báo cáo; số liệu cho đánh giá độc lập"),
    ("automation_agent", "Tự động hóa", "technology", "specialist", "growth_director", "Kết nối nền tảng, workflow, theo dõi lỗi hệ thống"),
]

# Giá tra cứu 26/11/2026 (ARCHITECTURE §8.2), USD / 1 triệu token. Sửa được trong registry, không hardcode trong agent.
MODELS = [
    ("claude-opus-5-5", "anthropic", "claude-opus-5-5", 4, 20, 0.20, False),  # tắt mặc định (DECISIONS Q-B1a)
    ("claude-sonnet-5-5", "anthropic", "claude-sonnet-5-5", 2, 10, 0.10, True),
    ("claude-haiku-5-5", "anthropic", "claude-haiku-5-5", 0.10, 0.50, 0.01, True),
    ("gpt-5.4", "openai", "gpt-5.4", 2.50, 15, 0.25, True),
    ("gpt-5.4-mini", "openai", "gpt-5.4-mini", 0.75, 4.50, 0.075, True),
]
PROFILES = [
    ("cheap", "claude-haiku-5-5", "gpt-5.4-mini", "Phân loại, trích xuất, nháp đầu"),
    ("writer_vi", "claude-sonnet-5-5", "gpt-5.4", "Bản cuối của bài sẽ xuất bản"),
    ("reasoning_mid", "claude-sonnet-5-5", "gpt-5.4", "Review của Director, lập kế hoạch"),
    ("reasoning_high", "claude-opus-5-5", "claude-sonnet-5-5", "Chiến lược tuần của AI CEO (chỉ khi ngân sách cho phép)"),
    ("fallback", "gpt-5.4-mini", "claude-haiku-5-5", "Dự phòng khi nhà cung cấp chính lỗi"),
    ("judge", "gpt-5.4-mini", "gpt-5.4", "LLM-judge khác họ với model viết (Claude)"),
]


def _q(s: str | None) -> str:
    return "NULL" if s is None else "'" + s.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
          id uuid PRIMARY KEY,
          email text NOT NULL UNIQUE,
          display_name text NOT NULL,
          role text NOT NULL CHECK (role IN ('owner','manager','reviewer','viewer')),
          password_hash text NOT NULL,
          totp_confirmed_at timestamptz,
          failed_logins int NOT NULL DEFAULT 0,
          locked_until timestamptz,
          status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          version int NOT NULL DEFAULT 1
        );
        CREATE TABLE user_sessions (
          id uuid PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          token_hash text NOT NULL UNIQUE,
          csrf_token text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          last_seen_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          reauth_until timestamptz,
          revoked_at timestamptz,
          user_agent text
        );
        CREATE INDEX idx_sessions_user ON user_sessions(user_id);

        -- Nhật ký kiểm toán: chỉ thêm; mỗi dòng nối hash dòng trước (SECURITY_PLAN §2.6, §9)
        CREATE TABLE audit_logs (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          at timestamptz NOT NULL,
          actor text NOT NULL,
          action text NOT NULL,
          resource text,
          data jsonb NOT NULL DEFAULT '{}'::jsonb,
          reason text,
          request_id text,
          prev_hash text NOT NULL,
          hash text NOT NULL UNIQUE
        );
        CREATE INDEX idx_audit_at ON audit_logs(at DESC);
        CREATE FUNCTION audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'audit_logs chỉ được thêm, không được sửa hay xóa'; END $$;
        CREATE TRIGGER audit_no_change BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION audit_immutable();
        CREATE FUNCTION audit_no_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF current_setting('aico.allow_truncate', true) IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION 'audit_logs không được TRUNCATE';
          END IF;
          RETURN NULL;
        END $$;
        CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit_logs FOR EACH STATEMENT EXECUTE FUNCTION audit_no_truncate();

        -- Mọi sự kiện mới phát qua NOTIFY để màn hình Diễn biến nhận ngay (SSE)
        CREATE FUNCTION audit_notify() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_notify('aico_events', json_build_object('source','audit','id',NEW.id)::text);
          RETURN NEW;
        END $$;
        CREATE TRIGGER audit_after_insert AFTER INSERT ON audit_logs FOR EACH ROW EXECUTE FUNCTION audit_notify();

        CREATE TABLE secrets (
          name text PRIMARY KEY,
          ciphertext bytea NOT NULL,
          wrapped_key bytea NOT NULL,
          key_version int NOT NULL DEFAULT 1,
          last4 text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          updated_by text
        );
        CREATE TABLE settings (
          key text PRIMARY KEY,
          value jsonb NOT NULL,
          updated_at timestamptz NOT NULL DEFAULT now(),
          updated_by text,
          version int NOT NULL DEFAULT 1
        );

        CREATE TABLE agents (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          agent_key text NOT NULL UNIQUE,
          display_name text NOT NULL,
          department text NOT NULL,
          kind text NOT NULL CHECK (kind IN ('executive','director','specialist')),
          reports_to text REFERENCES agents(agent_key),
          role_summary text NOT NULL,
          sort_order int NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          version int NOT NULL DEFAULT 1
        );
        CREATE TABLE agent_status (
          agent_id uuid PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
          state text NOT NULL DEFAULT 'active'
            CHECK (state IN ('active','paused','learning','waiting_approval','degraded','disabled')),
          reason text,
          changed_by text,
          circuit_failures int NOT NULL DEFAULT 0,
          updated_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE provider_registry (
          id text PRIMARY KEY,
          kind text NOT NULL CHECK (kind IN ('anthropic','openai_compat','google','ollama','vllm')),
          display_name text NOT NULL,
          base_url text NOT NULL,
          secret_name text,
          may_receive_pii boolean NOT NULL DEFAULT false,
          enabled boolean NOT NULL DEFAULT true,
          last_test_at timestamptz,
          last_test_ok boolean,
          last_test_detail text
        );
        CREATE TABLE model_registry (
          id text PRIMARY KEY,
          provider_id text NOT NULL REFERENCES provider_registry(id),
          model_name text NOT NULL,
          price_in_per_mtok numeric(10,4) NOT NULL,
          price_out_per_mtok numeric(10,4) NOT NULL,
          price_cache_read_per_mtok numeric(10,4),
          enabled boolean NOT NULL DEFAULT true,
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE model_profiles (
          profile text PRIMARY KEY,
          model_id text NOT NULL REFERENCES model_registry(id),
          fallback_model_id text REFERENCES model_registry(id),
          description text
        );
        CREATE TABLE model_usage (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          at timestamptz NOT NULL DEFAULT now(),
          model_id text NOT NULL,
          profile text,
          agent_key text,
          task_id uuid,
          purpose text,
          tokens_in int NOT NULL DEFAULT 0,
          tokens_out int NOT NULL DEFAULT 0,
          cost_usd numeric(14,8) NOT NULL DEFAULT 0,
          latency_ms int,
          ok boolean NOT NULL,
          error_code text,
          fallback_of text
        );
        CREATE INDEX idx_model_usage_at ON model_usage(at);

        CREATE TABLE telegram_chats (
          chat_id bigint PRIMARY KEY,
          title text NOT NULL,
          can_approve boolean NOT NULL DEFAULT false,
          receives text[] NOT NULL DEFAULT ARRAY['publish','report','alert','approval','test'],
          enabled boolean NOT NULL DEFAULT true,
          added_at timestamptz NOT NULL DEFAULT now(),
          added_by text
        );
        CREATE TABLE telegram_link_codes (
          code_hash text PRIMARY KEY,
          requested_by text NOT NULL,
          can_approve boolean NOT NULL DEFAULT false,
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          used_chat_id bigint
        );
        CREATE TABLE notifications (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          kind text NOT NULL CHECK (kind IN ('publish','report','alert','approval','test')),
          text text NOT NULL,
          urgent boolean NOT NULL DEFAULT false,
          dedupe_key text UNIQUE,
          status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','failed','no_recipient')),
          attempts int NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now(),
          sent_at timestamptz,
          last_error text
        );
        CREATE TABLE notification_deliveries (
          notification_id bigint NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
          chat_id bigint NOT NULL,
          sent_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (notification_id, chat_id)
        );
        CREATE FUNCTION notification_notify() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_notify('aico_events', json_build_object('source','notification','id',NEW.id)::text);
          RETURN NEW;
        END $$;
        CREATE TRIGGER notification_after_insert AFTER INSERT ON notifications FOR EACH ROW EXECUTE FUNCTION notification_notify();
        """
    )
    op.execute(
        """
        INSERT INTO provider_registry(id, kind, display_name, base_url, secret_name) VALUES
          ('anthropic', 'anthropic', 'Anthropic (Claude)', 'https://api.anthropic.com', 'provider.anthropic.api_key'),
          ('openai', 'openai_compat', 'OpenAI (ChatGPT)', 'https://api.openai.com/v1', 'provider.openai.api_key');
        """
    )
    for mid, prov, name, pin, pout, pcache, enabled in MODELS:
        op.execute(
            f"INSERT INTO model_registry(id, provider_id, model_name, price_in_per_mtok, price_out_per_mtok, price_cache_read_per_mtok, enabled) "  # noqa: S608
            f"VALUES ({_q(mid)}, {_q(prov)}, {_q(name)}, {pin}, {pout}, {pcache}, {str(enabled).lower()})"
        )
    for prof, mid, fb, desc in PROFILES:
        op.execute(f"INSERT INTO model_profiles VALUES ({_q(prof)}, {_q(mid)}, {_q(fb)}, {_q(desc)})")  # noqa: S608
    for i, (key, name, dept, kind, boss, summary) in enumerate(AGENTS):
        op.execute(
            "INSERT INTO agents(agent_key, display_name, department, kind, reports_to, role_summary, sort_order) "  # noqa: S608
            f"VALUES ({_q(key)}, {_q(name)}, {_q(dept)}, {_q(kind)}, {_q(boss)}, {_q(summary)}, {i})"
        )
    op.execute("INSERT INTO agent_status(agent_id) SELECT id FROM agents")


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS notification_deliveries, notifications, telegram_link_codes, telegram_chats,
          model_usage, model_profiles, model_registry, provider_registry,
          agent_status, agents, settings, secrets, user_sessions, users CASCADE;
        DROP TRIGGER IF EXISTS audit_no_truncate ON audit_logs;
        SET LOCAL aico.allow_truncate = 'on';
        DROP TABLE IF EXISTS audit_logs CASCADE;
        DROP FUNCTION IF EXISTS audit_immutable(), audit_no_truncate(), audit_notify(), notification_notify();
        """
    )
