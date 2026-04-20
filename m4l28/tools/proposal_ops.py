"""
第28课·数字员工的自我进化（v6）
tools/proposal_ops.py — 提案读写与状态管理

职责：
  - write_proposal / read_proposal / list_proposals — 提案 CRUD
  - update_proposal_status — 状态机变更 + history 追加 + status_entered_at 更新
  - can_auto_apply_memory — memory 类型提案的自动落地硬闸门（S4）
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from filelock import FileLock

from schemas import RetroProposal

logger = logging.getLogger(__name__)

MEMORY_DAILY_LIMIT_PER_AGENT = 3
MEMORY_MD_MAX_LINES = 200


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

def write_proposal(proposals_dir: Path, proposal: RetroProposal, proposal_id: str) -> Path:
    """写入一条提案到 proposals/{proposal_id}.json。"""
    proposals_dir.mkdir(parents=True, exist_ok=True)
    file_path = proposals_dir / f"{proposal_id}.json"
    lock_path = file_path.with_suffix(".lock")

    with FileLock(str(lock_path)):
        file_path.write_text(
            json.dumps(proposal.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return file_path


def read_proposal(proposals_dir: Path, proposal_id: str) -> RetroProposal | None:
    """读取单条提案，不存在或损坏返回 None。"""
    file_path = proposals_dir / f"{proposal_id}.json"
    if not file_path.exists():
        return None
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return RetroProposal(**data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("read_proposal: 解析失败 %s: %s", file_path, exc)
        return None


def list_proposals(proposals_dir: Path) -> list[tuple[str, RetroProposal]]:
    """列出全部提案，返回 [(proposal_id, proposal), ...]。"""
    if not proposals_dir.exists():
        return []

    results: list[tuple[str, RetroProposal]] = []
    for f in sorted(proposals_dir.glob("*.json")):
        proposal_id = f.stem
        p = read_proposal(proposals_dir, proposal_id)
        if p is not None:
            results.append((proposal_id, p))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 状态变更
# ─────────────────────────────────────────────────────────────────────────────

def update_proposal_status(
    proposals_dir: Path,
    proposal_id: str,
    new_status: str,
    note: str = "",
) -> RetroProposal | None:
    """
    变更提案状态 + 更新 status_entered_at + 追加 history。

    返回更新后的 RetroProposal，失败返回 None。
    """
    file_path = proposals_dir / f"{proposal_id}.json"
    lock_path = file_path.with_suffix(".lock")

    with FileLock(str(lock_path)):
        p = read_proposal(proposals_dir, proposal_id)
        if p is None:
            return None

        now_iso = datetime.now(timezone.utc).isoformat()
        old_status = p.status

        p.status = new_status  # type: ignore[assignment]
        p.status_entered_at = now_iso
        p.history.append({
            "ts": now_iso,
            "from": old_status,
            "to": new_status,
            "note": note,
        })
        if note:
            p.review_notes = note

        file_path.write_text(
            json.dumps(p.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return p


# ─────────────────────────────────────────────────────────────────────────────
# S4：memory 自动通道硬闸门
# ─────────────────────────────────────────────────────────────────────────────

def can_auto_apply_memory(
    proposal: RetroProposal,
    proposals_dir: Path,
    workspace_root: Path,
) -> tuple[bool, str]:
    """
    memory 类型提案是否可自动落地。

    硬限制：
      1. 每个 Agent 每天最多 MEMORY_DAILY_LIMIT_PER_AGENT 条
      2. append 后目标文件不超过 MEMORY_MD_MAX_LINES 行
    """
    if proposal.type != "memory_update":
        return False, "非 memory_update 类型"

    agent = proposal.initiator
    today = date.today().isoformat()

    applied_today = 0
    for _, p in list_proposals(proposals_dir):
        if (
            p.type == "memory_update"
            and p.initiator == agent
            and p.status == "已实施"
            and p.status_entered_at
            and p.status_entered_at.startswith(today)
        ):
            applied_today += 1

    if applied_today >= MEMORY_DAILY_LIMIT_PER_AGENT:
        return False, f"{agent} 今日 memory 自动落地已满 {applied_today}"

    for patch in proposal.patches:
        if patch.patch_format == "append":
            tgt = workspace_root / patch.target_file
            if tgt.exists():
                cur_lines = len(tgt.read_text(encoding="utf-8").splitlines())
                add_lines = len(str(patch.content).splitlines())
                if cur_lines + add_lines > MEMORY_MD_MAX_LINES:
                    return False, (
                        f"{patch.target_file} 当前 {cur_lines} 行，"
                        f"追加 {add_lines} 行后超过 {MEMORY_MD_MAX_LINES} 行上限"
                    )

    return True, "可自动落地"
