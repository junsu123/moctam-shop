"use client";

import { CheckCircle2, AlertCircle, X } from "lucide-react";
import { createContext, useCallback, useContext, useState } from "react";

type Toast = { id: number; text: string; kind: "success" | "error" };
type Notify = (text: string, kind?: Toast["kind"]) => void;
const Ctx = createContext<Notify>(() => undefined);

export const useToast = () => useContext(Ctx);

/** Thông báo nổi góc dưới phải. Thành công tự ẩn sau 4 giây; lỗi giữ tới khi bấm đóng. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const close = useCallback((id: number) => setItems((l) => l.filter((t) => t.id !== id)), []);
  const notify = useCallback<Notify>(
    (text, kind = "success") => {
      if (!text) return;
      const id = Date.now() + Math.random();
      setItems((l) => [...l.slice(-3), { id, text, kind }]);
      if (kind === "success") setTimeout(() => close(id), 4000);
    },
    [close],
  );
  return (
    <Ctx.Provider value={notify}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
            <span className="t-ic">{t.kind === "error" ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}</span>
            <p>{t.text}</p>
            <button type="button" aria-label="Đóng thông báo" onClick={() => close(t.id)}>
              <X size={16} />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
