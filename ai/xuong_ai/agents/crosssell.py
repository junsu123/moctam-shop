"""Gợi ý mua kèm từ các đơn ĐÃ GIAO (không cần LLM): đồng xuất hiện + lift."""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from itertools import permutations

from ..store import Store
from . import enqueue


def suggest(store: Store, min_support: int = 2, max_per_product: int = 3) -> list[dict]:
    rows = store.all("SELECT o.order_id, i.product_id FROM orders o JOIN order_items i ON i.order_id = o.order_id WHERE o.status = 'delivered'")
    baskets: dict[int, set[int]] = defaultdict(set)
    for r in rows:
        baskets[r["order_id"]].add(r["product_id"])
    n = len(baskets)
    if n == 0:
        return []
    single = Counter()
    pair = Counter()
    for items in baskets.values():
        single.update(items)
        pair.update(permutations(sorted(items), 2))
    out: dict[int, list[dict]] = defaultdict(list)
    for (a, b), c in pair.items():
        if c < min_support:
            continue
        conf = c / single[a]
        lift = conf / (single[b] / n)
        if lift <= 1.0:
            continue
        out[a].append({"product_id": a, "related_product_id": b, "support": c, "confidence": round(conf, 4), "lift": round(lift, 3),
                       "score": round(min(1.0, conf * min(lift, 3) / 3), 4),
                       "reason": f"{c} đơn đã giao mua cùng; {round(conf * 100)}% khách mua sản phẩm này cũng mua kèm (lift {lift:.2f})"})
    result = []
    for a, lst in out.items():
        lst.sort(key=lambda x: (-x["score"], -x["support"]))
        result.extend(lst[:max_per_product])
    return result


def run(store: Store, cfg) -> dict:
    sugg = suggest(store, cfg.crosssell_min_support, cfg.crosssell_max_per_product)
    week = dt.date.today().isocalendar()
    queued = 0
    for s in sugg:
        ref = f"xs:{s['product_id']}:{s['related_product_id']}:{week[0]}w{week[1]}"
        queued += enqueue(store, ref, "cross_sell", {k: s[k] for k in ("product_id", "related_product_id", "score", "reason")})
    return {"suggestions": len(sugg), "queued": queued}
