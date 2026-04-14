"""
第28课·数字员工的自我进化
schemas.py — 日志记录与复盘提案的 Pydantic 数据模型

教学要点（对应第28课 P2/P4）：
  - L2LogRecord：任务-Agent 层日志，result_quality 和 timestamp 均有校验
  - RetroProposal：结构化改进提案，强制填写所有字段，禁止空字符串和空 evidence
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# L2 日志记录（任务-Agent 层）
# ─────────────────────────────────────────────────────────────────────────────

class L2LogRecord(BaseModel):
    """
    每个 Agent 每次被触发时写入一条 L2 日志。
    对应第28课 P2 三层日志中的"L2 任务-Agent 层"。
    """

    agent_id:       str
    task_id:        str
    task_desc:      str
    result_quality: float           # 0.0（失败）到 1.0（完美）
    duration_sec:   float
    error_type:     str | None = None
    timestamp:      str             # ISO 8601，如 "2026-04-10T10:00:00+00:00"

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
# 复盘改进提案
# ─────────────────────────────────────────────────────────────────────────────

class RetroProposal(BaseModel):
    """
    Agent 自我复盘或 Manager 团队复盘生成的改进提案。
    对应第28课 P4 结构化提案 schema。

    设计原则：
      - 所有字段必填，禁止空字符串（type/root_cause 用 Literal 枚举约束）
      - evidence 必须至少引用1条日志 ID（可追溯原则）
      - expected_metric 必须可测量（由 not_empty 校验强制非空，由 LLM prompt 约束内容）
      - rollback_plan 必须填写（审批时人类评估风险）
    """

    type: Literal["tool_fix", "sop_update", "soul_update", "skill_add"]
    target:          str    # 具体文件/方法名，如 "pm/skills/design_spec_sop.md"
    root_cause:      Literal[
        "ability_gap",       # Agent 能力不足
        "tool_defect",       # 工具本身有问题
        "prompt_ambiguity",  # Prompt 描述不清
        "task_design",       # 任务/SOP 设计问题
    ]
    current:         str    # 当前存在的问题描述
    proposed:        str    # 具体改动内容
    expected_metric: str    # 可测量的预期效果，如"通过率从60%提升到80%"
    rollback_plan:   str    # 如果效果变差，如何回滚
    evidence:        list[str]  # 日志 ID 列表，至少1条
    priority:        Literal["low", "medium", "high"]
    status:          Literal[
        "待审批", "已批准", "已实施", "验证中", "已验证", "已回滚"
    ] = "待审批"

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
