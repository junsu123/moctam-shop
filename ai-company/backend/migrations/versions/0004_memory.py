"""Memory System (BRAIN_SPEC §3, §5, §6; DATABASE_SCHEMA §4): trí nhớ 4 loại có phạm vi, tìm theo từ khóa (bỏ dấu)
và theo vector, Row-Level Security, nhật ký truy hồi.

RLS chỉ có hiệu lực với vai trò không phải superuser/chủ bảng. Memory Service chạy truy vấn của agent dưới
`SET LOCAL ROLE aico_agent` (đọc theo `app.scopes`, chỉ ghi episodic/working vào vùng của chính mình);
Learning Engine/Owner ghi kiến thức dưới `aico_learning`.

Revision ID: 0004_memory
Revises: 0003_agent_core
"""

from alembic import op

revision = "0004_memory"
down_revision = "0003_agent_core"
branch_labels = None
depends_on = None

EMBED_MODEL = "openai-te3s-512"


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aico_agent') THEN CREATE ROLE aico_agent NOLOGIN; END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aico_learning') THEN CREATE ROLE aico_learning NOLOGIN; END IF;
        END $$;

        -- Model embedding: lấy giá từ model_registry; số chiều cố định theo model (HNSW cần số chiều cố định)
        INSERT INTO model_registry(id, provider_id, model_name, price_in_per_mtok, price_out_per_mtok, enabled)
        VALUES ('text-embedding-3-small', 'openai', 'text-embedding-3-small', 0.02, 0, true) ON CONFLICT (id) DO NOTHING;
        CREATE TABLE embedding_models (
          id text PRIMARY KEY,
          model_id text NOT NULL REFERENCES model_registry(id),
          dims int NOT NULL CHECK (dims BETWEEN 64 AND 2000),
          active boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX embedding_models_one_active ON embedding_models(active) WHERE active;
        INSERT INTO embedding_models(id, model_id, dims, active) VALUES ('openai-te3s-512', 'text-embedding-3-small', 512, true);

        CREATE TABLE agent_memories (
          id uuid PRIMARY KEY,
          owner_scope text NOT NULL CHECK (owner_scope ~ '^(agent:[a-z0-9_]+|dept:[a-z0-9_]+|company|owner_only)$'),
          type text NOT NULL CHECK (type IN ('working','episodic','semantic','procedural')),
          title text NOT NULL,
          content text NOT NULL,
          search_text text NOT NULL,                         -- bỏ dấu + mở rộng viết tắt (textnorm)
          tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', search_text)) STORED,
          metadata jsonb NOT NULL DEFAULT '{}',
          source_ref text,
          source_trust text NOT NULL CHECK (source_trust IN ('owner','internal','verified_external','unverified_external')),
          confidence numeric(3,2) NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
          verification_status text NOT NULL DEFAULT 'active'
            CHECK (verification_status IN ('candidate','verified','active','deprecated','retired')),
          valid_from timestamptz NOT NULL DEFAULT now(),
          valid_to timestamptz,
          usefulness int NOT NULL DEFAULT 0,
          content_hash text NOT NULL,
          supersedes_id uuid REFERENCES agent_memories(id),
          created_by_principal text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          version int NOT NULL DEFAULT 1,
          UNIQUE (owner_scope, content_hash)
        );
        CREATE INDEX agent_memories_tsv ON agent_memories USING gin (tsv);
        CREATE INDEX agent_memories_trgm ON agent_memories USING gin (search_text gin_trgm_ops);
        CREATE INDEX agent_memories_scope ON agent_memories(owner_scope, type, verification_status);
        CREATE INDEX agent_memories_meta ON agent_memories USING gin (metadata jsonb_path_ops);
        CREATE INDEX agent_memories_created ON agent_memories(created_at DESC);

        CREATE TABLE episodic_memories (
          memory_id uuid PRIMARY KEY REFERENCES agent_memories(id) ON DELETE CASCADE,
          task_id text,
          task_type text,
          outcome text CHECK (outcome IN ('success','failure','partial')),
          cost_usd numeric(14,8),
          occurred_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE semantic_memories (
          memory_id uuid PRIMARY KEY REFERENCES agent_memories(id) ON DELETE CASCADE,
          claim text NOT NULL,
          evidence jsonb NOT NULL DEFAULT '[]',
          evidence_level text CHECK (evidence_level IN ('L0','L1','L2','L3')),
          topic text
        );
        CREATE TABLE procedural_memories (
          memory_id uuid PRIMARY KEY REFERENCES agent_memories(id) ON DELETE CASCADE,
          procedure_key text NOT NULL,
          version text NOT NULL,
          steps jsonb NOT NULL DEFAULT '[]',
          checklist jsonb NOT NULL DEFAULT '[]',
          applies_to_task_types text[] NOT NULL DEFAULT '{}',
          UNIQUE (procedure_key, version)
        );

        -- Vector theo model: cột `vector` không cố định số chiều; mỗi model một chỉ mục HNSW riêng (biểu thức ép số chiều)
        CREATE TABLE memory_embeddings (
          memory_id uuid NOT NULL REFERENCES agent_memories(id) ON DELETE CASCADE,
          model_id text NOT NULL REFERENCES embedding_models(id),
          embedding vector NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (memory_id, model_id)
        );
        """
    )
    op.execute(
        f"CREATE INDEX memory_embeddings_hnsw_{EMBED_MODEL.replace('-', '_')} ON memory_embeddings "
        f"USING hnsw ((embedding::vector(512)) vector_cosine_ops) WHERE model_id = '{EMBED_MODEL}'"
    )
    op.execute(
        """
        CREATE TABLE memory_access_log (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          at timestamptz NOT NULL DEFAULT now(),
          memory_id uuid NOT NULL REFERENCES agent_memories(id) ON DELETE CASCADE,
          principal text NOT NULL,
          task_id text,
          purpose text NOT NULL,
          rank int,
          score real,
          used_in_output boolean NOT NULL DEFAULT false
        );
        CREATE INDEX memory_access_log_memory ON memory_access_log(memory_id, at DESC);
        CREATE INDEX memory_access_log_principal ON memory_access_log(principal, at DESC);

        -- Kiến thức chung (company), xem như một bảng riêng
        CREATE VIEW shared_knowledge AS
          SELECT id AS memory_id, type, title, content, metadata ->> 'category' AS category, created_by_principal AS approved_by,
                 valid_from AS effective_from, valid_to, verification_status
          FROM agent_memories WHERE owner_scope = 'company';

        -- ---------------- Row-Level Security ----------------
        ALTER TABLE agent_memories ENABLE ROW LEVEL SECURITY;
        ALTER TABLE episodic_memories ENABLE ROW LEVEL SECURITY;
        ALTER TABLE semantic_memories ENABLE ROW LEVEL SECURITY;
        ALTER TABLE procedural_memories ENABLE ROW LEVEL SECURITY;
        ALTER TABLE memory_embeddings ENABLE ROW LEVEL SECURITY;
        ALTER TABLE memory_access_log ENABLE ROW LEVEL SECURITY;

        CREATE FUNCTION aico_scopes() RETURNS text[] LANGUAGE sql STABLE AS
          $$ SELECT string_to_array(coalesce(current_setting('app.scopes', true), ''), ',') $$;

        -- Đọc: chỉ các phạm vi của phiên (vd agent:seo_agent, dept:marketing, company)
        CREATE POLICY mem_read ON agent_memories FOR SELECT TO aico_agent, aico_learning USING (owner_scope = ANY (aico_scopes()));
        -- Agent chỉ ghi episodic/working vào vùng của chính mình
        CREATE POLICY mem_agent_write ON agent_memories FOR INSERT TO aico_agent
          WITH CHECK (type IN ('episodic','working') AND owner_scope = current_setting('app.principal', true));
        -- Learning Engine / Owner ghi kiến thức (semantic, procedural) vào các phạm vi được giao
        CREATE POLICY mem_learning_write ON agent_memories FOR INSERT TO aico_learning WITH CHECK (owner_scope = ANY (aico_scopes()));
        CREATE POLICY mem_learning_update ON agent_memories FOR UPDATE TO aico_learning
          USING (owner_scope = ANY (aico_scopes())) WITH CHECK (owner_scope = ANY (aico_scopes()));

        CREATE POLICY sub_read_e ON episodic_memories FOR SELECT TO aico_agent, aico_learning
          USING (EXISTS (SELECT 1 FROM agent_memories m WHERE m.id = memory_id));
        CREATE POLICY sub_write_e ON episodic_memories FOR INSERT TO aico_agent, aico_learning
          WITH CHECK (EXISTS (SELECT 1 FROM agent_memories m WHERE m.id = memory_id));
        CREATE POLICY sub_read_s ON semantic_memories FOR SELECT TO aico_agent, aico_learning
          USING (EXISTS (SELECT 1 FROM agent_memories m WHERE m.id = memory_id));
        CREATE POLICY sub_write_s ON semantic_memories FOR INSERT TO aico_learning
          WITH CHECK (EXISTS (SELECT 1 FROM agent_memories m WHERE m.id = memory_id));
        CREATE POLICY sub_read_p ON procedural_memories FOR SELECT TO aico_agent, aico_learning
          USING (EXISTS (SELECT 1 FROM agent_memories m WHERE m.id = memory_id));
        CREATE POLICY sub_write_p ON procedural_memories FOR INSERT TO aico_learning
          WITH CHECK (EXISTS (SELECT 1 FROM agent_memories m WHERE m.id = memory_id));
        CREATE POLICY emb_read ON memory_embeddings FOR SELECT TO aico_agent, aico_learning
          USING (EXISTS (SELECT 1 FROM agent_memories m WHERE m.id = memory_id));
        CREATE POLICY log_write ON memory_access_log FOR INSERT TO aico_agent, aico_learning
          WITH CHECK (principal = current_setting('app.principal', true));

        GRANT SELECT, INSERT ON agent_memories, episodic_memories, memory_access_log TO aico_agent;
        GRANT SELECT ON semantic_memories, procedural_memories, memory_embeddings, embedding_models, agents TO aico_agent;
        GRANT SELECT, INSERT, UPDATE ON agent_memories TO aico_learning;
        GRANT SELECT, INSERT ON episodic_memories, semantic_memories, procedural_memories, memory_access_log TO aico_learning;
        GRANT SELECT ON memory_embeddings, embedding_models, agents TO aico_learning;
        GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO aico_agent, aico_learning;
        GRANT EXECUTE ON FUNCTION aico_scopes() TO aico_agent, aico_learning;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP VIEW IF EXISTS shared_knowledge;
        DROP TABLE IF EXISTS memory_access_log, memory_embeddings, procedural_memories, semantic_memories, episodic_memories,
          agent_memories, embedding_models CASCADE;
        DROP FUNCTION IF EXISTS aico_scopes();
        DELETE FROM model_registry WHERE id = 'text-embedding-3-small';
        -- Vai trò là của cả cụm Postgres (dùng chung cho các CSDL khác), nên chỉ thu quyền, không xóa vai trò
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aico_agent, aico_learning;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM aico_agent, aico_learning;
        """
    )
