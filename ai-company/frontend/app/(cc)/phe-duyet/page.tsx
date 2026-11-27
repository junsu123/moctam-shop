"use client";

import { Check, ClipboardCheck, Clock, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { DiffTable } from "@/components/diff-table";
import { useShell } from "@/components/shell";
import { useConfirm } from "@/components/ui/dialog";
import { Badge, Card, Empty, ErrorAlert, Loading, PageHeader } from "@/components/ui/primitives";
import { Tabs, TabPanel, useTabParam } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type Approval } from "@/lib/api";
import { ago, when } from "@/lib/format";
import { actor, APPROVAL_STATUS, RISK } from "@/lib/labels";
import { useApi } from "@/lib/use-api";

const TABS = ["cho-duyet", "da-xu-ly"] as const;
type Tab = (typeof TABS)[number];
const msg = (x: unknown) => (x instanceof ApiError ? (x.code === "REAUTH_CANCELLED" ? "" : x.message) : "Có lỗi, thử lại.");
const SUBJECT: Record<string, string> = { brain: "Bộ não", tool_call: "Dùng công cụ" };

function left(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "đã hết hạn";
  const h = Math.floor(ms / 3_600_000);
  return h >= 1 ? `còn ${h} giờ` : `còn ${Math.max(1, Math.floor(ms / 60_000))} phút`;
}

export default function ApprovalsPage() {
  const [tab, setTab] = useTabParam<Tab>(TABS, "cho-duyet");
  const pending = useApi<Approval[]>("/approvals?status=pending");
  const done = useApi<Approval[]>("/approvals?status=done");
  const reloadAll = async () => {
    await Promise.all([pending.reload(), done.reload()]);
  };
  return (
    <>
      <PageHeader
        title="Phê duyệt"
        description="Việc agent cần anh/chị đồng ý trước khi làm. Yêu cầu có hạn 72 giờ; hết hạn là tự hủy, im lặng không phải đồng ý. Việc rủi ro cao cần nhập lại mật khẩu và mã xác thực."
      />
      <Tabs
        label="Trạng thái phê duyệt"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "cho-duyet", label: "Đang chờ", count: pending.data?.length },
          { id: "da-xu-ly", label: "Đã xử lý", count: done.data?.length },
        ]}
      />
      <TabPanel id={tab}>
        {tab === "cho-duyet" ? (
          <List q={pending} empty="Không có việc nào chờ duyệt." onChange={reloadAll} actionable />
        ) : (
          <List q={done} empty="Chưa có việc nào được xử lý." onChange={reloadAll} />
        )}
      </TabPanel>
    </>
  );
}

function List({
  q,
  empty,
  onChange,
  actionable,
}: {
  q: { data: Approval[] | null; error: string };
  empty: string;
  onChange: () => Promise<void>;
  actionable?: boolean;
}) {
  if (!q.data) return q.error ? <ErrorAlert>{q.error}</ErrorAlert> : <Loading what="phê duyệt" />;
  if (!q.data.length)
    return (
      <Card>
        <Empty icon={<ClipboardCheck size={20} />} title={empty}>
          Khi agent cần duyệt, anh/chị cũng nhận tin báo qua Telegram.
        </Empty>
      </Card>
    );
  return (
    <>
      {q.data.map((a) => (
        <ApprovalCard key={a.id} a={a} onChange={onChange} actionable={actionable} />
      ))}
    </>
  );
}

function ApprovalCard({ a, onChange, actionable }: { a: Approval; onChange: () => Promise<void>; actionable?: boolean }) {
  const { withReauth } = useShell();
  const confirm = useConfirm();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [, tick] = useState(0);
  useEffect(() => {
    if (!actionable) return;
    const t = setInterval(() => tick((n) => n + 1), 60_000);
    return () => clearInterval(t);
  }, [actionable]);
  const [riskLabel, riskTone] = RISK[a.risk];
  const [stLabel, stTone] = APPROVAL_STATUS[a.status];

  async function decide(approve: boolean) {
    let note = "";
    if (!approve) {
      const r = await confirm({
        title: "Từ chối yêu cầu này?",
        body: a.title,
        confirmLabel: "Từ chối",
        tone: "danger",
        reason: { label: "Góp ý cho agent (ghi vào nhật ký)", placeholder: "Ví dụ: chưa đủ số liệu, làm lại sau" },
      });
      if (r === null) return;
      note = r;
    }
    setBusy(true);
    try {
      await withReauth(() => api(`/approvals/${a.id}/decide`, { method: "POST", body: { approve, note } }));
      toast(approve ? `Đã duyệt: ${a.title}` : `Đã từ chối: ${a.title}`);
      await onChange();
    } catch (x) {
      const m = msg(x);
      if (m) toast(m, "error");
    } finally {
      setBusy(false);
    }
  }

  const agent = typeof a.payload.agent === "string" ? a.payload.agent : null;
  return (
    <Card
      title={a.title}
      description={
        <>
          {SUBJECT[a.subject_type] ?? a.subject_type}, yêu cầu bởi {actor(a.requested_by)} {ago(a.created_at)}
          {agent && (
            <>
              {" "}
              (<Link href={`/agent/${agent}`}>xem agent</Link>)
            </>
          )}
        </>
      }
      actions={
        <>
          <Badge tone={riskTone}>{riskLabel}</Badge>
          {!actionable && <Badge tone={stTone}>{stLabel}</Badge>}
        </>
      }
      footer={
        actionable ? (
          <>
            <span className="hint">
              <Clock size={13} aria-hidden="true" /> Hết hạn {when(a.expires_at)} ({left(a.expires_at)})
            </span>
            <button type="button" className="btn btn-secondary" onClick={() => decide(false)} disabled={busy}>
              <X size={16} aria-hidden="true" /> Từ chối
            </button>
            <button type="button" className="btn btn-primary" onClick={() => decide(true)} disabled={busy}>
              <Check size={16} aria-hidden="true" /> Duyệt
            </button>
          </>
        ) : a.decided_at ? (
          <span className="hint">
            {stLabel} {when(a.decided_at)}
            {a.decided_by ? ` bởi ${actor(a.decided_by)}` : ""}
            {a.decision_note ? `. Ghi chú: ${a.decision_note}` : ""}
          </span>
        ) : undefined
      }
      flush
    >
      <div className="card-body stack">
        {a.summary && <p>{a.summary}</p>}
        {a.payload.core_changed && (
          <p className="alert warn">Phiên bản này đổi quy tắc cốt lõi hoặc quyền công cụ của agent. Xem kỹ các dòng bên dưới trước khi duyệt.</p>
        )}
      </div>
      {Array.isArray(a.payload.diff) ? (
        <DiffTable changes={a.payload.diff} />
      ) : a.payload.input !== undefined ? (
        <div className="card-body">
          <p className="muted small">Nội dung agent muốn gửi</p>
          <pre className="json">{JSON.stringify(a.payload.input, null, 2)}</pre>
        </div>
      ) : null}
    </Card>
  );
}
