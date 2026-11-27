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
