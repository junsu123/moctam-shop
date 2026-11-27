"""Agent Registry + vòng đời bộ não trong CSDL.

Luồng (BRAIN_SPEC §9):
1. `sync_all` đọc thư mục `brains/`. Agent chưa có bộ não → nạp lần đầu (bootstrap) và ghim hash quy tắc cốt lõi:
   bundle trong git đã qua review PR. Bundle có nội dung mới → bản `draft` + yêu cầu duyệt "thăng hạng" (rủi ro cao).
2. Owner duyệt → bản mới `active`, bản cũ `retired`, quyền công cụ được cập nhật theo bản mới, hash cốt lõi được ghim.
3. `resolve` dùng cho runtime: nạp đúng phiên bản (ghim theo task hoặc bản active), kiểm lại hash; hash cốt lõi
   chưa được ghim → từ chối nạp.
4. `rollback` trỏ lại một phiên bản đã từng active (một thao tác).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.brain.loader import BrainError, Loaded, agent_dirs, diff, from_stored, load_agent, semver
from app.core import audit, db
from app.core.errors import AppError
from app.core.ids import uuid7
from app.domain import approvals


@dataclass
class SyncItem:
    agent_key: str
    status: str  # unchanged | bootstrapped | proposed | pending | error
    detail: str
    brain_id: str | None = None


@dataclass
class Resolved:
    brain_id: str
    state: str
    loaded: Loaded

    @property
    def deliverable(self) -> bool:
        """Bản shadow/nháp chỉ để chấm, không được giao kết quả ra ngoài."""
        return self.state in ("active", "retired")


async def _versions_log(conn: AsyncConnection, agent: str, event: str, **kw: Any) -> None:
    await db.execute(
        conn,
        "INSERT INTO agent_versions(agent_key, event, component, from_version, to_version, brain_id, previous_brain_id, "
        "diff, proposed_by, approved_by, test_results) "
        "VALUES (:a, :e, :c, :f, :t, :b, :p, CAST(:d AS jsonb), :by, :ap, CAST(:tr AS jsonb))",
        {
            "a": agent,
            "e": event,
            "c": kw.get("component", "brain"),
            "f": kw.get("from_version"),
            "t": kw.get("to_version"),
            "b": kw.get("brain_id"),
            "p": kw.get("previous_brain_id"),
            "d": approvals._json(kw.get("diff", [])),
            "by": kw["proposed_by"],
            "ap": kw.get("approved_by"),
            "tr": approvals._json(kw.get("test_results", {})),
        },
    )


async def _apply_bundle(conn: AsyncConnection, agent: str, brain_id: str, loaded: Loaded, granted_by: str) -> None:
    """Đồng bộ danh tính và quyền công cụ từ bộ não vừa active sang các bảng dùng chung."""
    b = loaded.bundle
    await db.execute(
        conn,
        "UPDATE agents SET display_name = :n, role_summary = :s, department = :d, kind = :k, reports_to = :r, updated_at = now(), version = version + 1 "
        "WHERE agent_key = :a",
        {
            "n": b.identity.profile.display_name,
            "s": b.identity.profile.summary,
            "d": b.department,
            "k": b.kind,
            "r": b.reports_to,
            "a": agent,
        },
    )
    await db.execute(conn, "DELETE FROM agent_permissions WHERE agent_key = :a", {"a": agent})
    for p in b.tool_permissions:
        await db.execute(
            conn,
            "INSERT INTO agent_permissions(agent_key, tool_id, action, autonomy_level, limits, requires_approval, granted_by, brain_id) "
            "VALUES (:a, :t, :ac, :l, CAST(:lim AS jsonb), :ra, :by, :b)",
            {
                "a": agent,
                "t": p.tool,
                "ac": p.action,
                "l": p.level,
                "lim": approvals._json(p.limits.model_dump(exclude_none=True)),
                "ra": p.requires_approval,
                "by": granted_by,
                "b": brain_id,
            },
        )


async def _pin(conn: AsyncConnection, agent: str, core_hash: str, by: str, approval_id: str | None = None) -> None:
    await db.execute(
        conn,
        "INSERT INTO brain_core_pins(agent_key, core_rules_hash, approved_by, approval_id) VALUES (:a, :h, :by, CAST(:ap AS uuid)) ON CONFLICT DO NOTHING",
        {"a": agent, "h": core_hash, "by": by, "ap": approval_id},
    )


async def _pinned(conn: AsyncConnection, agent: str, core_hash: str) -> bool:
    return bool(
        await db.scalar(
            conn,
            "SELECT EXISTS (SELECT 1 FROM brain_core_pins WHERE agent_key = :a AND core_rules_hash = :h)",
            {"a": agent, "h": core_hash},
        )
    )


async def _check_refs(conn: AsyncConnection, loaded: Loaded) -> list[str]:
    b = loaded.bundle
    out = []
    if b.reports_to and not await db.scalar(conn, "SELECT EXISTS (SELECT 1 FROM agents WHERE agent_key = :r)", {"r": b.reports_to}):
        out.append(f"reports_to: không có agent {b.reports_to}")
    for prof in filter(None, (b.model.primary, b.model.fallback)):
        if not await db.scalar(conn, "SELECT EXISTS (SELECT 1 FROM model_profiles WHERE profile = :p)", {"p": prof}):
            out.append(f"model: không có hồ sơ model '{prof}' trong Model Gateway")
    return out


async def sync_agent(conn: AsyncConnection, loaded: Loaded, actor: str) -> SyncItem:
    agent = loaded.bundle.agent_id
    if not await db.scalar(conn, "SELECT EXISTS (SELECT 1 FROM agents WHERE agent_key = :a)", {"a": agent}):
        return SyncItem(agent, "error", "agent chưa được đăng ký (thêm agent mới cần Owner duyệt trên dashboard, AGENT_DESIGN §8)")
    if probs := await _check_refs(conn, loaded):
        return SyncItem(agent, "error", "; ".join(probs))
    same = await db.one(
        conn, "SELECT id, state FROM agent_brains WHERE agent_key = :a AND bundle_hash = :h", {"a": agent, "h": loaded.bundle_hash}
    )
    if same:
        st = {"active": "unchanged", "draft": "pending", "shadow": "pending"}.get(same["state"], same["state"])
        return SyncItem(agent, st, f"đã có (trạng thái {same['state']})", str(same["id"]))
    active = await db.one(conn, "SELECT * FROM agent_brains WHERE agent_key = :a AND state = 'active'", {"a": agent})
    v = loaded.bundle.versions
    bid = str(uuid7())
    if active is None:
        await _insert(conn, bid, loaded, "active", actor)
        await _pin(conn, agent, loaded.core_rules_hash, f"bootstrap:{actor}")
        await _apply_bundle(conn, agent, bid, loaded, f"bootstrap:{actor}")
        await _versions_log(
            conn, agent, "bootstrap", to_version=v.brain_version, brain_id=bid, proposed_by=actor, approved_by=f"bootstrap:{actor}"
        )
        await audit.record(conn, actor, "brain.bootstrap", f"agent:{agent}", {"version": v.brain_version, "hash": loaded.bundle_hash[:12]})
        return SyncItem(agent, "bootstrapped", f"nạp lần đầu phiên bản {v.brain_version}", bid)
    if semver(v.brain_version) <= semver(active["brain_version"]):
        return SyncItem(
            agent,
            "error",
            f"nội dung bộ não đã đổi nhưng brain_version ({v.brain_version}) chưa tăng so với bản đang chạy ({active['brain_version']})",
        )
    changes = diff(active["bundle"], loaded.data)
    core_changed = not await _pinned(conn, agent, loaded.core_rules_hash)
    await _insert(conn, bid, loaded, "draft", actor)
    await _versions_log(
        conn,
        agent,
        "proposed",
        from_version=active["brain_version"],
        to_version=v.brain_version,
        brain_id=bid,
        previous_brain_id=active["id"],
        diff=changes,
        proposed_by=actor,
    )
    ttl = loaded.bundle.constitution.approval_ttl_hours
    name = loaded.bundle.identity.profile.display_name
    await approvals.create(
        conn,
        subject_type="brain",
        subject_id=bid,
        action="promote_brain",
        risk="high",
        requested_by=actor,
        ttl_hours=ttl,
        title=f"Thăng hạng bộ não {name}: {active['brain_version']} → {v.brain_version}"
        + (" (đổi quy tắc cốt lõi)" if core_changed else ""),
        summary=f"{len(changes)} thay đổi." + (" Có thay đổi quy tắc cốt lõi hoặc quyền công cụ." if core_changed else ""),
        payload={
            "agent": agent,
            "brain_id": bid,
            "from": active["brain_version"],
            "to": v.brain_version,
            "bundle_hash": loaded.bundle_hash,
            "core_rules_hash": loaded.core_rules_hash,
            "core_changed": core_changed,
            "diff": changes[:200],
        },
    )
    return SyncItem(agent, "proposed", f"bản {v.brain_version} chờ Owner duyệt" + (" (đổi quy tắc cốt lõi)" if core_changed else ""), bid)


async def _insert(conn: AsyncConnection, bid: str, loaded: Loaded, state: str, actor: str) -> None:
    v = loaded.bundle.versions
    await db.execute(
        conn,
        "INSERT INTO agent_brains(id, agent_key, brain_version, prompt_version, knowledge_version, skill_version, bundle, "
        "bundle_hash, core_rules_hash, state, created_by, activated_at) "
        "VALUES (:id, :a, :bv, :pv, :kv, :sv, CAST(:b AS jsonb), :h, :ch, :st, :by, CASE WHEN CAST(:st AS text) = 'active' THEN now() END)",
        {
            "id": bid,
            "a": loaded.bundle.agent_id,
            "bv": v.brain_version,
            "pv": v.prompt_version,
            "kv": v.knowledge_version,
            "sv": v.skill_version,
            "b": approvals._json(loaded.data),
            "h": loaded.bundle_hash,
            "ch": loaded.core_rules_hash,
            "st": state,
            "by": actor,
        },
    )


async def sync_all(conn: AsyncConnection, root: Path, actor: str) -> list[SyncItem]:
    out: list[SyncItem] = []
    for agent in agent_dirs(root):
        try:
            loaded = load_agent(root, agent)
        except BrainError as e:
            out.append(SyncItem(agent, "error", "; ".join(e.problems)))
            continue
        out.append(await sync_agent(conn, loaded, actor))
    await audit.record(conn, actor, "brain.sync", "brains", {s: sum(1 for i in out if i.status == s) for s in {i.status for i in out}})
    return out


async def activate(
    conn: AsyncConnection, brain_id: str, approved_by: str, approval_id: str | None = None, event: str = "activated"
) -> None:
    row = await db.one(conn, "SELECT * FROM agent_brains WHERE id = CAST(:i AS uuid) FOR UPDATE", {"i": brain_id})
    if row is None:
        raise AppError("BRAIN_NOT_FOUND", "Không có phiên bản bộ não này.", 404)
    agent = row["agent_key"]
    loaded = from_stored(agent, row["bundle"])
    if loaded.bundle_hash != row["bundle_hash"]:
        raise AppError("BRAIN_TAMPERED", "Nội dung bộ não trong CSDL không khớp hash; từ chối kích hoạt.", 409)
    prev = await db.one(
        conn, "SELECT id, brain_version FROM agent_brains WHERE agent_key = :a AND state = 'active' FOR UPDATE", {"a": agent}
    )
    if prev and str(prev["id"]) == str(row["id"]):
        return
    await _pin(conn, agent, row["core_rules_hash"], approved_by, approval_id)
    if prev:
        await db.execute(conn, "UPDATE agent_brains SET state = 'retired' WHERE id = :i", {"i": prev["id"]})
    await db.execute(conn, "UPDATE agent_brains SET state = 'active', activated_at = now() WHERE id = :i", {"i": row["id"]})
    await _apply_bundle(conn, agent, str(row["id"]), loaded, approved_by)
    await _versions_log(
        conn,
        agent,
        event,
        from_version=prev["brain_version"] if prev else None,
        to_version=row["brain_version"],
        brain_id=row["id"],
        previous_brain_id=prev["id"] if prev else None,
        proposed_by=approved_by,
        approved_by=approved_by,
    )
    await audit.record(
        conn, approved_by, f"brain.{event}", f"agent:{agent}", {"from": prev["brain_version"] if prev else None, "to": row["brain_version"]}
    )


async def _on_approve(conn: AsyncConnection, appr: dict[str, Any], actor: str) -> None:
    await activate(conn, appr["subject_id"], actor, str(appr["id"]))


async def _on_reject(conn: AsyncConnection, appr: dict[str, Any], actor: str) -> None:
    row = await db.one(
        conn,
        "UPDATE agent_brains SET state = 'rejected' WHERE id = CAST(:i AS uuid) AND state IN ('draft','shadow') RETURNING agent_key, brain_version",
        {"i": appr["subject_id"]},
    )
    if row:
        await _versions_log(
            conn, row["agent_key"], "rejected", to_version=row["brain_version"], brain_id=appr["subject_id"], proposed_by=actor
        )


approvals.ON_APPROVE["brain"] = _on_approve
approvals.ON_REJECT["brain"] = _on_reject


async def set_shadow(conn: AsyncConnection, brain_id: str, actor: str) -> None:
    row = await db.one(
        conn,
        "UPDATE agent_brains SET state = 'shadow' WHERE id = CAST(:i AS uuid) AND state = 'draft' RETURNING agent_key, brain_version",
        {"i": brain_id},
    )
    if row is None:
        raise AppError("BRAIN_STATE", "Chỉ bản nháp mới chuyển sang chạy thử (shadow) được.", 409)
    await audit.record(conn, actor, "brain.shadow", f"agent:{row['agent_key']}", {"version": row["brain_version"]})


async def rollback(conn: AsyncConnection, agent: str, to_brain_id: str, actor: str) -> None:
    row = await db.one(conn, "SELECT state, activated_at, agent_key FROM agent_brains WHERE id = CAST(:i AS uuid)", {"i": to_brain_id})
    if row is None or row["agent_key"] != agent:
        raise AppError("BRAIN_NOT_FOUND", "Không có phiên bản bộ não này.", 404)
    if row["state"] != "retired" or row["activated_at"] is None:
        raise AppError("BRAIN_STATE", "Chỉ quay lại được phiên bản đã từng chạy chính thức.", 409)
    await activate(conn, to_brain_id, actor, event="rolled_back")


async def resolve(conn: AsyncConnection, agent: str, pinned_brain_id: str | None = None) -> Resolved:
    """Nạp bộ não cho runtime: phiên bản ghim theo task (nếu có) hoặc bản active; kiểm lại hash và hash cốt lõi đã ghim."""
    if pinned_brain_id:
        row = await db.one(
            conn, "SELECT * FROM agent_brains WHERE id = CAST(:i AS uuid) AND agent_key = :a", {"i": pinned_brain_id, "a": agent}
        )
    else:
        row = await db.one(conn, "SELECT * FROM agent_brains WHERE agent_key = :a AND state = 'active'", {"a": agent})
    if row is None or row["state"] == "rejected":
        raise BrainError(agent, ["không có phiên bản bộ não dùng được"], "BRAIN_NOT_FOUND")
    loaded = from_stored(agent, row["bundle"])
    if loaded.bundle_hash != row["bundle_hash"]:
        raise BrainError(agent, ["nội dung bộ não trong CSDL không khớp hash"], "BRAIN_TAMPERED")
    if not await _pinned(conn, agent, loaded.core_rules_hash):
        raise BrainError(agent, ["hash quy tắc cốt lõi chưa được Owner duyệt; từ chối nạp"], "CORE_HASH_MISMATCH")
    return Resolved(str(row["id"]), row["state"], loaded)
