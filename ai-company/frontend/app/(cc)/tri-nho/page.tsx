"use client";

import { BookOpen, Brain, Lock, Plus, Sparkles, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { MemoryBrowser } from "@/components/memory";
import { Bar, ErrorAlert, Loading, PageHeader } from "@/components/ui/primitives";
import { Tabs, TabPanel, useTabParam } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type Agent, type MemoryStats } from "@/lib/api";
import { DEPT, MEM_TYPE } from "@/lib/labels";
import { useApi } from "@/lib/use-api";

const TABS = ["chung", "phong-ban", "rieng", "owner"] as const;
type Tab = (typeof TABS)[number];
const DEPT_OPTS = Object.entries(DEPT).map(([k, v]) => ({ value: `dept:${k}`, label: `Phòng ${v}` }));

export default function MemoryPage() {
  const [tab, setTab] = useTabParam<Tab>(TABS, "chung");
  const { data: stats, error, reload } = useApi<MemoryStats>("/memory/stats");
  const { data: agents } = useApi<Agent[]>("/agents");
  const [adding, setAdding] = useState(false);
  const [rk, setRk] = useState(0);
  const toast = useToast();

  async function embedNow() {
    try {
      const r = await api<{ status: string; embedded: number; remaining: number; detail: string }>("/memory/embed", { method: "POST" });
      toast(r.status === "done" ? `Đã nhúng ${r.embedded} mục, còn ${r.remaining}.` : r.detail || "Chưa nhúng được.", r.status === "done" ? "success" : "error");
      await reload();
    } catch (x) {
      toast(x instanceof ApiError ? x.message : "Không thực hiện được.", "error");
    }
  }

  const count = (s: string) => stats?.by_scope.filter((x) => x.scope === s || (s.endsWith(":") && x.scope.startsWith(s))).reduce((a, b) => a + b.n, 0) ?? 0;
  const e = stats?.embedding;
  return (
    <>
      <PageHeader
        title="Trí nhớ"
        description="Những gì các agent nhớ: trải nghiệm riêng, kiến thức đã kiểm chứng, quy trình. Mỗi agent chỉ đọc được phạm vi của mình; kiến thức chung do anh/chị duyệt."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
            <Plus size={16} aria-hidden="true" /> Thêm kiến thức
          </button>
        }
      />
      {error && <ErrorAlert>{error}</ErrorAlert>}
      {!stats ? (
        <Loading what="trí nhớ" />
      ) : (
        <div className="grid-stats">
          <section className="card stat" aria-label="Tổng số mục">
            <span className="stat-label">
              <span className="stat-icon">
                <Brain size={16} />
              </span>
              Tổng số mục
            </span>
            <span className="stat-value">{stats.total.toLocaleString("vi-VN")}</span>
            <span className="stat-foot">
              {Object.entries(MEM_TYPE)
                .map(([k, [label]]) => `${stats.by_type[k as keyof typeof stats.by_type] ?? 0} ${label.toLowerCase()}`)
                .join(", ")}
            </span>
          </section>
          <section className="card stat" aria-label="Truy hồi hôm nay">
            <span className="stat-label">
              <span className="stat-icon info">
                <Sparkles size={16} />
              </span>
              Truy hồi hôm nay
            </span>
            <span className="stat-value">{stats.retrievals_today.toLocaleString("vi-VN")}</span>
            <span className="stat-foot">Mỗi lượt đều ghi lại để truy vết</span>
          </section>
          <section className="card stat span-2" aria-label="Tìm theo nghĩa">
            <span className="stat-label">
              <span className={`stat-icon${e?.configured ? "" : " warn"}`}>
                <BookOpen size={16} />
              </span>
              Tìm theo nghĩa
            </span>
            <span className="stat-value">
              {e?.configured ? `${e.embedded.toLocaleString("vi-VN")}` : "Chưa bật"} {e?.configured && <small>/ {stats.total.toLocaleString("vi-VN")} mục đã nhúng</small>}
            </span>
            {e?.configured ? <Bar value={e.embedded} max={Math.max(1, stats.total)} warnAt={101} label="Đã nhúng" /> : null}
            <span className="stat-foot">
              {e?.configured
                ? `${e.model}, ${e.dims} chiều. Mục mới được nhúng tự động mỗi phút.`
                : "Nhập khóa API OpenAI ở Cài đặt → Nhà cung cấp AI. Trong lúc chờ, trí nhớ vẫn tìm được theo từ khóa (có dấu, không dấu, viết tắt)."}
              {e?.configured && e.pending > 0 && (
                <>
                  {" "}
                  <button type="button" className="link-btn" onClick={embedNow}>
                    Nhúng ngay {e.pending} mục
                  </button>
                </>
              )}
            </span>
          </section>
        </div>
      )}
      <Tabs
        label="Phạm vi trí nhớ"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "chung", label: "Kiến thức chung", count: count("company"), icon: <Users size={16} aria-hidden="true" /> },
          { id: "phong-ban", label: "Theo phòng ban", count: count("dept:") },
          { id: "rieng", label: "Riêng từng agent", count: count("agent:") },
          { id: "owner", label: "Chỉ Owner", count: count("owner_only"), icon: <Lock size={16} aria-hidden="true" /> },
        ]}
      />
      <TabPanel id={tab}>
        {tab === "chung" && <MemoryBrowser scope="company" allowRetire reloadKey={rk} />}
        {tab === "phong-ban" && <MemoryBrowser scopeOptions={DEPT_OPTS} scope={undefined} allowRetire reloadKey={rk} key="dept" />}
        {tab === "rieng" && (
          <MemoryBrowser scopeOptions={(agents ?? []).map((a) => ({ value: `agent:${a.agent_key}`, label: a.display_name }))} allowRetire reloadKey={rk} key="agent" />
        )}
        {tab === "owner" && <MemoryBrowser scope="owner_only" allowRetire reloadKey={rk} />}
      </TabPanel>
      {adding && (
        <AddKnowledge
          onClose={() => setAdding(false)}
          onSaved={async () => {
            setAdding(false);
            setRk((v) => v + 1);
            await reload();
          }}
        />
      )}
    </>
  );
}

function AddKnowledge({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
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
      const validTo = String(f.get("valid_to") || "");
      await api("/memory", {
        method: "POST",
        body: {
          scope: f.get("scope"),
          type: f.get("type"),
          category: f.get("category"),
          title: f.get("title"),
          content: f.get("content"),
          valid_to: validTo ? new Date(validTo + "T23:59:59+07:00").toISOString() : null,
        },
      });
      toast("Đã thêm vào trí nhớ.");
      await onSaved();
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Có lỗi, thử lại.");
      setBusy(false);
    }
  }

  return (
    <dialog ref={ref} className="dialog wide" onCancel={onClose} aria-labelledby="add-k">
      <form onSubmit={submit}>
        <div className="dialog-body">
          <div className="dialog-head">
            <span className="dialog-ic">
              <BookOpen size={20} />
            </span>
            <div>
              <h2 id="add-k">Thêm kiến thức</h2>
              <p>Kiến thức anh/chị thêm có độ tin cậy cao nhất và dùng được ngay. Đừng ghi khóa API hay dữ liệu cá nhân của khách.</p>
            </div>
          </div>
          <div className="form-grid">
            <label className="field">
              <span>Ai được đọc</span>
              <select className="input" name="scope" defaultValue="company">
                <option value="company">Mọi agent (kiến thức chung)</option>
                {DEPT_OPTS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
                <option value="owner_only">Chỉ Owner</option>
              </select>
            </label>
            <label className="field">
              <span>Loại</span>
              <select className="input" name="type" defaultValue="semantic">
                <option value="semantic">Kiến thức</option>
                <option value="procedural">Quy trình</option>
              </select>
            </label>
            <label className="field">
              <span>Nhóm</span>
              <select className="input" name="category" defaultValue="product">
                <option value="product">Sản phẩm</option>
                <option value="brand">Thương hiệu</option>
                <option value="goal">Mục tiêu</option>
                <option value="strategy">Chiến lược</option>
                <option value="policy">Chính sách</option>
                <option value="other">Khác</option>
              </select>
            </label>
            <label className="field">
              <span>Hiệu lực đến (bỏ trống nếu không hết hạn)</span>
              <input className="input" type="date" name="valid_to" />
            </label>
          </div>
          <label className="field">
            <span>Tiêu đề</span>
            <input className="input" name="title" required minLength={3} maxLength={200} />
          </label>
          <label className="field">
            <span>Nội dung</span>
            <textarea className="textarea" name="content" required minLength={5} maxLength={8000} rows={5} />
          </label>
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
            Lưu vào trí nhớ
          </button>
        </div>
      </form>
    </dialog>
  );
}
