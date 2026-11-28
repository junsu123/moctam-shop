"use client";

import { ClipboardList, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Badge, Empty } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type Agent, type TaskRow } from "@/lib/api";
import { ago, usd, when } from "@/lib/format";
import { NODE, PRIORITY, TASK_STATUS, WAIT } from "@/lib/labels";

export function TaskStatus({ t }: { t: Pick<TaskRow, "status" | "wait_kind"> }) {
  const [label, tone] = TASK_STATUS[t.status] ?? [t.status, "neutral"];
  return <Badge tone={tone}>{label}</Badge>;
}

/** Một dòng mô tả việc đang ở đâu: bước của đồ thị, đang chờ gì, lỗi gì. */
export function taskWhere(t: TaskRow): string {
  if (t.status === "IN_PROGRESS") return t.graph_node ? NODE[t.graph_node] ?? t.graph_node : "Đang làm";
  if (t.status === "PENDING" && t.wait_kind === "children") return "Chờ các việc đã giao";
  if (t.status === "PENDING" && t.attempt > 1) return `Chờ thử lại (lần ${t.attempt}/${t.max_attempts})`;
  if (t.wait_kind && (t.status === "WAITING_APPROVAL" || t.status === "WAITING_REVIEW")) return WAIT[t.wait_kind] ?? "";
  if (t.status === "FAILED") return t.error ?? "Lỗi";
  if (t.status === "COMPLETED") return t.result_summary ?? "";
  return "";
}

export function TaskTable({ items, empty }: { items: TaskRow[]; empty: string }) {
  if (items.length === 0)
    return (
      <Empty icon={<ClipboardList size={20} />} title={empty}>
        Giao việc cho một agent bằng nút &quot;Giao việc&quot;, hoặc để AI CEO tự chia việc từ mục tiêu tuần.
      </Empty>
    );
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Việc</th>
            <th scope="col">Agent</th>
            <th scope="col">Trạng thái</th>
            <th scope="col" className="hide-sm">
              Chi phí
            </th>
            <th scope="col" className="hide-sm">
              Cập nhật
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => {
            const pr = PRIORITY[t.priority];
            return (
              <tr key={t.id}>
                <td>
                  <div className="cell-main">
                    <Link href={`/viec/${t.id}`} className="row-link">
                      {t.title}
                    </Link>
                    <span>
                      {t.priority < 2 && pr && <Badge tone={pr[1]} plain>{pr[0]}</Badge>} {taskWhere(t)}
                      {t.children > 0 && `, ${t.children} việc con`}
                    </span>
                  </div>
                </td>
                <td className="nowrap">{t.agent_name ?? t.assigned_agent}</td>
                <td className="nowrap">
                  <TaskStatus t={t} />
                </td>
                <td className="nowrap hide-sm muted">
                  {usd(Number(t.spent_usd), 3)} / {usd(Number(t.budget_usd), 2)}
                </td>
                <td className="nowrap hide-sm muted">
                  <time dateTime={t.updated_at} title={when(t.updated_at)}>
                    {ago(t.updated_at)}
                  </time>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function GiveTask({ agents, defaultAgent, onClose, onSaved }: { agents: Agent[]; defaultAgent?: string; onClose: () => void; onSaved: (id: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  useEffect(() => {
    ref.current?.showModal();
  }, []);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setErr("");
    try {
      const r = await api<{ id: string }>("/tasks", {
        method: "POST",
        body: {
          agent: f.get("agent"),
          title: f.get("title"),
          description: f.get("description"),
          success_criteria: String(f.get("criteria") || "")
            .split("\n")
            .map((x) => x.trim())
            .filter(Boolean),
          budget_usd: Number(f.get("budget") || 0.5),
          deadline: f.get("deadline") || null,
          priority: Number(f.get("priority") || 2),
          requires_review: f.get("review") === "on",
          task_type: f.get("kind") || "generic",
          publish: f.get("kind") === "faq" || f.get("kind") === "blog",
          requires_approval: f.get("approval") === "on",
        },
      });
      toast("Đã giao việc.");
      onSaved(r.id);
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Có lỗi, thử lại.");
      setBusy(false);
    }
  }

  return (
    <dialog ref={ref} className="dialog wide" onCancel={onClose} aria-labelledby="give-task">
      <form onSubmit={submit}>
        <div className="dialog-body">
          <div className="dialog-head">
            <span className="dialog-ic">
              <Send size={20} />
            </span>
            <div>
              <h2 id="give-task">Giao việc</h2>
              <p>Agent tự nhớ lại kinh nghiệm, lập kế hoạch, dùng công cụ được phép và tự kiểm tra trước khi nộp. Việc cần ra ngoài vẫn phải qua duyệt. Bài FAQ/blog được Giám đốc Marketing review rồi mới vào lịch đăng.</p>
            </div>
          </div>
          <div className="form-grid">
            <label className="field">
              <span>Giao cho</span>
              <select className="input" name="agent" defaultValue={defaultAgent ?? "ai_ceo"} required>
                {agents.map((a) => (
                  <option key={a.agent_key} value={a.agent_key}>
                    {a.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Mức ưu tiên</span>
              <select className="input" name="priority" defaultValue="2">
                <option value="0">Khẩn</option>
                <option value="1">Cao</option>
                <option value="2">Thường</option>
                <option value="3">Thấp</option>
              </select>
            </label>
            <label className="field">
              <span>Ngân sách AI (USD)</span>
              <input className="input" type="number" name="budget" min="0.01" max="5" step="0.01" defaultValue="0.5" />
            </label>
            <label className="field">
              <span>Hạn chót (bỏ trống nếu không gấp)</span>
              <input className="input" type="date" name="deadline" />
            </label>
          </div>
          <label className="field">
            <span>Việc cần làm</span>
            <input className="input" name="title" required minLength={3} maxLength={300} placeholder="Ví dụ: viết 3 câu hỏi thường gặp về giao hàng" />
          </label>
          <label className="field">
            <span>Mô tả thêm</span>
            <textarea className="textarea" name="description" rows={3} maxLength={4000} />
          </label>
          <label className="field">
            <span>Thế nào là xong (mỗi dòng một ý)</span>
            <textarea className="textarea" name="criteria" rows={3} maxLength={2000} placeholder={"có đủ 3 câu hỏi\ngiọng thân thiện, không hứa giao trong ngày"} />
          </label>
          <label className="field">
            <span>Loại việc</span>
            <select className="input" name="kind" defaultValue="generic">
              <option value="generic">Việc thường</option>
              <option value="faq">Viết FAQ và đăng lên website</option>
              <option value="blog">Viết blog và đăng lên website</option>
            </select>
          </label>
          <div className="checks">
            <label className="check">
              <input type="checkbox" name="review" /> Tôi xem lại trước khi xong (review)
            </label>
            <label className="check">
              <input type="checkbox" name="approval" /> Cần tôi duyệt kết quả
            </label>
          </div>
          {err && (
            <p className="alert danger" role="alert">
              {err}
            </p>
          )}
        </div>
        <div className="dialog-foot">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Hủy
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Giao việc
          </button>
        </div>
      </form>
    </dialog>
  );
}
