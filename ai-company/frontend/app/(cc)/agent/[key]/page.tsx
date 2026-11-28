"use client";

import { ArrowLeft, GitCompare, History, Pause, Play, RefreshCw, RotateCcw, ShieldAlert, ShieldCheck, FlaskConical } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { useShell } from "@/components/shell";
import { useConfirm } from "@/components/ui/dialog";
import { Badge, Bar, Card, Empty, ErrorAlert, Loading, PageHeader, StateBadge } from "@/components/ui/primitives";
import { Tabs, TabPanel, useTabParam } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type AgentDetail, type AgentHistory, type BrainMeta, type DiffItem } from "@/lib/api";
import { ago, usd, when } from "@/lib/format";
import { actor, BRAIN_STATE, CALL_STATUS, DECISION, DEPT, LEVEL, LEVEL_TONE, MODEL_PROFILE, short, VERSION_EVENT } from "@/lib/labels";
import { useApi } from "@/lib/use-api";
import { DiffTable } from "@/components/diff-table";
import { MemoryBrowser, MemoryPreview } from "@/components/memory";

const TABS = ["ho-so", "bo-nao", "quyen", "tri-nho", "lich-su"] as const;
type Tab = (typeof TABS)[number];
const msg = (x: unknown) => (x instanceof ApiError ? (x.code === "REAUTH_CANCELLED" ? "" : x.message) : "Có lỗi, thử lại.");

export default function AgentPage() {
  const { key } = useParams<{ key: string }>();
  const { data: a, error, reload } = useApi<AgentDetail>(`/agents/${key}`);
  const [tab, setTab] = useTabParam<Tab>(TABS, "ho-so");
  const confirm = useConfirm();
  const toast = useToast();

  async function toggle() {
    if (!a) return;
    const pausing = a.state !== "paused";
    const reason = pausing
      ? await confirm({
          title: `Tạm dừng ${a.display_name}?`,
          body: "Agent sẽ không nhận việc mới và không gọi AI hay công cụ cho tới khi anh/chị cho chạy lại.",
          confirmLabel: "Tạm dừng",
          tone: "warn",
          reason: { label: "Lý do (ghi vào nhật ký, có thể bỏ trống)" },
        })
      : "";
    if (reason === null) return;
    try {
      await api(`/agents/${key}/${pausing ? "pause" : "resume"}`, { method: "POST", body: pausing ? { reason } : {} });
      toast(pausing ? `Đã tạm dừng ${a.display_name}.` : `${a.display_name} đã chạy lại.`);
      await reload();
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  if (!a) return error ? <ErrorAlert>{error}</ErrorAlert> : <Loading what="agent" />;
  const b = a.bundle;

  return (
    <>
      <Link href="/agent" className="back-link">
        <ArrowLeft size={14} aria-hidden="true" /> Tất cả agent
      </Link>
      <PageHeader
        title={a.display_name}
        description={a.role_summary}
        actions={
          <>
            <StateBadge state={a.state} />
            <button type="button" className="btn btn-secondary" onClick={toggle}>
              {a.state === "paused" ? <Play size={16} aria-hidden="true" /> : <Pause size={16} aria-hidden="true" />}
              {a.state === "paused" ? "Chạy lại" : "Tạm dừng"}
            </button>
          </>
        }
      />
      <div className="meta-row">
        <span>
          Phòng <b>{DEPT[a.department] ?? a.department}</b>
        </span>
        <span>
          Bộ não <b>{a.brain ? `v${a.brain.brain_version}` : "chưa nạp"}</b>
        </span>
        <span>
          Chi phí AI hôm nay <b>{usd(a.spend_today_usd)}</b>
          {b ? ` / ${usd(b.budget.usd_per_day)}` : ""}
        </span>
        {a.approvals_pending > 0 && (
          <Link href="/phe-duyet">
            <Badge tone="warn">{a.approvals_pending} việc chờ duyệt</Badge>
          </Link>
        )}
      </div>
      <Tabs
        label="Thông tin agent"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "ho-so", label: "Hồ sơ" },
          { id: "bo-nao", label: "Bộ não" },
          { id: "quyen", label: "Quyền công cụ", count: a.permissions.length },
          { id: "tri-nho", label: "Trí nhớ" },
          { id: "lich-su", label: "Lịch sử" },
        ]}
      />
      <TabPanel id={tab}>
        {!b ? (
          <Card>
            <Empty icon={<ShieldAlert size={20} />} title="Chưa có bộ não">
              Chạy <code>python -m app.cli sync-brains</code> hoặc bấm “Đọc lại thư mục bộ não” ở tab Bộ não.
            </Empty>
          </Card>
        ) : tab === "ho-so" ? (
          <ProfileTab a={a} b={b} />
        ) : tab === "bo-nao" ? (
          <BrainTab a={a} onChange={reload} />
        ) : tab === "quyen" ? (
          <PermissionsTab a={a} />
        ) : tab === "tri-nho" ? (
          <>
            <MemoryPreview agent={a.agent_key} />
            <MemoryBrowser agent={a.agent_key} allowRetire />
          </>
        ) : (
          <HistoryTab agentKey={a.agent_key} />
        )}
      </TabPanel>
    </>
  );
}

// ---------------------------------------------------------------- Hồ sơ
function Param({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <li className="param">
      <span className="param-head">
        <span>{label}</span>
        <b>{value.toLocaleString("vi-VN")}</b>
      </span>
      <Bar value={value} max={1} warnAt={101} label={label} />
      <span className="help">{hint}</span>
    </li>
  );
}

function ProfileTab({ a, b }: { a: AgentDetail; b: NonNullable<AgentDetail["bundle"]> }) {
  const p = b.identity.personality;
  return (
    <div className="grid-2">
      <div className="stack">
        <Card title="Sứ mệnh và nhiệm vụ">
          <p className="lead-text">{b.identity.role.mission}</p>
          <ul className="bullets">
            {b.identity.role.responsibilities.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </Card>
        <Card title="Luật cứng" description="Giới hạn tuyệt đối của agent này, cộng với hiến pháp chung. Nằm trong hash quy tắc cốt lõi: sửa phải được anh/chị duyệt.">
          {b.identity.role.hard_rules.length ? (
            <ul className="bullets">
              {b.identity.role.hard_rules.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">Chỉ áp hiến pháp chung.</p>
          )}
        </Card>
        <Card title="Đo bằng gì" description="KPI tính từ đánh giá độc lập, không từ báo cáo tự khai." flush>
          <ul className="kv">
            {b.evaluation.performance.kpis.map((k) => (
              <li key={k.key}>
                <span className="k">{k.name}</span>
                <span className="mono-tag">{k.key}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <div className="stack">
        <Card title="Tính cách" description="Các tham số này đi vào mã, không chỉ vào câu lệnh cho AI.">
          <p className="small">
            Giọng: <b>{p.voice.tone}</b>
            {p.voice.emoji ? ", có dùng emoji" : ""}
          </p>
          <ul className="params">
            <Param label="Yêu cầu dẫn nguồn" value={p.evidence_strictness} hint="Tỉ lệ khẳng định bắt buộc có nguồn trước khi nộp." />
            <Param label="Chấp nhận rủi ro" value={p.risk_tolerance} hint="Càng thấp càng hay hỏi cấp trên." />
            <Param label="Độ chi tiết" value={p.verbosity} hint="Giới hạn độ dài báo cáo." />
            <Param label="Trang trọng" value={p.voice.formality} hint="Giọng văn khi viết." />
          </ul>
        </Card>
        <Card title="Tổ chức" flush>
          <ul className="kv">
            <li>
              <span className="k muted">Cấp trên</span>
              {a.manager ? <Link href={`/agent/${a.manager.agent_key}`}>{a.manager.display_name}</Link> : <span>Owner</span>}
            </li>
            <li>
              <span className="k muted">Cấp dưới</span>
              <span className="right-list">
                {a.direct_reports.length
                  ? a.direct_reports.map((r) => (
                      <Link key={r.agent_key} href={`/agent/${r.agent_key}`}>
                        {r.display_name}
                      </Link>
                    ))
                  : "Không có"}
              </span>
            </li>
          </ul>
        </Card>
        <Card title="Model và giới hạn" flush>
          <ul className="kv">
            <li>
              <span className="k muted">Hồ sơ model chính</span>
              <span>{MODEL_PROFILE[b.model.primary] ?? b.model.primary}</span>
            </li>
            <li>
              <span className="k muted">Dự phòng</span>
              <span>{b.model.fallback ? (MODEL_PROFILE[b.model.fallback] ?? b.model.fallback) : "Không"}</span>
            </li>
            <li>
              <span className="k muted">Ngân sách AI mỗi ngày</span>
              <span>{usd(b.budget.usd_per_day)}</span>
            </li>
            <li>
              <span className="k muted">Tối đa mỗi việc</span>
              <span>
                {b.budget.max_steps_per_task} bước, {b.budget.max_tool_calls_per_task} lần gọi công cụ
              </span>
            </li>
            <li>
              <span className="k muted">Hỏi cấp trên khi tự tin dưới</span>
              <span>{Math.round(b.reasoning.decision_policy.escalate_when.confidence_below * 100)}%</span>
            </li>
          </ul>
        </Card>
        <Card title="Kỹ năng" flush>
          <ul className="kv">
            {b.skills.map((s) => (
              <li key={s.key}>
                <span className="k">{s.name}</span>
                <span className="muted xs">v{s.version}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Bộ não
function BrainTab({ a, onChange }: { a: AgentDetail; onChange: () => Promise<void> }) {
  const { withReauth } = useShell();
  const toast = useToast();
  const confirm = useConfirm();
  const { data: versions, reload } = useApi<BrainMeta[]>(`/agents/${a.agent_key}/brains`);
  const [cmp, setCmp] = useState<{ title: string; changes: DiffItem[] } | null>(null);
  const active = versions?.find((v) => v.state === "active");

  async function compare(v: BrainMeta) {
    if (!active) return;
    try {
      const d = await api<{ from: string; to: string; changes: DiffItem[] }>(`/agents/${a.agent_key}/brains/diff?a=${active.id}&b=${v.id}`);
      setCmp({ title: `So sánh v${d.from} (đang chạy) với v${d.to}`, changes: d.changes });
    } catch (x) {
      toast(msg(x), "error");
    }
  }
  async function shadow(v: BrainMeta) {
    try {
      await api(`/agents/${a.agent_key}/brains/${v.id}/shadow`, { method: "POST" });
      toast(`Bản v${v.brain_version} chuyển sang chạy thử: kết quả chỉ đem chấm, không giao ra ngoài.`);
      await reload();
    } catch (x) {
      toast(msg(x), "error");
    }
  }
  async function rollback(v: BrainMeta) {
    const ok = await confirm({
      title: `Quay lại bộ não v${v.brain_version}?`,
      body: "Bản đang chạy chuyển thành bản cũ; quyền công cụ trở về như bản v" + v.brain_version + ". Việc đang chạy giữ phiên bản đã ghim.",
      confirmLabel: "Quay lại",
      tone: "warn",
    });
    if (ok === null) return;
    try {
      await withReauth(() => api(`/agents/${a.agent_key}/brains/${v.id}/rollback`, { method: "POST" }));
      toast(`Đã quay lại v${v.brain_version}.`);
      await Promise.all([reload(), onChange()]);
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    }
  }
  async function sync() {
    try {
      const items = await api<{ agent_key: string; status: string; detail: string }[]>("/brains/sync", { method: "POST" });
      const mine = items.find((i) => i.agent_key === a.agent_key);
      const proposed = items.filter((i) => i.status === "proposed").length;
      const errors = items.filter((i) => i.status === "error");
      if (errors.length) toast(`Lỗi bộ não: ${errors.map((e) => `${e.agent_key}: ${e.detail}`).join(" | ")}`, "error");
      else toast(proposed ? `Có ${proposed} phiên bản mới chờ duyệt.` : `Không có thay đổi${mine ? "" : ""}.`);
      await Promise.all([reload(), onChange()]);
    } catch (x) {
      toast(msg(x), "error");
    }
  }

  return (
    <>
      <Card
        title={a.brain ? `Bộ não đang chạy: v${a.brain.brain_version}` : "Bộ não"}
        description={a.brain ? `Kích hoạt ${when(a.brain.activated_at)}, nạp bởi ${actor(a.brain.created_by)}.` : undefined}
        actions={
          <>
            {a.integrity.ok ? (
              <Badge tone="success" plain>
                <ShieldCheck size={13} aria-hidden="true" /> Toàn vẹn
              </Badge>
            ) : (
              <Badge tone="danger">Không nạp được</Badge>
            )}
            <button type="button" className="btn btn-secondary btn-sm" onClick={sync}>
              <RefreshCw size={14} aria-hidden="true" /> Đọc lại thư mục bộ não
            </button>
          </>
        }
        flush
      >
        {!a.integrity.ok && (
          <div className="card-body">
            <p className="alert danger">{a.integrity.detail}</p>
          </div>
        )}
        {a.brain && (
          <ul className="kv kv-4">
            <li>
              <span className="k muted">Bộ não</span>
              <span>v{a.brain.brain_version}</span>
            </li>
            <li>
              <span className="k muted">Câu lệnh</span>
              <span>v{a.brain.prompt_version}</span>
            </li>
            <li>
              <span className="k muted">Kiến thức</span>
              <span>v{a.brain.knowledge_version}</span>
            </li>
            <li>
              <span className="k muted">Kỹ năng</span>
              <span>v{a.brain.skill_version}</span>
            </li>
            <li>
              <span className="k muted">Mã kiểm tra nội dung</span>
              <span className="mono-tag" title={a.brain.bundle_hash}>
                {short(a.brain.bundle_hash)}
              </span>
            </li>
            <li>
              <span className="k muted">Mã quy tắc cốt lõi</span>
              <span className="mono-tag" title={a.brain.core_rules_hash}>
                {short(a.brain.core_rules_hash)}
              </span>
            </li>
          </ul>
        )}
      </Card>

      <Card title="Các phiên bản" description="Bản mới chỉ chạy chính thức khi anh/chị duyệt. Có thể cho chạy thử (không giao kết quả) hoặc quay lại bản cũ." flush>
        {!versions ? (
          <Loading what="phiên bản" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Phiên bản</th>
                  <th scope="col">Trạng thái</th>
                  <th scope="col" className="hide-sm">
                    Tạo lúc
                  </th>
                  <th scope="col" className="hide-sm">
                    Mã kiểm tra
                  </th>
                  <th scope="col" className="right">
                    <span className="sr-only">Thao tác</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {versions.map((v) => {
                  const [label, tone] = BRAIN_STATE[v.state] ?? [v.state, "neutral"];
                  return (
                    <tr key={v.id} data-brain={v.brain_version}>
                      <td>
                        <b>v{v.brain_version}</b>
                      </td>
                      <td>
                        <Badge tone={tone}>{label}</Badge>
                      </td>
                      <td className="hide-sm nowrap muted">{when(v.created_at)}</td>
                      <td className="hide-sm">
                        <span className="mono-tag">{short(v.bundle_hash)}</span>
                      </td>
                      <td className="right">
                        <span className="row end">
                          {v.state !== "active" && active && (
                            <button type="button" className="btn btn-ghost btn-sm" onClick={() => compare(v)}>
                              <GitCompare size={14} aria-hidden="true" /> So sánh
                            </button>
                          )}
                          {v.state === "draft" && (
                            <button type="button" className="btn btn-ghost btn-sm" onClick={() => shadow(v)}>
                              <FlaskConical size={14} aria-hidden="true" /> Chạy thử
                            </button>
                          )}
                          {v.state === "retired" && v.activated_at && (
                            <button type="button" className="btn btn-secondary btn-sm" onClick={() => rollback(v)}>
                              <RotateCcw size={14} aria-hidden="true" /> Quay lại bản này
                            </button>
                          )}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {cmp && (
        <Card
          title={cmp.title}
          description={`${cmp.changes.length} thay đổi`}
          actions={
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setCmp(null)}>
              Đóng
            </button>
          }
          flush
        >
          <DiffTable changes={cmp.changes} />
        </Card>
      )}
    </>
  );
}

// ---------------------------------------------------------------- Quyền công cụ
function PermissionsTab({ a }: { a: AgentDetail }) {
  return (
    <>
      <p className="alert info">
        <ShieldCheck size={16} aria-hidden="true" /> Quyền lấy từ bộ não (tools/tool_permissions.yaml). Mọi hành động không có ở đây đều bị chặn. Đổi quyền là đổi bộ
        não và cần anh/chị duyệt; một số hành động luôn cần duyệt dù ở cấp nào.
      </p>
      <Card flush>
        {a.permissions.length === 0 ? (
          <Empty icon={<ShieldAlert size={20} />} title="Không có quyền nào" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Công cụ</th>
                  <th scope="col">Cấp tự chủ</th>
                  <th scope="col">Hạn mức</th>
                  <th scope="col">Duyệt</th>
                  <th scope="col">Kết nối</th>
                </tr>
              </thead>
              <tbody>
                {a.permissions.map((p) => {
                  const mandatory = a.bundle?.constitution.mandatory_approval_tags ?? {};
                  const always = p.requires_approval || (p.action_info?.tags ?? []).some((t) => t in mandatory);
                  return (
                    <tr key={`${p.tool_id}.${p.action}`} data-perm={`${p.tool_id}.${p.action}`}>
                      <td>
                        <div className="cell-main">
                          <b>{p.action_info?.description ?? `${p.tool_id}.${p.action}`}</b>
                          <span>
                            <span className="mono-tag">
                              {p.tool_id}.{p.action}
                            </span>{" "}
                            {p.tool_description}
                          </span>
                        </div>
                      </td>
                      <td className="nowrap">
                        <Badge tone={LEVEL_TONE[p.autonomy_level]} plain>
                          L{p.autonomy_level} {LEVEL[p.autonomy_level]}
                        </Badge>
                      </td>
                      <td className="nowrap muted">
                        {[p.limits.per_day ? `${p.limits.per_day} lần/ngày` : "", p.limits.max_usd != null ? `≤ ${usd(p.limits.max_usd)}/lần` : ""]
                          .filter(Boolean)
                          .join(", ") || "Không giới hạn riêng"}
                      </td>
                      <td className="nowrap">{always ? <Badge tone="warn">Luôn cần duyệt</Badge> : <span className="muted">Theo cấp</span>}</td>
                      <td className="nowrap">{p.available ? <Badge tone="success">Đã kết nối</Badge> : <Badge>Chưa kết nối</Badge>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------- Lịch sử
function HistoryTab({ agentKey }: { agentKey: string }) {
  const { data: h, error } = useApi<AgentHistory>(`/agents/${agentKey}/history`);
  if (!h) return error ? <ErrorAlert>{error}</ErrorAlert> : <Loading what="lịch sử" />;
  return (
    <>
      <Card title="Phiên bản bộ não" description="Nhật ký chỉ thêm, không sửa được." flush>
        <ul className="activity">
          {h.versions.map((v) => (
            <li key={v.id}>
              <span className="act-ic" aria-hidden="true">
                <History size={16} />
              </span>
              <span className="act-main">
                <b>
                  {VERSION_EVENT[v.event] ?? v.event}
                  {v.to_version ? `: ${v.from_version ? `v${v.from_version} → ` : ""}v${v.to_version}` : ""}
                  {v.changes ? ` (${v.changes} thay đổi)` : ""}
                </b>
                <span>
                  {v.approved_by ? `Duyệt bởi ${actor(v.approved_by)}` : `Đề xuất bởi ${actor(v.proposed_by)}`}
                </span>
              </span>
              <time className="subtle xs" dateTime={v.at}>
                {ago(v.at)}
              </time>
            </li>
          ))}
        </ul>
      </Card>
      <div className="grid-2 even">
        <Card title="Quyết định chính sách gần đây" description="Vì sao agent được phép, cần duyệt hay bị chặn." flush>
          {h.decisions.length === 0 ? (
            <Empty icon={<ShieldCheck size={20} />} title="Chưa có quyết định nào" />
          ) : (
            <ul className="activity">
              {h.decisions.map((d) => {
                const [label, tone] = DECISION[d.decision];
                return (
                  <li key={d.id}>
                    <Badge tone={tone} plain>
                      {label}
                    </Badge>
                    <span className="act-main">
                      <b>
                        {d.tool_id}.{d.action}
                      </b>
                      <span>{d.reason}</span>
                    </span>
                    <time className="subtle xs" dateTime={d.at}>
                      {ago(d.at)}
                    </time>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        <Card title="Lần gọi công cụ gần đây" flush>
          {h.invocations.length === 0 ? (
            <Empty icon={<History size={20} />} title="Chưa gọi công cụ nào" />
          ) : (
            <ul className="activity">
              {h.invocations.map((c) => {
                const [label, tone] = CALL_STATUS[c.status] ?? [c.status, "neutral"];
                return (
                  <li key={c.id}>
                    <Badge tone={tone} plain>
                      {label}
                    </Badge>
                    <span className="act-main">
                      <b>
                        {c.tool_id}.{c.action}
                      </b>
                      <span>{c.error ?? (c.duration_ms != null ? `${c.duration_ms} ms, ${c.attempts} lần thử` : "")}</span>
                    </span>
                    <time className="subtle xs" dateTime={c.at}>
                      {ago(c.at)}
                    </time>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
