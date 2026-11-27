import type { Tone } from "@/components/ui/primitives";

export const LEVEL: Record<number, string> = { 1: "Chỉ đọc", 2: "Soạn nháp", 3: "Thực hiện", 4: "Tự động nâng cao" };
export const LEVEL_TONE: Record<number, Tone> = { 1: "neutral", 2: "info", 3: "warn", 4: "danger" };

export const RISK: Record<string, [string, Tone]> = {
  low: ["Rủi ro thấp", "neutral"],
  medium: ["Rủi ro vừa", "warn"],
  high: ["Rủi ro cao", "danger"],
};

export const BRAIN_STATE: Record<string, [string, Tone]> = {
  active: ["Đang chạy", "success"],
  draft: ["Chờ duyệt", "warn"],
  shadow: ["Chạy thử", "info"],
  retired: ["Bản cũ", "neutral"],
  rejected: ["Bị từ chối", "danger"],
};

export const VERSION_EVENT: Record<string, string> = {
  bootstrap: "Nạp lần đầu",
  proposed: "Đề xuất phiên bản mới",
  activated: "Kích hoạt",
  rolled_back: "Quay lại bản cũ",
  rejected: "Bị từ chối",
  core_pinned: "Ghim quy tắc cốt lõi",
};

export const DECISION: Record<string, [string, Tone]> = {
  allow: ["Cho phép", "success"],
  require_approval: ["Cần duyệt", "warn"],
  deny: ["Chặn", "danger"],
};

export const CALL_STATUS: Record<string, [string, Tone]> = {
  succeeded: ["Thành công", "success"],
  running: ["Đang chạy", "info"],
  waiting_approval: ["Chờ duyệt", "warn"],
  denied: ["Bị chặn", "danger"],
  failed: ["Lỗi", "danger"],
};

export const APPROVAL_STATUS: Record<string, [string, Tone]> = {
  pending: ["Chờ duyệt", "warn"],
  approved: ["Đã duyệt", "success"],
  rejected: ["Đã từ chối", "danger"],
  expired: ["Hết hạn", "neutral"],
  cancelled: ["Đã hủy", "neutral"],
};

export const DEPT: Record<string, string> = {
  executive: "Điều hành",
  marketing: "Marketing",
  sales: "Kinh doanh",
  growth: "Tăng trưởng",
  technology: "Công nghệ & Dữ liệu",
};

export const MODEL_PROFILE: Record<string, string> = {
  cheap: "Rẻ (phân loại, nháp)",
  writer_vi: "Viết tiếng Việt",
  reasoning_mid: "Lập luận vừa",
  reasoning_high: "Lập luận mạnh",
  fallback: "Dự phòng",
  judge: "Chấm điểm",
};

export const short = (h: string | null | undefined, n = 10) => (h ? h.slice(0, n) : "");

export function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "(không có)";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

/** Người thực hiện dễ đọc: "user:a@b.vn" → a@b.vn, "agent:seo_agent" → seo_agent, hệ thống → chữ thường. */
export function actor(a: string | null | undefined): string {
  if (!a) return "";
  if (a.startsWith("user:")) return a.slice(5);
  if (a.startsWith("agent:")) return a.slice(6);
  if (a.startsWith("bootstrap:")) return "nạp lần đầu từ mã nguồn";
  if (a === "system:startup") return "hệ thống khi khởi động";
  if (a.startsWith("system")) return "hệ thống";
  return a;
}
