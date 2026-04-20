"""
第28课·数字员工的自我进化（v6）
test_m4l28_integration.py — 集成测试

运行条件：需要 ALIYUN_API_KEY 环境变量 + Docker 沙盒。
在 CI 中通过 pytest -m integration 运行；本地单测默认跳过。

标记：@pytest.mark.integration

集成测试关注（v6 架构 — 复盘即 Skill，不再直接调 LLM）：
  IT1  seed_logs → scheduler.tick() → 双条件满足 → 发 retro_trigger 邮件
  IT2  seed_logs L2 统计 → PM avg_quality < Manager（瓶颈识别基础）
  IT3  proposal_ops 全生命周期（write → update_status → read → verify history）
  IT4  run_validation.check() 对 seed_logs 数据执行 ValidationCheck
  IT5  run_validation.scan_stuck() 检测 48h 僵尸态提案
  IT6  DigitalWorkerCrew Manager 需求澄清（真实 LLM + 真实沙盒）
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from schemas import RetroProposal, ValidationCheck
from tools.log_ops import read_l2, count_l2_since
from tools.mailbox_ops import send_mail
from tools.proposal_ops import (
    write_proposal,
    read_proposal,
    update_proposal_status,
    list_proposals,
)

# ─────────────────────────────────────────────────────────────────────────────
# Marker + Skip 条件
# ─────────────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.integration

_SKIP_REASON = "需要 ALIYUN_API_KEY 环境变量"
_SKIP_SANDBOX = "需要 Docker 沙盒（localhost:8027）"


def _require_api_key() -> None:
    if not os.environ.get("ALIYUN_API_KEY"):
        pytest.skip(_SKIP_REASON)


def _require_sandbox() -> None:
    _require_api_key()
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:8027/", timeout=3)
    except Exception:
        pytest.skip(_SKIP_SANDBOX)


# ─────────────────────────────────────────────────────────────────────────────
# 共享 Fixture：预置7天历史日志
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def seeded_workspace(tmp_path):
    from seed_logs import seed_logs

    seed_logs(base_dir=tmp_path)

    logs_dir = tmp_path / "shared" / "logs"
    mailbox_dir = tmp_path / "shared" / "mailboxes"
    mailbox_dir.mkdir(parents=True, exist_ok=True)

    return tmp_path, logs_dir, mailbox_dir


# ─────────────────────────────────────────────────────────────────────────────
# IT1: seed_logs → scheduler.tick() → 发 retro_trigger 邮件
# ─────────────────────────────────────────────────────────────────────────────

def test_it1_scheduler_tick_triggers_retro(seeded_workspace):
    """
    seed_logs 预置的 L2 时间跨度为 1-6 天前，不在 24h 窗口内。
    额外写入 5 条当日 L2，让 scheduler 双条件满足后触发 retro_trigger。
    """
    from scheduler import tick
    from tools.log_ops import write_l2

    base_dir, logs_dir, mailbox_dir = seeded_workspace
    state_file = base_dir / ".last_retro.json"

    now = datetime.now(timezone.utc)
    for i in range(5):
        ts = now - timedelta(hours=i)
        write_l2(logs_dir, "pm", f"today_{i}", {
            "agent_id": "pm", "task_id": f"today_{i}",
            "task_desc": f"当日任务 {i}", "result_quality": 0.8,
            "duration_sec": 100, "error_type": None,
            "timestamp": ts.isoformat(),
        })

    triggered = tick(logs_dir=logs_dir, mailbox_dir=mailbox_dir, state_file=state_file)
    assert "pm" in triggered, "PM 有 5 条当日 L2，应触发复盘"

    pm_inbox = mailbox_dir / "pm.json"
    assert pm_inbox.exists()
    messages = json.loads(pm_inbox.read_text())
    retro_msgs = [m for m in messages if m.get("type") == "retro_trigger"]
    assert len(retro_msgs) >= 1, "PM 邮箱应收到 retro_trigger 邮件"

    state = json.loads(state_file.read_text())
    assert "pm" in state, "scheduler state 应记录 pm 的上次复盘时间"


# ─────────────────────────────────────────────────────────────────────────────
# IT2: seed_logs L2 统计 → 瓶颈识别基础数据验证
# ─────────────────────────────────────────────────────────────────────────────

def test_it2_seeded_data_bottleneck_stats(seeded_workspace):
    """
    验证 seed_logs 预置数据的统计特征：
      - PM: 8条任务，3条低质量（< 0.5），avg_quality 应明显低于 Manager
      - Manager: 3条任务，全部正常质量
    这是团队复盘瓶颈识别的数据基础。
    """
    _, logs_dir, _ = seeded_workspace

    pm_records = read_l2(logs_dir, "pm", days=7)
    manager_records = read_l2(logs_dir, "manager", days=7)

    assert len(pm_records) == 8
    assert len(manager_records) == 3

    pm_qualities = [r["result_quality"] for r in pm_records]
    manager_qualities = [r["result_quality"] for r in manager_records]

    pm_avg = sum(pm_qualities) / len(pm_qualities)
    manager_avg = sum(manager_qualities) / len(manager_qualities)

    assert pm_avg < manager_avg, (
        f"PM avg_quality({pm_avg:.3f}) 应 < Manager({manager_avg:.3f})"
    )

    pm_failures = [q for q in pm_qualities if q < 0.5]
    assert len(pm_failures) == 3, "PM 应有 3 条低质量任务（< 0.5）"

    pm_errors = [r for r in pm_records if r.get("error_type") == "checkpoint_rejected"]
    assert len(pm_errors) == 3


# ─────────────────────────────────────────────────────────────────────────────
# IT3: proposal_ops 全生命周期
# ─────────────────────────────────────────────────────────────────────────────

def test_it3_proposal_lifecycle(tmp_path):
    """
    测试提案从创建到落地的完整状态机：
      待审批 → 已批准 → 已实施 → 验证中 → 已验证
    """
    proposals_dir = tmp_path / "proposals"

    proposal = RetroProposal(
        type="sop_update",
        target="workspace/pm/skills/product_design/SKILL.md",
        root_cause="prompt_ambiguity",
        current="缺少移动端适配检查",
        proposed="新增移动端适配检查步骤",
        expected_metric="avg_quality >= 0.8",
        rollback_plan="还原 SKILL.md 到上一版本",
        evidence=["l1_001", "l1_002"],
        priority="medium",
        initiator="pm",
    )

    write_proposal(proposals_dir, proposal, "p001")

    loaded = read_proposal(proposals_dir, "p001")
    assert loaded is not None
    assert loaded.status == "待审批"

    for new_status, note in [
        ("已批准", "Manager 审批通过"),
        ("已实施", "补丁已应用"),
        ("验证中", "开始验证"),
        ("已验证", "指标达标"),
    ]:
        updated = update_proposal_status(proposals_dir, "p001", new_status, note=note)
        assert updated.status == new_status

    final = read_proposal(proposals_dir, "p001")
    assert final.status == "已验证"
    assert len(final.history) == 4
    assert final.history[0]["from"] == "待审批"
    assert final.history[0]["to"] == "已批准"
    assert final.history[-1]["to"] == "已验证"


# ─────────────────────────────────────────────────────────────────────────────
# IT4: run_validation.check() 对 seed_logs 执行 ValidationCheck
# ─────────────────────────────────────────────────────────────────────────────

def test_it4_validation_check_with_seeded_data(seeded_workspace):
    """
    用 stats_l2 脚本检查 PM 的平均质量。
    seed_logs 数据中 PM avg_quality ≈ 0.68，应 < 0.8（不达标）。
    """
    from run_validation import check

    _, logs_dir, _ = seeded_workspace
    sessions_dir = logs_dir.parent.parent / "pm" / "sessions"

    vc = ValidationCheck(
        script="stats_l2",
        args={"agent_id": "pm", "days": 7},
        metric="avg_quality",
        op=">=",
        threshold=0.8,
    )

    passed, actual_value = check(vc, logs_dir, sessions_dir)
    assert not passed, f"PM avg_quality({actual_value}) 应 < 0.8（seed_logs 中有低质量任务）"

    vc_low = ValidationCheck(
        script="stats_l2",
        args={"agent_id": "pm", "days": 7},
        metric="avg_quality",
        op=">=",
        threshold=0.5,
    )
    passed_low, _ = check(vc_low, logs_dir, sessions_dir)
    assert passed_low, "PM avg_quality 应 >= 0.5"


# ─────────────────────────────────────────────────────────────────────────────
# IT5: run_validation.scan_stuck() 48h 僵尸态检测
# ─────────────────────────────────────────────────────────────────────────────

def test_it5_scan_stuck_detects_zombie(tmp_path):
    """
    创建一个 48h 前进入"已批准"的提案，scan_stuck 应检测并发 retro_stuck 邮件。
    """
    from run_validation import scan_stuck

    proposals_dir = tmp_path / "proposals"
    mailbox_dir = tmp_path / "mailboxes"
    mailbox_dir.mkdir(parents=True)

    old_ts = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()

    proposal = RetroProposal(
        type="sop_update",
        target="some/file.md",
        root_cause="prompt_ambiguity",
        current="问题",
        proposed="方案",
        expected_metric="metric >= 0.8",
        rollback_plan="回滚",
        evidence=["e1"],
        priority="medium",
        initiator="pm",
        status="已批准",
        status_entered_at=old_ts,
    )

    write_proposal(proposals_dir, proposal, "stuck_001")

    stuck_count = scan_stuck(proposals_dir, mailbox_dir)
    assert stuck_count >= 1, "应检测到至少1个僵尸态提案"

    manager_inbox = mailbox_dir / "manager.json"
    if manager_inbox.exists():
        messages = json.loads(manager_inbox.read_text())
        stuck_msgs = [m for m in messages if m.get("type") == "retro_stuck"]
        assert len(stuck_msgs) >= 1, "应发 retro_stuck 邮件给 manager"


# ─────────────────────────────────────────────────────────────────────────────
# IT6: DigitalWorkerCrew Manager 需求澄清（真实 LLM + 真实沙盒）
# ─────────────────────────────────────────────────────────────────────────────

def test_it6_manager_requirements_clarification(clean_crewai_hooks):
    """
    使用真实 LLM + 真实 Docker 沙盒，验证 Manager 能完成需求澄清。
    检查：requirements.md 已生成，human.json 收到 needs_confirm 邮件。
    """
    _require_sandbox()

    import sys
    m4l28_dir = Path(__file__).resolve().parent
    project_root = m4l28_dir.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from shared.digital_worker import DigitalWorkerCrew

    manager_workspace = m4l28_dir / "workspace" / "manager"
    shared_dir = m4l28_dir / "workspace" / "shared"
    mailboxes_dir = shared_dir / "mailboxes"

    for f in mailboxes_dir.glob("*.json"):
        f.write_text("[]", encoding="utf-8")

    for p in [shared_dir / "needs", shared_dir / "design"]:
        if p.exists():
            for f in p.glob("*"):
                f.unlink()

    manager = DigitalWorkerCrew(
        workspace_dir=manager_workspace,
        sandbox_port=8027,
        session_id="it6_test",
        model="glm-5.1",
        has_shared=True,
    )

    result = manager.kickoff(
        "你是团队的 Manager，收到了以下新项目需求：\n\n"
        "帮我设计一个宠物健康记录App\n\n"
        "请按照你的工作规范（agent.md）完成：\n"
        "1. 初始化共享工作区（init_project Skill，包含 human 角色）\n"
        "2. 使用 requirements_discovery Skill 进行需求澄清\n"
        "3. 通知 Human 确认需求文档（type: needs_confirm）\n"
        "4. 完成本轮"
    )

    assert result, "Manager 应返回非空结果"

    req_file = shared_dir / "needs" / "requirements.md"
    assert req_file.exists(), "requirements.md 应已生成"

    human_inbox = mailboxes_dir / "human.json"
    messages = json.loads(human_inbox.read_text(encoding="utf-8"))
    confirm_msgs = [m for m in messages if m.get("type") == "needs_confirm"]
    assert len(confirm_msgs) >= 1, "human.json 应收到 needs_confirm 邮件"
