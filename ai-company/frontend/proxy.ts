import { NextRequest, NextResponse } from "next/server";

// CSP có nonce riêng cho mỗi lần tải trang: chỉ script do Next sinh ra (mang nonce) được chạy (SECURITY_PLAN §2.3).
// Chưa có cookie phiên thì chuyển về trang đăng nhập ngay ở đây, trước khi tải giao diện.
const PUBLIC = ["/dang-nhap", "/thiet-lap"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!PUBLIC.includes(pathname) && !request.cookies.has("aico_session")) {
    return NextResponse.redirect(new URL("/dang-nhap", request.url));
  }
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const dev = process.env.NODE_ENV === "development";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const res = NextResponse.next({ request: { headers } });
  res.headers.set("Content-Security-Policy", csp);
  return res;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico|favicon.svg).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
