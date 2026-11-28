"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { GiveTask, TaskTable } from "@/components/tasks";
import { Card, ErrorAlert, Loading, PageHeader } from "@/components/ui/primitives";
import { Tabs, TabPanel, useTabParam } from "@/components/ui/tabs";
import type { Agent, TaskRow, TaskStats } from "@/lib/api";
import { usd } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const TABS = ["dang-chay", "cho", "xong", "loi"] as const;
type Tab = (typeof TABS)[number];
const GROUP: Record<Tab, string> = { "dang-chay": "active", cho: "waiting", xong: "done", loi: "failed" };
const EMPTY: Record<Tab, string> = {
  "dang-chay": "Không có việc nào đang chạy",
  cho: "Không có việc nào đang chờ",
  xong: "Chưa có việc nào xong",
  loi: "Không có việc lỗi hay bị hủy",
};

export default function TasksPage() {
  const [tab, setTab] = useTabParam<Tab>(TABS, "dang-chay");
  const { data: stats, reload: reloadStats } = useApi<TaskStats>("/tasks/stats");
  const { data, error, reload } = useApi<{ items: TaskRow[]; total: number }>(`/tasks?group=${GROUP[tab]}&top=true&limit=100`);
  const { data: agents } = useApi<Agent[]>("/agents");
  const [giving, setGiving] = useState(false);
  const router = useRouter();
  const g = stats?.groups;

  return (
    <>
      <PageHeader
        title="Việc"
        description={
          <>
            Việc anh/chị giao và việc các agent tự chia cho nhau. Mở một việc để xem từng bước agent đã làm.
            {stats ? ` Chi phí AI hôm nay: ${usd(stats.spent_today_usd, 3)}.` : ""}
          </>
        }
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setGiving(true)} disabled={!agents}>
            <Plus size={16} aria-hidden="true" /> Giao việc
          </button>
        }
      />
      <Tabs
        label="Nhóm việc"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "dang-chay", label: "Đang chạy", count: g?.active },
          { id: "cho", label: "Chờ duyệt, review", count: g?.waiting },
          { id: "xong", label: "Xong", count: g?.done },
          { id: "loi", label: "Lỗi, đã hủy", count: g?.failed },
        ]}
      />
      <TabPanel id={tab}>
        {error && <ErrorAlert>{error}</ErrorAlert>}
        {!data ? (
          <Loading what="danh sách việc" />
        ) : (
          <Card flush>
            <TaskTable items={data.items} empty={EMPTY[tab]} />
          </Card>
        )}
      </TabPanel>
      {giving && agents && (
        <GiveTask
          agents={agents}
          onClose={() => setGiving(false)}
          onSaved={(id) => {
            setGiving(false);
            void reload();
            void reloadStats();
            router.push(`/viec/${id}`);
          }}
        />
      )}
    </>
  );
}
