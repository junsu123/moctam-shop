"use client";

import { Activity, ArrowRight, Bot, Check, Database, Inbox, Layers, MessageCircle, Send, TriangleAlert, Wallet } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, Bar, Card, Empty, ErrorAlert, Loading, PageHeader, STATE_TEXT } from "@/components/ui/primitives";
import { api, ApiError, type AgentState, type EventItem, type Overview } from "@/lib/api";
import { actorLabel, ago, dayLabel, usd } from "@/lib/format";

const CHECK_NAMES: Record<string, { label: string; icon: typeof Database }> = {
  database: { label: "Cơ sở dữ liệu", icon: Database },
  queue: { label: "Hàng đợi công việc", icon: Layers },
};
const PROVIDER_NAMES: Record<string, string> = { anthropic: "Anthropic (Claude)", openai: "OpenAI (ChatGPT)" };
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
        setEvents(e.slice(0, 8));
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

  if (!ov) return err ? <ErrorAlert>{err}</ErrorAlert> : <Loading what="tổng quan" />;

  const keyed = ov.providers.filter((p) => p.configured);
  const steps = [
    { text: "Tạo tài khoản Owner và bật xác thực hai lớp", done: true, href: "/" },
    { text: "Nhập khóa API của Anthropic hoặc OpenAI", done: keyed.length > 0, href: "/cai-dat?tab=nha-cung-cap" },
    { text: "Kiểm tra kết nối khóa API", done: keyed.some((p) => p.last_test_ok), href: "/cai-dat?tab=nha-cung-cap" },
    { text: "Dán token bot Telegram", done: ov.telegram.configured, href: "/cai-dat" },
    { text: "Kết nối điện thoại với bot bằng mã 6 số", done: ov.telegram.chats > 0, href: "/cai-dat" },
  ];
  const left = steps.filter((s) => !s.done).length;
  const b = ov.budget;
  const active = ov.agents.by_state.active ?? 0;
  const others = (Object.entries(ov.agents.by_state) as [AgentState, number][]).filter(([s]) => s !== "active");
  const healthy = ov.health.status === "ok";

  return (
    <>
      <PageHeader
        title="Tổng quan"
        description={`${dayLabel(ov.now)}. Số liệu tự cập nhật mỗi 10 giây.`}
        actions={
          <Link href="/dien-bien" className="btn btn-secondary">
            <Activity size={16} aria-hidden="true" /> Xem diễn biến
          </Link>
        }
      />
      {err && <ErrorAlert>{err}</ErrorAlert>}

      <div className="stack">
        {left > 0 && (
          <Card
            title={`Thiết lập ban đầu: còn ${left} bước`}
            description="Làm xong các bước này để văn phòng AI bắt đầu làm việc và báo cáo cho anh/chị."
            actions={<Badge tone="warn" plain>{`${steps.length - left}/${steps.length} xong`}</Badge>}
            flush
          >
            <ul className="checklist" aria-label="Các bước thiết lập">
              {steps.map((s) => (
                <li key={s.text} className={s.done ? "done" : ""}>
                  <span className="check-ic" aria-hidden="true">
                    <Check size={14} strokeWidth={3} />
                  </span>
                  <span className="step-text">
                    {s.text}
                    <span className="sr-only">{s.done ? " (đã xong)" : " (chưa xong)"}</span>
                  </span>
                  {!s.done && (
                    <Link href={s.href} className="btn btn-secondary btn-sm">
                      Làm ngay <ArrowRight size={14} aria-hidden="true" />
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        )}

        <div className="grid-stats">
          <section className="card stat" aria-label="Chi phí AI hôm nay">
            <span className="stat-label">
              <span className="stat-icon">
                <Wallet size={16} />
              </span>
              Chi phí AI hôm nay
            </span>
            <span className="stat-value">{usd(b.today_usd)}</span>
            <Bar value={b.today_usd} max={b.allowed_today_usd} warnAt={b.alert_pct} label="Chi phí hôm nay" />
            <span className="stat-foot">Được dùng tới {usd(b.allowed_today_usd)}</span>
          </section>
          <section className="card stat" aria-label="Chi phí AI tháng này">
            <span className="stat-label">
              <span className={`stat-icon${b.month_pct >= b.alert_pct ? " warn" : ""}`}>
                <Wallet size={16} />
              </span>
              Chi phí tháng này
            </span>
            <span className="stat-value">
              {usd(b.month_usd)} <small>/ {usd(b.month_cap_usd, 0)}</small>
            </span>
            <Bar value={b.month_usd} max={b.month_cap_usd} warnAt={b.alert_pct} label="Chi phí tháng này" />
            <span className="stat-foot">Báo Telegram khi đạt {b.alert_pct}% trần</span>
          </section>
          <section className="card stat" aria-label="Agent">
            <span className="stat-label">
              <span className="stat-icon info">
                <Bot size={16} />
              </span>
              Agent đang chạy
            </span>
            <span className="stat-value">
              {active} <small>/ {ov.agents.total}</small>
            </span>
            <span className="stat-foot">{others.length ? others.map(([s, n]) => `${n} ${STATE_TEXT[s].toLowerCase()}`).join(", ") : "Tất cả đang chạy"}</span>
          </section>
          <section className="card stat" aria-label="Telegram">
            <span className="stat-label">
              <span className="stat-icon info">
                <Send size={16} />
              </span>
              Telegram
            </span>
            <span className="stat-value">{ov.telegram.configured ? `${ov.telegram.chats} chat` : "Chưa cài"}</span>
            <span className="stat-foot">{ov.telegram.configured ? "Nhận bài mới, báo cáo, cảnh báo" : "Cài trong mục Cài đặt"}</span>
          </section>
        </div>

        <div className="grid-2">
          <Card
            title="Hoạt động gần đây"
            actions={
              <Link href="/dien-bien" className="btn btn-ghost btn-sm">
                Xem tất cả <ArrowRight size={14} aria-hidden="true" />
              </Link>
            }
            flush
          >
            {events.length === 0 ? (
              <Empty icon={<Inbox size={20} />} title="Chưa có hoạt động">
                Khi agent bắt đầu làm việc, từng bước sẽ hiện ở đây.
              </Empty>
            ) : (
              <ul className="activity">
                {events.map((e) => {
                  const tg = e.source === "notification";
                  const warn = e.action.endsWith("_failed") || e.urgent;
                  return (
                    <li key={`${e.source}-${e.id}`}>
                      <span className={`act-ic${tg ? " tg" : warn ? " warn" : ""}`} aria-hidden="true">
                        {tg ? <MessageCircle size={16} /> : warn ? <TriangleAlert size={16} /> : <Activity size={16} />}
                      </span>
                      <span className="act-main">
                        <b>{e.text}</b>
                        <span>{tg ? "Telegram" : actorLabel(e.actor)}</span>
                      </span>
                      <time className="subtle xs" dateTime={e.at}>
                        {ago(e.at)}
                      </time>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <div className="stack">
            <Card title="Tình trạng hệ thống" actions={<Badge tone={healthy ? "success" : "danger"}>{healthy ? "Ổn định" : "Có lỗi"}</Badge>} flush>
              <ul className="kv">
                {Object.entries(ov.health.checks).map(([k, c]) => {
                  const meta = CHECK_NAMES[k] ?? { label: k, icon: Database };
                  return (
                    <li key={k}>
                      <span className="k">
                        <meta.icon size={16} className="subtle" aria-hidden="true" /> {meta.label}
                      </span>
                      {c.status === "ok" ? (
                        <span className="muted xs">{c.latency_ms != null ? `${c.latency_ms} ms` : "ổn"}</span>
                      ) : (
                        <Badge tone="danger">{c.detail ?? "Lỗi"}</Badge>
                      )}
                    </li>
                  );
                })}
                <li>
                  <span className="k muted">Phiên bản</span>
                  <span className="muted xs">{ov.health.version}</span>
                </li>
              </ul>
            </Card>
            <Card
              title="Nhà cung cấp AI"
              actions={
                <Link href="/cai-dat?tab=nha-cung-cap" className="btn btn-ghost btn-sm">
                  Quản lý
                </Link>
              }
              flush
            >
              <ul className="kv">
                {ov.providers.map((p) => (
                  <li key={p.id}>
                    <span className="k">{PROVIDER_NAMES[p.id] ?? p.id}</span>
                    {!p.configured ? (
                      <Badge>Chưa có khóa</Badge>
                    ) : p.last_test_ok ? (
                      <Badge tone="success">Kết nối tốt</Badge>
                    ) : p.last_test_ok === false ? (
                      <Badge tone="danger">Lỗi kết nối</Badge>
                    ) : (
                      <Badge tone="warn">Chưa kiểm tra</Badge>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
