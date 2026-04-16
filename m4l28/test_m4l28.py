"""
第28课·数字员工的自我进化
test_m4l28.py — 单元测试

测试矩阵：
  T1   write_l2      文件创建 + 字段完整性
  T2   write_l3      路径正确性
  T3   purge_old_l3  31天前记录 → 删除，返回1
  T3b  purge_old_l3  29天前记录 → 保留（负向测试）
  T4   RetroProposal expected_metric="" → ValidationError
  T5   RetroProposal evidence=[]       → ValidationError
  T6   run_self_retrospective 任务数不足 → [] + 打印 [SKIP]
  T7   send_mail(to="human") → l1_human/ 有对应记录
  T7b  send_mail(to="pm")    → l1_human/ 数量不变（负向测试）
  T8   (mock) run_self_retrospective 7天预置日志 → 提案写入 human.json
  T9   (mock) run_team_retrospective → PM收到 retro_trigger，human收到周报
  T10  L2LogRecord result_quality=1.5 → ValidationError
  T11  read_l2 days=3 只返回3天内记录
  T12  read_l2 结果按 timestamp 升序排列
  T13  _save_proposals 多次调用应累积追加，不覆盖
  T14  send_mail(from_="pm", to="human") → 违反单一接口约束，抛出 ValueError
  T15  send_mail(from_="unknown") → 未知发件角色，抛出 ValueError
  T16  _find_bottleneck 全员无任务 → 返回 None
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from schemas import L2LogRecord, RetroProposal
from tools.log_ops import (
    purge_old_l3,
    read_l2,
    write_l2,
    write_l3,
)
from tools.mailbox_ops import send_mail


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _make_l2_record(
    agent_id: str = "pm",
    task_id: str  = "t_test",
    quality: float = 0.8,
    days_ago: int  = 1,
    error_type: str | None = None,
) -> dict:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "agent_id":       agent_id,
        "task_id":        task_id,
        "task_desc":      "测试任务",
        "result_quality": quality,
        "duration_sec":   120,
        "error_type":     error_type,
        "timestamp":      ts,
    }


def _make_l3_record(
    agent_id: str = "pm",
    task_id: str  = "t_test",
    step_idx: int = 0,
    days_ago: int = 1,
    converged: bool = True,
) -> dict:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "agent_id":    agent_id,
        "task_id":     task_id,
        "step_idx":    step_idx,
        "thought":     "分析问题",
        "action":      "write_document",
        "observation": "文档已写入",
        "converged":   converged,
        "timestamp":   ts,
    }


def _valid_proposal_dict(**overrides) -> dict:
    base = {
        "type":             "sop_update",
        "target":           "pm/skills/design_spec_sop.md",
        "root_cause":       "ability_gap",
        "current":          "缺少移动端设计检查步骤",
        "proposed":         "在 SOP 第3步新增移动端适配检查清单",
        "expected_metric":  "checkpoint通过率从45%提升到75%",
        "rollback_plan":    "删除新增检查步骤，恢复原始 SOP v1",
        "evidence":         ["t001", "t003"],
        "priority":         "high",
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# T1: write_l2 文件创建 + 字段完整性
# ─────────────────────────────────────────────────────────────────────────────

def test_t1_write_l2_creates_file_with_correct_fields(tmp_path):
    """write_l2 在正确路径创建文件，内容包含全部字段。"""
    logs_dir = tmp_path / "logs"
    record   = _make_l2_record(agent_id="pm", task_id="t001")

    path = write_l2(logs_dir, "pm", "t001", record)

    assert path.exists(), "write_l2 应创建文件"
    assert path == logs_dir / "l2_task" / "pm_t001.json"

    saved = json.loads(path.read_text())
    assert saved["agent_id"]       == "pm"
    assert saved["task_id"]        == "t001"
    assert saved["result_quality"] == 0.8
    assert "timestamp" in saved


# ─────────────────────────────────────────────────────────────────────────────
# T2: write_l3 路径正确性
# ─────────────────────────────────────────────────────────────────────────────

def test_t2_write_l3_creates_at_correct_path(tmp_path):
    """write_l3 在 l3_react/{agent_id}/{task_id}/step_{N}.json 创建文件。"""
    logs_dir = tmp_path / "logs"
    record   = _make_l3_record(agent_id="pm", task_id="t001", step_idx=2)

    path = write_l3(logs_dir, "pm", "t001", 2, record)

    expected = logs_dir / "l3_react" / "pm" / "t001" / "step_2.json"
    assert path == expected
    assert path.exists()

    saved = json.loads(path.read_text())
    assert saved["step_idx"] == 2
    assert saved["action"]   == "write_document"


# ─────────────────────────────────────────────────────────────────────────────
# T3: purge_old_l3 删除31天前记录
# ─────────────────────────────────────────────────────────────────────────────

def test_t3_purge_old_l3_deletes_stale_record(tmp_path):
    """31天前的 L3 记录（timestamp字段）应被删除，返回1。"""
    logs_dir = tmp_path / "logs"
    record   = _make_l3_record(days_ago=31)

    write_l3(logs_dir, "pm", "t_old", 0, record)
    deleted = purge_old_l3(logs_dir, retention_days=30)

    assert deleted == 1
    assert not (logs_dir / "l3_react" / "pm" / "t_old" / "step_0.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
# T3b: purge_old_l3 保留29天内记录（负向测试）
# ─────────────────────────────────────────────────────────────────────────────

def test_t3b_purge_old_l3_keeps_recent_record(tmp_path):
    """29天前的 L3 记录（未超过30天）应被保留，返回0。"""
    logs_dir = tmp_path / "logs"
    record   = _make_l3_record(days_ago=29)

    write_l3(logs_dir, "pm", "t_recent", 0, record)
    deleted = purge_old_l3(logs_dir, retention_days=30)

    assert deleted == 0
    assert (logs_dir / "l3_react" / "pm" / "t_recent" / "step_0.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
# T4: RetroProposal expected_metric 为空字符串 → ValidationError
# ─────────────────────────────────────────────────────────────────────────────

def test_t4_retro_proposal_rejects_empty_expected_metric():
    """RetroProposal.expected_metric 为空字符串时应抛出 ValidationError。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="expected_metric|字段不允许为空"):
        RetroProposal(**_valid_proposal_dict(expected_metric=""))


# ─────────────────────────────────────────────────────────────────────────────
# T5: RetroProposal evidence 为空列表 → ValidationError
# ─────────────────────────────────────────────────────────────────────────────

def test_t5_retro_proposal_rejects_empty_evidence():
    """RetroProposal.evidence 为空列表时应抛出 ValidationError。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="evidence|至少需要"):
        RetroProposal(**_valid_proposal_dict(evidence=[]))


# ─────────────────────────────────────────────────────────────────────────────
# T6: run_self_retrospective 任务数不足 → 跳过，返回 []
# ─────────────────────────────────────────────────────────────────────────────

def test_t6_self_retro_skips_when_insufficient_samples(tmp_path, capsys):
    """任务数 < min_tasks 时打印 [SKIP] 并返回空列表，不调用 LLM。"""
    from retro.self_retrospective import run_self_retrospective

    logs_dir    = tmp_path / "logs"
    mailbox_dir = tmp_path / "mailboxes"

    for i in range(3):
        write_l2(logs_dir, "pm", f"t00{i}", _make_l2_record(task_id=f"t00{i}"))

    result = run_self_retrospective(
        agent_id    = "pm",
        logs_dir    = logs_dir,
        mailbox_dir = mailbox_dir,
        days        = 7,
        min_tasks   = 5,
    )

    assert result == []
    captured = capsys.readouterr()
    assert "[SKIP]" in captured.out
    assert "pm" in captured.out


# ─────────────────────────────────────────────────────────────────────────────
# T7: send_mail(to="human") 自动写 L1 日志
# ─────────────────────────────────────────────────────────────────────────────

def test_t7_send_mail_to_human_writes_l1_log(tmp_path):
    """send_mail(to='human') 时，l1_human/ 目录下应生成对应的 JSON 文件。"""
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    msg_id = send_mail(
        mailbox_dir = mailbox_dir,
        to          = "human",
        from_       = "manager",
        type_       = "needs_confirm",
        subject     = "测试消息",
        content     = "测试内容",
    )

    l1_dir   = tmp_path / "logs" / "l1_human"
    l1_files = list(l1_dir.glob("*.json")) if l1_dir.exists() else []
    assert len(l1_files) == 1, "应在 l1_human/ 生成1个文件"

    saved = json.loads(l1_files[0].read_text())
    assert saved["id"]   == msg_id
    assert saved["to"]   == "human"
    assert saved["type"] == "needs_confirm"


# ─────────────────────────────────────────────────────────────────────────────
# T7b: send_mail(to="pm") 不写 L1 日志（负向测试）
# ─────────────────────────────────────────────────────────────────────────────

def test_t7b_send_mail_to_pm_does_not_write_l1(tmp_path):
    """send_mail(to='pm') 时，l1_human/ 不应新增文件。"""
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    send_mail(
        mailbox_dir = mailbox_dir,
        to          = "pm",
        from_       = "manager",
        type_       = "task_assign",
        subject     = "任务分配",
        content     = "请设计产品文档",
    )

    l1_dir    = tmp_path / "logs" / "l1_human"
    l1_count  = len(list(l1_dir.glob("*.json"))) if l1_dir.exists() else 0
    assert l1_count == 0, "发给 pm 时不应写 L1 日志"


# ─────────────────────────────────────────────────────────────────────────────
# T8: (mock) run_self_retrospective 7天预置日志 → 提案写入 human.json
# ─────────────────────────────────────────────────────────────────────────────

def test_t8_self_retro_mock_writes_proposals(tmp_path):
    """
    Mock 测试：seed_logs 预置 8 条 PM 任务（含3条低质量），
    run_self_retrospective mock LLM → 提案写入 human.json。
    """
    from retro.self_retrospective import run_self_retrospective
    from seed_logs import seed_logs

    logs_dir    = tmp_path / "shared" / "logs"
    mailbox_dir = tmp_path / "shared" / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    seed_logs(base_dir=tmp_path)

    mock_proposal = {"proposals": [_valid_proposal_dict()]}
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(mock_proposal, ensure_ascii=False)

    with patch("retro.self_retrospective.get_llm_client") as mock_client:
        mock_client.return_value.chat.completions.create.return_value = mock_response

        proposals = run_self_retrospective(
            agent_id    = "pm",
            logs_dir    = logs_dir,
            mailbox_dir = mailbox_dir,
            days        = 7,
            min_tasks   = 5,
        )

    assert len(proposals) >= 1
    assert proposals[0].type == "sop_update"

    human_inbox = mailbox_dir / "human.json"
    assert human_inbox.exists()
    messages    = json.loads(human_inbox.read_text())
    retro_msgs  = [m for m in messages if m.get("type") == "retrospective_proposal"]
    assert len(retro_msgs) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# T9: (mock) run_team_retrospective → PM 收到 retro_trigger，human 收到周报
# ─────────────────────────────────────────────────────────────────────────────

def test_t9_team_retro_mock_triggers_agent_and_sends_report(tmp_path):
    """
    Mock 测试：seed_logs 预置 PM(低分) + Manager(高分)，
    run_team_retrospective 应向 PM 写 retro_trigger，向 human 写周报。
    """
    from retro.team_retrospective import run_team_retrospective
    from seed_logs import seed_logs

    logs_dir    = tmp_path / "shared" / "logs"
    mailbox_dir = tmp_path / "shared" / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    seed_logs(base_dir=tmp_path)

    with patch("retro.team_retrospective._call_team_llm") as mock_team_llm:
        mock_team_llm.return_value = []

        result = run_team_retrospective(
            manager_id  = "manager",
            agent_ids   = ["pm", "manager"],
            logs_dir    = logs_dir,
            mailbox_dir = mailbox_dir,
            days        = 7,
        )

    pm_inbox     = mailbox_dir / "pm.json"
    assert pm_inbox.exists()
    pm_messages  = json.loads(pm_inbox.read_text())
    triggers     = [m for m in pm_messages if m.get("type") == "retro_trigger"]
    assert len(triggers) >= 1, "瓶颈 Agent(PM) 应收到 retro_trigger"

    human_inbox   = mailbox_dir / "human.json"
    assert human_inbox.exists()
    human_messages = json.loads(human_inbox.read_text())
    reports        = [m for m in human_messages if m.get("type") == "team_retrospective_report"]
    assert len(reports) >= 1, "human 应收到团队周报"

    assert "agent_stats" in result
    assert result["bottleneck_agent"] == "pm"


# ─────────────────────────────────────────────────────────────────────────────
# T10: L2LogRecord result_quality 超范围 → ValidationError
# ─────────────────────────────────────────────────────────────────────────────

def test_t10_l2_log_record_rejects_out_of_range_quality():
    """L2LogRecord.result_quality=1.5 应抛出 ValidationError（超出0-1范围）。"""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="result_quality|0.0.1.0"):
        L2LogRecord(
            agent_id       = "pm",
            task_id        = "t001",
            task_desc      = "测试",
            result_quality = 1.5,
            duration_sec   = 120,
            timestamp      = datetime.now(timezone.utc).isoformat(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# T11: read_l2 days=3 只返回3天内的记录
# ─────────────────────────────────────────────────────────────────────────────

def test_t11_read_l2_filters_by_days_window(tmp_path):
    """read_l2(days=3) 应只返回3天内的记录，过滤掉5天前的记录。"""
    logs_dir = tmp_path / "logs"

    write_l2(logs_dir, "pm", "recent", _make_l2_record(task_id="recent", days_ago=2))
    write_l2(logs_dir, "pm", "old",    _make_l2_record(task_id="old",    days_ago=5))

    results  = read_l2(logs_dir, "pm", days=3)
    task_ids = [r["task_id"] for r in results]

    assert "recent" in task_ids,     "2天前的记录应在3天窗口内返回"
    assert "old" not in task_ids,    "5天前的记录应被过滤"
    assert len(results) == 1


# ─────────────────────────────────────────────────────────────────────────────
# T12: read_l2 结果按 timestamp 升序排列
# ─────────────────────────────────────────────────────────────────────────────

def test_t12_read_l2_returns_sorted_by_timestamp(tmp_path):
    """read_l2 应按 timestamp 升序返回，而不是文件系统顺序。"""
    logs_dir = tmp_path / "logs"

    # 写入顺序故意乱序：newer 先写，older 后写
    write_l2(logs_dir, "pm", "newer", _make_l2_record(task_id="newer", days_ago=1))
    write_l2(logs_dir, "pm", "older", _make_l2_record(task_id="older", days_ago=3))
    write_l2(logs_dir, "pm", "mid",   _make_l2_record(task_id="mid",   days_ago=2))

    results  = read_l2(logs_dir, "pm", days=7)
    task_ids = [r["task_id"] for r in results]

    assert task_ids == ["older", "mid", "newer"], (
        f"结果应按 timestamp 升序（oldest first），实际：{task_ids}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T13: _save_proposals 多次调用应累积追加，不覆盖
# ─────────────────────────────────────────────────────────────────────────────

def test_t13_save_proposals_appends_across_calls(tmp_path):
    """_save_proposals 第二次调用应追加，不覆盖第一次的提案。"""
    from retro.self_retrospective import save_proposals

    proposals_file = tmp_path / "proposals" / "proposals.json"

    p1 = RetroProposal(**_valid_proposal_dict(target="file_a.md", evidence=["t001"]))
    p2 = RetroProposal(**_valid_proposal_dict(target="file_b.md", evidence=["t002"]))

    save_proposals([p1], proposals_file)
    save_proposals([p2], proposals_file)

    saved = json.loads(proposals_file.read_text())
    assert len(saved) == 2, "两次调用后应有2条提案"
    targets = [s["target"] for s in saved]
    assert "file_a.md" in targets
    assert "file_b.md" in targets


# ─────────────────────────────────────────────────────────────────────────────
# T14: send_mail(from_="pm", to="human") 违反单一接口约束 → ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_t14_send_mail_rejects_pm_sending_to_human(tmp_path):
    """PM 不能直接发消息给 human（单一接口约束）。"""
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="单一接口约束|from_.*manager"):
        send_mail(
            mailbox_dir = mailbox_dir,
            to          = "human",
            from_       = "pm",       # 违反约束
            type_       = "task_done",
            subject     = "任务完成",
            content     = "产品文档已完成",
        )


# ─────────────────────────────────────────────────────────────────────────────
# T15: send_mail(from_="unknown") → 未知发件角色，抛出 ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_t15_send_mail_rejects_unknown_from_role(tmp_path):
    """未知 from_ 角色应抛出 ValueError。"""
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="未知发件角色"):
        send_mail(
            mailbox_dir = mailbox_dir,
            to          = "manager",
            from_       = "unknown_agent",
            type_       = "task_done",
            subject     = "测试",
            content     = "测试",
        )


# ─────────────────────────────────────────────────────────────────────────────
# T16: _find_bottleneck 全员无任务 → 返回 None
# ─────────────────────────────────────────────────────────────────────────────

def test_t16_find_bottleneck_returns_none_when_no_tasks():
    """所有 Agent 任务数为0时，_find_bottleneck 应返回 None。"""
    from retro.team_retrospective import find_bottleneck

    agent_stats = {
        "pm":      {"task_count": 0, "avg_quality": None, "failure_rate": None},
        "manager": {"task_count": 0, "avg_quality": None, "failure_rate": None},
    }

    result = find_bottleneck(agent_stats)
    assert result is None, "全员无任务时不应认定瓶颈"
