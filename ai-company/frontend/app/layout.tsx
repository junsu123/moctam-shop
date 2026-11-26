import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trung tâm điều hành: AI Marketing Company",
  description: "Trang quản trị của Owner: tình trạng hệ thống, agent, phê duyệt, cài đặt.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
