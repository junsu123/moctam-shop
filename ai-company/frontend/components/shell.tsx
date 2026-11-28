"use client";

import { Activity, Bot, Brain, ChevronDown, ChevronRight, ClipboardCheck, ListChecks, LayoutDashboard, Leaf, LogOut, Settings, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { DialogProvider } from "@/components/ui/dialog";
import { ToastProvider } from "@/components/ui/toast";
import { api, ApiError, setCsrf, type AuthState } from "@/lib/api";

type Ctx = {
  user: NonNullable<AuthState["user"]>;
  /** Chạy thao tác nhạy cảm; nếu máy chủ đòi xác thực lại thì hỏi mật khẩu + mã 2FA rồi chạy lại một lần. */
  withReauth: <T>(fn: () => Promise<T>) => Promise<T>;
};
const ShellCtx = createContext<Ctx | null>(null);

export function useShell(): Ctx {
  const c = useContext(ShellCtx);
  if (!c) throw new Error("useShell ngoài Shell");
  return c;
}

const NAV = [
  { href: "/", label: "Tổng quan", icon: LayoutDashboard },
  { href: "/agent", label: "Agent", icon: Bot },
  { href: "/viec", label: "Việc", icon: ListChecks },
  { href: "/tri-nho", label: "Trí nhớ", icon: Brain },
  { href: "/dien-bien", label: "Diễn biến", icon: Activity },
  { href: "/phe-duyet", label: "Phê duyệt", icon: ClipboardCheck },
  { href: "/cai-dat", label: "Cài đặt", icon: Settings },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [state, setState] = useState<AuthState | null>(null);
  const [failed, setFailed] = useState("");
  const pending = useRef<{ resolve: () => void; reject: (e: unknown) => void } | null>(null);
  const [asking, setAsking] = useState(false);
  const approvalsPending = usePendingCount(path, !!state?.authenticated);

  useEffect(() => {
    let alive = true;
    api<AuthState>("/auth/state")
      .then((s) => {
        if (!alive) return;
        if (s.needs_setup) return router.replace("/thiet-lap");
        if (!s.authenticated) return router.replace("/dang-nhap");
        setCsrf(s.csrf);
        setState(s);
      })
      .catch((e: ApiError) => alive && setFailed(e.message));
    return () => {
      alive = false;
    };
  }, [router]);

  const withReauth = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T> => {
      try {
        return await fn();
      } catch (e) {
        if (!(e instanceof ApiError)) throw e;
        if (e.code === "UNAUTHENTICATED") {
          router.replace("/dang-nhap");
          throw e;
        }
        if (e.code !== "REAUTH_REQUIRED") throw e;
        await new Promise<void>((resolve, reject) => {
          pending.current = { resolve, reject };
          setAsking(true);
        });
        return fn();
      }
    },
    [router],
  );

  if (failed) {
    return (
      <main className="auth">
        <div className="auth-card">
          <h1>Không mở được trang quản trị</h1>
          <p className="alert danger">{failed}</p>
        </div>
      </main>
    );
  }
  if (!state?.user) {
    return (
      <main className="auth" aria-busy="true">
        <span className="spinner" role="status" aria-label="Đang tải" />
      </main>
    );
  }

  const current = NAV.find((n) => (n.href === "/" ? path === "/" : path.startsWith(n.href)));

  return (
    <ShellCtx.Provider value={{ user: state.user, withReauth }}>
      <ToastProvider>
        <DialogProvider>
          <div className="app">
            <aside className="sidebar">
              <div className="sb-brand">
                <span className="logo" aria-hidden="true">
                  <Leaf size={17} />
                </span>
                <div className="sb-brand-text">
                  <b>Xưởng Trà Mộc</b>
                  <span>Văn phòng AI</span>
                </div>
              </div>
              <nav className="sb-nav" aria-label="Mục chính">
                <div className="sb-group">Vận hành</div>
                {NAV.map((n) => (
                  <Link key={n.href} href={n.href} className="sb-link" aria-current={current?.href === n.href ? "page" : undefined}>
                    <n.icon size={18} aria-hidden="true" />
                    {n.label}
                    {n.href === "/phe-duyet" && approvalsPending > 0 && (
                      <span className="sb-count" aria-label={`${approvalsPending} việc chờ duyệt`}>
                        {approvalsPending}
                      </span>
                    )}
                  </Link>
                ))}
              </nav>
              <div className="sb-foot">
                <span>AI Marketing Company</span>
                <span className="subtle">Chạy trên máy của anh/chị</span>
              </div>
            </aside>
            <div className="content">
              <header className="topbar">
                <nav className="crumbs" aria-label="Vị trí">
                  <span className="hide-sm">Văn phòng AI</span>
                  <ChevronRight size={14} className="hide-sm" aria-hidden="true" />
                  <b>{current?.label ?? ""}</b>
                </nav>
                <div className="grow" />
                <HealthPill />
                <UserMenu user={state.user} />
              </header>
              <main className="page">{children}</main>
            </div>
          </div>
          {asking && (
            <ReauthDialog
              onDone={() => {
                setAsking(false);
                pending.current?.resolve();
              }}
              onCancel={() => {
                setAsking(false);
                pending.current?.reject(new ApiError("REAUTH_CANCELLED", "Đã hủy.", 0));
              }}
            />
          )}
        </DialogProvider>
      </ToastProvider>
    </ShellCtx.Provider>
  );
}

/** Số việc chờ duyệt cho thanh bên: hỏi lại mỗi 30 giây và mỗi khi chuyển trang. */
function usePendingCount(path: string, enabled: boolean): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    const tick = () =>
      api<{ pending: number }>("/approvals/count")
        .then((r) => alive && setN(r.pending))
        .catch(() => undefined);
    void tick();
    const t = setInterval(tick, 30_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [path, enabled]);
  return n;
}

function HealthPill() {
  const [st, setSt] = useState<"ok" | "bad" | "">("");
  useEffect(() => {
    let alive = true;
    const tick = () =>
      api<{ status: string }>("/health/ready")
        .then((r) => alive && setSt(r.status === "ok" ? "ok" : "bad"))
        .catch(() => alive && setSt("bad"));
    void tick();
    const t = setInterval(tick, 30_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  if (!st) return null;
  return (
    <Link href="/" className={`health-pill ${st}`} title="Tình trạng cơ sở dữ liệu và hàng đợi, kiểm tra mỗi 30 giây">
      <span className="badge-dot" aria-hidden="true" />
      {st === "ok" ? "Hệ thống ổn định" : "Hệ thống có lỗi"}
    </Link>
  );
}

function UserMenu({ user }: { user: NonNullable<AuthState["user"]> }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", off);
    document.addEventListener("keydown", off);
    return () => {
      document.removeEventListener("mousedown", off);
      document.removeEventListener("keydown", off);
    };
  }, [open]);
  const initials = user.display_name
    .split(/\s+/)
    .slice(-2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/dang-nhap");
  }

  return (
    <div className="menu" ref={box}>
      <button type="button" className="menu-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="avatar" aria-hidden="true">
          {initials}
        </span>
        <span className="hide-sm">{user.display_name}</span>
        <ChevronDown size={16} aria-hidden="true" />
      </button>
      {open && (
        <div className="menu-pop" role="menu">
          <div className="menu-head">
            <b>{user.display_name}</b>
            <span className="muted xs">{user.email}</span>
            <span className="row xs muted">
              <ShieldCheck size={14} aria-hidden="true" /> Chủ sở hữu, đã bật xác thực hai lớp
            </span>
          </div>
          <button type="button" role="menuitem" className="menu-item danger" onClick={logout}>
            <LogOut size={16} aria-hidden="true" /> Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
}

function ReauthDialog({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    ref.current?.showModal();
  }, []);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setErr("");
    try {
      await api("/auth/reauth", { method: "POST", body: { password: f.get("password"), code: f.get("code") } });
      onDone();
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Có lỗi, thử lại.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog ref={ref} className="dialog" onCancel={onCancel} aria-labelledby="reauth-h">
      <form onSubmit={submit}>
        <div className="dialog-body">
          <div className="dialog-head">
            <span className="dialog-ic warn">
              <ShieldCheck size={20} />
            </span>
            <div>
              <h2 id="reauth-h">Xác nhận lại</h2>
              <p>Thao tác này đổi khóa hoặc quyền, nên cần nhập lại mật khẩu và mã trong ứng dụng xác thực. Có hiệu lực 5 phút.</p>
            </div>
          </div>
          <label className="field">
            <span>Mật khẩu</span>
            <input className="input" name="password" type="password" autoComplete="current-password" required autoFocus />
          </label>
          <label className="field">
            <span>Mã 6 số</span>
            <input className="input" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" required />
          </label>
          {err && (
            <p className="alert danger" role="alert">
              {err}
            </p>
          )}
        </div>
        <div className="dialog-foot">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            Hủy
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Xác nhận
          </button>
        </div>
      </form>
    </dialog>
  );
}
