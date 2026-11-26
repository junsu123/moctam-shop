"use client";

import { useEffect, useMemo, useState } from "react";

import { Loading } from "@/components/bits";
import { api, ApiError, type EventItem } from "@/lib/api";
import { actorLabel, clock, dayKey, dayLabel } from "@/lib/format";

type Live = "connecting" | "live" | "retrying";
const NOTE_STATUS: Record<string, string> = { queued: "chờ gửi", sent: "đã gửi", failed: "gửi lỗi", no_recipient: "chưa có chat nhận" };

export default function EventsPage() {
  const [items, setItems] = useState<EventItem[] | null>(null);
  const [live, setLive] = useState<Live>("connecting");
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState<"all" | "audit" | "notification">("all");

  useEffect(() => {
    let alive = true;
    const merge = (incoming: EventItem[]) =>
      setItems((cur) => {
        const seen = new Map((cur ?? []).map((e) => [`${e.source}-${e.id}`, e]));
        for (const e of incoming) seen.set(`${e.source}-${e.id}`, e);
        return [...seen.values()].sort((a, b) => Date.parse(b.at) - Date.parse(a.at) || b.id - a.id).slice(0, 300);
      });
    const reload = () =>
      api<EventItem[]>("/events")
        .then((e) => alive && merge(e))
        .catch((x) => alive && setErr(x instanceof ApiError ? x.message : "Không tải được."));
    void reload();
    // Luồng trực tiếp (SSE). Mất kết nối thì trình duyệt tự nối lại; khi nối lại thì tải lại để không sót sự kiện.
    const es = new EventSource("/api/v1/events/stream");
    es.onopen = () => {
      setLive("live");
      void reload();
    };
    es.onerror = () => setLive("retrying");
    es.onmessage = (m) => merge([JSON.parse(m.data) as EventItem]);
    return () => {
      alive = false;
      es.close();
    };
  }, []);

  const groups = useMemo(() => {
    const list = (items ?? []).filter((e) => filter === "all" || e.source === filter);
    const out: { day: string; label: string; items: EventItem[] }[] = [];
    for (const e of list) {
      const k = dayKey(e.at);
      if (out.at(-1)?.day !== k) out.push({ day: k, label: dayLabel(e.at), items: [] });
      out.at(-1)!.items.push(e);
    }
    return out;
  }, [items, filter]);

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Diễn biến</h1>
          <p className="muted">Mọi thao tác của anh/chị, của agent và mọi tin gửi Telegram, mới nhất ở trên.</p>
        </div>
        <p className={`live ${live}`} role="status">
          <span className="dot" aria-hidden="true" />
          {live === "live" ? "Đang cập nhật trực tiếp" : live === "connecting" ? "Đang kết nối…" : "Mất kết nối, đang thử lại…"}
        </p>
      </header>

      <div className="seg" role="group" aria-label="Lọc diễn biến">
        {(
          [
            ["all", "Tất cả"],
            ["audit", "Thao tác"],
            ["notification", "Tin Telegram"],
          ] as const
        ).map(([k, label]) => (
          <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>
            {label}
          </button>
        ))}
      </div>

      {err && <p className="err">{err}</p>}
      {!items ? (
        <Loading what="diễn biến" />
      ) : groups.length === 0 ? (
        <p className="muted">Chưa có diễn biến nào. Khi agent bắt đầu làm việc, từng bước sẽ hiện ở đây ngay lập tức.</p>
      ) : (
        groups.map((g) => (
          <section key={g.day} className="panel" aria-label={g.label}>
            <h2 className="day">{g.label}</h2>
            <ol className="feed">
              {g.items.map((e) => (
                <li key={`${e.source}-${e.id}`} className={e.source === "notification" ? `note ${e.status ?? ""}` : e.action.endsWith("_failed") ? "warn" : ""}>
                  <time dateTime={e.at}>{clock(e.at)}</time>
                  <span className="who">{e.source === "notification" ? "Telegram" : actorLabel(e.actor)}</span>
                  <span className="what">
                    {e.text}
                    {e.resource && e.source === "audit" ? <span className="obj">{e.resource.replace(/^[a-z_]+:/, "")}</span> : null}
                    {e.reason ? <span className="sub">Lý do: {e.reason}</span> : null}
                  </span>
                  {e.source === "notification" && <span className="small muted">{NOTE_STATUS[e.status ?? ""] ?? e.status}</span>}
                </li>
              ))}
            </ol>
          </section>
        ))
      )}
    </>
  );
}
