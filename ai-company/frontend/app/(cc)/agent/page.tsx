"use client";

import { useState } from "react";

import { Loading, StateTag, useFlash } from "@/components/bits";
import { api, ApiError, type Agent } from "@/lib/api";
import { ago } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const DEPTS: { key: string; name: string; note: string }[] = [
  { key: "executive", name: "Điều hành", note: "Nhận mục tiêu từ anh/chị, chia việc cho các phòng" },
  { key: "marketing", name: "Phòng Marketing", note: "SEO, nội dung, mạng xã hội, quảng cáo, thiết kế" },
  { key: "sales", name: "Phòng Kinh doanh", note: "Khách hàng, đối tác, khách sỉ" },
  { key: "growth", name: "Phòng Tăng trưởng", note: "Thí nghiệm và tối ưu chuyển đổi" },
  { key: "technology", name: "Phòng Công nghệ & Dữ liệu", note: "Website, số liệu, tự động hóa" },
];

export default function AgentsPage() {
  const { data: agents, error, reload: load } = useApi<Agent[]>("/agents");
  const [flash, say] = useFlash();
  const [busy, setBusy] = useState<string>("");

  async function act(a: Agent) {
    let body: { reason: string } | undefined;
    if (a.state !== "paused") {
      const reason = window.prompt(`Tạm dừng “${a.display_name}”. Lý do (để ghi vào nhật ký, có thể bỏ trống):`, "");
      if (reason === null) return;
      body = { reason };
    }
    setBusy(a.agent_key);
    try {
      await api(`/agents/${a.agent_key}/${a.state === "paused" ? "resume" : "pause"}`, { method: "POST", body: body ?? {} });
      say(a.state === "paused" ? `${a.display_name} đã chạy lại.` : `${a.display_name} đã tạm dừng.`);
      await load();
    } catch (x) {
      say(x instanceof ApiError ? x.message : "Không thực hiện được.", "err");
    } finally {
      setBusy("");
    }
  }

  async function pauseAll() {
    const reason = window.prompt("Tạm dừng TẤT CẢ agent. Lý do:", "Tạm dừng toàn bộ");
    if (reason === null) return;
    setBusy("*");
    try {
      const r = await api<{ paused: number }>("/agents/pause-all", { method: "POST", body: { reason } });
      say(`Đã tạm dừng ${r.paused} agent.`);
      await load();
    } catch (x) {
      say(x instanceof ApiError ? x.message : "Không thực hiện được.", "err");
    } finally {
      setBusy("");
    }
  }

  if (!agents) return error ? <p className="err">{error}</p> : <Loading what="danh sách agent" />;
  const paused = agents.filter((a) => a.state === "paused").length;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Agent</h1>
          <p className="muted">
            {agents.length} agent, {paused ? `${paused} đang tạm dừng` : "tất cả đang chạy"}. Agent tạm dừng không nhận việc mới và không gọi AI.
          </p>
        </div>
        <button type="button" className="btn danger" onClick={pauseAll} disabled={busy !== "" || paused === agents.length}>
          Tạm dừng tất cả
        </button>
      </header>
      {flash}
      {DEPTS.map((d) => {
        const list = agents.filter((a) => a.department === d.key);
        if (!list.length) return null;
        return (
          <section key={d.key} className="panel" aria-labelledby={`d-${d.key}`}>
            <div className="panel-head">
              <h2 id={`d-${d.key}`}>{d.name}</h2>
              <p className="muted small">{d.note}</p>
            </div>
            <ul className="agents">
              {list.map((a) => (
                <li key={a.agent_key} className={a.kind}>
                  <div className="who">
                    <span className="name">{a.display_name}</span>
                    <span className="muted small">{a.role_summary}</span>
                    {a.state === "paused" && (
                      <span className="small paused-note">
                        Dừng {ago(a.updated_at)}
                        {a.reason ? `: ${a.reason}` : ""}
                      </span>
                    )}
                  </div>
                  <StateTag state={a.state} />
                  <button type="button" className="btn ghost" onClick={() => act(a)} disabled={busy !== ""}>
                    {a.state === "paused" ? "Chạy lại" : "Tạm dừng"}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </>
  );
}
