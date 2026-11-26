import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Văn phòng AI: Xưởng Trà Mộc",
  description: "Trang quản trị của Owner: tình trạng hệ thống, agent, diễn biến, cài đặt.",
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Đọc header để trang luôn render theo từng request: Next gắn nonce CSP (proxy.ts) vào script của nó.
  await headers();
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
