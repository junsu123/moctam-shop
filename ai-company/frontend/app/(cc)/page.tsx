"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Bar, Loading, STATE_TEXT } from "@/components/bits";
import { api, ApiError, type AgentState, type EventItem, type Overview } from "@/lib/api";
import { actorLabel, ago, clock, dayLabel, usd } from "@/lib/format";

const CHECK_NAMES: Record<string, string> = { database: "Cơ sở dữ liệu", queue: "Hàng đợi công việc" };
const REFRESH_MS = 10_000;

export default function OverviewPage() {
  const [ov, setOv] = useState<Overview | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    let t: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const [o, e] = await Promise.all([api<Overview>("/overview"), api<EventItem[]>("/events")]);
        if (!alive) return;
        setOv(o);
        setEvents(e.slice(0, 6));
        setErr("");
      } catch (x) {
        if (alive) setErr(x instanceof ApiError ? x.message : "Không tải được.");
      }
      if (alive) t = setTimeout(tick, REFRESH_MS);
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, []);

  if (!ov) return err ? <p className="err">{err}</p> : <Loading what="tổng quan" />;

  const todo: { text: string; href: string }[] = [];
  const keyed = ov.providers.filter((p) => p.configured);
  if (keyed.length === 0) todo.push({ text: "Nhập khóa API của Anthropic hoặc OpenAI để agent có thể làm việc", href: "/cai-dat#nha-cung-cap" });
  else if (!keyed.some((p) => p.last_test_ok)) todo.push({ text: "Bấm “Kiểm tra kết nối” cho khóa API vừa nhập", href: "/cai-dat#nha-cung-cap" });
  if (!ov.telegram.configured) todo.push({ text: "Dán token bot Telegram để nhận báo cáo trên điện thoại", href: "/cai-dat#telegram" });
  else if (ov.telegram.chats === 0) todo.push({ text: "Kết nối điện thoại với bot bằng mã 6 số", href: "/cai-dat#telegram" });

  const b = ov.budget;
  const states = Object.entries(ov.agents.by_state) as [AgentState, number][];
  const healthy = ov.health.status === "ok";

  return (
    <>
      <header className="page-head">
        <h1>Tổng quan</h1>
        <p className="muted">{dayLabel(ov.now)}</p>
      </header>

      {todo.length > 0 && (
        <section className="todo" aria-labelledby="todo-h">
          <h2 id="todo-h">Còn {todo.length} bước để văn phòng AI bắt đầu làm việc</h2>
          <ol>
            {todo.map((t) => (
              <li key={t.text}>
                <Link href={t.href}>{t.text}</Link>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="grid">
        <section className="tile" aria-labelledby="cost-h">
          <h2 id="cost-h">Chi phí AI</h2>
          <div className="spend">
            <div>
              <p className="figure">{usd(b.today_usd)}</p>
              <p className="muted small">hôm nay, được dùng tới {usd(b.allowed_today_usd)}</p>
              <Bar value={b.today_usd} max={b.allowed_today_usd} warnAt={b.alert_pct} label="Chi phí hôm nay" />
            </div>
            <div>
              <p className="figure">{usd(b.month_usd)}</p>
              <p className="muted small">tháng này, trần {usd(b.month_cap_usd, 0)}</p>
              <Bar value={b.month_usd} max={b.month_cap_usd} warnAt={b.alert_pct} label="Chi phí tháng này" />
            </div>
          </div>
          <p className="muted small">Đạt {b.alert_pct}% trần tháng thì báo qua Telegram; hết trần thì agent tự dừng gọi AI.</p>
        </section>

        <section className="tile" aria-labelledby="ag-h">
          <h2 id="ag-h">Agent</h2>
          <p className="figure">{ov.agents.total}</p>
          <ul className="plain">
            {states.map(([s, n]) => (
              <li key={s}>
                <span className={`dot s-${s}`} aria-hidden="true" /> {n} {STATE_TEXT[s].toLowerCase()}
              </li>
            ))}
          </ul>
          <Link href="/agent">Xem và tạm dừng từng agent</Link>
        </section>

        <section className="tile" aria-labelledby="sys-h">
          <h2 id="sys-h">Hệ thống</h2>
          <p className={`figure ${healthy ? "" : "bad-text"}`}>{healthy ? "Ổn định" : "Có lỗi"}</p>
          <ul className="plain">
            {Object.entries(ov.health.checks).map(([k, c]) => (
              <li key={k}>
                <span className={`dot ${c.status === "ok" ? "s-active" : "s-degraded"}`} aria-hidden="true" /> {CHECK_NAMES[k] ?? k}
                {c.status === "ok" ? (c.latency_ms != null ? `, ${c.latency_ms} ms` : "") : `: ${c.detail ?? "lỗi"}`}
              </li>
            ))}
          </ul>
          <p className="muted small">Phiên bản {ov.health.version}</p>
        </section>

        <section className="tile" aria-labelledby="tg-h">
          <h2 id="tg-h">Telegram</h2>
          <p className="figure">{ov.telegram.configured ? `${ov.telegram.chats} chat` : "Chưa cài"}</p>
          <p className="muted small">
            {ov.telegram.configured
              ? "Bài mới, báo cáo và cảnh báo được gửi vào các chat đã kết nối."
              : "Báo cáo và link bài mới sẽ gửi qua bot Telegram của anh/chị."}
          </p>
          <Link href="/cai-dat#telegram">Cài đặt Telegram</Link>
        </section>
      </div>

      <section className="panel" aria-labelledby="ev-h">
        <div className="panel-head">
          <h2 id="ev-h">Mới nhất</h2>
          <Link href="/dien-bien">Toàn bộ diễn biến</Link>
        </div>
        {events.length === 0 ? (
          <p className="muted">Chưa có diễn biến nào.</p>
        ) : (
          <ol className="feed compact">
            {events.map((e) => (
              <li key={`${e.source}-${e.id}`}>
                <time dateTime={e.at} title={ago(e.at)}>
                  {clock(e.at)}
                </time>
                <span className="who">{e.source === "notification" ? "Telegram" : actorLabel(e.actor)}</span>
                <span className="what">{e.text}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
      {err && <p className="err">{err}</p>}
    </>
  );
}
