"use client";

import { ArrowLeft, Ban, Check, MessageSquareWarning, RotateCcw, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { TaskStatus, TaskTable, taskWhere } from "@/components/tasks";
import { useConfirm } from "@/components/ui/dialog";
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader } from "@/components/ui/primitives";
import { Tabs, TabPanel, useTabParam } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type TaskDetail } from "@/lib/api";
import { actorLabel, clock, usd, when } from "@/lib/format";
import { CALL_STATUS, MSG_TYPE, NODE, VERDICT } from "@/lib/labels";
import { useApi } from "@/lib/use-api";

const TABS = ["tung-buoc", "ket-qua", "viec-con", "trao-doi"] as const;
type Tab = (typeof TABS)[number];
const OPEN = new Set(["CREATED", "PENDING", "ASSIGNED", "IN_PROGRESS", "WAITING_REVIEW", "WAITING_APPROVAL"]);
const msg = (x: unknown) => (x instanceof ApiError ? (x.code === "REAUTH_CANCELLED" ? "" : x.message) : "Có lỗi, thử lại.");

function who(p: string): string {
  if (p === "owner") return "Owner";
  return actorLabel(p);
}

export default function TaskPage() {
  const { id } = useParams<{ id: string }>();
  const { data: d, error, reload } = useApi<TaskDetail>(`/tasks/${id}`);
  const [tab, setTab] = useTabParam<Tab>(TABS, "tung-buoc");
  const confirm = useConfirm();
  const toast = useToast();
  const open = d ? OPEN.has(d.task.status) : false;

  useEffect(() => {
    if (!open) return;
    const h = setInterval(() => void reload(), 3000); // đang chạy: cập nhật từng bước
    return () => clearInterval(h);
  }, [open, reload]);

  async function cancel() {
    const reason = await confirm({
      title: "Hủy việc này?",
      body: "Các việc con chưa xong cũng bị hủy; yêu cầu duyệt đang chờ của chúng bị gỡ khỏi hàng chờ.",
      confirmLabel: "Hủy việc",
      tone: "danger",
      reason: { label: "Lý do (ghi vào nhật ký)" },
    });
    if (reason === null) return;
    try {
      await api(`/tasks/${id}/cancel`, { method: "POST", body: { reason: reason || "Owner hủy" } });
      toast("Đã hủy việc.");
      await reload();
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    }
  }

  async function retry() {
    try {
      await api(`/tasks/${id}/retry`, { method: "POST" });
      toast("Đã cho chạy lại.");
      await reload();
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    }
  }

  if (error) return <ErrorAlert>{error}</ErrorAlert>;
  if (!d) return <Loading what="việc" />;
  const t = d.task;
  const crit = t.success_criteria.map((c) => (typeof c === "string" ? c : String(c.description ?? JSON.stringify(c))));
  return (
    <>
      <Link href="/viec" className="back-link">
        <ArrowLeft size={16} aria-hidden="true" /> Việc
      </Link>
      <PageHeader
        title={t.title}
        description={
          <>
            Giao cho <Link href={`/agent/${t.assigned_agent}`}>{t.agent_name ?? t.assigned_agent}</Link>, người giao: {who(t.created_by)}.
            {d.parent && (
              <>
                {" "}
                Là việc con của <Link href={`/viec/${d.parent.id}`}>{d.parent.title}</Link>.
              </>
            )}
          </>
        }
        actions={
          <>
            {t.status === "FAILED" && (
              <button type="button" className="btn btn-secondary" onClick={retry}>
                <RotateCcw size={16} aria-hidden="true" /> Chạy lại
              </button>
            )}
            {open && (
              <button type="button" className="btn btn-danger-outline" onClick={cancel}>
                <Ban size={16} aria-hidden="true" /> Hủy việc
              </button>
            )}
          </>
        }
      />
      <div className="task-summary">
        <div>
          <span className="k">Trạng thái</span>
          <span className="v">
            <TaskStatus t={t} /> {open && <span className="muted">{taskWhere(t)}</span>}
          </span>
        </div>
        <div>
          <span className="k">Chi phí AI</span>
          <span className="v">
            {usd(Number(t.spent_usd), 4)} <span className="muted">/ {usd(Number(t.budget_usd), 2)}</span>
          </span>
        </div>
        <div>
          <span className="k">Hạn chót</span>
          <span className="v">{t.deadline ? when(t.deadline) : "Không có"}</span>
        </div>
        <div>
          <span className="k">Lượt thử</span>
          <span className="v">
            {t.attempt}/{t.max_attempts}
          </span>
        </div>
      </div>
      {t.status === "FAILED" && t.error && <ErrorAlert>{t.error}</ErrorAlert>}
      {t.status === "WAITING_APPROVAL" && (
        <p className="alert warn" role="status">
          Việc này đang chờ anh/chị duyệt. <Link href="/phe-duyet">Mở hàng chờ phê duyệt</Link>
        </p>
      )}
      {d.can_review && <ReviewBox d={d} onDone={reload} />}
      <Tabs
        label="Chi tiết việc"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "tung-buoc", label: "Từng bước", count: d.logs.length },
          { id: "ket-qua", label: "Kết quả" },
          { id: "viec-con", label: "Việc con, review", count: d.children.length + d.reviews.length },
          { id: "trao-doi", label: "Trao đổi, công cụ", count: d.messages.length + d.tools.length },
        ]}
      />
      <TabPanel id={tab}>
        {tab === "tung-buoc" && (
          <Card flush>
            <ol className="timeline">
              {d.logs.map((l) => (
                <li key={l.id} className={`ev-${l.event}`}>
                  <time dateTime={l.at} title={when(l.at)}>
                    {clock(l.at)}
                  </time>
                  <div>
                    {l.node && <span className="step-tag">{NODE[l.node] ?? l.node}</span>}
                    <span>{l.text}</span>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        )}
        {tab === "ket-qua" && (
          <Card title="Kết quả">
            {t.output_data ? <Output data={t.output_data} /> : <p className="muted">Chưa có kết quả.</p>}
            <h3 className="sub">Thế nào là xong</h3>
            {crit.length ? (
              <ul className="plain-list">
                {crit.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">Không đặt tiêu chí riêng.</p>
            )}
            {t.description && (
              <>
                <h3 className="sub">Mô tả</h3>
                <p className="pre">{t.description}</p>
              </>
            )}
          </Card>
        )}
        {tab === "viec-con" && (
          <>
            <Card title="Việc đã giao tiếp" flush>
              <TaskTable items={d.children} empty="Việc này không giao cho ai" />
            </Card>
            <Card title="Các lượt review">
              {d.reviews.length === 0 ? (
                <p className="muted">Chưa có lượt review nào.</p>
              ) : (
                <ul className="plain-list">
                  {d.reviews.map((r) => (
                    <li key={r.round}>
                      <Badge tone={VERDICT[r.verdict][1]}>{VERDICT[r.verdict][0]}</Badge> vòng {r.round}, {who(r.reviewer)}
                      {r.notes && <span className="muted">: {r.notes}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </>
        )}
        {tab === "trao-doi" && (
          <>
            <Card title="Tin nhắn giữa các agent" flush>
              {d.messages.length === 0 ? (
                <Empty icon={<MessageSquareWarning size={20} />} title="Chưa có tin nhắn" />
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Lúc</th>
                        <th scope="col">Loại</th>
                        <th scope="col">Từ → tới</th>
                        <th scope="col">Trạng thái</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.messages.map((m) => (
                        <tr key={m.id}>
                          <td className="nowrap muted">{clock(m.created_at)}</td>
                          <td>{MSG_TYPE[m.message_type] ?? m.message_type}</td>
                          <td className="nowrap">
                            {who(m.sender)} → {who(m.receiver)}
                          </td>
                          <td>{m.status === "delivered" ? "Đã giao" : m.status === "queued" ? "Đang chờ giao" : (m.last_error ?? m.status)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
            <Card title="Lời gọi công cụ" flush>
              {d.tools.length === 0 ? (
                <p className="muted pad">Không dùng công cụ nào.</p>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <tbody>
                      {d.tools.map((c) => {
                        const st = CALL_STATUS[c.status];
                        return (
                          <tr key={c.id}>
                            <td className="nowrap muted">{clock(c.at)}</td>
                            <td className="mono-tag">
                              {c.tool_id}.{c.action}
                            </td>
                            <td>{st ? <Badge tone={st[1]}>{st[0]}</Badge> : c.status}</td>
                            <td className="muted">{c.error ?? ""}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </>
        )}
      </TabPanel>
    </>
  );
}

function Output({ data }: { data: Record<string, unknown> }) {
  return (
    <dl className="output">
      {Object.entries(data).map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd className="pre">{typeof v === "string" ? v : JSON.stringify(v, null, 2)}</dd>
        </div>
      ))}
    </dl>
  );
}

function ReviewBox({ d, onDone }: { d: TaskDetail; onDone: () => Promise<void> }) {
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  async function send(verdict: "approve" | "request_changes" | "reject") {
    setBusy(true);
    try {
      await api(`/tasks/${d.task.id}/review`, { method: "POST", body: { verdict, notes } });
      toast(verdict === "approve" ? "Đã duyệt." : verdict === "reject" ? "Đã từ chối." : "Đã gửi góp ý, agent sẽ sửa lại.");
      setNotes("");
      await onDone();
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card title={`Anh/chị review (vòng ${d.next_round})`}>
      {d.task.output_data && <Output data={d.task.output_data} />}
      <label className="field">
        <span>Góp ý (bắt buộc khi yêu cầu sửa; agent ghi nhớ góp ý này cho những lần sau)</span>
        <textarea className="textarea" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} />
      </label>
      <div className="btn-row">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => send("approve")}>
          <Check size={16} aria-hidden="true" /> Duyệt
        </button>
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => send("request_changes")}>
          Yêu cầu sửa
        </button>
        <button type="button" className="btn btn-danger-outline" disabled={busy} onClick={() => send("reject")}>
          <X size={16} aria-hidden="true" /> Từ chối
        </button>
      </div>
    </Card>
  );
}
