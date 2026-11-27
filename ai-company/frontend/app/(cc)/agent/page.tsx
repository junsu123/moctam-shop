"use client";

import { Bot, Pause, Play, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useConfirm } from "@/components/ui/dialog";
import { Card, Empty, ErrorAlert, Loading, PageHeader, StateBadge } from "@/components/ui/primitives";
import { Tabs, TabPanel, useTabParam } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type Agent } from "@/lib/api";
import { ago } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const DEPTS = [
  { id: "all", label: "Tất cả" },
  { id: "executive", label: "Điều hành" },
  { id: "marketing", label: "Marketing" },
  { id: "sales", label: "Kinh doanh" },
  { id: "growth", label: "Tăng trưởng" },
  { id: "technology", label: "Công nghệ & Dữ liệu" },
] as const;
type Dept = (typeof DEPTS)[number]["id"];
const DEPT_NAME: Record<string, string> = Object.fromEntries(DEPTS.map((d) => [d.id, d.label]));
const KIND_NAME: Record<Agent["kind"], string> = { executive: "Điều hành", director: "Giám đốc", specialist: "Chuyên viên" };

export default function AgentsPage() {
  const { data: agents, error, reload } = useApi<Agent[]>("/agents");
  const [tab, setTab] = useTabParam<Dept>(
    DEPTS.map((d) => d.id),
    "all",
  );
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  const confirm = useConfirm();
  const toast = useToast();

  async function act(a: Agent) {
    const pausing = a.state !== "paused";
    const reason = pausing
      ? await confirm({
          title: `Tạm dừng ${a.display_name}?`,
          body: "Agent sẽ không nhận việc mới và không gọi AI cho tới khi anh/chị cho chạy lại.",
          confirmLabel: "Tạm dừng",
          tone: "warn",
          reason: { label: "Lý do (ghi vào nhật ký, có thể bỏ trống)", placeholder: "Ví dụ: chờ duyệt bộ từ khóa mới" },
        })
      : "";
    if (reason === null) return;
    setBusy(a.agent_key);
    try {
      await api(`/agents/${a.agent_key}/${pausing ? "pause" : "resume"}`, { method: "POST", body: pausing ? { reason } : {} });
      toast(pausing ? `Đã tạm dừng ${a.display_name}.` : `${a.display_name} đã chạy lại.`);
      await reload();
    } catch (x) {
      toast(x instanceof ApiError ? x.message : "Không thực hiện được.", "error");
    } finally {
      setBusy("");
    }
  }

  async function pauseAll() {
    const reason = await confirm({
      title: "Tạm dừng tất cả agent?",
      body: "Toàn bộ văn phòng AI ngừng nhận việc và ngừng gọi AI. Có thể cho chạy lại từng agent.",
      confirmLabel: "Tạm dừng tất cả",
      tone: "danger",
      reason: { label: "Lý do", initial: "Tạm dừng toàn bộ" },
    });
    if (reason === null) return;
    setBusy("*");
    try {
      const r = await api<{ paused: number }>("/agents/pause-all", { method: "POST", body: { reason } });
      toast(`Đã tạm dừng ${r.paused} agent.`);
      await reload();
    } catch (x) {
      toast(x instanceof ApiError ? x.message : "Không thực hiện được.", "error");
    } finally {
      setBusy("");
    }
  }

  if (!agents) return error ? <ErrorAlert>{error}</ErrorAlert> : <Loading what="danh sách agent" />;
  const paused = agents.filter((a) => a.state === "paused").length;
  const needle = q.trim().toLowerCase();
  const list = agents.filter(
    (a) => (tab === "all" || a.department === tab) && (!needle || `${a.display_name} ${a.role_summary} ${a.agent_key}`.toLowerCase().includes(needle)),
  );

  return (
    <>
      <PageHeader
        title="Agent"
        description={`${agents.length} agent, ${paused ? `${paused} đang tạm dừng` : "tất cả đang chạy"}. Agent tạm dừng không nhận việc mới và không gọi AI.`}
        actions={
          <button type="button" className="btn btn-danger-outline" onClick={pauseAll} disabled={busy !== "" || paused === agents.length}>
            <Pause size={16} aria-hidden="true" /> Tạm dừng tất cả
          </button>
        }
      />
      <Tabs
        label="Phòng ban"
        value={tab}
        onChange={setTab}
        tabs={DEPTS.map((d) => ({ id: d.id, label: d.label, count: d.id === "all" ? agents.length : agents.filter((a) => a.department === d.id).length }))}
      />
      <TabPanel id={tab}>
        <Card
          title={tab === "all" ? "Toàn bộ agent" : `Phòng ${DEPT_NAME[tab]}`}
          actions={
            <label className="input-icon">
              <Search size={16} aria-hidden="true" />
              <input className="input" type="search" placeholder="Tìm agent" aria-label="Tìm agent" value={q} onChange={(e) => setQ(e.target.value)} />
            </label>
          }
          flush
        >
          {list.length === 0 ? (
            <Empty icon={<Bot size={20} />} title="Không có agent phù hợp">
              Thử từ khóa khác hoặc chọn tab Tất cả.
            </Empty>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Agent</th>
                    {tab === "all" && (
                      <th scope="col" className="hide-sm">
                        Phòng ban
                      </th>
                    )}
                    <th scope="col" className="hide-sm">
                      Cấp
                    </th>
                    <th scope="col">Trạng thái</th>
                    <th scope="col" className="hide-sm">
                      Cập nhật
                    </th>
                    <th scope="col" className="right">
                      <span className="sr-only">Thao tác</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((a) => (
                    <tr key={a.agent_key} data-agent={a.agent_key}>
                      <td>
                        <div className="cell-main">
                          <Link href={`/agent/${a.agent_key}`} className="row-link">
                            {a.display_name}
                          </Link>
                          <span>{a.role_summary}</span>
                          {a.state === "paused" && a.reason && <span className="note">Lý do dừng: {a.reason}</span>}
                        </div>
                      </td>
                      {tab === "all" && <td className="hide-sm nowrap">{DEPT_NAME[a.department] ?? a.department}</td>}
                      <td className="hide-sm nowrap">{KIND_NAME[a.kind]}</td>
                      <td>
                        <StateBadge state={a.state} />
                      </td>
                      <td className="hide-sm nowrap muted">{ago(a.updated_at)}</td>
                      <td className="right">
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => act(a)} disabled={busy !== ""}>
                          {a.state === "paused" ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
                          {a.state === "paused" ? "Chạy lại" : "Tạm dừng"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </TabPanel>
    </>
  );
}
