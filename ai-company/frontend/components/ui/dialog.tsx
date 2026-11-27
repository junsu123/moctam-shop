"use client";

import { AlertTriangle, Info, PauseCircle } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

export type ConfirmOptions = {
  title: string;
  body?: string;
  confirmLabel: string;
  tone?: "primary" | "danger" | "warn";
  /** Có ô nhập lý do (ghi vào nhật ký). */
  reason?: { label: string; placeholder?: string; initial?: string };
};
/** Trả về lý do (chuỗi, có thể rỗng) khi đồng ý; null khi hủy. */
type Confirm = (o: ConfirmOptions) => Promise<string | null>;
const Ctx = createContext<Confirm>(async () => null);

export const useConfirm = () => useContext(Ctx);

export function DialogProvider({ children }: { children: React.ReactNode }) {
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((v: string | null) => void) | null>(null);
  const confirm = useCallback<Confirm>(
    (o) =>
      new Promise((resolve) => {
        resolver.current = resolve;
        setOpts(o);
      }),
    [],
  );
  const done = (v: string | null) => {
    resolver.current?.(v);
    resolver.current = null;
    setOpts(null);
  };
  return (
    <Ctx.Provider value={confirm}>
      {children}
      {opts && <ConfirmDialog opts={opts} onDone={done} />}
    </Ctx.Provider>
  );
}

function ConfirmDialog({ opts, onDone }: { opts: ConfirmOptions; onDone: (v: string | null) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState(opts.reason?.initial ?? "");
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  const tone = opts.tone ?? "primary";
  const Icon = tone === "danger" ? AlertTriangle : tone === "warn" ? PauseCircle : Info;
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="cf-title" onCancel={() => onDone(null)}>
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault();
          onDone(reason.trim());
        }}
      >
        <div className="dialog-body">
          <div className="dialog-head">
            <span className={`dialog-ic ${tone}`}>
              <Icon size={20} />
            </span>
            <div>
              <h2 id="cf-title">{opts.title}</h2>
              {opts.body && <p>{opts.body}</p>}
            </div>
          </div>
          {opts.reason && (
            <label className="field">
              <span>{opts.reason.label}</span>
              <textarea className="textarea" value={reason} placeholder={opts.reason.placeholder} maxLength={300} onChange={(e) => setReason(e.target.value)} autoFocus />
            </label>
          )}
        </div>
        <div className="dialog-foot">
          <button type="button" className="btn btn-secondary" onClick={() => onDone(null)}>
            Hủy
          </button>
          <button type="submit" className={`btn ${tone === "danger" ? "btn-danger" : "btn-primary"}`} autoFocus={!opts.reason}>
            {opts.confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
