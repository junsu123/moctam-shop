"""Tham số tính cách đi vào mã, không chỉ vào prompt (BRAIN_SPEC §2.2, UT-BRAIN-08).

- `evidence_strictness`: tỉ lệ khẳng định bắt buộc có nguồn; bước tự kiểm tra chặn kết quả thiếu nguồn.
- `risk_tolerance`: càng thấp thì ngưỡng tự tin để tự quyết càng cao, dễ chuyển cấp trên hơn.
- `verbosity`: giới hạn độ dài báo cáo.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.brain.schema import DecisionPolicy, Personality


class Claim(BaseModel):
    text: str
    sources: list[str] = Field(default_factory=list)  # url, memory_id, truy vấn…


@dataclass(frozen=True)
class EvidenceResult:
    ok: bool
    sourced_ratio: float
    required: float
    unsourced: list[str]


def evidence_gate(claims: list[Claim], p: Personality) -> EvidenceResult:
    if not claims:
        return EvidenceResult(True, 1.0, p.evidence_strictness, [])
    unsourced = [c.text for c in claims if not c.sources]
    ratio = 1 - len(unsourced) / len(claims)
    return EvidenceResult(ratio + 1e-9 >= p.evidence_strictness, round(ratio, 3), p.evidence_strictness, unsourced)


def escalation_threshold(p: Personality, d: DecisionPolicy) -> float:
    """Ngưỡng tự tin: mức của decision_policy, dịch lên tối đa +0,1 khi rủi ro chấp nhận thấp (và xuống khi cao)."""
    return round(min(0.95, max(0.3, d.escalate_when.confidence_below + (0.5 - p.risk_tolerance) * 0.2)), 3)


def should_escalate(confidence: float, action_tags: list[str], p: Personality, d: DecisionPolicy) -> tuple[bool, str]:
    hit = sorted(set(action_tags) & set(d.escalate_when.action_tags))
    if hit:
        return True, f"hành động thuộc nhóm phải hỏi cấp trên: {', '.join(hit)}"
    th = escalation_threshold(p, d)
    if confidence < th:
        return True, f"độ tự tin {confidence:.2f} dưới ngưỡng {th:.2f}"
    return False, "tự quyết trong phạm vi"


def report_char_limit(p: Personality) -> int:
    return int(400 + p.verbosity * 2600)
