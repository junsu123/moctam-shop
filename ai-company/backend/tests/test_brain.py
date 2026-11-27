"""UT-AG-01…05, UT-BRAIN-01…08: bộ não có phiên bản, kế thừa mẫu, hash quy tắc cốt lõi, ghim, so sánh, rollback, shadow,
tham số tính cách đổi hành vi thật."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncConnection

from app.brain import behavior, registry
from app.brain.loader import BrainError, agent_dirs, load_agent
from tests.conftest import BRAINS, needs_db, sync_brains

pytestmark = needs_db
AGENTS = agent_dirs(BRAINS)


def edit(root: Path, rel: str, fn) -> None:  # type: ignore[no-untyped-def]
    p = root / rel
    data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    fn(data)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


@pytest.fixture
def tmp_brains(tmp_path: Path) -> Path:
    root = tmp_path / "brains"
    shutil.copytree(BRAINS, root)
    return root


# ------------------------------------------------------------------ UT-AG-01: 15 agent, danh tính riêng
def test_ag01_all_15_bundles_load_with_distinct_identity() -> None:
    assert len(AGENTS) == 15
    loaded = [load_agent(BRAINS, a) for a in AGENTS]
    assert len({lb.bundle_hash for lb in loaded}) == 15
    assert len({lb.bundle.identity.profile.display_name for lb in loaded}) == 15
    assert len({lb.bundle.identity.role.mission for lb in loaded}) == 15
    ceo = next(lb for lb in loaded if lb.bundle.agent_id == "ai_ceo")
    assert ceo.bundle.reports_to is None and ceo.bundle.kind == "executive"
    assert all(lb.bundle.reports_to for lb in loaded if lb.bundle.agent_id != "ai_ceo")


async def test_ag01_bootstrap_sync_registers_everything(synced: list[registry.SyncItem], conn: AsyncConnection) -> None:
    from app.core import db

    assert [i.status for i in synced] == ["bootstrapped"] * 15
    assert await db.scalar(conn, "SELECT count(*) FROM agent_brains WHERE state = 'active'") == 15
    assert await db.scalar(conn, "SELECT count(*) FROM brain_core_pins") == 15
    n = await db.scalar(conn, "SELECT count(*) FROM agent_permissions WHERE agent_key = 'seo_agent'")
    assert n == len(load_agent(BRAINS, "seo_agent").bundle.tool_permissions)
    assert await db.scalar(conn, "SELECT count(*) FROM agent_versions WHERE event = 'bootstrap'") == 15
    again = await sync_brains()
    assert {i.status for i in again} == {"unchanged"}  # nạp lại không tạo bản mới


# ------------------------------------------------------------------ UT-AG-02: thiếu trường → lỗi rõ ràng
def test_ag02_missing_and_unknown_fields_give_clear_errors(tmp_brains: Path) -> None:
    edit(tmp_brains, "seo_agent/identity/role.yaml", lambda d: d.pop("mission"))
    edit(tmp_brains, "seo_agent/brain.yaml", lambda d: d.update(budjet={"usd_per_day": 1}))
    with pytest.raises(BrainError) as e:
        load_agent(tmp_brains, "seo_agent")
    assert "identity.role.mission: thiếu trường bắt buộc" in e.value.problems
    assert "budjet: trường không được phép (gõ sai tên?)" in e.value.problems


def test_ag02_permission_checked_against_registry_and_constitution(tmp_brains: Path) -> None:
    edit(tmp_brains, "ads_agent/tools/tool_permissions.yaml",
         lambda d: d["permissions"].extend([{"tool": "ads", "action": "change_budget", "level": 2}, {"tool": "khong_co", "action": "x", "level": 1}]))
    with pytest.raises(BrainError) as e:
        load_agent(tmp_brains, "ads_agent")
    joined = " | ".join(e.value.problems)
    assert "ads.change_budget cấp L2 thấp hơn cấp tối thiểu L3" in joined
    assert "khong_co.x không có trong Tool Registry" in joined


def test_ag02_bad_yaml_and_wrong_ranges(tmp_brains: Path) -> None:
    (tmp_brains / "social_agent/identity/personality.yaml").write_text("risk_tolerance: [không đóng ngoặc\n", encoding="utf-8")
    with pytest.raises(BrainError) as e:
        load_agent(tmp_brains, "social_agent")
    assert "personality.yaml: YAML lỗi cú pháp" in e.value.problems[0]
    edit(tmp_brains, "data_analyst/identity/personality.yaml", lambda d: d.update(evidence_strictness=1.5))
    with pytest.raises(BrainError) as e:
        load_agent(tmp_brains, "data_analyst")
    assert e.value.problems == ["identity.personality.evidence_strictness: lớn hơn mức cho phép"]


# ------------------------------------------------------------------ UT-AG-03: kế thừa mẫu phòng ban
def test_ag03_inherits_department_template() -> None:
    seo = load_agent(BRAINS, "seo_agent").bundle
    assert seo.identity.personality.voice.tone == "chuyên nghiệp, gần gũi"  # từ specialist_marketing
    assert seo.identity.personality.evidence_strictness == 0.9  # agent ghi đè
    assert seo.reasoning.planning_policy.max_subtasks == 3  # từ mẫu
    assert seo.model.primary == "reasoning_mid" and seo.model.fallback == "fallback"  # ghi đè primary, giữ fallback của mẫu
    gd = load_agent(BRAINS, "growth_director").bundle
    assert gd.reasoning.planning_policy.max_subtasks == 6 and gd.model.primary == "reasoning_high"


# ------------------------------------------------------------------ UT-AG-04/05: vòng đời, tạm dừng/tiếp tục
def test_ag04_lifecycle_transitions() -> None:
    from app.domain.lifecycle import STATES, TRANSITIONS, can

    assert set(TRANSITIONS) == set(STATES)
    assert can("active", "paused") and can("paused", "active") and can("degraded", "active")
    assert not can("disabled", "active")  # bật lại phải qua tạm dừng
    assert not can("paused", "learning")


async def test_ag04_invalid_transition_rejected(synced: object, conn: AsyncConnection) -> None:
    from app.core.errors import AppError
    from app.domain import lifecycle

    await lifecycle.transition(conn, "seo_agent", "disabled", "user:o")
    with pytest.raises(AppError) as e:
        await lifecycle.transition(conn, "seo_agent", "active", "user:o")
    assert e.value.code == "AGENT_STATE" and "tắt" in e.value.message


async def test_ag05_pause_blocks_tools_resume_allows(synced: object, conn: AsyncConnection) -> None:
    from app.domain import lifecycle
    from app.policy.engine import authorize

    assert (await authorize(conn, "data_analyst", "signals", "read")).kind == "allow"
    await lifecycle.transition(conn, "data_analyst", "paused", "user:o", "bảo trì")
    d = await authorize(conn, "data_analyst", "signals", "read")
    assert d.kind == "deny" and d.rule == "agent_state"
    await lifecycle.transition(conn, "data_analyst", "active", "user:o")
    assert (await authorize(conn, "data_analyst", "signals", "read")).kind == "allow"


# ------------------------------------------------------------------ UT-BRAIN-01: nạp + kiểm schema
def test_brain01_schema_rules(tmp_brains: Path) -> None:
    edit(tmp_brains, "ai_ceo/brain.yaml", lambda d: d.update(memory={"share_ratio": {"procedural": 0.5, "experience": 0.6}}))
    with pytest.raises(BrainError) as e:
        load_agent(tmp_brains, "ai_ceo")
    assert any("share_ratio phải cộng lại bằng 1" in p for p in e.value.problems)
    edit(tmp_brains, "content_agent/brain.yaml", lambda d: d["versions"].update(brain_version="1.0"))
    with pytest.raises(BrainError) as e:
        load_agent(tmp_brains, "content_agent")
    assert "versions.brain_version: sai định dạng" in e.value.problems


# ------------------------------------------------------------------ UT-BRAIN-02: hash cốt lõi lệch → từ chối nạp
async def test_brain02_core_hash_not_pinned_is_refused(synced: object, conn: AsyncConnection) -> None:
    from app.brain.loader import core_rules, digest
    from app.core import db
    from app.domain.approvals import _json

    ok = await registry.resolve(conn, "ads_agent")
    assert ok.state == "active" and ok.deliverable
    # Ai đó sửa thẳng CSDL: thêm quyền tăng ngân sách và tính lại bundle_hash cho "khớp"
    data = dict(ok.loaded.data)
    data["tool_permissions"] = [*data["tool_permissions"], {"tool": "ads", "action": "change_budget", "level": 4, "limits": {"per_day": None, "max_usd": None}, "requires_approval": False}]
    await db.execute(conn, "UPDATE agent_brains SET bundle = CAST(:b AS jsonb), bundle_hash = :h WHERE id = CAST(:i AS uuid)",
                     {"b": _json(data), "h": digest(data), "i": ok.brain_id})
    with pytest.raises(BrainError) as e:
        await registry.resolve(conn, "ads_agent")
    assert e.value.code == "CORE_HASH_MISMATCH" and digest(core_rules(data)) != ok.loaded.core_rules_hash
    # Sửa nội dung mà không tính lại hash cũng bị phát hiện
    await db.execute(conn, "UPDATE agent_brains SET bundle = jsonb_set(bundle, '{budget,usd_per_day}', '9') WHERE agent_key = 'seo_agent'")
    with pytest.raises(BrainError) as e:
        await registry.resolve(conn, "seo_agent")
    assert e.value.code == "BRAIN_TAMPERED"


async def _propose(root: Path, agent: str, version: str, fn) -> registry.SyncItem:  # type: ignore[no-untyped-def]
    edit(root, f"{agent}/brain.yaml", lambda d: d["versions"].update(brain_version=version))
    fn(root)
    items = {i.agent_key: i for i in await sync_brains(root)}
    return items[agent]


# ------------------------------------------------------------------ UT-BRAIN-03/04: ghim theo task, so sánh, duyệt, rollback
async def test_brain03_04_pin_compare_promote_rollback(synced: object, tmp_brains: Path) -> None:
    from app.core import db
    from app.domain import approvals

    async with db.engine().connect() as c:
        v1 = await registry.resolve(c, "content_agent")
    item = await _propose(tmp_brains, "content_agent", "1.1.0",
                          lambda r: edit(r, "content_agent/identity/personality.yaml", lambda d: d.update(verbosity=0.3)))
    assert item.status == "proposed" and "chờ Owner duyệt" in item.detail
    async with db.engine().begin() as c:
        appr = await db.one(c, "SELECT * FROM approvals WHERE subject_type = 'brain' AND status = 'pending'")
        assert appr is not None and appr["risk"] == "high" and appr["action"] == "promote_brain"
        assert appr["payload"]["core_changed"] is False
        assert {"path": "identity.personality.verbosity", "from": 0.55, "to": 0.3} in appr["payload"]["diff"]
        # Chưa duyệt: runtime vẫn dùng bản 1.0.0
        assert (await registry.resolve(c, "content_agent")).loaded.bundle.versions.brain_version == "1.0.0"
        await approvals.decide(c, str(appr["id"]), True, "user:owner@x.vn", "ok")
    async with db.engine().connect() as c:
        now = await registry.resolve(c, "content_agent")
        assert now.loaded.bundle.versions.brain_version == "1.1.0" and now.loaded.bundle.identity.personality.verbosity == 0.3
        pinned = await registry.resolve(c, "content_agent", v1.brain_id)  # task tạo trước khi đổi vẫn chạy bản đã ghim
        assert pinned.loaded.bundle.versions.brain_version == "1.0.0" and pinned.state == "retired" and pinned.deliverable
    async with db.engine().begin() as c:
        await registry.rollback(c, "content_agent", v1.brain_id, "user:owner@x.vn")
    async with db.engine().connect() as c:
        assert (await registry.resolve(c, "content_agent")).brain_id == v1.brain_id
        events = [r["event"] for r in await db.all_(c, "SELECT event FROM agent_versions WHERE agent_key = 'content_agent' ORDER BY id")]
        assert events == ["bootstrap", "proposed", "activated", "rolled_back"]
        from sqlalchemy.exc import DBAPIError

        with pytest.raises(DBAPIError):  # changelog chỉ thêm
            await c.execute(__import__("sqlalchemy").text("UPDATE agent_versions SET proposed_by = 'x'"))


async def test_brain05_content_change_requires_version_bump(synced: object, tmp_brains: Path) -> None:
    edit(tmp_brains, "seo_agent/identity/personality.yaml", lambda d: d.update(verbosity=0.2))
    items = {i.agent_key: i for i in await sync_brains(tmp_brains)}
    assert items["seo_agent"].status == "error" and "chưa tăng" in items["seo_agent"].detail


async def test_brain06_shadow_is_not_deliverable_and_reject(synced: object, tmp_brains: Path) -> None:
    from app.core import db
    from app.domain import approvals

    item = await _propose(tmp_brains, "seo_agent", "1.0.1", lambda r: edit(r, "seo_agent/identity/personality.yaml", lambda d: d.update(verbosity=0.3)))
    async with db.engine().begin() as c:
        await registry.set_shadow(c, str(item.brain_id), "user:o")
        shadow = await registry.resolve(c, "seo_agent", item.brain_id)
        assert shadow.state == "shadow" and not shadow.deliverable
        appr = await db.one(c, "SELECT id FROM approvals WHERE subject_id = :s", {"s": item.brain_id})
        assert appr is not None
        await approvals.decide(c, str(appr["id"]), False, "user:o", "chưa cần")
        assert await db.scalar(c, "SELECT state FROM agent_brains WHERE id = CAST(:i AS uuid)", {"i": item.brain_id}) == "rejected"


async def test_brain07_core_change_flagged_and_pinned_on_approval(synced: object, tmp_brains: Path) -> None:
    from app.core import db
    from app.domain import approvals

    item = await _propose(tmp_brains, "seo_agent", "1.1.0",
                          lambda r: edit(r, "seo_agent/identity/role.yaml", lambda d: d["hard_rules"].append("Không viết quá 2.000 chữ")))
    assert "đổi quy tắc cốt lõi" in item.detail
    async with db.engine().begin() as c:
        appr = await db.one(c, "SELECT * FROM approvals WHERE subject_id = :s", {"s": item.brain_id})
        assert appr is not None and appr["payload"]["core_changed"] is True and "quy tắc cốt lõi" in appr["title"]
        new_hash = appr["payload"]["core_rules_hash"]
        assert not await db.scalar(c, "SELECT EXISTS (SELECT 1 FROM brain_core_pins WHERE core_rules_hash = :h)", {"h": new_hash})
        await approvals.decide(c, str(appr["id"]), True, "user:o")
        assert await db.scalar(c, "SELECT approved_by FROM brain_core_pins WHERE core_rules_hash = :h", {"h": new_hash}) == "user:o"
        b = await registry.resolve(c, "seo_agent")
        assert "Không viết quá 2.000 chữ" in b.loaded.bundle.identity.role.hard_rules


# ------------------------------------------------------------------ UT-BRAIN-08: tham số tính cách đổi hành vi thật
def test_brain08_personality_changes_behaviour() -> None:
    from app.brain.behavior import Claim

    analyst = load_agent(BRAINS, "data_analyst").bundle  # evidence_strictness 0.95, risk_tolerance 0.1
    social = load_agent(BRAINS, "social_agent").bundle  # evidence_strictness 0.8, risk_tolerance 0.3
    claims = [Claim(text=f"Khẳng định {i}", sources=["https://x"] if i < 9 else []) for i in range(10)]  # 90% có nguồn
    assert behavior.evidence_gate(claims, social.identity.personality).ok
    gate = behavior.evidence_gate(claims, analyst.identity.personality)
    assert not gate.ok and gate.unsourced == ["Khẳng định 9"]
    # Cùng độ tự tin 0,66 (ngưỡng: phân tích 0,68, mạng xã hội 0,64): agent ít chấp nhận rủi ro phải hỏi cấp trên, agent kia tự quyết
    esc_a, _ = behavior.should_escalate(0.66, [], analyst.identity.personality, analyst.reasoning.decision_policy)
    esc_s, _ = behavior.should_escalate(0.66, [], social.identity.personality, social.reasoning.decision_policy)
    assert esc_a and not esc_s
    assert behavior.report_char_limit(analyst.identity.personality) < behavior.report_char_limit(social.identity.personality)
    esc, why = behavior.should_escalate(0.99, ["publish_risky"], social.identity.personality, social.reasoning.decision_policy)
    assert esc and "publish_risky" in why
