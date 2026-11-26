"use client";

import { useEffect, useState } from "react";

import { Bar, Loading, useFlash } from "@/components/bits";
import { useShell } from "@/components/shell";
import { api, ApiError, type Budget, type Hours, type Overview, type Provider, type TgStatus } from "@/lib/api";
import { usd, when } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const err = (x: unknown) => (x instanceof ApiError ? (x.code === "REAUTH_CANCELLED" ? "" : x.message) : "Có lỗi, thử lại.");

export default function SettingsPage() {
  return (
    <>
      <header className="page-head">
        <div>
          <h1>Cài đặt</h1>
          <p className="muted">Mọi thay đổi ở đây được ghi vào nhật ký. Token và khóa API được mã hóa, chỉ hiện 4 ký tự cuối.</p>
        </div>
      </header>
      <nav className="toc" aria-label="Các mục cài đặt">
        <a href="#telegram">Telegram</a>
        <a href="#ngan-sach">Ngân sách AI</a>
        <a href="#gio">Giờ làm việc</a>
        <a href="#nha-cung-cap">Nhà cung cấp AI</a>
      </nav>
      <TelegramSection />
      <BudgetSection />
      <HoursSection />
      <ProvidersSection />
    </>
  );
}

// ---------------------------------------------------------------- Telegram
const KINDS: [string, string][] = [
  ["publish", "Bài mới đăng"],
  ["report", "Báo cáo"],
  ["alert", "Cảnh báo"],
  ["approval", "Việc cần duyệt"],
];

function TelegramSection() {
  const { withReauth } = useShell();
  const { data: st, error: loadErr, reload: load } = useApi<TgStatus>("/telegram");
  const [code, setCode] = useState<{ code: string; expires_at: string; bot_username: string | null } | null>(null);
  const [editing, setEditing] = useState(false);
  const [flash, say] = useFlash();

  // Chờ điện thoại nhắn mã: hỏi lại danh sách chat mỗi 3 giây cho tới khi mã hết hạn
  useEffect(() => {
    if (!code) return;
    const t = setInterval(load, 3000);
    const stop = setTimeout(() => setCode(null), new Date(code.expires_at).getTime() - Date.now());
    return () => {
      clearInterval(t);
      clearTimeout(stop);
    };
  }, [code, load]);

  async function saveToken(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const token = String(new FormData(form).get("token")).trim();
    try {
      const r = await withReauth(() => api<{ bot_username: string }>("/telegram/token", { method: "PUT", body: { token } }));
      form.reset();
      setEditing(false);
      say(`Đã lưu. Bot @${r.bot_username} đã sẵn sàng.`);
      await load();
    } catch (x) {
      const m = err(x);
      if (m) say(m, "err");
    }
  }

  async function newCode(canApprove: boolean) {
    try {
      const r = await withReauth(() => api<typeof code>("/telegram/link-code", { method: "POST", body: { can_approve: canApprove } }));
      setCode(r);
    } catch (x) {
      const m = err(x);
      if (m) say(m, "err");
    }
  }

  async function patch(chatId: number, body: Record<string, unknown>) {
    try {
      await withReauth(() => api(`/telegram/chats/${chatId}`, { method: "PATCH", body }));
      await load();
    } catch (x) {
      const m = err(x);
      if (m) say(m, "err");
    }
  }

  async function remove(chatId: number, title: string) {
    if (!window.confirm(`Gỡ “${title}”? Chat này sẽ không nhận tin nữa.`)) return;
    try {
      await api(`/telegram/chats/${chatId}`, { method: "DELETE" });
      await load();
    } catch (x) {
      say(err(x), "err");
    }
  }

  async function test() {
    try {
      await api("/telegram/test", { method: "POST" });
      say("Đã xếp tin thử. Điện thoại sẽ nhận trong vài giây nếu worker Telegram đang chạy.");
    } catch (x) {
      say(err(x), "err");
    }
  }

  const linked = st?.chats.length ?? 0;

  return (
    <section id="telegram" className="setting" aria-labelledby="tg-h">
      <div className="setting-head">
        <h2 id="tg-h">Telegram</h2>
        <p className="muted">Kênh báo cáo của anh/chị: link bài mới, báo cáo, cảnh báo chi phí.</p>
      </div>
      {flash}
      {loadErr && <p className="err">{loadErr}</p>}
      {!st ? (
        <Loading what="Telegram" />
      ) : (
        <>
          <div className="step">
            <h3>Token bot</h3>
            {st.configured && !editing ? (
              <p>
                Bot <b>@{st.bot_username}</b>, token kết thúc bằng <code>…{st.token_last4}</code>, lưu {when(st.token_updated_at)}.{" "}
                <button type="button" className="link" onClick={() => setEditing(true)}>
                  Đổi token
                </button>
              </p>
            ) : (
              <form className="inline" onSubmit={saveToken}>
                <label className="grow">
                  Token do BotFather cấp
                  <input name="token" type="password" autoComplete="off" placeholder="123456789:AA…" required pattern="\d+:[A-Za-z0-9_\-]+" />
                </label>
                <button type="submit" className="btn">
                  Kiểm tra và lưu
                </button>
                {st.configured && (
                  <button type="button" className="btn ghost" onClick={() => setEditing(false)}>
                    Hủy
                  </button>
                )}
              </form>
            )}
          </div>

          {st.configured && (
            <div className="step">
              <h3>Chat nhận tin</h3>
              {code ? (
                <div className="code-box" role="status">
                  <p>
                    Mở Telegram, nhắn cho bot <b>@{code.bot_username}</b> (hoặc trong nhóm có bot) đúng dòng sau:
                  </p>
                  <p className="code">/ketnoi {code.code}</p>
                  <p className="muted small">Mã dùng một lần, hết hạn lúc {when(code.expires_at)}. Trang tự cập nhật khi kết nối xong.</p>
                  <button type="button" className="link" onClick={() => setCode(null)}>
                    Đóng
                  </button>
                </div>
              ) : (
                <div className="row">
                  <button type="button" className="btn" onClick={() => newCode(false)}>
                    Tạo mã kết nối
                  </button>
                  <button type="button" className="btn ghost" onClick={() => newCode(true)}>
                    Tạo mã cho chat được duyệt việc
                  </button>
                </div>
              )}
              {linked === 0 ? (
                <p className="muted">Chưa có chat nào. Tạo mã rồi nhắn cho bot từ điện thoại.</p>
              ) : (
                <ul className="chats">
                  {st.chats.map((c) => (
                    <li key={c.chat_id} className={c.enabled ? "" : "off"}>
                      <div className="who">
                        <span className="name">{c.title}</span>
                        <span className="muted small">
                          Kết nối {when(c.added_at)}
                          {c.can_approve ? ", được duyệt việc" : ""}
                        </span>
                      </div>
                      <fieldset className="kinds">
                        <legend className="sr-only">Loại tin {c.title} nhận</legend>
                        {KINDS.map(([k, label]) => (
                          <label key={k} className="check">
                            <input
                              type="checkbox"
                              checked={c.receives.includes(k)}
                              onChange={(e) =>
                                patch(c.chat_id, {
                                  receives: e.target.checked ? [...c.receives, k] : c.receives.filter((x) => x !== k),
                                })
                              }
                            />
                            {label}
                          </label>
                        ))}
                      </fieldset>
                      <div className="row">
                        <button type="button" className="btn ghost" onClick={() => patch(c.chat_id, { enabled: !c.enabled })}>
                          {c.enabled ? "Tắt" : "Bật"}
                        </button>
                        <button type="button" className="btn ghost" onClick={() => remove(c.chat_id, c.title)}>
                          Gỡ
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {linked > 0 && (
                <button type="button" className="btn ghost" onClick={test}>
                  Gửi tin thử
                </button>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- Ngân sách
function BudgetSection() {
  const [b, setB] = useState<Budget | null>(null);
  const [spend, setSpend] = useState<Overview["budget"] | null>(null);
  const [flash, say] = useFlash();

  useEffect(() => {
    api<{ budget: Budget }>("/settings")
      .then((s) => setB(s.budget))
      .catch((x) => say(err(x), "err"));
    api<Overview>("/overview")
      .then((o) => setSpend(o.budget))
      .catch(() => undefined);
  }, [say]);

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
      setB(await api<Budget>("/settings/budget", { method: "PUT", body }));
      say("Đã lưu ngân sách.");
    } catch (x) {
      say(err(x), "err");
    }
  }

  return (
    <section id="ngan-sach" className="setting" aria-labelledby="b-h">
      <div className="setting-head">
        <h2 id="b-h">Ngân sách AI</h2>
        <p className="muted">Hệ thống kiểm trần trước mỗi lần gọi AI. Hết trần thì dừng gọi và báo khẩn qua Telegram.</p>
      </div>
      {flash}
      {spend && (
        <div className="spend wide">
          <div>
            <p className="small muted">Tháng này</p>
            <p className="figure">
              {usd(spend.month_usd)} <span className="muted small">/ {usd(spend.month_cap_usd, 0)}</span>
            </p>
            <Bar value={spend.month_usd} max={spend.month_cap_usd} warnAt={spend.alert_pct} label="Chi phí tháng" />
          </div>
          <div>
            <p className="small muted">Hôm nay</p>
            <p className="figure">
              {usd(spend.today_usd)} <span className="muted small">/ {usd(spend.allowed_today_usd)}</span>
            </p>
            <Bar value={spend.today_usd} max={spend.allowed_today_usd} warnAt={spend.alert_pct} label="Chi phí hôm nay" />
          </div>
        </div>
      )}
      {!b ? (
        <Loading what="ngân sách" />
      ) : (
        <form className="fields" onSubmit={save} key={JSON.stringify(b)}>
          <label>
            Trần mỗi tháng (USD)
            <input name="month_usd" type="number" min="0" step="0.01" defaultValue={b.month_usd} required />
          </label>
          <label>
            Định mức mỗi ngày (USD)
            <input name="day_usd" type="number" min="0" step="0.01" defaultValue={b.day_usd} required />
          </label>
          <label>
            Tối đa một ngày (USD)
            <input name="day_burst_usd" type="number" min="0" step="0.01" defaultValue={b.day_burst_usd} required />
            <span className="hint">Ngày bận được dùng tới mức này nếu các ngày trước còn dư.</span>
          </label>
          <label>
            Báo khi tháng đạt (%)
            <input name="alert_pct" type="number" min="10" max="100" step="1" defaultValue={b.alert_pct} required />
          </label>
          <div className="row">
            <button type="submit" className="btn">
              Lưu ngân sách
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- Giờ làm việc
function HoursSection() {
  const [h, setH] = useState<Hours | null>(null);
  const [flash, say] = useFlash();

  useEffect(() => {
    api<{ hours: Hours }>("/settings")
      .then((s) => setH(s.hours))
      .catch((x) => say(err(x), "err"));
  }, [say]);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body = Object.fromEntries(["work_start", "work_end", "quiet_start", "quiet_end"].map((k) => [k, String(f.get(k))])) as Hours;
    try {
      setH(await api<Hours>("/settings/hours", { method: "PUT", body }));
      say("Đã lưu giờ làm việc.");
    } catch (x) {
      say(err(x), "err");
    }
  }

  return (
    <section id="gio" className="setting" aria-labelledby="h-h">
      <div className="setting-head">
        <h2 id="h-h">Giờ làm việc</h2>
        <p className="muted">Giờ máy chạy việc nặng, và giờ Telegram im lặng (chỉ gửi cảnh báo khẩn). Theo giờ Việt Nam.</p>
      </div>
      {flash}
      {!h ? (
        <Loading what="giờ làm việc" />
      ) : (
        <form className="fields" onSubmit={save} key={JSON.stringify(h)}>
          <label>
            Bắt đầu làm việc
            <input name="work_start" type="time" defaultValue={h.work_start} required />
          </label>
          <label>
            Kết thúc làm việc
            <input name="work_end" type="time" defaultValue={h.work_end} required />
          </label>
          <label>
            Telegram im lặng từ
            <input name="quiet_start" type="time" defaultValue={h.quiet_start} required />
          </label>
          <label>
            Đến
            <input name="quiet_end" type="time" defaultValue={h.quiet_end} required />
          </label>
          <div className="row">
            <button type="submit" className="btn">
              Lưu giờ
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- Nhà cung cấp AI
function ProvidersSection() {
  const { withReauth } = useShell();
  const { data: list, error: loadErr, reload: load } = useApi<Provider[]>("/providers");
  const [editing, setEditing] = useState<string>("");
  const [testing, setTesting] = useState<string>("");
  const [flash, say] = useFlash();

  async function saveKey(e: React.FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault();
    const form = e.currentTarget;
    const api_key = String(new FormData(form).get("api_key")).trim();
    try {
      await withReauth(() => api(`/providers/${id}/key`, { method: "PUT", body: { api_key } }));
      form.reset();
      setEditing("");
      say("Đã lưu khóa. Bấm “Kiểm tra kết nối” để thử.");
      await load();
    } catch (x) {
      const m = err(x);
      if (m) say(m, "err");
    }
  }

  async function test(id: string) {
    setTesting(id);
    try {
      const r = await api<{ ok: boolean; detail: string }>(`/providers/${id}/test`, { method: "POST" });
      say(r.ok ? `Kết nối tốt: ${r.detail}` : `Chưa kết nối được: ${r.detail}`, r.ok ? "ok" : "err");
      await load();
    } catch (x) {
      say(err(x), "err");
    } finally {
      setTesting("");
    }
  }

  return (
    <section id="nha-cung-cap" className="setting" aria-labelledby="p-h">
      <div className="setting-head">
        <h2 id="p-h">Nhà cung cấp AI</h2>
        <p className="muted">Agent gọi AI qua một cổng chung: nhà cung cấp chính lỗi thì tự chuyển sang nhà cung cấp còn lại.</p>
      </div>
      {flash}
      {loadErr && <p className="err">{loadErr}</p>}
      {!list ? (
        <Loading what="nhà cung cấp" />
      ) : (
        list.map((p) => (
          <div key={p.id} className="step provider">
            <div className="provider-head">
              <h3>{p.display_name}</h3>
              <span className={`tag ${p.last_test_ok ? "s-active" : p.configured ? (p.last_test_ok === false ? "s-degraded" : "s-waiting_approval") : "s-disabled"}`}>
                {!p.configured ? "Chưa có khóa" : p.last_test_ok ? "Kết nối tốt" : p.last_test_ok === false ? "Lỗi kết nối" : "Chưa kiểm tra"}
              </span>
            </div>
            {p.configured && editing !== p.id ? (
              <p>
                Khóa kết thúc bằng <code>…{p.key_last4}</code>, lưu {when(p.key_updated_at)}.
                {p.last_test_at && (
                  <>
                    {" "}
                    Lần kiểm tra cuối {when(p.last_test_at)}: {p.last_test_detail}.
                  </>
                )}
              </p>
            ) : (
              <form className="inline" onSubmit={(e) => saveKey(e, p.id)}>
                <label className="grow">
                  Khóa API
                  <input name="api_key" type="password" autoComplete="off" minLength={20} required placeholder={p.id === "anthropic" ? "sk-ant-…" : "sk-…"} />
                </label>
                <button type="submit" className="btn">
                  Lưu khóa
                </button>
                {p.configured && (
                  <button type="button" className="btn ghost" onClick={() => setEditing("")}>
                    Hủy
                  </button>
                )}
              </form>
            )}
            {p.configured && editing !== p.id && (
              <div className="row">
                <button type="button" className="btn ghost" onClick={() => test(p.id)} disabled={testing !== ""}>
                  {testing === p.id ? "Đang kiểm tra…" : "Kiểm tra kết nối"}
                </button>
                <button type="button" className="btn ghost" onClick={() => setEditing(p.id)}>
                  Đổi khóa
                </button>
              </div>
            )}
            <table className="models">
              <caption className="sr-only">Model và giá của {p.display_name}</caption>
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Giá vào / 1 triệu token</th>
                  <th scope="col">Giá ra / 1 triệu token</th>
                  <th scope="col">Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {p.models.map((m) => (
                  <tr key={m.id} className={m.enabled ? "" : "off"}>
                    <td>{m.model_name}</td>
                    <td>{usd(m.price_in_per_mtok)}</td>
                    <td>{usd(m.price_out_per_mtok)}</td>
                    <td>{m.enabled ? "Đang dùng" : "Tắt để giữ ngân sách"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))
      )}
    </section>
  );
}
