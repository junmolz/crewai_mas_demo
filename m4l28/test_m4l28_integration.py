"""
第28课·数字员工的自我进化
test_m4l28_integration.py — 真实 LLM 集成测试

运行条件：需要 ALIYUN_API_KEY 环境变量（DashScope）。
在 CI 中通过 pytest -m integration 运行；本地单测默认跳过。

标记：@pytest.mark.integration

集成测试关注：
  IT1  run_self_retrospective 调用真实 LLM → 返回通过 Pydantic 校验的提案
  IT2  run_team_retrospective 调用真实 LLM → 生成 agent_stats + 写 human.json 周报
  IT3  proposals.json 可反序列化回 RetroProposal 列表（schema 闭环）
  IT4  _find_bottleneck 正确识别低质量 Agent（不依赖 LLM，纯统计）

测试策略：
  - 不 assert 具体 type/target（LLM 输出非确定性）
  - assert schema 合法性（RetroProposal(**item) 不抛异常）
  - assert 关键字段不为空字符串
  - assert 文件系统副作用（proposals.json / human.json 已写入）
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Marker + Skip 条件
# ─────────────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.integration

_SKIP_REASON = "需要 ALIYUN_API_KEY 环境变量，在真实 Docker 集成测试环境中运行"


def _require_api_key() -> None:
    """没有 API Key 时跳过整个测试，给出明确提示。"""
    if not os.environ.get("ALIYUN_API_KEY"):
        pytest.skip(_SKIP_REASON)


# ─────────────────────────────────────────────────────────────────────────────
# 共享 Fixture：预置7天历史日志
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def seeded_workspace(tmp_path):
    """
    预置 seed_logs 历史数据，返回 (logs_dir, mailbox_dir)。
    每个测试独立 tmp_path，互不污染。
    """
    from seed_logs import seed_logs

    seed_logs(base_dir=tmp_path)

    logs_dir    = tmp_path / "shared" / "logs"
    mailbox_dir = tmp_path / "shared" / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    return logs_dir, mailbox_dir


# ─────────────────────────────────────────────────────────────────────────────
# IT1: run_self_retrospective 真实 LLM → 提案通过 Pydantic 校验
# ─────────────────────────────────────────────────────────────────────────────

def test_it1_self_retro_real_llm_returns_valid_proposals(seeded_workspace):
    """
    使用真实 LLM 调用执行 PM 自我复盘。
    不 assert 具体提案内容（非确定性），只验证：
      - 返回值非空
      - 每个元素都是合法的 RetroProposal
      - human.json 收到 retrospective_proposal 邮件
    """
    _require_api_key()

    from retro.self_retrospective import run_self_retrospective
    from schemas import RetroProposal

    logs_dir, mailbox_dir = seeded_workspace

    proposals = run_self_retrospective(
        agent_id    = "pm",
        logs_dir    = logs_dir,
        mailbox_dir = mailbox_dir,
        days        = 7,
        min_tasks   = 5,
    )

    assert len(proposals) >= 1, "LLM 应生成至少1条改进提案"

    for p in proposals:
        assert isinstance(p, RetroProposal), "每个提案应通过 Pydantic 校验"
        assert p.target.strip(),            "target 不应为空字符串"
        assert p.expected_metric.strip(),   "expected_metric 不应为空字符串"
        assert len(p.evidence) >= 1,        "evidence 至少需要1条"

    human_inbox = mailbox_dir / "human.json"
    assert human_inbox.exists()
    messages   = json.loads(human_inbox.read_text())
    retro_msgs = [m for m in messages if m.get("type") == "retrospective_proposal"]
    assert len(retro_msgs) >= 1, "提案通知应发至 human.json"


# ─────────────────────────────────────────────────────────────────────────────
# IT2: run_team_retrospective 真实 LLM → agent_stats 正确 + 周报写入
# ─────────────────────────────────────────────────────────────────────────────

def test_it2_team_retro_real_llm_writes_report_and_stats(seeded_workspace):
    """
    使用真实 LLM 执行 Manager 团队复盘。
    验证：
      - agent_stats 包含 pm 和 manager 的统计数据
      - pm 的 avg_quality < manager 的 avg_quality（符合 seed_logs 设计）
      - pm 是瓶颈 agent
      - pm.json 收到 retro_trigger
      - human.json 收到 team_retrospective_report
    """
    _require_api_key()

    from retro.team_retrospective import run_team_retrospective

    logs_dir, mailbox_dir = seeded_workspace

    result = run_team_retrospective(
        manager_id  = "manager",
        agent_ids   = ["pm", "manager"],
        logs_dir    = logs_dir,
        mailbox_dir = mailbox_dir,
        days        = 7,
    )

    # 统计数据正确性
    assert "agent_stats" in result
    pm_stats      = result["agent_stats"]["pm"]
    manager_stats = result["agent_stats"]["manager"]

    assert pm_stats["task_count"]  == 8
    assert manager_stats["task_count"] == 3
    assert pm_stats["avg_quality"] < manager_stats["avg_quality"], (
        "PM 平均质量应低于 Manager（seed_logs 设计：PM 有3条低质量任务）"
    )

    # 瓶颈识别
    assert result["bottleneck_agent"] == "pm"

    # PM 收到 retro_trigger
    pm_inbox = mailbox_dir / "pm.json"
    assert pm_inbox.exists()
    pm_messages = json.loads(pm_inbox.read_text())
    triggers    = [m for m in pm_messages if m.get("type") == "retro_trigger"]
    assert len(triggers) >= 1

    # human 收到周报
    human_inbox   = mailbox_dir / "human.json"
    assert human_inbox.exists()
    human_messages = json.loads(human_inbox.read_text())
    reports        = [m for m in human_messages if m.get("type") == "team_retrospective_report"]
    assert len(reports) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# IT3: proposals.json schema 闭环验证
# ─────────────────────────────────────────────────────────────────────────────

def test_it3_proposals_json_deserializable(seeded_workspace):
    """
    自我复盘写入的 proposals.json 应能完整反序列化回 RetroProposal 对象。
    验证写入 schema 与读取 schema 的一致性（proposal_id 字段应被忽略）。
    """
    _require_api_key()

    from retro.self_retrospective import run_self_retrospective
    from schemas import RetroProposal

    logs_dir, mailbox_dir = seeded_workspace

    proposals = run_self_retrospective(
        agent_id    = "pm",
        logs_dir    = logs_dir,
        mailbox_dir = mailbox_dir,
        days        = 7,
        min_tasks   = 5,
    )

    if not proposals:
        pytest.skip("LLM 未生成任何提案，跳过 schema 闭环测试")

    proposals_file = mailbox_dir.parent / "proposals" / "proposals.json"
    assert proposals_file.exists(), "proposals.json 应已创建"

    raw = json.loads(proposals_file.read_text())
    assert len(raw) >= 1

    for item in raw:
        # proposal_id 是写入时额外加的字段，Pydantic model 用 model_validate 时应能忽略
        item_without_id = {k: v for k, v in item.items() if k != "proposal_id"}
        parsed = RetroProposal(**item_without_id)
        assert parsed.status in ("待审批", "已批准", "已实施", "验证中", "已验证", "已回滚")


# ─────────────────────────────────────────────────────────────────────────────
# IT4: _find_bottleneck 纯统计逻辑（不依赖 LLM）
# ─────────────────────────────────────────────────────────────────────────────

def test_it4_find_bottleneck_with_seeded_data(seeded_workspace):
    """
    不调用 LLM，直接验证 seed_logs 数据下 _find_bottleneck 能识别 PM 为瓶颈。
    这是一个确定性测试，可以在没有 ALIYUN_API_KEY 的环境中运行。
    """
    from retro.team_retrospective import _find_bottleneck
    from tools.log_ops import read_l2

    logs_dir, _ = seeded_workspace

    pm_records      = read_l2(logs_dir, "pm",      days=7)
    manager_records = read_l2(logs_dir, "manager",  days=7)

    def _stats(records: list[dict]) -> dict:
        if not records:
            return {"task_count": 0, "avg_quality": None, "failure_rate": None}
        qualities = [r.get("result_quality", 0.0) for r in records]
        failed    = [r for r in records if (r.get("result_quality", 1.0) or 1.0) < 0.5]
        return {
            "task_count":   len(records),
            "avg_quality":  round(sum(qualities) / len(qualities), 3),
            "failure_rate": round(len(failed) / len(records), 3),
        }

    agent_stats = {
        "pm":      _stats(pm_records),
        "manager": _stats(manager_records),
    }

    bottleneck = _find_bottleneck(agent_stats)
    assert bottleneck == "pm", (
        f"seed_logs 中 PM 平均质量({agent_stats['pm']['avg_quality']}) "
        f"< Manager({agent_stats['manager']['avg_quality']})，应识别 PM 为瓶颈"
    )
