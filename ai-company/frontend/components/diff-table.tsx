import { GitCompare } from "lucide-react";

import { Empty } from "@/components/ui/primitives";
import type { DiffItem } from "@/lib/api";
import { fmtValue } from "@/lib/labels";

/** Bảng so sánh hai phiên bản bộ não: mỗi dòng là một mục đổi (đường dẫn, trước, sau). */
export function DiffTable({ changes }: { changes: DiffItem[] }) {
  if (!changes.length) return <Empty icon={<GitCompare size={20} />} title="Không có khác biệt" />;
  return (
    <div className="table-wrap">
      <table className="table diff">
        <thead>
          <tr>
            <th scope="col">Mục</th>
            <th scope="col">Trước</th>
            <th scope="col">Sau</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((c) => (
            <tr key={c.path}>
              <td>
                <span className="mono-tag">{c.path}</span>
              </td>
              <td className="del">{fmtValue(c.from)}</td>
              <td className="ins">{fmtValue(c.to)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
