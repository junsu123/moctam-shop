"""Dòng lệnh:
  python -m xuong_ai run                 # chạy nền theo lịch
  python -m xuong_ai once sync|catalog|crosssell|care|faq_drafts|blog_drafts|maintenance
  python -m xuong_ai snapshot            # tải lại toàn bộ bản chụp
  python -m xuong_ai calibrate [tệp.jsonl]
  python -m xuong_ai status
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from . import config
from . import sync as syncmod
from .scheduler import App


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="xuong_ai", description="Dịch vụ AI cục bộ của xưởng")
    ap.add_argument("--config", help="Đường dẫn config.toml")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    o = sub.add_parser("once"); o.add_argument("job", choices=["sync", "catalog", "crosssell", "care", "faq_drafts", "blog_drafts", "maintenance"])
    sub.add_parser("snapshot")
    c = sub.add_parser("calibrate"); c.add_argument("eval", nargs="?")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    app = App(config.load(a.config))

    if a.cmd == "run":
        try:
            app.loop()
        except KeyboardInterrupt:
            return 0
    elif a.cmd == "once":
        res = app.run_job(a.job)
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return 0 if res is not None else 1
    elif a.cmd == "snapshot":
        print(json.dumps(syncmod.load_snapshot(app.store, app.client), ensure_ascii=False, indent=2))
    elif a.cmd == "calibrate":
        r = app.calibrate(a.eval)
        if not r:
            print("Chưa có FAQ đã xuất bản hoặc tệp kiểm tra.")
            return 1
        b = r["best"]
        print(f"Ngưỡng đề xuất: {r['recommended']}  (độ chính xác {b['precision']:.0%}, độ phủ {b['recall']:.0%}, đạt {b['accuracy']:.0%} trên {r['n']} câu)")
        for t in r["table"]:
            if round(t["threshold"] * 100) % 5 == 0:
                print(f"  {t['threshold']:.2f}: chính xác {t['precision']:.0%}  phủ {t['recall']:.0%}  đạt {t['accuracy']:.0%}")
        if r["errors"]:
            print("Câu chưa đạt ở ngưỡng đề xuất:")
            for e in r["errors"]:
                print(f"  - {e['q']}  → mong: {e['expect']}  nhận: {e['got']}  ({e['score']})")
    elif a.cmd == "status":
        s = app.store
        print(json.dumps({
            "cursor": s.get("cursor"), "orders": s.one("SELECT COUNT(*) n FROM orders")["n"],
            "knowledge": {r["status"]: r["n"] for r in s.all("SELECT status, COUNT(*) n FROM knowledge GROUP BY status")},
            "outbox": {r["status"]: r["n"] for r in s.all("SELECT status, COUNT(*) n FROM outbox GROUP BY status")},
            "llm_today": app.llm.usage_today(),
            "jobs": [dict(r) for r in s.all("SELECT name, last_run, next_run, failures, last_error FROM jobs ORDER BY name")],
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
