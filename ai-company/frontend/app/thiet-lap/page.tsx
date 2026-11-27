"use client";

import { Leaf } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, type AuthState } from "@/lib/api";

type Enroll = { totp_secret: string; totp_uri: string; qr_svg: string };

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [enroll, setEnroll] = useState<Enroll | null>(null);
  const [cred, setCred] = useState({ email: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api<AuthState>("/auth/state")
      .then((s) => {
        if (alive && !s.needs_setup) router.replace(s.authenticated ? "/" : "/dang-nhap");
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [router]);

  async function step1(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const password = String(f.get("password"));
    if (password !== f.get("password2")) return setErr("Hai lần nhập mật khẩu không khớp.");
    setBusy(true);
    setErr("");
    try {
      const email = String(f.get("email"));
      const r = await api<Enroll>("/auth/setup", {
        method: "POST",
        body: { setup_token: f.get("setup_token"), email, display_name: f.get("display_name"), password },
      });
      setEnroll(r);
      setCred({ email, password });
      setStep(2);
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Có lỗi, thử lại.");
    } finally {
      setBusy(false);
    }
  }

  async function step2(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setErr("");
    try {
      await api("/auth/setup/confirm", { method: "POST", body: { ...cred, code: f.get("code") } });
      router.replace("/");
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Có lỗi, thử lại.");
      setBusy(false);
    }
  }

  const head = (
    <>
      <div className="auth-brand">
        <span className="logo lg" aria-hidden="true">
          <Leaf size={20} />
        </span>
        <div>
          <b>Xưởng Trà Mộc</b>
          <span>Thiết lập văn phòng AI, bước {step}/2</span>
        </div>
      </div>
      <div className="steps" aria-hidden="true">
        <span className="on" />
        <span className={step === 2 ? "on" : ""} />
      </div>
    </>
  );
  const error = err && (
    <p className="alert danger" role="alert">
      {err}
    </p>
  );

  return (
    <main className="auth">
      {step === 1 ? (
        <form className="auth-card" onSubmit={step1}>
          {head}
          <h1>Tạo tài khoản Owner</h1>
          <p className="lead">
            Mã thiết lập hiện trong cửa sổ PowerShell khi chạy <code>khoi-dong.ps1</code>, dùng một lần trong 30 phút.
          </p>
          <label className="field">
            <span>Mã thiết lập</span>
            <input className="input" name="setup_token" autoComplete="off" placeholder="ABCD-1234" required autoFocus />
          </label>
          <label className="field">
            <span>Tên hiển thị</span>
            <input className="input" name="display_name" autoComplete="name" required maxLength={80} />
          </label>
          <label className="field">
            <span>Email</span>
            <input className="input" name="email" type="email" autoComplete="username" required />
          </label>
          <div className="field">
            <label htmlFor="pw">Mật khẩu</label>
            <input className="input" id="pw" name="password" type="password" autoComplete="new-password" minLength={10} required aria-describedby="pw-help" />
            <span className="help" id="pw-help">
              Ít nhất 10 ký tự.
            </span>
          </div>
          <label className="field">
            <span>Nhập lại mật khẩu</span>
            <input className="input" name="password2" type="password" autoComplete="new-password" minLength={10} required />
          </label>
          {error}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            Tiếp tục
          </button>
        </form>
      ) : (
        <form className="auth-card" onSubmit={step2}>
          {head}
          <h1>Bật xác thực hai lớp</h1>
          <p className="lead">Mở Google Authenticator hoặc Microsoft Authenticator, quét mã dưới đây, rồi nhập mã 6 số ứng dụng hiện ra.</p>
          {/* SVG do backend sinh bằng thư viện segno */}
          <div className="qr" dangerouslySetInnerHTML={{ __html: enroll?.qr_svg ?? "" }} />
          <details>
            <summary>Không quét được? Nhập khóa bằng tay</summary>
            <code className="secret">{enroll?.totp_secret}</code>
          </details>
          <label className="field">
            <span>Mã 6 số</span>
            <input className="input" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" required autoFocus />
          </label>
          {error}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            Hoàn tất
          </button>
        </form>
      )}
    </main>
  );
}
