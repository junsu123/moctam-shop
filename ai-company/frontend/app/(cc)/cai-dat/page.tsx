"use client";

import { Clock, Cpu, KeyRound, Link2, MessageCircle, Plug, Send, ShieldCheck, Trash2, Wallet } from "lucide-react";
import { useEffect, useState } from "react";

import { useShell } from "@/components/shell";
import { useConfirm } from "@/components/ui/dialog";
import { Badge, Bar, Card, Empty, ErrorAlert, Loading, PageHeader } from "@/components/ui/primitives";
import { Tabs, TabPanel, useTabParam } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type Budget, type Hours, type Overview, type Provider, type TgStatus } from "@/lib/api";
import { usd, when } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const TABS = ["telegram", "ngan-sach", "gio", "nha-cung-cap"] as const;
type Tab = (typeof TABS)[number];
const msg = (x: unknown) => (x instanceof ApiError ? (x.code === "REAUTH_CANCELLED" ? "" : x.message) : "Có lỗi, thử lại.");

export default function SettingsPage() {
  const [tab, setTab] = useTabParam<Tab>(TABS, "telegram");
  return (
    <>
      <PageHeader title="Cài đặt" description="Mọi thay đổi ở đây được ghi vào nhật ký. Token và khóa API được mã hóa, chỉ hiện 4 ký tự cuối." />
      <Tabs
        label="Mục cài đặt"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "telegram", label: "Telegram", icon: <Send size={16} aria-hidden="true" /> },
          { id: "ngan-sach", label: "Ngân sách AI", icon: <Wallet size={16} aria-hidden="true" /> },
          { id: "gio", label: "Giờ làm việc", icon: <Clock size={16} aria-hidden="true" /> },
          { id: "nha-cung-cap", label: "Nhà cung cấp AI", icon: <Cpu size={16} aria-hidden="true" /> },
        ]}
      />
      <TabPanel id={tab}>
        {tab === "telegram" && <TelegramTab />}
        {tab === "ngan-sach" && <BudgetTab />}
        {tab === "gio" && <HoursTab />}
        {tab === "nha-cung-cap" && <ProvidersTab />}
      </TabPanel>
    </>
  );
}

// ---------------------------------------------------------------- Telegram
const KINDS: [string, string][] = [
  ["publish", "Bài mới"],
  ["report", "Báo cáo"],
  ["alert", "Cảnh báo"],
  ["approval", "Cần duyệt"],
];

function TelegramTab() {
  const { withReauth } = useShell();
  const toast = useToast();
  const confirm = useConfirm();
  const { data: st, error, reload } = useApi<TgStatus>("/telegram");
  const [code, setCode] = useState<{ code: string; expires_at: string; bot_username: string | null } | null>(null);
  const [editing, setEditing] = useState(false);

  // Chờ điện thoại nhắn mã: hỏi lại danh sách chat mỗi 3 giây tới khi mã hết hạn
  useEffect(() => {
    if (!code) return;
    const t = setInterval(reload, 3000);
    const stop = setTimeout(() => setCode(null), new Date(code.expires_at).getTime() - Date.now());
    return () => {
      clearInterval(t);
      clearTimeout(stop);
    };
  }, [code, reload]);

  async function saveToken(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const token = String(new FormData(form).get("token")).trim();
    try {
      const r = await withReauth(() => api<{ bot_username: string }>("/telegram/token", { method: "PUT", body: { token } }));
      form.reset();
      setEditing(false);
      toast(`Đã lưu. Bot @${r.bot_username} đã sẵn sàng.`);
      await reload();
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  async function newCode(canApprove: boolean) {
    try {
      setCode(await withReauth(() => api<typeof code>("/telegram/link-code", { method: "POST", body: { can_approve: canApprove } })));
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  async function patch(chatId: number, body: Record<string, unknown>) {
    try {
      await withReauth(() => api(`/telegram/chats/${chatId}`, { method: "PATCH", body }));
      await reload();
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  async function remove(chatId: number, title: string) {
    const ok = await confirm({ title: `Gỡ “${title}”?`, body: "Chat này sẽ không nhận tin nữa. Muốn nhận lại thì kết nối bằng mã mới.", confirmLabel: "Gỡ chat", tone: "danger" });
    if (ok === null) return;
    try {
      await api(`/telegram/chats/${chatId}`, { method: "DELETE" });
      toast(`Đã gỡ ${title}.`);
      await reload();
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  async function test() {
    try {
      await api("/telegram/test", { method: "POST" });
      toast("Đã xếp tin thử. Điện thoại sẽ nhận trong vài giây nếu worker Telegram đang chạy.");
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  if (!st) return error ? <ErrorAlert>{error}</ErrorAlert> : <Loading what="Telegram" />;

  return (
    <>
      <Card
        title="Bot Telegram"
        description="Kênh báo cáo của anh/chị: link bài mới, báo cáo, cảnh báo chi phí. Tạo bot bằng @BotFather rồi dán token vào đây."
        actions={st.configured ? <Badge tone="success">Đã kết nối</Badge> : <Badge>Chưa cài</Badge>}
      >
        {st.configured && !editing ? (
          <div className="row">
            <span>
              Bot <b>@{st.bot_username}</b>, token kết thúc bằng <code>…{st.token_last4}</code>, lưu lúc {when(st.token_updated_at)}.
            </span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
              <KeyRound size={14} aria-hidden="true" /> Đổi token
            </button>
          </div>
        ) : (
          <form className="form-inline" onSubmit={saveToken}>
            <label className="field">
              <span>Token do BotFather cấp</span>
              <input className="input" name="token" type="password" autoComplete="off" placeholder="123456789:AA…" required pattern="\d+:[A-Za-z0-9_\-]+" />
            </label>
            <button type="submit" className="btn btn-primary">
              Kiểm tra và lưu
            </button>
            {st.configured && (
              <button type="button" className="btn btn-secondary" onClick={() => setEditing(false)}>
                Hủy
              </button>
            )}
          </form>
        )}
      </Card>

      {st.configured && (
        <Card
          title="Chat nhận tin"
          description="Từng chat chọn được loại tin muốn nhận. Từ giờ yên lặng chỉ gửi cảnh báo khẩn."
          actions={
            <>
              {st.chats.length > 0 && (
                <button type="button" className="btn btn-secondary btn-sm" onClick={test}>
                  <Send size={14} aria-hidden="true" /> Gửi tin thử
                </button>
              )}
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => newCode(true)}>
                <ShieldCheck size={14} aria-hidden="true" /> Mã cho chat được duyệt việc
              </button>
              <button type="button" className="btn btn-primary btn-sm" onClick={() => newCode(false)}>
                <Link2 size={14} aria-hidden="true" /> Tạo mã kết nối
              </button>
            </>
          }
          flush
        >
          {code && (
            <div className="card-body">
              <div className="code-panel" role="status">
                <span>
                  Mở Telegram, nhắn cho bot <b>@{code.bot_username}</b> (hoặc trong nhóm có bot) đúng dòng sau:
                </span>
                <span className="code">/ketnoi {code.code}</span>
                <span className="muted xs">Mã dùng một lần, hết hạn lúc {when(code.expires_at)}. Danh sách tự cập nhật khi kết nối xong.</span>
              </div>
            </div>
          )}
          {st.chats.length === 0 ? (
            <Empty icon={<MessageCircle size={20} />} title="Chưa có chat nào">
              Bấm “Tạo mã kết nối” rồi nhắn mã cho bot từ điện thoại.
            </Empty>
          ) : (
            <div className="table-wrap">
              <table className="table chats">
                <thead>
                  <tr>
                    <th scope="col">Chat</th>
                    <th scope="col">Loại tin nhận</th>
                    <th scope="col">Bật</th>
                    <th scope="col" className="right">
                      <span className="sr-only">Thao tác</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {st.chats.map((c) => (
                    <tr key={c.chat_id} className={c.enabled ? "" : "dim"} data-chat={c.chat_id}>
                      <td>
                        <div className="cell-main">
                          <b>{c.title}</b>
                          <span>
                            Kết nối {when(c.added_at)}
                            {c.can_approve ? ", được duyệt việc" : ""}
                          </span>
                        </div>
                      </td>
                      <td>
                        <fieldset className="kinds">
                          <legend className="sr-only">Loại tin {c.title} nhận</legend>
                          {KINDS.map(([k, label]) => (
                            <label key={k} className="check">
                              <input
                                type="checkbox"
                                checked={c.receives.includes(k)}
                                onChange={(e) => patch(c.chat_id, { receives: e.target.checked ? [...c.receives, k] : c.receives.filter((x) => x !== k) })}
                              />
                              {label}
                            </label>
                          ))}
                        </fieldset>
                      </td>
                      <td>
                        <label className="switch">
                          <input type="checkbox" checked={c.enabled} aria-label={`Bật nhận tin cho ${c.title}`} onChange={() => patch(c.chat_id, { enabled: !c.enabled })} />
                          <span />
                        </label>
                      </td>
                      <td className="right">
                        <button type="button" className="btn btn-ghost btn-sm" aria-label={`Gỡ ${c.title}`} onClick={() => remove(c.chat_id, c.title)}>
                          <Trash2 size={15} aria-hidden="true" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  );
}

// ---------------------------------------------------------------- Ngân sách
function BudgetTab() {
  const toast = useToast();
  const { data: s, error } = useApi<{ budget: Budget }>("/settings");
  const { data: ov } = useApi<Overview>("/overview");
  const [saved, setSaved] = useState<Budget | null>(null);
  const b = saved ?? s?.budget;

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body: Budget = {
      month_usd: Number(f.get("month_usd")),
      day_usd: Number(f.get("day_usd")),
      day_burst_usd: Number(f.get("day_burst_usd")),
      alert_pct: Number(f.get("alert_pct")),
    };
    try {
      setSaved(await api<Budget>("/settings/budget", { method: "PUT", body }));
      toast("Đã lưu ngân sách.");
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  if (!b) return error ? <ErrorAlert>{error}</ErrorAlert> : <Loading what="ngân sách" />;
  const sp = ov?.budget;

  return (
    <>
      {sp && (
        <div className="grid-stats">
          <section className="card stat" aria-label="Đã dùng tháng này">
            <span className="stat-label">Đã dùng tháng này</span>
            <span className="stat-value">
              {usd(sp.month_usd)} <small>/ {usd(sp.month_cap_usd, 0)}</small>
            </span>
            <Bar value={sp.month_usd} max={sp.month_cap_usd} warnAt={sp.alert_pct} label="Chi phí tháng" />
          </section>
          <section className="card stat" aria-label="Đã dùng hôm nay">
            <span className="stat-label">Đã dùng hôm nay</span>
            <span className="stat-value">
              {usd(sp.today_usd)} <small>/ {usd(sp.allowed_today_usd)}</small>
            </span>
            <Bar value={sp.today_usd} max={sp.allowed_today_usd} warnAt={sp.alert_pct} label="Chi phí hôm nay" />
          </section>
        </div>
      )}
      <form onSubmit={save} key={JSON.stringify(b)}>
        <Card
          title="Giới hạn chi phí"
          description="Hệ thống kiểm trần trước mỗi lần gọi AI. Hết trần thì dừng gọi và báo khẩn qua Telegram."
          footer={
            <>
              <span className="hint">Áp dụng ngay cho lần gọi AI tiếp theo.</span>
              <button type="submit" className="btn btn-primary">
                Lưu ngân sách
              </button>
            </>
          }
        >
          <div className="form-grid">
            <label className="field">
              <span>Trần mỗi tháng (USD)</span>
              <input className="input" name="month_usd" type="number" min="0" step="0.01" defaultValue={b.month_usd} required />
            </label>
            <label className="field">
              <span>Báo khi tháng đạt (%)</span>
              <input className="input" name="alert_pct" type="number" min="10" max="100" step="1" defaultValue={b.alert_pct} required />
            </label>
            <label className="field">
              <span>Định mức mỗi ngày (USD)</span>
              <input className="input" name="day_usd" type="number" min="0" step="0.01" defaultValue={b.day_usd} required />
            </label>
            <div className="field">
              <label htmlFor="burst">Tối đa một ngày (USD)</label>
              <input className="input" id="burst" name="day_burst_usd" type="number" min="0" step="0.01" defaultValue={b.day_burst_usd} required aria-describedby="burst-help" />
              <span className="help" id="burst-help">
                Ngày bận được dùng tới mức này nếu các ngày trước còn dư.
              </span>
            </div>
          </div>
        </Card>
      </form>
    </>
  );
}

// ---------------------------------------------------------------- Giờ làm việc
function HoursTab() {
  const toast = useToast();
  const { data: s, error } = useApi<{ hours: Hours }>("/settings");
  const [saved, setSaved] = useState<Hours | null>(null);
  const h = saved ?? s?.hours;

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body = Object.fromEntries(["work_start", "work_end", "quiet_start", "quiet_end"].map((k) => [k, String(f.get(k))])) as Hours;
    try {
      setSaved(await api<Hours>("/settings/hours", { method: "PUT", body }));
      toast("Đã lưu giờ làm việc.");
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  if (!h) return error ? <ErrorAlert>{error}</ErrorAlert> : <Loading what="giờ làm việc" />;
  return (
    <form onSubmit={save} key={JSON.stringify(h)}>
      <Card
        title="Giờ làm việc và giờ yên lặng"
        description="Giờ máy chạy việc nặng, và giờ Telegram im lặng (chỉ gửi cảnh báo khẩn). Theo giờ Việt Nam."
        footer={
          <button type="submit" className="btn btn-primary">
            Lưu giờ
          </button>
        }
      >
        <div className="form-grid">
          <label className="field">
            <span>Bắt đầu làm việc</span>
            <input className="input" name="work_start" type="time" defaultValue={h.work_start} required />
          </label>
          <label className="field">
            <span>Kết thúc làm việc</span>
            <input className="input" name="work_end" type="time" defaultValue={h.work_end} required />
          </label>
          <label className="field">
            <span>Telegram im lặng từ</span>
            <input className="input" name="quiet_start" type="time" defaultValue={h.quiet_start} required />
          </label>
          <label className="field">
            <span>Im lặng đến</span>
            <input className="input" name="quiet_end" type="time" defaultValue={h.quiet_end} required />
          </label>
        </div>
      </Card>
    </form>
  );
}

// ---------------------------------------------------------------- Nhà cung cấp AI
function ProvidersTab() {
  const { withReauth } = useShell();
  const toast = useToast();
  const { data: list, error, reload } = useApi<Provider[]>("/providers");
  const [editing, setEditing] = useState("");
  const [testing, setTesting] = useState("");

  async function saveKey(e: React.FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault();
    const form = e.currentTarget;
    const api_key = String(new FormData(form).get("api_key")).trim();
    try {
      await withReauth(() => api(`/providers/${id}/key`, { method: "PUT", body: { api_key } }));
      form.reset();
      setEditing("");
      toast("Đã lưu khóa. Bấm “Kiểm tra kết nối” để thử.");
      await reload();
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  async function test(id: string) {
    setTesting(id);
    try {
      const r = await api<{ ok: boolean; detail: string }>(`/providers/${id}/test`, { method: "POST" });
      toast(r.ok ? `Kết nối tốt: ${r.detail}` : `Chưa kết nối được: ${r.detail}`, r.ok ? "success" : "error");
      await reload();
    } catch (x) {
      toast(msg(x), "error");
    } finally {
      setTesting("");
    }
  }

  if (!list) return error ? <ErrorAlert>{error}</ErrorAlert> : <Loading what="nhà cung cấp" />;
  return (
    <>
      <p className="alert info">
        <Plug size={16} aria-hidden="true" /> Agent gọi AI qua một cổng chung. Nhà cung cấp chính lỗi thì tự chuyển sang nhà cung cấp còn lại; chi phí mọi lần gọi được tính vào ngân sách.
      </p>
      {list.map((p) => (
        <Card
          key={p.id}
          title={p.display_name}
          description={
            p.configured
              ? `Khóa kết thúc bằng …${p.key_last4}, lưu lúc ${when(p.key_updated_at)}.${p.last_test_at ? ` Kiểm tra lần cuối ${when(p.last_test_at)}: ${p.last_test_detail}.` : ""}`
              : "Chưa có khóa API."
          }
          actions={
            <>
              {!p.configured ? (
                <Badge>Chưa có khóa</Badge>
              ) : p.last_test_ok ? (
                <Badge tone="success">Kết nối tốt</Badge>
              ) : p.last_test_ok === false ? (
                <Badge tone="danger">Lỗi kết nối</Badge>
              ) : (
                <Badge tone="warn">Chưa kiểm tra</Badge>
              )}
              {p.configured && editing !== p.id && (
                <>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(p.id)}>
                    <KeyRound size={14} aria-hidden="true" /> Đổi khóa
                  </button>
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => test(p.id)} disabled={testing !== ""}>
                    <Plug size={14} aria-hidden="true" /> {testing === p.id ? "Đang kiểm tra…" : "Kiểm tra kết nối"}
                  </button>
                </>
              )}
            </>
          }
          flush
        >
          {(!p.configured || editing === p.id) && (
            <div className="card-body">
              <form className="form-inline" onSubmit={(e) => saveKey(e, p.id)}>
                <label className="field">
                  <span>Khóa API</span>
                  <input className="input" name="api_key" type="password" autoComplete="off" minLength={20} required placeholder={p.id === "anthropic" ? "sk-ant-…" : "sk-…"} />
                </label>
                <button type="submit" className="btn btn-primary">
                  Lưu khóa
                </button>
                {p.configured && (
                  <button type="button" className="btn btn-secondary" onClick={() => setEditing("")}>
                    Hủy
                  </button>
                )}
              </form>
            </div>
          )}
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Model và giá của {p.display_name}</caption>
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col" className="right">
                    Giá vào / 1 triệu token
                  </th>
                  <th scope="col" className="right">
                    Giá ra / 1 triệu token
                  </th>
                  <th scope="col">Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {p.models.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="muted">
                      <Empty icon={<Cpu size={20} />} title="Chưa có model" />
                    </td>
                  </tr>
                ) : (
                  p.models.map((m) => (
                    <tr key={m.id} className={m.enabled ? "" : "dim"}>
                      <td>
                        <span className="mono-tag">{m.model_name}</span>
                      </td>
                      <td className="right nowrap">{usd(m.price_in_per_mtok)}</td>
                      <td className="right nowrap">{usd(m.price_out_per_mtok)}</td>
                      <td>{m.enabled ? <Badge tone="success">Đang dùng</Badge> : <Badge>Tắt để giữ ngân sách</Badge>}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </>
  );
}
