"""
第28课·数字员工的自我进化（v6）
test_m4l28.py — 单元测试

测试矩阵：
  T1   write_l2      文件创建 + 字段完整性
  T2   write_l3      路径正确性
  T3   purge_old_l3  31天前记录 → 删除，返回1
  T3b  purge_old_l3  29天前记录 → 保留（负向测试）
  T4   RetroProposal expected_metric="" → ValidationError
  T5   RetroProposal evidence=[]       → ValidationError
  T7   send_mail(to="human") → l1_human/ 有对应记录
  T7b  send_mail(to="pm")    → l1_human/ 数量不变（负向测试）
  T10  L2LogRecord result_quality=1.5 → ValidationError
  T11  read_l2 days=3 只返回3天内记录
  T12  read_l2 结果按 timestamp 升序排列
  T14  send_mail(from_="pm", to="human") → 违反单一接口约束
  T15  send_mail(from_="unknown") → 未知发件角色
  T16  send_mail type 白名单校验

  ---- v6 新增 ----
  T20  ProposalPatch target_file="" → ValidationError
  T21  blast_radius > 5 → ValidationError
  T22  ValidationCheck script 白名单
  T23  RetroProposal memory_update 类型
  T24  read_session_index 正向 + 空
  T25  read_l3_from_sessions 按 task_id 过滤
  T26  read_l3_from_sessions only_failed 过滤
  T27  scheduler should_trigger 双条件
  T28  scheduler tick 发送 retro_trigger
  T29  proposal_ops write/read/list
  T30  proposal_ops update_status + history
  T31  proposal_ops can_auto_apply_memory
  T32  l2_task_callback 写入 L2
  T33  seed_logs 写入 session L3
  T34  send_mail project_id 字段
  T35  count_l2_since 统计
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from schemas import L2LogRecord, RetroProposal, ProposalPatch, ValidationCheck
from tools.log_ops import (
    count_l2_since,
    purge_old_l3,
    read_l2,
    read_l3_from_sessions,
    read_session_index,
    write_l2,
    write_l3,
)
from tools.mailbox_ops import send_mail
from tools.proposal_ops import (
    can_auto_apply_memory,
    list_proposals,
    read_proposal,
    update_proposal_status,
    write_proposal,
)


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _make_l2_record(
    agent_id: str = "pm",
    task_id: str = "test_001",
    quality: float = 0.8,
    days_ago: int = 0,
) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "agent_id": agent_id,
        "task_id": task_id,
        "task_desc": f"测试任务 {task_id}",
        "result_quality": quality,
        "duration_sec": 100,
        "error_type": None,
        "timestamp": ts.isoformat(),
    }


def _make_proposal(**overrides) -> RetroProposal:
    defaults = {
        "type": "sop_update",
        "target": "workspace/pm/skills/product_design/SKILL.md",
        "root_cause": "prompt_ambiguity",
        "current": "当前缺少移动端适配检查",
        "proposed": "新增移动端适配检查步骤",
        "expected_metric": "avg_quality >= 0.8",
        "rollback_plan": "还原 SKILL.md 到上一版本",
        "evidence": ["l1_001", "l1_002"],
        "priority": "medium",
        "initiator": "pm",
    }
    defaults.update(overrides)
    return RetroProposal(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# T1: write_l2 文件创建
# ─────────────────────────────────────────────────────────────────────────────

def test_t1_write_l2_creates_file(tmp_path):
    record = _make_l2_record()
    path = write_l2(tmp_path, "pm", "test_001", record)
    assert path.exists()
    saved = json.loads(path.read_text())
    assert saved["agent_id"] == "pm"
    assert saved["task_id"] == "test_001"


# ─────────────────────────────────────────────────────────────────────────────
# T2: write_l3 路径正确性
# ─────────────────────────────────────────────────────────────────────────────

def test_t2_write_l3_path(tmp_path):
    record = {"agent_id": "pm", "task_id": "t001", "step_idx": 0, "thought": "test"}
    path = write_l3(tmp_path, "pm", "t001", 0, record)
    assert "l3_react/pm/t001/step_0.json" in str(path)
    assert path.exists()


# ─────────────────────────────────────────────────────────────────────────────
# T3: purge_old_l3 删除过期记录
# ─────────────────────────────────────────────────────────────────────────────

def test_t3_purge_old_l3_deletes_expired(tmp_path):
    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    write_l3(tmp_path, "pm", "old_task", 0, {"timestamp": old_ts})
    deleted = purge_old_l3(tmp_path, retention_days=30)
    assert deleted == 1


def test_t3b_purge_old_l3_keeps_recent(tmp_path):
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=29)).isoformat()
    write_l3(tmp_path, "pm", "recent_task", 0, {"timestamp": recent_ts})
    deleted = purge_old_l3(tmp_path, retention_days=30)
    assert deleted == 0


# ─────────────────────────────────────────────────────────────────────────────
# T4: RetroProposal expected_metric="" → ValidationError
# ─────────────────────────────────────────────────────────────────────────────

def test_t4_retro_proposal_rejects_empty_metric():
    with pytest.raises(Exception, match="不允许为空"):
        _make_proposal(expected_metric="")


# ─────────────────────────────────────────────────────────────────────────────
# T5: RetroProposal evidence=[] → ValidationError
# ─────────────────────────────────────────────────────────────────────────────

def test_t5_retro_proposal_rejects_empty_evidence():
    with pytest.raises(Exception, match="至少需要1条"):
        _make_proposal(evidence=[])


# ─────────────────────────────────────────────────────────────────────────────
# T7: send_mail(to="human") 自动写 L1 日志
# ─────────────────────────────────────────────────────────────────────────────

def test_t7_send_mail_to_human_writes_l1(tmp_path):
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    msg_id = send_mail(
        mailbox_dir=mailbox_dir,
        to="human",
        from_="manager",
        type_="checkpoint_request",
        subject="测试消息",
        content="测试内容",
    )

    l1_dir = tmp_path / "logs" / "l1_human"
    l1_files = list(l1_dir.glob("*.json")) if l1_dir.exists() else []
    assert len(l1_files) == 1
    saved = json.loads(l1_files[0].read_text())
    assert saved["id"] == msg_id
    assert saved["type"] == "checkpoint_request"


def test_t7b_send_mail_to_pm_does_not_write_l1(tmp_path):
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    send_mail(
        mailbox_dir=mailbox_dir,
        to="pm",
        from_="manager",
        type_="task_assign",
        subject="任务分配",
        content="请设计产品文档",
    )

    l1_dir = tmp_path / "logs" / "l1_human"
    l1_files = list(l1_dir.glob("*.json")) if l1_dir.exists() else []
    assert len(l1_files) == 0


# ─────────────────────────────────────────────────────────────────────────────
# T10: L2LogRecord result_quality=1.5 → ValidationError
# ─────────────────────────────────────────────────────────────────────────────

def test_t10_l2_rejects_quality_out_of_range():
    with pytest.raises(Exception, match="0.0–1.0"):
        L2LogRecord(
            agent_id="pm", task_id="t1", task_desc="test",
            result_quality=1.5, duration_sec=10,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# T11: read_l2 days=3 只返回3天内记录
# ─────────────────────────────────────────────────────────────────────────────

def test_t11_read_l2_respects_days_filter(tmp_path):
    write_l2(tmp_path, "pm", "old", _make_l2_record(task_id="old", days_ago=5))
    write_l2(tmp_path, "pm", "new", _make_l2_record(task_id="new", days_ago=1))
    records = read_l2(tmp_path, "pm", days=3)
    task_ids = [r["task_id"] for r in records]
    assert "new" in task_ids
    assert "old" not in task_ids


# ─────────────────────────────────────────────────────────────────────────────
# T12: read_l2 结果按 timestamp 升序
# ─────────────────────────────────────────────────────────────────────────────

def test_t12_read_l2_sorted_ascending(tmp_path):
    write_l2(tmp_path, "pm", "later", _make_l2_record(task_id="later", days_ago=1))
    write_l2(tmp_path, "pm", "earlier", _make_l2_record(task_id="earlier", days_ago=3))
    records = read_l2(tmp_path, "pm", days=7)
    assert records[0]["task_id"] == "earlier"
    assert records[1]["task_id"] == "later"


# ─────────────────────────────────────────────────────────────────────────────
# T14: send_mail 单一接口约束
# ─────────────────────────────────────────────────────────────────────────────

def test_t14_send_mail_rejects_pm_to_human(tmp_path):
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir()
    with pytest.raises(ValueError, match="单一接口约束"):
        send_mail(mailbox_dir, to="human", from_="pm",
                  type_="retro_proposal", subject="test", content="test")


# ─────────────────────────────────────────────────────────────────────────────
# T15: send_mail 未知发件角色
# ─────────────────────────────────────────────────────────────────────────────

def test_t15_send_mail_rejects_unknown_from(tmp_path):
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir()
    with pytest.raises(ValueError, match="未知发件角色"):
        send_mail(mailbox_dir, to="manager", from_="unknown",
                  type_="task_assign", subject="test", content="test")


# ─────────────────────────────────────────────────────────────────────────────
# T16: send_mail type 白名单校验
# ─────────────────────────────────────────────────────────────────────────────

def test_t16_send_mail_rejects_unknown_type(tmp_path):
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir()
    with pytest.raises(ValueError, match="未知消息类型"):
        send_mail(mailbox_dir, to="manager", from_="pm",
                  type_="invalid_type", subject="test", content="test")


# ═════════════════════════════════════════════════════════════════════════════
# v6 新增测试
# ═════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# T20: ProposalPatch target_file="" → ValidationError
# ─────────────────────────────────────────────────────────────────────────────

def test_t20_proposal_patch_rejects_empty_target():
    with pytest.raises(Exception, match="不允许为空"):
        ProposalPatch(target_file="", patch_format="append", content="test")


# ─────────────────────────────────────────────────────────────────────────────
# T21: blast_radius > 5 → ValidationError
# ─────────────────────────────────────────────────────────────────────────────

def test_t21_blast_radius_over_5():
    patches = [
        ProposalPatch(target_file=f"file_{i}.md", patch_format="append", content="test")
        for i in range(6)
    ]
    with pytest.raises(Exception, match="涉及文件 > 5"):
        _make_proposal(patches=patches)


def test_t21b_blast_radius_at_5_ok():
    patches = [
        ProposalPatch(target_file=f"file_{i}.md", patch_format="append", content="test")
        for i in range(5)
    ]
    p = _make_proposal(patches=patches)
    assert len(p.patches) == 5


# ─────────────────────────────────────────────────────────────────────────────
# T22: ValidationCheck script 白名单
# ─────────────────────────────────────────────────────────────────────────────

def test_t22_validation_check_valid():
    vc = ValidationCheck(
        script="stats_l2", args={"agent_id": "pm"}, metric="avg_quality",
        op=">=", threshold=0.7,
    )
    assert vc.script == "stats_l2"


def test_t22b_validation_check_invalid_script():
    with pytest.raises(Exception):
        ValidationCheck(
            script="evil_script", args={}, metric="x", op=">=", threshold=0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# T23: RetroProposal memory_update 类型
# ─────────────────────────────────────────────────────────────────────────────

def test_t23_memory_update_type():
    p = _make_proposal(type="memory_update")
    assert p.type == "memory_update"


# ─────────────────────────────────────────────────────────────────────────────
# T24: read_session_index
# ─────────────────────────────────────────────────────────────────────────────

def test_t24_read_session_index(tmp_path):
    idx_file = tmp_path / "index.jsonl"
    idx_file.write_text(
        json.dumps({"session_id": "s1", "task_id": "t1", "agent_id": "pm",
                     "start_line": 0, "end_line": 5}) + "\n",
        encoding="utf-8",
    )
    entries = read_session_index(tmp_path)
    assert len(entries) == 1
    assert entries[0]["task_id"] == "t1"


def test_t24b_read_session_index_empty(tmp_path):
    assert read_session_index(tmp_path) == []


# ─────────────────────────────────────────────────────────────────────────────
# T25: read_l3_from_sessions 按 task_id 过滤
# ─────────────────────────────────────────────────────────────────────────────

def test_t25_read_l3_from_sessions_filter_task_id(tmp_path):
    # Write index
    idx = tmp_path / "index.jsonl"
    idx.write_text(
        json.dumps({"session_id": "s1", "task_id": "t1", "agent_id": "pm",
                     "start_line": 0, "end_line": 2}) + "\n"
        + json.dumps({"session_id": "s1", "task_id": "t2", "agent_id": "pm",
                       "start_line": 2, "end_line": 4}) + "\n",
        encoding="utf-8",
    )
    # Write raw
    raw = tmp_path / "s1_raw.jsonl"
    lines = [
        json.dumps({"role": "assistant", "content": "task1 step1", "ts": "2026-04-15T10:00:00"}),
        json.dumps({"role": "tool", "content": "task1 result", "ts": "2026-04-15T10:01:00"}),
        json.dumps({"role": "assistant", "content": "task2 step1", "ts": "2026-04-15T11:00:00"}),
        json.dumps({"role": "tool", "content": "task2 result", "ts": "2026-04-15T11:01:00"}),
    ]
    raw.write_text("\n".join(lines) + "\n", encoding="utf-8")

    results = read_l3_from_sessions(tmp_path, task_id="t1")
    assert len(results) == 2
    assert "task1" in results[0]["content"]


# ─────────────────────────────────────────────────────────────────────────────
# T26: read_l3_from_sessions only_failed
# ─────────────────────────────────────────────────────────────────────────────

def test_t26_read_l3_only_failed(tmp_path):
    idx = tmp_path / "index.jsonl"
    idx.write_text(
        json.dumps({"session_id": "s1", "task_id": "t1", "agent_id": "pm",
                     "start_line": 0, "end_line": 3}) + "\n",
        encoding="utf-8",
    )
    raw = tmp_path / "s1_raw.jsonl"
    lines = [
        json.dumps({"role": "assistant", "content": "正常步骤"}),
        json.dumps({"role": "tool", "content": "Error: 操作失败"}),
        json.dumps({"role": "assistant", "content": "另一个正常步骤"}),
    ]
    raw.write_text("\n".join(lines) + "\n", encoding="utf-8")

    all_results = read_l3_from_sessions(tmp_path, task_id="t1", only_failed=False)
    assert len(all_results) == 3

    failed_only = read_l3_from_sessions(tmp_path, task_id="t1", only_failed=True)
    assert len(failed_only) == 1
    assert "Error" in failed_only[0]["content"]


# ─────────────────────────────────────────────────────────────────────────────
# T27: scheduler should_trigger 双条件
# ─────────────────────────────────────────────────────────────────────────────

def test_t27_scheduler_should_trigger(tmp_path):
    from scheduler import should_trigger

    logs_dir = tmp_path / "logs"
    state_file = tmp_path / ".last_retro.json"

    # 没有日志 → 不触发
    ok, why = should_trigger("pm", logs_dir, state_file=state_file)
    assert not ok
    assert "任务量" in why

    # 写入 5 条 L2 → 触发
    for i in range(5):
        write_l2(logs_dir, "pm", f"t{i}", _make_l2_record(task_id=f"t{i}"))

    ok, why = should_trigger("pm", logs_dir, state_file=state_file)
    assert ok


# ─────────────────────────────────────────────────────────────────────────────
# T28: scheduler tick 发送 retro_trigger
# ─────────────────────────────────────────────────────────────────────────────

def test_t28_scheduler_tick(tmp_path):
    from scheduler import tick

    logs_dir = tmp_path / "logs"
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir(parents=True)
    state_file = tmp_path / ".last_retro.json"

    # 写入足够 L2
    for i in range(6):
        write_l2(logs_dir, "pm", f"t{i}", _make_l2_record(task_id=f"t{i}"))

    triggered = tick(logs_dir=logs_dir, mailbox_dir=mailbox_dir, state_file=state_file)
    assert "pm" in triggered

    # 验证邮件已写入
    pm_inbox = mailbox_dir / "pm.json"
    assert pm_inbox.exists()
    messages = json.loads(pm_inbox.read_text())
    assert any(m["type"] == "retro_trigger" for m in messages)


# ─────────────────────────────────────────────────────────────────────────────
# T29: proposal_ops CRUD
# ─────────────────────────────────────────────────────────────────────────────

def test_t29_proposal_ops_crud(tmp_path):
    p = _make_proposal()
    path = write_proposal(tmp_path, p, "p001")
    assert path.exists()

    loaded = read_proposal(tmp_path, "p001")
    assert loaded is not None
    assert loaded.type == "sop_update"
    assert loaded.target == p.target

    all_proposals = list_proposals(tmp_path)
    assert len(all_proposals) == 1
    assert all_proposals[0][0] == "p001"


# ─────────────────────────────────────────────────────────────────────────────
# T30: update_proposal_status + history
# ─────────────────────────────────────────────────────────────────────────────

def test_t30_update_proposal_status(tmp_path):
    p = _make_proposal()
    write_proposal(tmp_path, p, "p001")

    updated = update_proposal_status(tmp_path, "p001", "已批准", note="测试批准")
    assert updated is not None
    assert updated.status == "已批准"
    assert updated.status_entered_at is not None
    assert len(updated.history) == 1
    assert updated.history[0]["from"] == "待审批"
    assert updated.history[0]["to"] == "已批准"


# ─────────────────────────────────────────────────────────────────────────────
# T31: can_auto_apply_memory
# ─────────────────────────────────────────────────────────────────────────────

def test_t31_can_auto_apply_memory(tmp_path):
    proposals_dir = tmp_path / "proposals"
    workspace_root = tmp_path / "workspace"

    p = _make_proposal(type="memory_update", initiator="pm")
    ok, reason = can_auto_apply_memory(p, proposals_dir, workspace_root)
    assert ok

    # 非 memory_update → False
    p2 = _make_proposal(type="sop_update")
    ok, reason = can_auto_apply_memory(p2, proposals_dir, workspace_root)
    assert not ok


# ─────────────────────────────────────────────────────────────────────────────
# T32: l2_task_callback
# ─────────────────────────────────────────────────────────────────────────────

def test_t32_l2_task_callback(tmp_path):
    from hooks.l2_task_callback import make_l2_task_callback

    logs_dir = tmp_path / "logs"
    cb = make_l2_task_callback("pm", logs_dir)

    class FakeOutput:
        task_id = "cb_test_001"
        description = "测试回调任务"
        duration_sec = 42.0
        error_type = None

    cb(FakeOutput())

    l2_dir = logs_dir / "l2_task"
    files = list(l2_dir.glob("pm_*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["agent_id"] == "pm"
    assert saved["result_quality"] == 0.75


# ─────────────────────────────────────────────────────────────────────────────
# T33: seed_logs 写入 session L3
# ─────────────────────────────────────────────────────────────────────────────

def test_t33_seed_logs_writes_session_l3(tmp_path):
    from seed_logs import seed_logs

    seed_logs(base_dir=tmp_path)

    sessions_dir = tmp_path / "pm" / "sessions"
    assert (sessions_dir / "index.jsonl").exists()
    assert (sessions_dir / "demo_m4l28_raw.jsonl").exists()

    entries = read_session_index(sessions_dir)
    assert len(entries) == 3

    task_ids = {e["task_id"] for e in entries}
    assert task_ids == {"t001", "t003", "t006"}


# ─────────────────────────────────────────────────────────────────────────────
# T34: send_mail project_id 字段
# ─────────────────────────────────────────────────────────────────────────────

def test_t34_send_mail_with_project_id(tmp_path):
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir()

    send_mail(mailbox_dir, to="pm", from_="manager",
              type_="task_assign", subject="test", content="test",
              project_id="proj_001")

    pm_inbox = mailbox_dir / "pm.json"
    messages = json.loads(pm_inbox.read_text())
    assert messages[0]["project_id"] == "proj_001"


def test_t34b_send_mail_without_project_id(tmp_path):
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir()

    send_mail(mailbox_dir, to="pm", from_="manager",
              type_="task_assign", subject="test", content="test")

    pm_inbox = mailbox_dir / "pm.json"
    messages = json.loads(pm_inbox.read_text())
    assert "project_id" not in messages[0]


# ─────────────────────────────────────────────────────────────────────────────
# T35: count_l2_since
# ─────────────────────────────────────────────────────────────────────────────

def test_t35_count_l2_since(tmp_path):
    # 写 3 条近期 + 1 条 48h 前
    for i in range(3):
        write_l2(tmp_path, "pm", f"recent_{i}", _make_l2_record(task_id=f"recent_{i}"))
    write_l2(tmp_path, "pm", "old", _make_l2_record(task_id="old", days_ago=3))

    assert count_l2_since(tmp_path, "pm", hours=24) == 3
    assert count_l2_since(tmp_path, "pm", hours=168) == 4
