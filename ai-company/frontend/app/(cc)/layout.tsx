import { Suspense } from "react";

import { Shell } from "@/components/shell";

export default function ControlCenterLayout({ children }: { children: React.ReactNode }) {
  return (
    <Shell>
      <Suspense>{children}</Suspense>
    </Shell>
  );
}
