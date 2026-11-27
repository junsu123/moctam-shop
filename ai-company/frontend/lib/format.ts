// Hiển thị theo giờ Việt Nam; dữ liệu lưu UTC (CLAUDE.md: Quy ước).
const TZ = "Asia/Ho_Chi_Minh";

const timeFmt = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const dateTimeFmt = new Intl.DateTimeFormat("vi-VN", {
  timeZone: TZ,
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dayFmt = new Intl.DateTimeFormat("vi-VN", { timeZone: TZ, weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });

export const clock = (iso: string | Date) => timeFmt.format(new Date(iso));
/** "23:27, 26/11" */
export function when(iso: string | Date | null | undefined): string {
  if (!iso) return "";
  const p = Object.fromEntries(dateTimeFmt.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return `${p.hour}:${p.minute}, ${p.day}/${p.month}`;
}
export const dayLabel = (iso: string | Date) => dayFmt.format(new Date(iso));
export const dayKey = (iso: string | Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date(iso));

export function usd(v: number, digits = 2): string {
  if (v > 0 && v < 0.01) return "< 0,01 USD";
  return `${v.toLocaleString("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits })} USD`;
}

export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "vừa xong";
  if (s < 3600) return `${Math.floor(s / 60)} phút trước`;
  if (s < 86400) return `${Math.floor(s / 3600)} giờ trước`;
  return when(iso);
}

export function actorLabel(actor: string): string {
  if (actor.startsWith("user:")) return "Owner";
  if (actor.startsWith("agent:")) return actor.slice(6);
  if (actor === "telegram") return "Telegram";
  return "Hệ thống";
}
