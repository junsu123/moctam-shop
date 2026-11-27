"use client";

import { Leaf, LogIn } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, type AuthState } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api<AuthState>("/auth/state")
      .then((s) => {
        if (!alive) return;
        if (s.needs_setup) router.replace("/thiet-lap");
        else if (s.authenticated) router.replace("/");
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [router]);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setErr("");
    try {
      await api("/auth/login", { method: "POST", body: { email: f.get("email"), password: f.get("password"), code: f.get("code") } });
      router.replace("/");
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Có lỗi, thử lại.");
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-brand">
          <span className="logo lg" aria-hidden="true">
            <Leaf size={20} />
          </span>
          <div>
            <b>Xưởng Trà Mộc</b>
            <span>Văn phòng AI</span>
          </div>
        </div>
        <h1>Đăng nhập</h1>
        <p className="lead">Dùng email, mật khẩu và mã 6 số trong ứng dụng xác thực trên điện thoại.</p>
        <label className="field">
          <span>Email</span>
          <input className="input" name="email" type="email" autoComplete="username" required autoFocus />
        </label>
        <label className="field">
          <span>Mật khẩu</span>
          <input className="input" name="password" type="password" autoComplete="current-password" required />
        </label>
        <label className="field">
          <span>Mã xác thực 6 số</span>
          <input className="input" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" required />
        </label>
        {err && (
          <p className="alert danger" role="alert">
            {err}
          </p>
        )}
        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          <LogIn size={16} aria-hidden="true" /> Đăng nhập
        </button>
        <p className="auth-foot">Sai 5 lần liên tiếp thì tài khoản tạm khóa 15 phút.</p>
      </form>
    </main>
  );
}
