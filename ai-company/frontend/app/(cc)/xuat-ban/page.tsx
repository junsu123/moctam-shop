"use client";

import { ExternalLink, MessageSquarePlus, Newspaper, Pause, Play, ShieldAlert, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useConfirm } from "@/components/ui/dialog";
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader, type Tone } from "@/components/ui/primitives";
import { Tabs, TabPanel, useTabParam } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type GateConfig, type PublishItem, type PublishList, type PublishSettings } from "@/lib/api";
import { actorLabel, when } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const TABS = ["sap-dang", "da-dang", "bi-chan", "lich", "content-gate"] as const;
type Tab = (typeof TABS)[number];
const GROUP: Partial<Record<Tab, "queue" | "live" | "blocked">> = { "sap-dang": "queue", "da-dang": "live", "bi-chan": "blocked" };
const STATUS: Record<string, [string, Tone]> = {
  scheduled: ["Chờ giờ đăng", "info"],
  publishing: ["Đang đăng", "info"],
  published: ["Đã đăng", "success"],
  retracted: ["Đã gỡ", "neutral"],
  blocked: ["Bị chặn", "danger"],
  failed: ["Lỗi", "danger"],
  cancelled: ["Đã hủy", "neutral"],
};
const DAYS = ["", "T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const msg = (x: unknown) => (x instanceof ApiError ? (x.code === "REAUTH_CANCELLED" ? "" : x.message) : "Có lỗi, thử lại.");

export default function PublishingPage() {
  const [tab, setTab] = useTabParam<Tab>(TABS, "sap-dang");
  const group = GROUP[tab] ?? "queue";
  const { data, error, reload } = useApi<PublishList>(`/publishing?group=${group}`);
  const confirm = useConfirm();
  const toast = useToast();

  async function togglePause() {
    if (!data) return;
    const pausing = !data.paused;
    const reason = pausing
      ? await confirm({
          title: "Tạm dừng tự xuất bản?",
          body: "Bài trong hàng chờ được giữ nguyên, không bài nào lên website cho tới khi anh/chị cho chạy lại. Trên Telegram: /tamdung xuatban.",
          confirmLabel: "Tạm dừng",
          tone: "warn",
          reason: { label: "Lý do (ghi vào nhật ký)" },
        })
      : "";
    if (reason === null) return;
    try {
      await api("/publishing/pause", { method: "POST", body: { paused: pausing, reason } });
      toast(pausing ? "Đã tạm dừng tự xuất bản." : "Đã cho tự xuất bản chạy lại.");
      await reload();
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    }
  }

  return (
    <>
      <PageHeader
        title="Xuất bản"
        description="FAQ và blog agent tự đăng lên website. Mỗi bài qua 5 lớp: Content Gate, review của Giám đốc Marketing, anh/chị duyệt nếu là chủ đề nhạy cảm, lịch đăng theo giờ vàng, website kiểm lần cuối."
        actions={
          data && (
            <>
              <Badge tone="info">Giai đoạn {data.phase}</Badge>
              <button type="button" className={`btn ${data.paused ? "btn-primary" : "btn-secondary"}`} onClick={togglePause}>
                {data.paused ? <Play size={16} aria-hidden="true" /> : <Pause size={16} aria-hidden="true" />} {data.paused ? "Cho chạy lại" : "Tạm dừng xuất bản"}
              </button>
            </>
          )
        }
      />
      {data?.paused && (
        <p className="alert warn" role="status">
          Tự xuất bản đang tạm dừng{data.paused_reason ? ` (${data.paused_reason})` : ""}. Bài trong hàng chờ được giữ nguyên.
        </p>
      )}
      <Tabs
        label="Xuất bản"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "sap-dang", label: "Sắp đăng", count: data?.counts.queue },
          { id: "da-dang", label: "Đã đăng", count: data?.counts.live },
          { id: "bi-chan", label: "Bị chặn", count: data?.counts.blocked },
          { id: "lich", label: "Lịch đăng bài" },
          { id: "content-gate", label: "Content Gate" },
        ]}
      />
      <TabPanel id={tab}>
        {tab === "lich" ? (
          <ScheduleTab />
        ) : tab === "content-gate" ? (
          <GateTab />
        ) : error ? (
          <ErrorAlert>{error}</ErrorAlert>
        ) : !data ? (
          <Loading what="hàng chờ xuất bản" />
        ) : data.items.length === 0 ? (
          <Card>
            <Empty icon={<Newspaper size={20} />} title={tab === "sap-dang" ? "Chưa có bài nào chờ đăng" : tab === "da-dang" ? "Chưa đăng bài nào" : "Không có bài nào bị chặn"}>
              Bài viết xong và được Giám đốc Marketing duyệt sẽ vào đây, chờ đúng khung giờ của lịch đăng.
            </Empty>
          </Card>
        ) : (
          <ul className="pub-list">
            {data.items.map((it) => (
              <PubItem key={it.id} it={it} onChange={reload} />
            ))}
          </ul>
        )}
      </TabPanel>
    </>
  );
}

function PubItem({ it, onChange }: { it: PublishItem; onChange: () => Promise<void> }) {
  const confirm = useConfirm();
  const toast = useToast();
  const st = STATUS[it.status] ?? [it.status, "neutral"];
  const live = it.status === "published";

  async function remove() {
    const reason = await confirm({
      title: live ? "Gỡ bài khỏi website?" : "Hủy bài này?",
      body: live ? "Bài biến khỏi website ngay; agent ghi nhớ lý do để lần sau không lặp lại." : "Bài không được đăng nữa.",
      confirmLabel: live ? "Gỡ bài" : "Hủy bài",
      tone: "danger",
      reason: { label: "Lý do (agent sẽ học từ lý do này)" },
    });
    if (reason === null) return;
    try {
      await api(`/publishing/${it.id}/unpublish`, { method: "POST", body: { reason: reason || (live ? "Owner gỡ trên trang quản trị" : "Owner hủy") } });
      toast(live ? "Đã gỡ bài." : "Đã hủy bài.");
      await onChange();
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    }
  }

  async function feedback() {
    const text = await confirm({
      title: "Góp ý cho bài này",
      body: "Agent viết bài ghi nhớ góp ý và áp dụng cho những bài sau.",
      confirmLabel: "Gửi góp ý",
      reason: { label: "Góp ý" },
    });
    if (!text) return;
    try {
      await api(`/publishing/${it.id}/feedback`, { method: "POST", body: { text } });
      toast("Đã ghi góp ý.");
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    }
  }

  return (
    <li className="pub-item">
      <div className="pub-head">
        <div className="pub-title">
          <Badge plain>{it.kind === "faq" ? "FAQ" : "Blog"}</Badge>
          <b>{it.title}</b>
        </div>
        <Badge tone={st[1]}>{st[0]}</Badge>
      </div>
      <p className="pub-excerpt">{it.excerpt.replace(/<[^>]+>/g, " ")}</p>
      <div className="pub-meta">
        <span>{it.agent_name ?? it.agent_key}</span>
        {it.status === "scheduled" && it.slot_at && <span>Đăng lúc {when(it.slot_at)}</span>}
        {it.published_at && <span>Đăng {when(it.published_at)}</span>}
        {it.retracted_at && (
          <span>
            Gỡ {when(it.retracted_at)} bởi {actorLabel(it.retracted_by ?? "")}
            {it.retract_reason ? `: ${it.retract_reason}` : ""}
          </span>
        )}
        {it.approval_id && <span>Anh/chị đã duyệt</span>}
        {it.task_id && <Link href={`/viec/${it.task_id}`}>Xem việc</Link>}
        {it.url && live && (
          <a href={it.url} target="_blank" rel="noopener noreferrer">
            Mở bài <ExternalLink size={12} aria-hidden="true" />
          </a>
        )}
      </div>
      {(it.gate.topics?.length || it.gate.blocked?.length || it.last_error) && (
        <div className="pub-gate">
          {it.gate.topics?.map((t) => (
            <Badge key={t} tone="warn">
              {t}
            </Badge>
          ))}
          {it.status === "blocked" && (
            <span className="note">
              <ShieldAlert size={14} aria-hidden="true" /> {it.last_error}
            </span>
          )}
          {it.status !== "blocked" && it.last_error && <span className="muted">{it.last_error}</span>}
        </div>
      )}
      {(live || it.status === "scheduled" || it.status === "retracted") && (
        <div className="btn-row">
          {(live || it.status === "scheduled") && (
            <button type="button" className="btn btn-danger-outline btn-sm" onClick={remove}>
              <Trash2 size={14} aria-hidden="true" /> {live ? "Gỡ bài" : "Hủy bài"}
            </button>
          )}
          {(live || it.status === "retracted") && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={feedback}>
              <MessageSquarePlus size={14} aria-hidden="true" /> Góp ý
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function ScheduleTab() {
  const { data: s, error, reload } = useApi<PublishSettings>("/publishing/settings");
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorAlert>{error}</ErrorAlert>;
  if (!s) return <Loading what="lịch đăng" />;

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    try {
      await api("/publishing/settings", {
        method: "PUT",
        body: {
          phase: Number(f.get("phase")),
          auto_progress: f.get("auto") === "on",
          window_start: f.get("ws"),
          window_end: f.get("we"),
          min_gap_hours: Number(f.get("gap")),
          holidays: String(f.get("holidays") || "")
            .split(/[\s,]+/)
            .map((x) => x.trim())
            .filter(Boolean),
        },
      });
      toast("Đã lưu lịch đăng.");
      await reload();
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card title="Giai đoạn" description="Bắt đầu thấp, tăng dần khi bài đăng không bị gỡ. Anh/chị gỡ ≥ 2 bài trong 7 ngày thì tự lùi một giai đoạn và báo Telegram.">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Giai đoạn</th>
                <th scope="col">Blog</th>
                <th scope="col">FAQ</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(s.phases).map(([k, p]) => (
                <tr key={k} className={Number(k) === s.phase ? "current" : ""}>
                  <td className="nowrap">
                    {k} {Number(k) === s.phase && <Badge tone="info">Đang dùng</Badge>}
                  </td>
                  <td>
                    {p.blog.per_week ? `${p.blog.per_week} bài/tuần` : `${p.blog.per_day} bài/ngày`}: {p.blog.weekdays.length === 7 ? "mỗi ngày" : p.blog.weekdays.map((d) => DAYS[d]).join(", ")}, {p.blog.times.join(", ")}
                  </td>
                  <td>
                    Tối đa {p.faq.per_day} bài/ngày: {p.faq.times.join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Chỉnh lịch">
        <form onSubmit={save}>
          <div className="form-grid">
            <label className="field">
              <span>Giai đoạn hiện tại</span>
              <select className="input" name="phase" defaultValue={s.phase}>
                <option value="1">1. Thử</option>
                <option value="2">2. Ổn định</option>
                <option value="3">3. Đầy đủ</option>
              </select>
            </label>
            <label className="field">
              <span>Cách nhau tối thiểu (giờ)</span>
              <input className="input" name="gap" type="number" min="0" max="12" step="0.5" defaultValue={s.min_gap_hours} />
            </label>
            <label className="field">
              <span>Không đăng trước</span>
              <input className="input" name="ws" type="time" defaultValue={s.window_start} />
            </label>
            <label className="field">
              <span>Không đăng sau</span>
              <input className="input" name="we" type="time" defaultValue={s.window_end} />
            </label>
          </div>
          <label className="field">
            <span>Ngày nghỉ không đăng (mỗi ngày một dòng, dạng 2027-02-06)</span>
            <textarea className="textarea" name="holidays" rows={3} defaultValue={s.holidays.join("\n")} />
          </label>
          <label className="check">
            <input type="checkbox" name="auto" defaultChecked={s.auto_progress} /> Tự lên giai đoạn khi đủ điều kiện (2 tuần, rồi 4 tuần, tỉ lệ gỡ dưới 10%)
          </label>
          <div className="btn-row">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              Lưu lịch
            </button>
          </div>
        </form>
      </Card>
      <Card title="Khung giờ sắp tới">
        {s.upcoming.length ? (
          <ul className="plain-list">
            {s.upcoming.map((t) => (
              <li key={t}>{when(t)}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">Chưa có bài nào được xếp lịch.</p>
        )}
      </Card>
    </>
  );
}

function GateTab() {
  const { data: g, error, reload } = useApi<GateConfig>("/publishing/gate");
  const toast = useToast();
  const [res, setRes] = useState<{ ok: boolean; blocked: string[]; topics: string[] } | null>(null);
  if (error) return <ErrorAlert>{error}</ErrorAlert>;
  if (!g) return <Loading what="Content Gate" />;
  const lines = (v: FormDataEntryValue | null) =>
    String(v || "")
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const topics: Record<string, string[]> = {};
    for (const l of lines(f.get("topics"))) {
      const [k, v] = l.split(":");
      if (k && v) topics[k.trim()] = v.split(",").map((x) => x.trim()).filter(Boolean);
    }
    try {
      await api("/publishing/gate", {
        method: "PUT",
        body: { ...g, risk_phrases: lines(f.get("risk")), compare_phrases: lines(f.get("compare")), owner_topics: topics, use_classifier: f.get("cls") === "on" },
      });
      toast("Đã lưu Content Gate.");
      await reload();
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    }
  }

  async function test(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      setRes(await api("/publishing/gate/test", { method: "POST", body: { kind: f.get("kind"), title: f.get("title"), body: f.get("body") } }));
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    }
  }

  return (
    <>
      <Card title="Thử một đoạn văn" description="Xem Content Gate sẽ chặn, hỏi anh/chị, hay cho qua (chỉ phần kiểm tra tất định, không tốn tiền AI).">
        <form onSubmit={test}>
          <div className="form-grid">
            <label className="field">
              <span>Loại</span>
              <select className="input" name="kind" defaultValue="faq">
                <option value="faq">FAQ</option>
                <option value="blog">Blog</option>
              </select>
            </label>
            <label className="field">
              <span>Tiêu đề</span>
              <input className="input" name="title" required />
            </label>
          </div>
          <label className="field">
            <span>Nội dung</span>
            <textarea className="textarea" name="body" rows={4} required />
          </label>
          <div className="btn-row">
            <button type="submit" className="btn btn-secondary">
              Thử
            </button>
          </div>
        </form>
        {res && (
          <div className="gate-result" role="status">
            {res.blocked.length ? (
              <>
                <Badge tone="danger">Bị chặn, không tự đăng</Badge>
                <ul className="plain-list">
                  {res.blocked.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              </>
            ) : res.topics.length ? (
              <Badge tone="warn">Cần anh/chị duyệt: {res.topics.join(", ")}</Badge>
            ) : (
              <Badge tone="success">Qua (còn bộ phân loại rủi ro chạy khi đăng thật)</Badge>
            )}
          </div>
        )}
      </Card>
      <Card title="Từ điển" description="Chỉ anh/chị sửa được. So khớp nguyên cụm, viết không dấu cũng bị bắt (với cụm từ 2 chữ trở lên).">
        <form onSubmit={save}>
          <div className="form-grid">
            <label className="field">
              <span>Cụm rủi ro: chặn, không bao giờ tự đăng (mỗi dòng một cụm)</span>
              <textarea className="textarea" name="risk" rows={10} defaultValue={g.risk_phrases.join("\n")} />
            </label>
            <label className="field">
              <span>So sánh, tuyệt đối hóa: chặn</span>
              <textarea className="textarea" name="compare" rows={10} defaultValue={g.compare_phrases.join("\n")} />
            </label>
          </div>
          <label className="field">
            <span>Chủ đề cần anh/chị duyệt (mỗi dòng: chủ đề: từ, từ)</span>
            <textarea
              className="textarea"
              name="topics"
              rows={5}
              defaultValue={Object.entries(g.owner_topics)
                .map(([k, v]) => `${k}: ${v.join(", ")}`)
                .join("\n")}
            />
          </label>
          <label className="check">
            <input type="checkbox" name="cls" defaultChecked={g.use_classifier} /> Dùng thêm bộ phân loại rủi ro (model rẻ) cho phần còn lại
          </label>
          <div className="btn-row">
            <button type="submit" className="btn btn-primary">
              Lưu từ điển
            </button>
          </div>
        </form>
      </Card>
    </>
  );
}
