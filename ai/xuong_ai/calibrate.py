"""Hiệu chỉnh ngưỡng khớp FAQ bằng tập câu hỏi tiếng Việt (gần nghĩa, không dấu, dễ nhầm, ngoài phạm vi).

Mỗi dòng eval/faq_eval.jsonl: {"q": "câu hỏi", "expect": "tiêu đề FAQ đúng" | null}
- expect = null nghĩa là KHÔNG được trả lời bằng FAQ (phải chuyển kênh hỗ trợ).
Chọn ngưỡng tối đa hóa tỷ lệ trả lời đạt với ràng buộc độ chính xác ≥ min_precision.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import textnorm


def evaluate(faqs: list[dict], cases: list[dict], thresholds=None, min_precision: float = 0.9) -> dict:
    docs = {f["question"]: f"{f['question']} {f['question']} {f.get('search_text') or textnorm.fold(f['question'] + ' ' + f.get('answer', ''))}" for f in faqs}
    preds = []
    for c in cases:
        r = textnorm.rank(c["q"], docs)
        preds.append((c, r[0] if r else (None, 0.0)))
    thresholds = thresholds or [round(x * 0.01, 2) for x in range(3, 81)]
    table = []
    for th in thresholds:
        tp = fp = fn = tn = 0
        for c, (top, score) in preds:
            answered = top is not None and score >= th
            if c["expect"] is None:
                fp += answered
                tn += not answered
            elif answered and top == c["expect"]:
                tp += 1
            elif answered:
                fp += 1
            else:
                fn += 1
        prec = tp / (tp + fp) if tp + fp else 1.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        acc = (tp + tn) / len(cases) if cases else 0.0
        table.append({"threshold": th, "precision": prec, "recall": rec, "accuracy": acc, "tp": tp, "fp": fp, "fn": fn, "tn": tn})
    ok = [t for t in table if t["precision"] >= min_precision] or table
    best = max(ok, key=lambda t: (t["accuracy"], t["recall"], -t["threshold"]))
    errors = []
    for c, (top, score) in preds:
        answered = top is not None and score >= best["threshold"]
        good = (c["expect"] is None and not answered) or (answered and top == c["expect"])
        if not good:
            errors.append({"q": c["q"], "expect": c["expect"], "got": top if answered else None, "score": round(score, 4)})
    return {"n": len(cases), "recommended": best["threshold"], "best": best, "table": table, "errors": errors}


def load_cases(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("//")]
