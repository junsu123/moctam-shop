"use client";

import { useCallback, useEffect, useState } from "react";

import type { AgentState } from "@/lib/api";

/** Thanh mức dùng vẽ bằng SVG (thuộc tính, không dùng style inline: CSP chặn style-src không nonce). */
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

export const STATE_TEXT: Record<AgentState, string> = {
  active: "Đang chạy",
  paused: "Tạm dừng",
  learning: "Đang học",
  waiting_approval: "Chờ duyệt",
  degraded: "Gặp lỗi",
  disabled: "Tắt",
};

export function StateTag({ state }: { state: AgentState }) {
  return <span className={`tag s-${state}`}>{STATE_TEXT[state]}</span>;
}

/** Thông báo ngắn sau thao tác; tự ẩn sau 4 giây. */
export function useFlash(): [React.ReactNode, (msg: string, kind?: "ok" | "err") => void] {
  const [m, setM] = useState<{ msg: string; kind: "ok" | "err"; n: number } | null>(null);
  useEffect(() => {
    if (!m || m.kind === "err") return;
    const t = setTimeout(() => setM(null), 4000);
    return () => clearTimeout(t);
  }, [m]);
  const node = m ? (
    <p className={m.kind === "ok" ? "flash" : "err"} role={m.kind === "err" ? "alert" : "status"} key={m.n}>
      {m.msg}
    </p>
  ) : null;
  const say = useCallback((msg: string, kind: "ok" | "err" = "ok") => setM(msg ? { msg, kind, n: Date.now() } : null), []);
  return [node, say];
}

export function Loading({ what }: { what: string }) {
  return (
    <p className="muted" aria-busy="true">
      Đang tải {what}…
    </p>
  );
}
