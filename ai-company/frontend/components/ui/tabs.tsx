"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef } from "react";

export type TabDef<T extends string> = { id: T; label: string; count?: number; icon?: React.ReactNode };

/** Tab đang chọn lưu trên URL (?tab=…): tải lại trang, quay lại, hay gửi link đều mở đúng tab. */
export function useTabParam<T extends string>(ids: readonly T[], fallback: T): [T, (t: T) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const raw = params.get("tab") as T | null;
  const current = raw && ids.includes(raw) ? raw : fallback;
  const set = useCallback(
    (t: T) => {
      const q = new URLSearchParams(params.toString());
      if (t === fallback) q.delete("tab");
      else q.set("tab", t);
      const s = q.toString();
      router.replace(s ? `${path}?${s}` : path, { scroll: false });
    },
    [params, router, path, fallback],
  );
  return [current, set];
}

/** Thanh tab theo mẫu WAI-ARIA: mũi tên trái/phải, Home/End để chuyển tab. */
export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: TabDef<T>[]; value: T; onChange: (t: T) => void; label: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  function onKey(e: React.KeyboardEvent, i: number) {
    const n = tabs.length;
    const to = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i - 1 + n) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (to < 0) return;
    e.preventDefault();
    refs.current[to]?.focus();
    onChange(tabs[to].id);
  }
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={value === t.id}
          aria-controls={`panel-${t.id}`}
          tabIndex={value === t.id ? 0 : -1}
          className="tab"
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKey(e, i)}
        >
          {t.icon}
          {t.label}
          {t.count !== undefined && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className="stack">
      {children}
    </div>
  );
}
