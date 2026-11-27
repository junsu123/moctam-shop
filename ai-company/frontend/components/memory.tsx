"use client";

import { Archive, ChevronDown, ChevronRight, Inbox, Search, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { useConfirm } from "@/components/ui/dialog";
import { Badge, Card, Empty, ErrorAlert, Loading } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type MemoryDetail, type MemoryItem, type RetrievalResult } from "@/lib/api";
import { ago, when } from "@/lib/format";
import { actor, CATEGORY, MEM_STATUS, MEM_TYPE, scopeLabel, TRUST } from "@/lib/labels";

const n2 = (x: number) => x.toLocaleString("vi-VN", { maximumFractionDigits: 2 });

/** Danh sách trí nhớ có lọc loại/phạm vi/tìm kiếm; bấm một dòng để xem đầy đủ và ai đã truy hồi. */
export function MemoryBrowser({
  agent,
  scope,
  scopeOptions,
  allowRetire,
  reloadKey = 0,
}: {
  agent?: string;
  scope?: string;
  scopeOptions?: { value: string; label: string }[];
  allowRetire?: boolean;
  reloadKey?: number;
}) {
  const [type, setType] = useState("");
  const [sc, setSc] = useState("");
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [data, setData] = useState<{ total: number; items: MemoryItem[] } | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<string>("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let alive = true;
    const p = new URLSearchParams();
    if (agent) p.set("agent", agent);
    if (scope || sc) p.set("scope", scope || sc);
    if (type) p.set("type", type);
    if (applied) p.set("q", applied);
    p.set("limit", "100");
    api<{ total: number; items: MemoryItem[] }>(`/memory?${p}`)
      .then((d) => alive && (setData(d), setErr("")))
      .catch((x) => alive && setErr(x instanceof ApiError ? x.message : "Không tải được trí nhớ."));
    return () => {
      alive = false;
    };
  }, [agent, scope, sc, type, applied, version, reloadKey]);

  return (
    <Card
      title={data ? `${data.total.toLocaleString("vi-VN")} mục` : "Trí nhớ"}
      actions={
        <form
          className="filters"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(q.trim());
          }}
        >
          <select className="input" aria-label="Loại trí nhớ" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">Mọi loại</option>
            {Object.entries(MEM_TYPE).map(([k, [label]]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
          {scopeOptions && (
            <select className="input" aria-label="Phạm vi" value={sc} onChange={(e) => setSc(e.target.value)}>
              <option value="">Mọi phạm vi</option>
              {scopeOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          )}
          <label className="input-icon">
            <Search size={16} aria-hidden="true" />
            <input className="input" type="search" placeholder="Tìm (có dấu hoặc không dấu)" aria-label="Tìm trong trí nhớ" value={q}
              onChange={(e) => setQ(e.target.value)} onBlur={() => setApplied(q.trim())} />
          </label>
        </form>
      }
      flush
    >
      {err && (
        <div className="card-body">
          <ErrorAlert>{err}</ErrorAlert>
        </div>
      )}
      {!data ? (
        <Loading what="trí nhớ" />
      ) : data.items.length === 0 ? (
        <Empty icon={<Inbox size={20} />} title="Chưa có mục nào">
          Trí nhớ được ghi khi agent làm việc (Sprint 4) hoặc khi anh/chị thêm kiến thức.
        </Empty>
      ) : (
        <ul className="mem-list">
          {data.items.map((m) => (
            <MemoryRow key={m.id} m={m} open={open === m.id} onToggle={() => setOpen(open === m.id ? "" : m.id)} allowRetire={allowRetire}
              onChanged={() => setVersion((v) => v + 1)} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function MemoryRow({ m, open, onToggle, allowRetire, onChanged }: { m: MemoryItem; open: boolean; onToggle: () => void; allowRetire?: boolean; onChanged: () => void }) {
  const [type, tone] = MEM_TYPE[m.type] ?? [m.type, "neutral"];
  const [d, setD] = useState<MemoryDetail | null>(null);
  const confirm = useConfirm();
  const toast = useToast();
  useEffect(() => {
    if (!open || d) return;
    api<MemoryDetail>(`/memory/${m.id}`).then(setD).catch(() => undefined);
  }, [open, d, m.id]);

  async function retire() {
    const reason = await confirm({ title: `Cho “${m.title}” nghỉ hưu?`, body: "Agent sẽ không truy hồi mục này nữa. Mục vẫn được giữ để truy vết.",
      confirmLabel: "Cho nghỉ hưu", tone: "warn", reason: { label: "Lý do (ghi vào nhật ký)" } });
    if (reason === null) return;
    try {
      await api(`/memory/${m.id}/retire`, { method: "POST", body: { reason } });
      toast("Đã cho nghỉ hưu.");
      onChanged();
    } catch (x) {
      toast(x instanceof ApiError ? x.message : "Không thực hiện được.", "error");
    }
  }

  return (
    <li className={open ? "open" : ""} data-memory={m.id}>
      <button type="button" className="mem-head" aria-expanded={open} onClick={onToggle}>
        {open ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
        <span className="mem-main">
          <b>{m.title}</b>
          <span>{m.snippet}</span>
        </span>
        <span className="mem-tags">
          <Badge tone={tone} plain>
            {type}
          </Badge>
          <Badge plain>{scopeLabel(m.owner_scope)}</Badge>
        </span>
      </button>
      <div className="mem-meta">
        <span>{TRUST[m.source_trust]}</span>
        <span>Tin cậy {Math.round(m.confidence * 100)}%</span>
        <span>{m.access_count} lần được truy hồi</span>
        {m.usefulness > 0 && <span>{m.usefulness} lần được dùng</span>}
        {m.verification_status !== "active" && <span>{MEM_STATUS[m.verification_status] ?? m.verification_status}</span>}
        {m.valid_to && <span>Hiệu lực đến {when(m.valid_to)}</span>}
        <span>{ago(m.created_at)}</span>
      </div>
      {open && (
        <div className="mem-body">
          {!d ? (
            <Loading what="chi tiết" />
          ) : (
            <>
              <p className="mem-content">{d.content}</p>
              <ul className="kv compact">
                <li>
                  <span className="k muted">Ghi bởi</span>
                  <span>{actor(d.created_by_principal)}</span>
                </li>
                {d.source_ref && (
                  <li>
                    <span className="k muted">Nguồn</span>
                    <span className="mono-tag">{d.source_ref}</span>
                  </li>
                )}
                {d.detail &&
                  Object.entries(d.detail)
                    .filter(([k, v]) => v !== null && !(Array.isArray(v) && v.length === 0) && !(k === "claim" && v === d.content))
                    .map(([k, v]) => (
                      <li key={k}>
                        <span className="k muted">{DETAIL_LABEL[k] ?? k}</span>
                        <span>{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                      </li>
                    ))}
                <li>
                  <span className="k muted">Tìm theo nghĩa</span>
                  <span>{d.embeddings.length ? "Đã có vector" : "Chưa nhúng (vẫn tìm được theo từ khóa)"}</span>
                </li>
              </ul>
              {d.access.length > 0 && (
                <div className="table-wrap">
                  <table className="table">
                    <caption className="sr-only">Lượt truy hồi</caption>
                    <thead>
                      <tr>
                        <th scope="col">Lúc</th>
                        <th scope="col">Ai truy hồi</th>
                        <th scope="col">Việc</th>
                        <th scope="col">Thứ hạng</th>
                        <th scope="col">Dùng trong kết quả</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.access.map((a, i) => (
                        <tr key={i}>
                          <td className="nowrap muted">{when(a.at)}</td>
                          <td>{actor(a.principal)}</td>
                          <td className="muted">{a.task_id ?? a.purpose}</td>
                          <td>{a.rank ?? ""}</td>
                          <td>{a.used_in_output ? <Badge tone="success">Có</Badge> : <span className="muted">Chưa</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {allowRetire && m.verification_status !== "retired" && (
                <div className="row">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={retire}>
                    <Archive size={14} aria-hidden="true" /> Cho nghỉ hưu
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </li>
  );
}

const DETAIL_LABEL: Record<string, string> = {
  task_id: "Việc",
  task_type: "Loại việc",
  outcome: "Kết quả",
  cost_usd: "Chi phí (USD)",
  occurred_at: "Lúc xảy ra",
  claim: "Mệnh đề",
  evidence: "Bằng chứng",
  evidence_level: "Mức bằng chứng",
  topic: "Chủ đề",
  procedure_key: "Mã quy trình",
  version: "Phiên bản",
  steps: "Các bước",
  checklist: "Danh sách kiểm",
  applies_to_task_types: "Áp dụng cho",
};

const VEC: Record<string, string> = {
  used: "có dùng tìm theo nghĩa",
  not_configured: "chỉ tìm theo từ khóa (chưa có khóa OpenAI cho tìm theo nghĩa)",
  skipped: "chỉ tìm theo từ khóa",
};

/** Thử truy hồi đúng như agent sẽ thấy, kèm giải thích điểm của từng mục ("Giải thích căn cứ"). */
export function MemoryPreview({ agent }: { agent: string }) {
  const [q, setQ] = useState("");
  const [r, setR] = useState<RetrievalResult | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    try {
      setR(await api<RetrievalResult>(`/agents/${agent}/memory/search`, { method: "POST", body: { query: q.trim() } }));
    } catch (x) {
      toast(x instanceof ApiError ? x.message : "Không truy hồi được.", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Thử truy hồi" description="Gõ một yêu cầu như khi giao việc; xem agent sẽ nhớ ra những gì và vì sao (cùng phạm vi, trọng số và ngân sách token như khi chạy thật).">
      <form className="form-inline" onSubmit={run}>
        <label className="field">
          <span className="sr-only">Yêu cầu</span>
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ví dụ: viết bài trà gừng mật ong cho mùa đông" />
        </label>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          <Sparkles size={16} aria-hidden="true" /> Thử truy hồi
        </button>
      </form>
      {r && (
        <div className="stack preview">
          <p className="muted small">
            Xét {r.considered} mục, chọn {r.items.length} mục, dùng {r.used_tokens.toLocaleString("vi-VN")}/{r.budget_tokens.toLocaleString("vi-VN")} token;{" "}
            {VEC[r.vector_search] ?? r.vector_search}. Phạm vi đọc: {r.scopes.map(scopeLabel).join(", ")}.
          </p>
          {r.items.length === 0 ? (
            <Empty icon={<Search size={20} />} title="Agent không nhớ ra mục nào cho yêu cầu này" />
          ) : (
            <ol className="hits">
              {r.items.map((it) => (
                <li key={it.memory_id}>
                  <div className="hit-head">
                    <b>{it.title}</b>
                    <span className="mem-tags">
                      <Badge tone={MEM_TYPE[it.type]?.[1] ?? "neutral"} plain>
                        {CATEGORY[it.category] ?? it.category}
                      </Badge>
                      <Badge plain>{scopeLabel(it.scope)}</Badge>
                    </span>
                  </div>
                  <p className="muted small clamp">{it.content}</p>
                  <p className="why">
                    {it.kw_rank && <span>Từ khóa hạng {it.kw_rank}</span>}
                    {it.vec_rank && <span>Theo nghĩa hạng {it.vec_rank}</span>}
                    <span>Độ mới ×{n2(it.w_recency)}</span>
                    <span>Tin cậy ×{n2(it.w_conf)}</span>
                    <span>Nguồn ×{n2(it.w_trust)}</span>
                    <span>{it.tokens} token</span>
                    <b>Điểm {it.score.toFixed(4)}</b>
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </Card>
  );
}
