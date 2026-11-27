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
  source: "audit" | "notification";
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
