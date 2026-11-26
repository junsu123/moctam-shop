"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api";

/** Tải dữ liệu từ API khi mở trang; `reload()` tải lại (gọi sau thao tác ghi). Lỗi trả về dạng câu tiếng Việt. */
export function useApi<T>(path: string): { data: T | null; error: string; reload: () => Promise<void> } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    api<T>(path)
      .then((d) => alive && setData(d))
      .catch((x: unknown) => alive && setError(x instanceof ApiError ? x.message : "Không tải được dữ liệu."));
    return () => {
      alive = false;
    };
  }, [path]);

  const reload = useCallback(async () => {
    try {
      setData(await api<T>(path));
      setError("");
    } catch (x) {
      setError(x instanceof ApiError ? x.message : "Không tải được dữ liệu.");
    }
  }, [path]);

  return { data, error, reload };
}
