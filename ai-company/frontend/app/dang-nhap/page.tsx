"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, type AuthState } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<AuthState>("/auth/state")
      .then((s) => {
        if (s.needs_setup) router.replace("/thiet-lap");
        else if (s.authenticated) router.replace("/");
      })
      .catch(() => undefined);
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
    <main className="gate">
      <form className="card-form" onSubmit={submit}>
        <p className="brand-name">Xưởng Trà Mộc</p>
        <h1>Đăng nhập văn phòng AI</h1>
        <label>
          Email
          <input name="email" type="email" autoComplete="username" required autoFocus />
        </label>
        <label>
          Mật khẩu
          <input name="password" type="password" autoComplete="current-password" required />
        </label>
        <label>
          Mã 6 số trong ứng dụng xác thực
          <input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" required />
        </label>
        {err && (
          <p className="err" role="alert">
            {err}
          </p>
        )}
        <button type="submit" className="btn wide" disabled={busy}>
          Đăng nhập
        </button>
        <p className="muted small">Sai 5 lần liên tiếp thì tài khoản tạm khóa 15 phút.</p>
      </form>
    </main>
  );
}
