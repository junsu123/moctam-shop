"use client";

import { Inbox } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader, type Tone } from "@/components/ui/primitives";
import { Tabs, TabPanel, useTabParam } from "@/components/ui/tabs";
import { api, ApiError, type EventItem } from "@/lib/api";
import { actorLabel, clock, dayKey, dayLabel } from "@/lib/format";

type Live = "connecting" | "on" | "retry";
type Filter = "all" | "audit" | "notification";
const FILTERS = ["all", "audit", "notification"] as const;
const NOTE_STATUS: Record<string, [string, Tone]> = {
  queued: ["Chờ gửi", "warn"],
  sent: ["Đã gửi", "success"],
  failed: ["Gửi lỗi", "danger"],
  no_recipient: ["Chưa có chat nhận", "neutral"],
};

export default function EventsPage() {
  const [items, setItems] = useState<EventItem[] | null>(null);
  const [live, setLive] = useState<Live>("connecting");
  const [err, setErr] = useState("");
  const [tab, setTab] = useTabParam<Filter>(FILTERS, "all");

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
    // Luồng trực tiếp (SSE). Mất kết nối thì trình duyệt tự nối lại; nối lại xong thì tải lại để không sót sự kiện.
    const es = new EventSource("/api/v1/events/stream");
    es.onopen = () => {
      setLive("on");
      void reload();
    };
    es.onerror = () => setLive("retry");
    es.onmessage = (m) => merge([JSON.parse(m.data) as EventItem]);
    return () => {
      alive = false;
      es.close();
    };
  }, []);

  const counts = useMemo(() => {
    const l = items ?? [];
    return { all: l.length, audit: l.filter((e) => e.source === "audit").length, notification: l.filter((e) => e.source === "notification").length };
  }, [items]);

  const groups = useMemo(() => {
    const out: { day: string; label: string; items: EventItem[] }[] = [];
    for (const e of (items ?? []).filter((x) => tab === "all" || x.source === tab)) {
      const k = dayKey(e.at);
      if (out.at(-1)?.day !== k) out.push({ day: k, label: dayLabel(e.at), items: [] });
      out.at(-1)!.items.push(e);
    }
    return out;
  }, [items, tab]);

  return (
    <>
      <PageHeader
        title="Diễn biến"
        description="Mọi thao tác của anh/chị, của agent và mọi tin gửi Telegram. Mới nhất ở trên, cập nhật ngay khi có."
        actions={
          <span className={`live ${live === "on" ? "on" : live === "retry" ? "retry" : ""}`} role="status">
            <span className="dot" aria-hidden="true" />
            {live === "on" ? "Đang cập nhật trực tiếp" : live === "connecting" ? "Đang kết nối…" : "Mất kết nối, đang thử lại…"}
          </span>
        }
      />
      <Tabs
        label="Loại diễn biến"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "all", label: "Tất cả", count: counts.all },
          { id: "audit", label: "Thao tác", count: counts.audit },
          { id: "notification", label: "Tin Telegram", count: counts.notification },
        ]}
      />
      <TabPanel id={tab}>
        {err && <ErrorAlert>{err}</ErrorAlert>}
        {!items ? (
          <Loading what="diễn biến" />
        ) : (
          <Card flush>
            {groups.length === 0 ? (
              <Empty icon={<Inbox size={20} />} title="Chưa có diễn biến">
                Khi agent bắt đầu làm việc, từng bước sẽ hiện ở đây ngay lập tức.
              </Empty>
            ) : (
              <div className="table-wrap">
                <table className="table feed">
                  <thead>
                    <tr>
                      <th scope="col">Thời gian</th>
                      <th scope="col">Nguồn</th>
                      <th scope="col">Nội dung</th>
                      <th scope="col" className="hide-sm">
                        Đối tượng
                      </th>
                    </tr>
                  </thead>
                  {groups.map((g) => (
                    <tbody key={g.day}>
                      <tr className="day">
                        <td colSpan={4}>{g.label}</td>
                      </tr>
                      {g.items.map((e) => {
                        const tg = e.source === "notification";
                        const st = tg ? NOTE_STATUS[e.status ?? ""] : undefined;
                        return (
                          <tr key={`${e.source}-${e.id}`}>
                            <td className="nowrap muted">
                              <time dateTime={e.at}>{clock(e.at)}</time>
                            </td>
                            <td className="nowrap">{tg ? <Badge tone="info" plain>Telegram</Badge> : actorLabel(e.actor)}</td>
                            <td>
                              <div className="cell-main">
                                <span className={e.action.endsWith("_failed") ? "note" : ""}>{e.text}</span>
                                {e.reason && <span>Lý do: {e.reason}</span>}
                              </div>
                            </td>
                            <td className="hide-sm">
                              {tg ? st && <Badge tone={st[1]}>{st[0]}</Badge> : e.resource && <span className="mono-tag">{e.resource.replace(/^[a-z_]+:/, "")}</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  ))}
                </table>
              </div>
            )}
          </Card>
        )}
      </TabPanel>
    </>
  );
}
