"""
第28课·数字员工的自我进化（v6）
schemas.py — 日志记录、Patch、验证判据与复盘提案的 Pydantic 数据模型

v6 变更：
  - 新增 ProposalPatch（精确 patch，含 checksum_before）
  - 新增 ValidationCheck（结构化验证判据，零 eval）
  - RetroProposal 扩展：patches / validation_check / status_entered_at /
    apply_commit_sha / pre_apply_commit_sha / history / review_notes /
    dry_run_output / initiator / memory_update 类型 / LLM预审中+已拒绝 状态 /
    blast_radius ≤ 5
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# L2 日志记录（任务-Agent 层）
# ─────────────────────────────────────────────────────────────────────────────

class L2LogRecord(BaseModel):
    agent_id:       str
    task_id:        str
    task_desc:      str
    result_quality: float
    duration_sec:   float
    error_type:     str | None = None
    timestamp:      str

    @field_validator("result_quality")
    @classmethod
    def quality_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"result_quality 必须在 0.0–1.0 之间，当前值：{v}")
        return v

    @field_validator("timestamp")
    @classmethod
    def valid_iso_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"timestamp 格式不合法（需要 ISO 8601），当前值：{v!r}") from exc
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Patch 与验证判据（v6 新增）
# ─────────────────────────────────────────────────────────────────────────────

class ProposalPatch(BaseModel):
    """由 propose_patch.py 脚本生成的精确 patch。"""
    target_file:     str
    patch_format:    Literal["unified_diff", "before_after", "append", "create"]
    content:         str | dict   # before_after → {"before": ..., "after": ...}
    checksum_before: str | None = None

    @field_validator("target_file")
    @classmethod
    def target_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("target_file 不允许为空")
        return v


class ValidationCheck(BaseModel):
    """结构化验证判据，零 eval。script 必须在白名单内。"""
    script:    Literal["stats_l2", "find_low_quality_tasks", "tool_call_stats", "stats_all_agents"]
    args:      dict
    metric:    str
    op:        Literal[">=", ">", "<=", "<", "==", "!="]
    threshold: float


# ─────────────────────────────────────────────────────────────────────────────
# 复盘改进提案（v6 扩展）
# ─────────────────────────────────────────────────────────────────────────────

class RetroProposal(BaseModel):
    type: Literal["tool_fix", "sop_update", "soul_update", "skill_add", "memory_update"]
    target:          str
    root_cause:      Literal[
        "ability_gap",
        "tool_defect",
        "prompt_ambiguity",
        "task_design",
    ]
    current:         str
    proposed:        str
    expected_metric: str
    rollback_plan:   str
    evidence:        list[str]
    priority:        Literal["low", "medium", "high"]
    status:          Literal[
        "待审批", "LLM预审中", "已批准", "已拒绝",
        "已实施", "验证中", "已验证", "已回滚",
    ] = "待审批"

    # v6 新增字段
    initiator:            str = ""
    patches:              list[ProposalPatch] = []
    validation_check:     ValidationCheck | None = None
    status_entered_at:    str | None = None
    apply_commit_sha:     str | None = None
    pre_apply_commit_sha: str | None = None
    history:              list[dict] = []
    review_notes:         str = ""
    dry_run_output:       str | None = None

    @field_validator("target", "current", "proposed", "expected_metric", "rollback_plan")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("字段不允许为空字符串")
        return v

    @field_validator("evidence")
    @classmethod
    def has_evidence(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("evidence 至少需要1条日志 ID，不允许空列表")
        return v

    @field_validator("patches")
    @classmethod
    def blast_radius(cls, v: list[ProposalPatch]) -> list[ProposalPatch]:
        if v and len({p.target_file for p in v}) > 5:
            raise ValueError("patches 涉及文件 > 5，一条提案只解决一个 root_cause，请拆分")
        return v
