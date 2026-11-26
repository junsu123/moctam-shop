"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

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
  { href: "/", label: "Tổng quan" },
  { href: "/agent", label: "Agent" },
  { href: "/dien-bien", label: "Diễn biến" },
  { href: "/cai-dat", label: "Cài đặt" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [state, setState] = useState<AuthState | null>(null);
  const [failed, setFailed] = useState<string>("");
  const pending = useRef<{ resolve: () => void; reject: (e: unknown) => void } | null>(null);
  const [asking, setAsking] = useState(false);

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

  const withReauth = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
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
  }, [router]);

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/dang-nhap");
  }

  if (failed) {
    return (
      <main className="gate">
        <h1>Không mở được trang quản trị</h1>
        <p>{failed}</p>
      </main>
    );
  }
  if (!state?.user) return <main className="gate" aria-busy="true" />;

  return (
    <ShellCtx.Provider value={{ user: state.user, withReauth }}>
      <div className="frame">
        <aside className="side">
          <div className="brand">
            <span className="brand-name">Xưởng Trà Mộc</span>
            <span className="brand-sub">Văn phòng AI</span>
          </div>
          <nav aria-label="Mục chính">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="nav" aria-current={path === n.href ? "page" : undefined}>
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="me">
            <span>{state.user.display_name}</span>
            <button type="button" className="link" onClick={logout}>
              Đăng xuất
            </button>
          </div>
        </aside>
        <main className="main">{children}</main>
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
    </ShellCtx.Provider>
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
        <h2 id="reauth-h">Xác nhận lại</h2>
        <p className="muted">Thao tác này đổi khóa hoặc quyền, nên cần nhập lại mật khẩu và mã trong ứng dụng xác thực. Có hiệu lực 5 phút.</p>
        <label>
          Mật khẩu
          <input name="password" type="password" autoComplete="current-password" required autoFocus />
        </label>
        <label>
          Mã 6 số
          <input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" required />
        </label>
        {err && (
          <p className="err" role="alert">
            {err}
          </p>
        )}
        <div className="row">
          <button type="submit" className="btn" disabled={busy}>
            Xác nhận
          </button>
          <button type="button" className="btn ghost" onClick={onCancel}>
            Hủy
          </button>
        </div>
      </form>
    </dialog>
  );
}
