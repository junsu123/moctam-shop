// Gọi API backend qua cùng nguồn (/api/v1). Cookie phiên HttpOnly do trình duyệt tự gửi;
// thao tác ghi kèm X-CSRF-Token lấy từ /auth/state.

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

let csrf = "";
export function setCsrf(v: string | null | undefined) {
  csrf = v ?? "";
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = init.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrf) headers["X-CSRF-Token"] = csrf;
  let r: Response;
  try {
    r = await fetch(`/api/v1${path}`, {
      method,
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError("NETWORK", "Không kết nối được máy chủ. Kiểm tra container backend đã chạy chưa (docker compose ps).", 0);
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const e = data?.error;
    if (e?.code) throw new ApiError(e.code, e.message, r.status);
    if (Array.isArray(data?.detail)) throw new ApiError("VALIDATION_FAILED", "Dữ liệu không hợp lệ.", r.status);
    throw new ApiError("HTTP_" + r.status, `Máy chủ trả lỗi ${r.status}.`, r.status);
  }
  return data as T;
}

// ---------------------------------------------------------------- kiểu dữ liệu
export type AuthState = {
  needs_setup: boolean;
  authenticated: boolean;
  user: { email: string; display_name: string; role: string } | null;
  csrf: string | null;
  reauth_until: string | null;
};

export type AgentState = "active" | "paused" | "learning" | "waiting_approval" | "degraded" | "disabled";
export type Agent = {
  agent_key: string;
  display_name: string;
  department: string;
  kind: "executive" | "director" | "specialist";
  reports_to: string | null;
  role_summary: string;
  state: AgentState;
  reason: string | null;
  changed_by: string | null;
  updated_at: string;
};

export type Budget = { month_usd: number; day_usd: number; day_burst_usd: number; alert_pct: number };
export type Hours = { work_start: string; work_end: string; quiet_start: string; quiet_end: string };
export type Spend = {
  today_usd: number;
  month_usd: number;
  day_cap_usd: number;
  allowed_today_usd: number;
  month_cap_usd: number;
  alert_pct: number;
  month_pct: number;
};

export type Provider = {
  id: "anthropic" | "openai";
  display_name: string;
  configured: boolean;
  key_last4: string | null;
  key_updated_at: string | null;
  last_test_at: string | null;
  last_test_ok: boolean | null;
  last_test_detail: string | null;
  models: { id: string; model_name: string; price_in_per_mtok: number; price_out_per_mtok: number; enabled: boolean }[];
};

export type Check = { status: "ok" | "error"; latency_ms?: number | null; detail?: string | null };
export type Overview = {
  health: { status: "ok" | "degraded"; version: string; checks: Record<string, Check> };
  budget: Spend;
  agents: { total: number; by_state: Partial<Record<AgentState, number>> };
  telegram: { configured: boolean; chats: number };
  approvals_pending: number;
  providers: { id: string; configured: boolean; last_test_ok: boolean | null }[];
  now: string;
};

export type EventItem = {
  source: "audit" | "notification" | "task";
  agent_name?: string | null;
  task_id?: string;
  task_title?: string;
  node?: string | null;
  id: number;
  at: string;
  actor: string;
  action: string;
  text: string;
  resource?: string | null;
  reason?: string | null;
  status?: string;
  urgent?: boolean;
};

export type TgChat = {
  chat_id: number;
  title: string;
  can_approve: boolean;
  receives: string[];
  enabled: boolean;
  added_at: string;
  added_by: string | null;
};
export type TgStatus = {
  configured: boolean;
  bot_username: string | null;
  token_last4: string | null;
  token_updated_at: string | null;
  chats: TgChat[];
};

// ---------------------------------------------------------------- Agent Core (Sprint 2)
export type Personality = {
  voice: { tone: string; formality: number; emoji: boolean };
  risk_tolerance: number;
  verbosity: number;
  evidence_strictness: number;
};
export type Bundle = {
  agent_id: string;
  kind: string;
  versions: { brain_version: string; prompt_version: string; knowledge_version: string; skill_version: string };
  department: string;
  reports_to: string | null;
  model: { primary: string; fallback: string | null; parameters: { temperature: number; max_output_tokens: number } };
  budget: { usd_per_day: number; max_steps_per_task: number; max_tool_calls_per_task: number };
  memory: { retrieval_budget_tokens: number; share_ratio: Record<string, number> };
  identity: {
    profile: { display_name: string; summary: string };
    role: { mission: string; responsibilities: string[]; hard_rules: string[] };
    personality: Personality;
  };
  reasoning: {
    reasoning_policy: { style: string; max_reasoning_steps: number; cite_memory: boolean };
    planning_policy: { max_subtasks: number; max_depth: number; require_success_criteria: boolean };
    decision_policy: { escalate_when: { confidence_below: number; action_tags: string[]; conflicts_with_memory: boolean } };
  };
  skills: { key: string; name: string; version: string }[];
  tool_permissions: { tool: string; action: string; level: number }[];
  evaluation: { performance: { kpis: { key: string; name: string }[] } };
  constitution: { version: string; principles: string[]; forbidden_tags: Record<string, string>; mandatory_approval_tags: Record<string, string> };
};
export type BrainMeta = {
  id: string;
  brain_version: string;
  prompt_version: string;
  knowledge_version: string;
  skill_version: string;
  bundle_hash: string;
  core_rules_hash: string;
  state: "draft" | "shadow" | "active" | "retired" | "rejected";
  created_at: string;
  created_by: string;
  activated_at: string | null;
};
export type AgentPermission = {
  tool_id: string;
  action: string;
  autonomy_level: number;
  limits: { per_day?: number; max_usd?: number };
  requires_approval: boolean;
  expires_at: string | null;
  tool_description: string | null;
  risk: "low" | "medium" | "high" | null;
  available: boolean | null;
  action_info: { description: string; min_level: number; side_effects: string; tags: string[]; available: boolean } | null;
};
export type AgentDetail = Agent & {
  manager: { agent_key: string; display_name: string } | null;
  direct_reports: { agent_key: string; display_name: string }[];
  brain: BrainMeta | null;
  bundle: Bundle | null;
  integrity: { ok: boolean; detail: string };
  permissions: AgentPermission[];
  spend_today_usd: number;
  approvals_pending: number;
};
export type AgentHistory = {
  versions: {
    id: number;
    at: string;
    event: string;
    from_version: string | null;
    to_version: string | null;
    proposed_by: string;
    approved_by: string | null;
    changes: number;
  }[];
  decisions: { id: number; at: string; tool_id: string; action: string; decision: "allow" | "require_approval" | "deny"; rule: string; reason: string }[];
  invocations: {
    id: string;
    at: string;
    tool_id: string;
    action: string;
    task_id: string | null;
    status: string;
    error_code: string | null;
    error: string | null;
    attempts: number;
    duration_ms: number | null;
  }[];
};
export type DiffItem = { path: string; from: unknown; to: unknown };
export type Approval = {
  id: string;
  subject_type: string;
  subject_id: string;
  action: string;
  title: string;
  summary: string;
  payload: { agent?: string; diff?: DiffItem[]; input?: unknown; core_changed?: boolean; from?: string; to?: string } & Record<string, unknown>;
  risk: "low" | "medium" | "high";
  requested_by: string;
  status: "pending" | "approved" | "rejected" | "expired" | "cancelled";
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
  expires_at: string;
};
export type ToolInfo = {
  id: string;
  description: string;
  actions: Record<string, { description: string; min_level: number; side_effects: string; tags: string[]; available: boolean }>;
  side_effects: string;
  risk: "low" | "medium" | "high";
  available: boolean;
  grants: { action: string; agent_key: string; display_name: string; level: number }[];
};

// ---------------------------------------------------------------- Trí nhớ (Sprint 3)
export type MemType = "working" | "episodic" | "semantic" | "procedural";
export type MemoryItem = {
  id: string;
  owner_scope: string;
  type: MemType;
  title: string;
  snippet: string;
  source_ref: string | null;
  source_trust: "owner" | "internal" | "verified_external" | "unverified_external";
  confidence: number;
  verification_status: string;
  valid_from: string;
  valid_to: string | null;
  usefulness: number;
  created_at: string;
  created_by_principal: string;
  metadata: Record<string, unknown>;
  access_count: number;
};
export type MemoryDetail = Omit<MemoryItem, "snippet"> & {
  content: string;
  supersedes_id: string | null;
  version: number;
  detail?: Record<string, unknown>;
  access: { at: string; principal: string; task_id: string | null; purpose: string; rank: number | null; score: number | null; used_in_output: boolean }[];
  embeddings: string[];
};
export type MemoryStats = {
  total: number;
  by_type: Partial<Record<MemType, number>>;
  by_scope: { scope: string; n: number }[];
  embedding: { model: string | null; dims: number | null; configured: boolean; embedded: number; pending: number };
  retrievals_today: number;
};
export type RetrievedItem = {
  memory_id: string;
  type: MemType;
  scope: string;
  title: string;
  content: string;
  source_trust: string;
  confidence: number;
  category: string;
  tokens: number;
  kw_rank: number | null;
  vec_rank: number | null;
  rrf: number;
  w_recency: number;
  w_conf: number;
  w_trust: number;
  score: number;
};
export type RetrievalResult = {
  items: RetrievedItem[];
  considered: number;
  used_tokens: number;
  budget_tokens: number;
  vector_search: string;
  scopes: string[];
};

export type TaskStatus =
  | "CREATED"
  | "PENDING"
  | "ASSIGNED"
  | "IN_PROGRESS"
  | "WAITING_REVIEW"
  | "WAITING_APPROVAL"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type TaskRow = {
  id: string;
  parent_id: string | null;
  root_id: string;
  depth: number;
  title: string;
  task_type: string;
  status: TaskStatus;
  priority: number;
  assigned_agent: string;
  agent_name: string | null;
  department: string | null;
  created_by: string;
  deadline: string | null;
  budget_usd: number;
  spent_usd: number;
  graph_node: string | null;
  wait_kind: "approval" | "review" | "children" | null;
  attempt: number;
  max_attempts: number;
  error_code: string | null;
  error: string | null;
  result_summary: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  children: number;
};

export type TaskLog = { id: number; at: string; event: string; node: string | null; step_no: number | null; text: string; agent_key: string | null; agent_name: string | null };

export type TaskDetail = {
  task: TaskRow & {
    description: string;
    input_data: Record<string, unknown>;
    output_data: Record<string, unknown> | null;
    success_criteria: (string | Record<string, unknown>)[];
    requires_review: boolean;
    reviewer: string | null;
    requires_approval: boolean;
    autonomy_max: number;
    started_at: string | null;
  };
  parent: { id: string; title: string; assigned_agent: string; status: TaskStatus } | null;
  logs: TaskLog[];
  children: TaskRow[];
  reviews: { round: number; reviewer: string; verdict: "approve" | "request_changes" | "reject"; notes: string | null; created_at: string }[];
  messages: { id: string; message_type: string; sender: string; receiver: string; status: string; created_at: string; delivered_at: string | null; last_error: string | null }[];
  tools: { id: string; tool_id: string; action: string; status: string; error_code: string | null; error: string | null; at: string; duration_ms: number | null }[];
  approvals: { id: string; title: string; status: string; created_at: string; decided_at: string | null; decision_note: string | null }[];
  can_review: boolean;
  next_round: number;
};

export type TaskStats = {
  by_status: Partial<Record<TaskStatus, number>>;
  groups: { active: number; waiting: number; done: number; failed: number };
  owner_reviews: number;
  spent_today_usd: number;
};

export type LiveAgent = {
  agent_key: string;
  display_name: string;
  department: string;
  kind: string;
  state: AgentState;
  current: { id: string; title: string; status: TaskStatus; graph_node: string | null; updated_at: string } | null;
  queued: number;
  waiting: number;
  done_24h: number;
};
export type LiveOffice = { agents: LiveAgent[]; need_owner: { approvals: number; reviews: number; failed: number } };

export type Schedule = {
  id: string;
  name: string;
  agent_key: string;
  agent_name: string;
  cron: string;
  timezone: string;
  task_template: { title: string };
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
};

export type WebsiteInfo = {
  base_url: string;
  keys: Record<"read" | "drafts" | "publish", { last4: string; updated_at: string } | null>;
};

export type PublishItem = {
  id: string;
  task_id: string | null;
  agent_key: string;
  agent_name: string | null;
  kind: "faq" | "blog";
  title: string;
  status: "scheduled" | "publishing" | "published" | "blocked" | "retracted" | "cancelled" | "failed";
  slot_at: string | null;
  published_at: string | null;
  url: string | null;
  gate: { blocked?: string[]; topics?: string[]; risk?: string; risk_reason?: string };
  last_error: string | null;
  retracted_at: string | null;
  retracted_by: string | null;
  retract_reason: string | null;
  created_at: string;
  approval_id: string | null;
  excerpt: string;
};
export type PublishList = { items: PublishItem[]; counts: { queue: number; live: number; blocked: number }; phase: number; paused: boolean; paused_reason: string };

export type KindPlan = { times: string[]; weekdays: number[]; per_day: number; per_week: number | null };
export type PublishSettings = {
  phase: number;
  phase_since: string | null;
  auto_progress: boolean;
  paused: boolean;
  paused_reason: string;
  holidays: string[];
  window_start: string;
  window_end: string;
  min_gap_hours: number;
  phases: Record<string, { blog: KindPlan; faq: KindPlan }>;
  upcoming: string[];
};
export type GateConfig = {
  risk_phrases: string[];
  compare_phrases: string[];
  owner_topics: Record<string, string[]>;
  min_body_chars: Record<string, number>;
  max_title_chars: number;
  use_classifier: boolean;
};
