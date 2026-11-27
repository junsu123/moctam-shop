import type { AgentState } from "@/lib/api";

export function PageHeader({ title, description, actions }: { title: string; description?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  description,
  actions,
  footer,
  flush,
  children,
  id,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  footer?: React.ReactNode;
  flush?: boolean;
  children?: React.ReactNode;
  id?: string;
}) {
  return (
    <section className="card" id={id} aria-label={typeof title === "string" ? title : undefined}>
      {title && (
        <div className="card-head">
          <div className="card-title">
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children !== undefined && <div className={`card-body${flush ? " flush" : ""}`}>{children}</div>}
      {footer && <div className="card-foot">{footer}</div>}
    </section>
  );
}

export type Tone = "success" | "warn" | "danger" | "info" | "neutral";
export function Badge({ tone = "neutral", children, plain }: { tone?: Tone; children: React.ReactNode; plain?: boolean }) {
  return <span className={`badge ${tone}${plain ? " plain" : ""}`}>{children}</span>;
}

export const STATE_TEXT: Record<AgentState, string> = {
  active: "Đang chạy",
  paused: "Tạm dừng",
  learning: "Đang học",
  waiting_approval: "Chờ duyệt",
  degraded: "Gặp lỗi",
  disabled: "Tắt",
};
const STATE_TONE: Record<AgentState, Tone> = {
  active: "success",
  paused: "warn",
  learning: "info",
  waiting_approval: "warn",
  degraded: "danger",
  disabled: "neutral",
};
export function StateBadge({ state }: { state: AgentState }) {
  return <Badge tone={STATE_TONE[state]}>{STATE_TEXT[state]}</Badge>;
}

/** Thanh mức dùng vẽ bằng thuộc tính SVG (không dùng style inline vì CSP). */
export function Bar({ value, max, warnAt = 80, label }: { value: number; max: number; warnAt?: number; label: string }) {
  const pct = max > 0 ? Math.min(100, (100 * value) / max) : 0;
  const tone = pct >= 100 ? "bad" : pct >= warnAt ? "warn" : "good";
  return (
    <svg className={`bar ${tone}`} viewBox="0 0 100 6" preserveAspectRatio="none" role="img" aria-label={`${label}: ${pct.toFixed(0)}%`}>
      <rect className="bar-track" x="0" y="0" width="100" height="6" rx="3" />
      <rect className="bar-fill" x="0" y="0" width={Math.max(pct, value > 0 ? 1.5 : 0)} height="6" rx="3" />
      <line className="bar-mark" x1={warnAt} x2={warnAt} y1="0" y2="6" />
    </svg>
  );
}

export function Empty({ icon, title, children, action }: { icon: React.ReactNode; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-ic">{icon}</span>
      <b>{title}</b>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <div className="gate" aria-busy="true">
      <span className="spinner" role="status" aria-label={`Đang tải ${what}`} />
    </div>
  );
}

export function ErrorAlert({ children }: { children: React.ReactNode }) {
  return (
    <p className="alert danger" role="alert">
      {children}
    </p>
  );
}
