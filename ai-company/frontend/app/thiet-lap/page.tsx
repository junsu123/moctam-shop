"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, type AuthState } from "@/lib/api";

type Enroll = { totp_secret: string; totp_uri: string; qr_svg: string };

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [enroll, setEnroll] = useState<Enroll | null>(null);
  const [cred, setCred] = useState<{ email: string; password: string }>({ email: "", password: "" });
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

  return (
    <main className="gate">
      {step === 1 ? (
        <form className="card-form" onSubmit={step1}>
          <p className="brand-name">Xưởng Trà Mộc</p>
          <h1>Thiết lập văn phòng AI</h1>
          <p className="muted">
            Tạo tài khoản Owner. Mã thiết lập hiện trong cửa sổ PowerShell khi chạy <code>scripts\windows\khoi-dong.ps1</code>, dùng một lần trong 30 phút.
          </p>
          <label>
            Mã thiết lập
            <input name="setup_token" autoComplete="off" placeholder="ABCD-1234" required autoFocus />
          </label>
          <label>
            Tên hiển thị
            <input name="display_name" autoComplete="name" required maxLength={80} />
          </label>
          <label>
            Email
            <input name="email" type="email" autoComplete="username" required />
          </label>
          <label>
            Mật khẩu (ít nhất 10 ký tự)
            <input name="password" type="password" autoComplete="new-password" minLength={10} required />
          </label>
          <label>
            Nhập lại mật khẩu
            <input name="password2" type="password" autoComplete="new-password" minLength={10} required />
          </label>
          {err && (
            <p className="err" role="alert">
              {err}
            </p>
          )}
          <button type="submit" className="btn wide" disabled={busy}>
            Tiếp tục
          </button>
        </form>
      ) : (
        <form className="card-form" onSubmit={step2}>
          <p className="brand-name">Bước 2 / 2</p>
          <h1>Bật xác thực hai lớp</h1>
          <p className="muted">
            Mở Google Authenticator hoặc Microsoft Authenticator trên điện thoại, quét mã dưới đây, rồi nhập mã 6 số ứng dụng hiện ra.
          </p>
          {/* SVG do backend sinh từ thư viện segno (không chứa dữ liệu người dùng nhập ngoài email đã kiểm tra) */}
          <div className="qr" dangerouslySetInnerHTML={{ __html: enroll?.qr_svg ?? "" }} />
          <details>
            <summary>Không quét được? Nhập khóa bằng tay</summary>
            <code className="secret">{enroll?.totp_secret}</code>
          </details>
          <label>
            Mã 6 số
            <input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" required autoFocus />
          </label>
          {err && (
            <p className="err" role="alert">
              {err}
            </p>
          )}
          <button type="submit" className="btn wide" disabled={busy}>
            Hoàn tất
          </button>
        </form>
      )}
    </main>
  );
}
