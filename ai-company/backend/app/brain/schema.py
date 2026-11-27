"""Schema của brain bundle (BRAIN_SPEC §2). Mọi mô hình cấm trường lạ: gõ sai tên trường là lỗi, không bị bỏ qua lặng lẽ."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SemVer = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,40}$")]
Ratio = Annotated[float, Field(ge=0, le=1)]
DEPARTMENTS = ("executive", "marketing", "sales", "growth", "technology")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Versions(Strict):
    brain_version: SemVer
    prompt_version: SemVer
    knowledge_version: SemVer
    skill_version: SemVer


class ModelParams(Strict):
    temperature: float = Field(ge=0, le=2)
    max_output_tokens: int = Field(ge=64, le=32000)


class ModelCfg(Strict):
    primary: Key  # hồ sơ trong Model Gateway, không phải tên model/nhà cung cấp
    fallback: Key | None = None
    parameters: ModelParams
    capabilities: dict[str, bool] = Field(default_factory=dict)


class BudgetCfg(Strict):
    usd_per_day: float = Field(ge=0, le=50)
    max_steps_per_task: int = Field(ge=1, le=100)
    max_tool_calls_per_task: int = Field(ge=1, le=200)


class MemoryCfg(Strict):
    retrieval_budget_tokens: int = Field(ge=500, le=32000)
    share_ratio: dict[str, Ratio]

    @model_validator(mode="after")
    def _sum(self) -> MemoryCfg:
        total = sum(self.share_ratio.values())
        if abs(total - 1) > 0.01:
            raise ValueError(f"share_ratio phải cộng lại bằng 1 (đang là {total:.2f})")
        return self


class Voice(Strict):
    tone: str = Field(min_length=1, max_length=200)
    formality: Ratio
    emoji: bool


class Personality(Strict):
    voice: Voice
    risk_tolerance: Ratio
    verbosity: Ratio
    evidence_strictness: Ratio


class Profile(Strict):
    display_name: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=300)


class Role(Strict):
    mission: str = Field(min_length=10, max_length=600)
    responsibilities: list[str] = Field(min_length=1)
    hard_rules: list[str] = Field(default_factory=list)


class Identity(Strict):
    profile: Profile
    role: Role
    personality: Personality


class EscalateWhen(Strict):
    confidence_below: Ratio
    action_tags: list[str] = Field(default_factory=list)
    conflicts_with_memory: bool = True


class Clarify(Strict):
    missing_inputs: list[str] = Field(default_factory=list)


class Reuse(Strict):
    min_similarity: Ratio


class DecisionPolicy(Strict):
    escalate_when: EscalateWhen
    ask_clarification_when: Clarify
    prefer_reuse: Reuse


class ReasoningPolicy(Strict):
    style: str
    max_reasoning_steps: int = Field(ge=1, le=20)
    cite_memory: bool


class PlanningPolicy(Strict):
    max_subtasks: int = Field(ge=0, le=6)  # AGENT_DESIGN §5: tối đa 6 task con
    max_depth: int = Field(ge=1, le=4)  # độ sâu cây tối đa 4
    require_success_criteria: bool


class Reasoning(Strict):
    reasoning_policy: ReasoningPolicy
    planning_policy: PlanningPolicy
    decision_policy: DecisionPolicy


class Skill(Strict):
    key: Key
    name: str
    version: SemVer


class Limits(Strict):
    per_day: int | None = Field(default=None, ge=1, le=1000)
    max_usd: float | None = Field(default=None, ge=0)


class Permission(Strict):
    tool: str
    action: str
    level: int = Field(ge=1, le=4)
    limits: Limits = Field(default_factory=Limits)
    requires_approval: bool = False


class Kpi(Strict):
    key: Key
    name: str


class Performance(Strict):
    kpis: list[Kpi] = Field(min_length=1)


class EvaluationRules(Strict):
    signals: dict[str, str | float]
    min_samples_for_kpi: int = Field(ge=1)
    judge_must_differ_from_writer: bool


class Evaluation(Strict):
    performance: Performance
    evaluation_rules: EvaluationRules


class Constitution(Strict):
    version: SemVer
    principles: list[str] = Field(min_length=1)
    forbidden_tags: dict[str, str]
    mandatory_approval_tags: dict[str, str]
    high_risk_tags: list[str]
    approval_ttl_hours: int = Field(ge=1, le=720)


class Bundle(Strict):
    agent_id: Key
    extends: str | None = None
    kind: Annotated[str, StringConstraints(pattern=r"^(executive|director|specialist)$")]
    versions: Versions
    department: Annotated[str, StringConstraints(pattern=r"^(executive|marketing|sales|growth|technology)$")]
    reports_to: Key | None
    model: ModelCfg
    budget: BudgetCfg
    memory: MemoryCfg
    identity: Identity
    reasoning: Reasoning
    skills: list[Skill]
    tool_permissions: list[Permission]
    evaluation: Evaluation
    constitution: Constitution

    @model_validator(mode="after")
    def _unique(self) -> Bundle:
        seen: set[tuple[str, str]] = set()
        for p in self.tool_permissions:
            if (p.tool, p.action) in seen:
                raise ValueError(f"quyền {p.tool}.{p.action} bị khai báo hai lần")
            seen.add((p.tool, p.action))
        keys = [s.key for s in self.skills]
        if len(keys) != len(set(keys)):
            raise ValueError("kỹ năng bị trùng key")
        if self.kind != "executive" and not self.reports_to:
            raise ValueError("thiếu reports_to (chỉ AI CEO không có cấp trên)")
        return self
