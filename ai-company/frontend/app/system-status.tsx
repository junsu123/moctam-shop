"use client";

import { useEffect, useState } from "react";

type Check = { status: "ok" | "error"; latency_ms?: number | null; detail?: string | null };
type Ready = { status: "ok" | "degraded"; version: string; checks: Record<string, Check> };
type Row = { key: string; name: string; status: "ok" | "error" | "loading"; text: string; ms?: number | null };

const NAMES: Record<string, string> = { api: "Máy chủ", database: "Cơ sở dữ liệu", queue: "Hàng đợi công việc" };
const REFRESH_MS = 5000;

async function load(): Promise<Row[]> {
  try {
    const r = await fetch("/api/v1/health/ready", { cache: "no-store" });
    const body = (await r.json()) as Ready;
    if (!body.checks) throw new Error("bad body");
    const rows: Row[] = [{ key: "api", name: NAMES.api, status: "ok", text: `Đang chạy, phiên bản ${body.version}` }];
    for (const [key, c] of Object.entries(body.checks)) {
      rows.push({
        key,
        name: NAMES[key] ?? key,
        status: c.status,
        text: c.status === "ok" ? "Sẵn sàng" : `Chưa sẵn sàng${c.detail ? ` (${c.detail})` : ""}`,
        ms: c.latency_ms,
      });
    }
    return rows;
  } catch {
    return [{ key: "api", name: NAMES.api, status: "error", text: "Không kết nối được. Kiểm tra container backend đã chạy chưa (docker compose ps)." }];
  }
}

export function SystemStatus() {
  const [rows, setRows] = useState<Row[]>([{ key: "api", name: NAMES.api, status: "loading", text: "Đang kiểm tra…" }]);
  const [at, setAt] = useState<string>("");

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const next = await load();
      if (!alive) return;
      setRows(next);
      setAt(new Intl.DateTimeFormat("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date()));
      timer = setTimeout(tick, REFRESH_MS);
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  return (
    <>
      <ul className="checks" aria-live="polite">
        {rows.map((r) => (
          <li key={r.key} className={r.status}>
            <span className="dot" aria-hidden="true" />
            <span className="name">{r.name}</span>
            <span className="state">{r.text}</span>
            <span className="ms">{r.ms != null ? `${r.ms} ms` : ""}</span>
          </li>
        ))}
      </ul>
      <p className="note">{at ? `Kiểm tra lúc ${at}, tự cập nhật mỗi 5 giây.` : ""}</p>
    </>
  );
}
