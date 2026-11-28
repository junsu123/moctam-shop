# DATABASE_SCHEMA: lược đồ PostgreSQL + pgvector

> Trạng thái: v0.2 (26/11/2026, theo `DECISIONS.md`), chờ Owner duyệt. Có đủ mọi bảng SRS §11 yêu cầu. Bảng **bổ sung** (không có trong SRS) được đánh dấu ➕ kèm lý do.

## 1. Quy ước chung

- **Khóa chính** `id uuid`, sinh theo **UUIDv7** để sắp được theo thời gian và giữ chỉ mục gọn. Postgres < 18 sinh ở tầng ứng dụng.
- **Cột chung** (SRS): `created_at timestamptz`, `updated_at timestamptz`, `status`, `version int`. Bảng có dữ liệu của tổ chức có thêm `org_id uuid`: hiện chỉ một xưởng, nhưng sẵn sàng tách dữ liệu sau này (SRS "tenant scope khi cần").
- **Khóa lạc quan:** `UPDATE … WHERE version = :v`, tránh hai worker ghi đè nhau.
- **Thời gian** lưu UTC, hiển thị Asia/Ho_Chi_Minh (giống website).
- **Tiền** dùng `bigint` VND, hoặc `numeric(12,6)` USD cho chi phí LLM.
- **JSON** dùng `jsonb`, kèm `CHECK (jsonb_typeof(...) = 'object')` ở các cột cấu trúc.
- **Migration** dùng Alembic. Mỗi migration có cả up và down, chạy trong CI trên Postgres thật (testcontainers).
- **Vai trò CSDL:**
  - `app_api`: đọc/ghi qua dịch vụ;
  - `app_worker`;
  - `app_readonly_analytics`: chỉ đọc các view đã ẩn danh;
  - `app_audit_writer`: chỉ INSERT vào audit.

  **Không có vai trò nào cho agent**: agent không bao giờ cầm kết nối CSDL (SRS §15).

## 2. Sơ đồ quan hệ chính

```mermaid
erDiagram
  agents ||--|| agent_profiles : ""
  agents ||--o{ agent_brains : "phiên bản đang chạy/lịch sử"
  agent_brains ||--o{ agent_versions : "changelog"
  agents ||--o{ agent_permissions : ""
  agents ||--o{ agent_skills : ""
  agents ||--|| agent_status : ""
  agents ||--o{ agent_memories : "owner_scope"
  agent_memories ||--o{ memory_embeddings : ""
  agent_memories ||--o| episodic_memories : "chi tiết"
  agent_memories ||--o| semantic_memories : "chi tiết"
  agent_memories ||--o| procedural_memories : "chi tiết"
  tasks ||--o{ task_assignments : ""
  tasks ||--o{ task_dependencies : ""
  tasks ||--o{ task_outputs : ""
  tasks ||--o{ task_reviews : ""
  tasks ||--o{ task_logs : ""
  tasks ||--o{ experience_records : ""
  experience_records ||--o{ evaluation_results : ""
  research_sources ||--o{ knowledge_candidates : ""
  knowledge_candidates ||--o{ knowledge_approvals : ""
  agent_conversations ||--o{ agent_messages : ""
  model_registry ||--o{ model_usage : ""
  tool_registry ||--o{ tool_invocations : ""
```

## 3. Quản lý agent

| Bảng | Cột chính | Ràng buộc / chỉ mục |
|---|---|---|
| `agents` | `id`, `agent_key` (vd `seo_agent`), `department`, `reports_to_agent_id`, `kind` (`executive/director/specialist`), `status` | `UNIQUE(org_id, agent_key)` |
| `agent_profiles` | `agent_id`, `display_name`, `avatar_url`, `role_summary`, `personality jsonb` (tham số BRAIN_SPEC §2.2) | 1–1 với `agents` |
| `agent_brains` | `id`, `agent_key`, `brain_version`, `prompt_version`, `knowledge_version`, `skill_version`, `bundle jsonb` (đã chuẩn hóa), `bundle_hash`, `core_rules_hash`, `state` (`draft/shadow/active/retired/rejected`), `created_by`, `activated_at` | Tối đa 1 bản `active` cho mỗi agent (unique index một phần); `UNIQUE(agent_key, bundle_hash)`. *Đã có từ Sprint 2* |
| ➕ `brain_core_pins` | `agent_key`, `core_rules_hash`, `approved_by`, `approved_at`, `approval_id` | Hash quy tắc cốt lõi Owner đã chấp nhận; runtime từ chối nạp bundle có hash không nằm ở đây (BRAIN_SPEC §9). *Sprint 2* |
| `agent_versions` | `id`, `agent_key`, `event` (`bootstrap/proposed/activated/rolled_back/rejected`), `component`, `from_version`, `to_version`, `brain_id`, `previous_brain_id`, `diff`, `sources jsonb`, `proposed_by`, `approved_by`, `test_results jsonb` | Chỉ thêm, không sửa: trigger chặn UPDATE/DELETE (SRS §4.5). *Sprint 2* |
| `agent_permissions` | `agent_key`, `tool_id`, `action`, `autonomy_level 1..4`, `limits jsonb` (vd `max_usd`, `per_day`), `requires_approval bool`, `granted_by`, `brain_id`, `expires_at` | Khóa `(agent_key, tool_id, action)`. Chỉ ghi khi một bộ não được kích hoạt (lấy từ `tools/tool_permissions.yaml`); agent không có công cụ nào ghi vào đây. *Sprint 2* |
| `agent_skills` | `agent_id`, `skill_key`, `version`, `procedural_memory_id`, `enabled` | |
| `agent_status` | `agent_id`, `state`, `reason`, `circuit_failures`, `paused_by`, `updated_at` | |
| ➕ `agent_budgets` | `agent_id`, `period` (`day/month`), `usd_limit`, `usd_used`, `token_used` | Ngân sách theo agent (ARCH §8) |

## 4. Trí nhớ

| Bảng | Cột chính | Ghi chú |
|---|---|---|
| `agent_memories` | `id`, `owner_scope` (`agent:<key>` / `dept:<key>` / `company` / `owner_only`), `type`, `title`, `content`, `search_text` (bỏ dấu), `tsv tsvector` (tạo từ `search_text`, cấu hình `simple`), `metadata jsonb`, `source_ref`, `source_trust`, `confidence numeric(3,2)`, `verification_status`, `valid_from`, `valid_to`, `usefulness`, `content_hash`, `supersedes_id`, `created_by_principal` | Bảng gốc cho mọi loại trí nhớ. Chỉ mục GIN trên `tsv`, trigram trên `search_text`, B-tree `(owner_scope, type, verification_status)`, GIN trên `metadata` |
| ➕ `embedding_models` | `id` (vd `openai-te3s-512`), `model_id` → `model_registry`, `dims`, `active` (chỉ một model bật) | Model embedding đang dùng. Đổi model: bật model mới, nhúng lại, xóa vector cũ khi đã nhúng đủ (IT-VEC-02) |
| `memory_embeddings` | `memory_id`, `model_id` → `embedding_models`, `embedding vector` (không cố định số chiều), PK `(memory_id, model_id)` | **Đã đổi (Sprint 3):** một bảng, mỗi model một **chỉ mục HNSW một phần** trên biểu thức `(embedding::vector(N)) vector_cosine_ops WHERE model_id = '…'`, thay vì mỗi model một bảng con. Truy vấn ghi thẳng `model_id` để Postgres chọn đúng chỉ mục |
| `episodic_memories` | `memory_id`, `task_id`, `task_type`, `outcome` (`success/failure/partial`), `cost_usd`, `occurred_at` | |
| `semantic_memories` | `memory_id`, `claim`, `evidence jsonb` (danh sách nguồn + vị trí), `evidence_level` (`L1..L3`), `topic` | |
| `procedural_memories` | `memory_id`, `procedure_key`, `version`, `steps jsonb`, `checklist jsonb`, `applies_to_task_types text[]` | `UNIQUE(procedure_key, version)` |
| `shared_knowledge` | `memory_id`, `category` (`product/brand/goal/strategy/policy`), `approved_by`, `effective_from` | View trên `agent_memories` với `owner_scope='company'` cộng metadata duyệt |
| `experience_records` | `id`, `agent_id`, `task_id`, `brain_id`, `task_type`, `inputs_digest`, `output_ref`, `human_verdict`, `business_metrics jsonb`, `observed_window`, `score`, `score_breakdown jsonb` | Nguồn của bài học. Điểm do Evaluation Service ghi |
| ➕ `memory_access_log` | `memory_id`, `principal`, `task_id`, `purpose`, `rank`, `score`, `used_in_output bool`, `at` | Audit truy hồi + tính `usefulness` (BRAIN_SPEC §5.7). Một câu `INSERT` cho cả lượt truy hồi. Phân vùng theo tháng: khi bảng vượt vài triệu dòng (chưa cần ở Sprint 3) |

### 4.1. Row-Level Security (ví dụ)

```sql
ALTER TABLE agent_memories ENABLE ROW LEVEL SECURITY;
-- Phiên làm việc của Memory Service đặt: SET LOCAL app.principal = 'agent:seo_agent'; SET LOCAL app.scopes = '{agent:seo_agent,dept:marketing,company}';
CREATE POLICY mem_read ON agent_memories FOR SELECT
  USING (owner_scope = ANY (string_to_array(current_setting('app.scopes', true), ',')));
CREATE POLICY mem_write_episodic ON agent_memories FOR INSERT
  WITH CHECK (type IN ('episodic','working') AND owner_scope = current_setting('app.principal', true));
-- semantic/procedural/company chỉ ghi được bằng vai trò learning_engine (policy riêng).
```

**Cách chạy thật (Sprint 3, `0004_memory`).** Hai vai trò Postgres không đăng nhập được: `aico_agent` (đọc trong phạm vi, ghi episodic/working của chính mình, ghi `memory_access_log`) và `aico_learning` (ghi semantic/procedural vào phạm vi được giao). Mã gọi `store.acting_as(conn, role, principal, scopes)`:
- trong giao dịch đang mở: `SET LOCAL ROLE …` và `set_config('app.scopes' | 'app.principal', …, true)`;
- kiểm `current_user` đúng vai trò, sai thì dừng với `RLS_NOT_ACTIVE` (ví dụ lỡ chạy ngoài giao dịch, nơi `SET LOCAL` không có tác dụng);
- truy vấn vẫn lọc phạm vi ở tầng ứng dụng (hai lớp).

`memory_embeddings` có policy đọc `EXISTS (agent_memories …)` nên vector của mục ngoài phạm vi cũng không đọc được. Downgrade thu hồi quyền nhưng không xóa hai vai trò (vai trò dùng chung cả cụm Postgres).

## 5. Học tập

| Bảng | Cột chính |
|---|---|
| `learning_sessions` | `id`, `agent_id`, `goal`, `trigger` (`schedule/failure/owner`), `budget_usd`, `status`, `summary` |
| `research_sources` | `id`, `url_or_file`, `fetched_at`, `content_hash`, `object_key` (bản gốc), `robots_ok`, `tos_note`, `trust` |
| `knowledge_candidates` | `id`, `source_id`, `proposed_by_principal`, `target_scope`, `claim`, `evidence jsonb`, `dup_of_memory_id`, `scores jsonb` (nguồn, trùng, liên quan, chính xác), `risk` (`low/medium/high`), `status` |
| `knowledge_approvals` | `candidate_id`, `decision`, `decided_by` (user hoặc `auto:validator@v`), `reason`, `resulting_memory_id` |
| `evaluation_results` | `id`, `experience_id`, `evaluator` (`deterministic/human/business/llm_judge`), `rubric_key`, `rubric_version`, `score`, `details jsonb`, `evaluator_model_id` |
| `improvement_proposals` | `id`, `agent_id`, `component`, `proposal`, `evidence jsonb`, `shadow_results jsonb`, `status`, `decided_by` |

## 6. Nhiệm vụ

| Bảng | Cột chính | Ghi chú |
|---|---|---|
| `tasks` | `id`, `parent_id`, `root_id`, `depth`, `title`, `description`, `task_type`, `created_by_principal`, `assigned_agent_id`, `priority`, `deadline`, `input_data jsonb`, `output_data jsonb`, `success_criteria jsonb`, `status` (9 trạng thái SRS), `requires_approval`, `autonomy_max`, `budget_usd`, `spent_usd`, `brain_id` (ghim), `state jsonb` (checkpoint của working memory), `attempt`, `max_attempts`, `lease_owner`, `lease_until`, `idempotency_key`, `timeout_at` | `UNIQUE(idempotency_key)`; chỉ mục `(status, lease_until)` để quét việc bị bỏ dở |
| `task_assignments` | `task_id`, `agent_id`, `assigned_by`, `assigned_at`, `unassigned_at` | Lịch sử giao lại |
| `task_dependencies` | `task_id`, `depends_on_task_id` | Kiểm tra không có chu trình khi thêm |
| `task_messages` | `task_id`, `message_id` | Liên kết task ↔ message |
| `task_outputs` | `task_id`, `kind`, `content jsonb`, `asset_id`, `version` | |
| `task_reviews` | `task_id`, `reviewer_principal`, `verdict` (`approve/request_changes/reject`), `notes`, `rubric_scores jsonb` | |
| `task_logs` | `task_id`, `step_no`, `event`, `data jsonb`, `at` | Phân vùng theo tháng |
| ➕ `approvals` | `id`, `subject_type`, `subject_id`, `action`, `title`, `summary`, `payload jsonb`, `payload_digest`, `risk`, `requested_by`, `status`, `decided_by`, `decided_at`, `decision_note`, `expires_at` | Hàng chờ phê duyệt chung cho task, công cụ, kiến thức, quyền (SRS §13). Một yêu cầu đang chờ cho mỗi (subject, digest). *Sprint 2* |
| ➕ `schedules` | `id`, `name`, `agent_key`, `cron`, `timezone`, `task_template jsonb`, `enabled`, `catch_up_hours`, `last_run_at`, `next_run_at` | Lịch cấu hình được (SRS §14). Lỡ trong `catch_up_hours` (24 giờ) thì chạy bù **một** lần |

**Đã làm ở Sprint 4a (`0005_tasks`), khác bản thiết kế ở các điểm sau:**
- `tasks` dùng `assigned_agent` = `agent_key` và `created_by` (principal `user:…`/`agent:…`/`system:…`), giống các bảng đã có; thêm `reviewer`, `requires_review`, `wait_kind` (`approval`/`review`/`children`: đồ thị đang dừng chờ gì), `not_before` (giờ thử lại), `timeout_s`, `result_summary`, `error_code`, `version` (khóa phiên bản). Không có cột `state jsonb`: trạng thái làm việc nằm trong checkpoint LangGraph.
- Chưa tạo `task_assignments`, `task_messages`, `task_outputs`: lịch sử giao lại nằm trong `task_logs`; message đã có `task_id`; bản nháp chờ review ghi vào `output_data`. Tạo khi Sprint 5–8 cần.
- `task_dependencies.depends_on` có thể trỏ tới task **chưa tồn tại** (task con do Message Bus tạo sau, id định trước). Phụ thuộc chưa tồn tại = chưa xong.
- `task_logs` phát `NOTIFY aico_events` (màn hình Diễn biến). Chưa phân vùng theo tháng.

**Checkpoint LangGraph (v0.2, ADR-05):** bảng do thư viện quản lý (checkpoint, các lần ghi đang chờ) nằm trong schema riêng `langgraph` của cùng CSDL. `thread_id` = `tasks.id`. Bảng `tasks` thêm cột `graph_key` (đồ thị nào đang chạy) và `graph_node` (nút gần nhất, để hiển thị). Checkpoint của task đã đóng được dọn sau 30 ngày.

Các chuyển trạng thái hợp lệ được kiểm tra trong mã **và** bằng trigger:

```
CREATED→PENDING→ASSIGNED→IN_PROGRESS→{WAITING_REVIEW|WAITING_APPROVAL|COMPLETED|FAILED}
IN_PROGRESS→PENDING (chờ task con / phụ thuộc; thêm ở Sprint 4a)
ASSIGNED→PENDING (thêm phụ thuộc sau khi đã xếp hàng)
WAITING_REVIEW→{IN_PROGRESS (làm lại)|WAITING_APPROVAL|COMPLETED}
WAITING_APPROVAL→{IN_PROGRESS|COMPLETED|CANCELLED}
*→CANCELLED (trừ COMPLETED)
FAILED→PENDING (retry nếu còn lượt)
```

Nghĩa của trạng thái trong mã: PENDING = đang chờ điều kiện (phụ thuộc, giờ thử lại); ASSIGNED = sẵn sàng, xếp hàng chờ worker; IN_PROGRESS có lease = worker đang chạy, IN_PROGRESS **không** lease = vừa được đánh thức sau duyệt/review hoặc worker cũ chết, worker kế tiếp nhận và chạy tiếp từ checkpoint.

## 7. Giao tiếp

| Bảng | Cột chính |
|---|---|
| `agent_messages` | Đúng schema SRS §6.1 (`message_id`, `sender_agent`, `receiver_agent`, `message_type`, `task_id`, `priority`, `payload`, `created_at`, `status`) cộng `conversation_id`, `correlation_id`, `idempotency_key`, `trust`, `expires_at`, `delivered_at`, `attempts` |
| `agent_conversations` | `id`, `kind` (`owner_chat/agent_chat/company_chat`), `participants`, `title` |
| `collaboration_sessions` | `id`, `root_task_id`, `topic`, `options jsonb`, `evidence jsonb`, `decision`, `decided_by` |

`agent_messages` đồng thời là **outbox**: ghi trong cùng giao dịch với thay đổi task, rồi dispatcher phát đi (P4).

**Đã làm ở Sprint 4a:** `agent_messages` (`sender`/`receiver` là principal: `agent:<key>`, `owner`, `learning_engine`; `status` `queued/delivered/failed/expired`; `last_error`, `not_before` cho thử lại giãn cách) và ➕ `knowledge_candidates` (`proposed_by`, `target_scope`, `title`, `claim`, `evidence`, `trust`, `source_message_id` duy nhất, `status` `pending/accepted/rejected/duplicate`): hộp ứng viên của `knowledge_sharing`, Sprint 5 thêm luồng thẩm định. `agent_conversations`, `collaboration_sessions` làm ở Sprint 4c.

## 8. Nghiệp vụ

Nguyên tắc: dữ liệu bán hàng là **bản sao chỉ đọc** từ website (ADR-14). Nền tảng không tự tạo đơn hay sửa giá.

| Bảng | Nguồn | Ghi chú quyền |
|---|---|---|
| `products` | `catalog` của website (*Sprint 4b*: chưa sao vào CSDL; `app/integrations/website.py` đọc `catalog` qua API, đệm 10 phút, Content Gate đọc bản mới ngay trước giờ đăng) | Theo mẫu SRS §10 (`product_id`, `name`, `category`, `selling_price`, `stock_quantity`, `description`, `ingredients`, `images`, `compliance_documents`, `status`) cộng `info_version` |
| ➕ `product_costs` | Nhập tay hoặc `finance:read` | Tách riêng để **phân quyền giá vốn** (SRS §10). Chỉ `owner_only` và Data Analyst (`finance.read`) đọc được |
| `customers` | `customer_key` (mã băm) + phân khúc + đồng ý tiếp thị | **Không có tên/SĐT/địa chỉ** theo mặc định (P6, Owner đồng ý ở Q-L1) |
| `orders` | `events`/`snapshot` | Dạng tối thiểu như dịch vụ hiện tại |
| `campaigns` | Ads Agent (nháp) + API quảng cáo | `status`: `draft/proposed/approved/live/ended`; chỉ người chuyển sang `live` |
| `leads` | Sales Intelligence | Mỗi dòng có `source_url`, `collected_at`, `contact_allowed bool`; tự xóa nếu không dùng sau 180 ngày |
| `affiliates` | Affiliate Agent | Tương tự `leads` + `commission_policy`, mã giới thiệu |
| `content_assets` | Content/Creative | `object_key`, `kind`, `ai_generated bool`, `brand_check jsonb`, `published_url`, `metrics jsonb` |
| `marketing_reports` | Data Analyst, CEO | `period`, `body`, `data_refs` |
| ➕ `metric_snapshots` | GA4, GSC, Ads, website | `source`, `entity_type`, `entity_id`, `date`, `metrics jsonb`: chuỗi thời gian để đánh giá kết quả |

## 9. Hạ tầng

| Bảng | Cột chính |
|---|---|
| `model_registry` | `id`, `profile` (`reasoning_high`…), `provider_id`, `model_name`, `context_window`, `price_in_per_mtok`, `price_out_per_mtok`, `capabilities jsonb`, `fallback_model_id`, `enabled` |
| ➕ `provider_registry` | `id`, `kind` (`anthropic/openai_compat/google/ollama/vllm`), `base_url`, `secret_ref`, `rate_limits jsonb`, `data_policy` (`may_receive_pii false` mặc định) |
| `model_usage` | `id`, `model_id`, `agent_id`, `task_id`, `purpose`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`, `ok`, `error_code`, `at` (phân vùng theo tháng) |
| `tool_registry` | `id` (vd `site`), `description`, `actions jsonb` (mỗi hành động: cấp tối thiểu, tác động, thẻ chính sách), `input_schema`, `output_schema` (theo hành động), `side_effects` (`none/internal/external`), `default_timeout_s`, `retry_policy jsonb`, `risk`, `available` | Bản chiếu của danh mục công cụ trong mã (`app/tools/catalog.py`). *Sprint 2* |
| ➕ `tool_invocations` | `id`, `tool_id`, `action`, `agent_key`, `task_id`, `idempotency_key` (UNIQUE), `input_digest`, `status` (`running/succeeded/failed/denied/waiting_approval`), `output`, `error_code`, `attempts`, `duration_ms`, `approval_id`, `at` | *Sprint 2* |
| ➕ `policy_decisions` | `id`, `at`, `agent_key`, `tool_id`, `action`, `decision` (`allow/require_approval/deny`), `rule`, `reason`, `context jsonb` | Trả lời "vì sao agent bị chặn". *Sprint 2* |
| `integration_configs` | `id`, `kind`, `display_name`, `config jsonb` (không có secret), `secret_ref`, `oauth_expires_at`, `status` (`connected/expired/error/not_configured`), `last_sync_at`, `last_error` |
| ➕ `secrets` | `id`, `name`, `ciphertext`, `key_version`, `rotated_at` | Mã hóa phong bì (SECURITY_PLAN §5) |
| `system_logs` | Log ứng dụng có cấu trúc (mức ≥ WARN), đã che dữ liệu nhạy cảm |
| `audit_logs` | `id`, `at`, `actor` (user/agent/system), `action`, `resource`, `before_digest`, `after_digest`, `reason`, `request_id`, `prev_hash`, `hash` | **Chỉ thêm**; chuỗi băm phát hiện sửa/xóa; không vai trò nào có UPDATE/DELETE (SRS §15) |
| ➕ `users`, `roles`, `user_sessions` | Người dùng Owner/nhân viên, RBAC, phiên |
| ➕ `publish_queue` (*Sprint 4b*, gộp `publications` + `publication_queue` của bản thiết kế) | `id`, `task_id`, `agent_key`, `kind` (`faq/blog`), `title`, `body`, `meta_description`, `keywords`, `product_id`, `category_id`, `source_refs jsonb`, `status` (`scheduled/publishing/published/blocked/retracted/cancelled/failed`), `slot_at`, `attempts`, `last_error`, `gate jsonb` (kết quả Content Gate), `approval_id`, `invocation_key` (UNIQUE, = khóa chống trùng của lời gọi `site.publish`), `content_id`, `url`, `published_at`, `retracted_at`, `retracted_by`, `retract_reason` | Một dòng đi suốt đời bài: chờ giờ → lên website / bị chặn khi kiểm lại trước giờ đăng → có thể bị gỡ. Hạn mức ngày đếm ở website (lớp 5) và lịch đăng ở đây (lớp 4)
| ➕ `telegram_chats` (v0.2) | `chat_id`, `title`, `user_id`, `can_approve bool`, `receives jsonb` (bài mới/báo cáo/cảnh báo/duyệt), `quiet_hours`, `enabled`, `added_at`, `added_by` | Danh sách chat được phép; Owner quản lý trong *Cài đặt → Telegram* (ADR-15) |
| ➕ `telegram_link_codes` (v0.2) | `code_hash`, `requested_by`, `can_approve`, `expires_at`, `used_at`, `used_chat_id` | Mã 6 số để kết nối chat, hiệu lực 10 phút, dùng một lần |
| ~~`publish_schedule`~~ | Không tạo bảng. Lịch đăng là cài đặt `publishing` trong `settings` (giai đoạn, giờ đăng từng giai đoạn, khung 7:00–21:30, cách nhau tối thiểu, ngày nghỉ, tạm dừng); chỉ Owner sửa, mọi lần sửa ghi audit | *Sprint 4b*: một bản đang dùng là đủ; lịch sử nằm trong audit. Giờ vàng học được (sau 4 tuần) ghi đè cài đặt này |
| ➕ `notifications` (v0.2) | `id`, `channel` (`telegram/dashboard`), `chat_id`, `kind` (`publish/report/alert/approval`), `subject_type`, `subject_id`, `text_digest`, `status`, `sent_at`, `attempts` | Outbox thông báo: máy mất mạng thì gửi lại sau. *Sprint 4b*: thêm `buttons jsonb` (nút đính kèm, chỉ gửi cho chat có quyền duyệt) |
| ➕ `telegram_buttons` (*Sprint 4b*, tên trong bản thiết kế: `telegram_actions`) | `token` (PK, ngẫu nhiên), `action` (`approve/reject/unpublish/feedback`), `subject_type`, `subject_id`, `digest` (digest nội dung), `chat_id`, `expires_at` (72 giờ), `used_at`, `used_result` | `callback_data` = token + chữ ký HMAC-SHA256 (khóa dẫn xuất từ khóa chủ). Dùng một lần, gắn chat, digest phải khớp; bấm một nút thì các nút cùng đối tượng hết hiệu lực |
| ➕ `telegram_prompts` (*Sprint 4b*) | `chat_id` (PK), `kind`, `subject_type`, `subject_id`, `expires_at` (30 phút) | Chat đang được hỏi "góp ý cho bài…" hoặc "lý do từ chối": tin nhắn kế tiếp của chat đó là câu trả lời |

## 10. Giữ dữ liệu và kích thước

| Dữ liệu | Giữ | Ước tính năm đầu (15 agent) |
|---|---|---|
| `task_logs`, `model_usage`, `memory_access_log` | 13 tháng (phân vùng; xóa theo phân vùng) | Vài triệu dòng |
| Episodic | 12 tháng nguyên bản → tóm tắt | Vài chục nghìn |
| Semantic/procedural | Theo phiên bản, không xóa (chỉ `retired`) | Vài nghìn |
| `leads`/`affiliates` chưa dùng | 180 ngày | |
| `audit_logs` | ≥ 2 năm | |

Tổng dung lượng dự kiến năm đầu: dưới 20 GB, chưa tính tệp media (media nằm trong object storage).
