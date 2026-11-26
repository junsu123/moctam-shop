import type { NextConfig } from "next";

// Trang quản trị gọi API qua cùng nguồn (/api/v1/...) và Next chuyển tiếp sang backend trong mạng Docker.
// Nhờ vậy trình duyệt không cần biết địa chỉ backend, cookie phiên là cùng nguồn, và CSP chỉ cần 'self'.
const backend = process.env.AICO_BACKEND_URL ?? "http://127.0.0.1:8000";

const securityHeaders = [
  // Content-Security-Policy (có nonce) do proxy.ts đặt cho từng lần tải trang.
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-Frame-Options", value: "DENY" },
];

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Tắt nén: trang chỉ chạy trên 127.0.0.1, và nén làm luồng diễn biến (SSE) bị giữ lại thay vì đẩy ngay.
  compress: false,
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default config;
