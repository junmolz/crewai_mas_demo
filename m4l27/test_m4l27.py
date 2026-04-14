"""
第27课·Human as 甲方
test_m4l27.py — 单元测试 + 集成测试

单元测试（无需LLM，每次 CI 必跑）：
  T_unit_1_no_message_blocks     human.json 为空时 check 返回 False
  T_unit_2_pm_cannot_write_human PM 尝试直接写 human.json → raise ValueError
  T_unit_3_manager_can_write_human Manager 写 human.json → 消息写入成功
  T_unit_4_wait_marks_read       wait_for_human 找到消息后标记 read=True

集成测试（需要 LLM，标记 @needs_llm）：
  T_int_1_requirements_generated RequirementsDiscoveryCrew 运行后 requirements.md 存在
  T_int_2_task_assign_sent       ManagerAssignCrew 运行后 pm.json 有 task_assign
  T_int_3_product_spec_exists    PMExecuteCrew 运行后 product_spec.md 存在
  T_int_4_review_result_exists   ManagerReviewCrew 运行后 review_result.md 存在
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# ── 路径设置 ──────────────────────────────────────────────────────────────────
_M4L27_DIR    = Path(__file__).resolve().parent
_PROJECT_ROOT = _M4L27_DIR.parent
for _p in [str(_PROJECT_ROOT), str(_M4L27_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.mailbox_ops import send_mail, read_inbox  # noqa: E402

# 集成测试跳过条件
needs_llm = pytest.mark.skipif(
    not (os.getenv("ALIYUN_API_KEY") or os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")),
    reason="requires ALIYUN_API_KEY / QWEN_API_KEY / DASHSCOPE_API_KEY (LLM credentials)",
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_mailboxes(tmp_path: Path) -> Path:
    """返回一个临时的 mailboxes 目录，已初始化三个邮箱文件。"""
    mb = tmp_path / "mailboxes"
    mb.mkdir()
    for role in ("manager", "pm", "human"):
        (mb / f"{role}.json").write_text("[]", encoding="utf-8")
    return mb


# ─────────────────────────────────────────────────────────────────────────────
# 单元测试
# ─────────────────────────────────────────────────────────────────────────────

class TestHumanInboxEmpty:
    """T_unit_1: human.json 为空时，check 函数返回 False"""

    def test_empty_human_inbox_has_no_unread(self, tmp_mailboxes: Path) -> None:
        human_inbox = tmp_mailboxes / "human.json"
        messages = json.loads(human_inbox.read_text(encoding="utf-8"))
        unread = [m for m in messages if not m.get("read", False)]
        assert unread == [], "空 human.json 不应有未读消息"

    def test_no_matching_type_returns_empty(self, tmp_mailboxes: Path) -> None:
        """有消息但 type 不匹配时，也找不到目标消息"""
        send_mail(
            tmp_mailboxes,
            to="human",
            from_="manager",
            type_="other_type",
            subject="test",
            content="hello",
        )
        messages = json.loads((tmp_mailboxes / "human.json").read_text(encoding="utf-8"))
        matching = [m for m in messages if m.get("type") == "needs_confirm" and not m.get("read")]
        assert matching == []


class TestSinglePointOfContact:
    """T_unit_2: PM / Dev 等非 Manager 角色不得直接写 human.json"""

    def test_pm_cannot_write_human(self, tmp_mailboxes: Path) -> None:
        with pytest.raises(ValueError, match="单一接口约束"):
            send_mail(
                tmp_mailboxes,
                to="human",
                from_="pm",
                type_="checkpoint_request",
                subject="我想直接联系人",
                content="bypass manager",
            )

    def test_unknown_role_cannot_write_human(self, tmp_mailboxes: Path) -> None:
        with pytest.raises(ValueError):
            send_mail(
                tmp_mailboxes,
                to="human",
                from_="dev",
                type_="error_alert",
                subject="direct alert",
                content="error",
            )

    def test_manager_can_write_human(self, tmp_mailboxes: Path) -> None:
        """T_unit_3: Manager 写 human.json 成功"""
        msg_id = send_mail(
            tmp_mailboxes,
            to="human",
            from_="manager",
            type_="needs_confirm",
            subject="请确认需求文档",
            content="shared/needs/requirements.md",
        )
        messages = json.loads((tmp_mailboxes / "human.json").read_text(encoding="utf-8"))
        assert len(messages) == 1
        assert messages[0]["id"] == msg_id
        assert messages[0]["from"] == "manager"
        assert messages[0]["type"] == "needs_confirm"
        assert messages[0]["read"] is False


class TestWaitForHuman:
    """T_unit_4: wait_for_human 正确标记消息已读"""

    def test_wait_marks_message_read_on_confirm(self, tmp_mailboxes: Path) -> None:
        from m4l27_run import wait_for_human  # 延迟导入，实现后生效

        # 先发一条 needs_confirm 消息
        send_mail(
            tmp_mailboxes,
            to="human",
            from_="manager",
            type_="needs_confirm",
            subject="请确认需求文档",
            content="shared/needs/requirements.md",
        )

        human_inbox = tmp_mailboxes / "human.json"

        # 模拟用户输入 y
        with patch("builtins.input", return_value="y"):
            result = wait_for_human(human_inbox, expected_type="needs_confirm", step_label="需求确认")

        assert result is True
        messages = json.loads(human_inbox.read_text(encoding="utf-8"))
        assert messages[0]["read"] is True, "用户确认后消息应标记为已读"

    def test_wait_returns_false_on_reject(self, tmp_mailboxes: Path) -> None:
        from m4l27_run import wait_for_human

        send_mail(
            tmp_mailboxes,
            to="human",
            from_="manager",
            type_="needs_confirm",
            subject="请确认需求文档",
            content="shared/needs/requirements.md",
        )

        human_inbox = tmp_mailboxes / "human.json"

        with patch("builtins.input", return_value="n"):
            result = wait_for_human(human_inbox, expected_type="needs_confirm", step_label="需求确认")

        assert result is False
        messages = json.loads(human_inbox.read_text(encoding="utf-8"))
        assert messages[0]["read"] is False, "用户拒绝后消息不应标记已读"

    def test_wait_returns_false_when_no_message(self, tmp_mailboxes: Path) -> None:
        from m4l27_run import wait_for_human

        human_inbox = tmp_mailboxes / "human.json"
        # 不发任何消息
        with patch("builtins.input", return_value="y"):
            result = wait_for_human(human_inbox, expected_type="needs_confirm", step_label="需求确认")

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# 集成测试（需要 LLM）
# ─────────────────────────────────────────────────────────────────────────────

@needs_llm
class TestIntegrationRequirements:
    """T_int_1: RequirementsDiscoveryCrew 运行后 requirements.md 存在"""

    def test_requirements_file_created(self, clean_crewai_hooks) -> None:  # noqa: ARG002
        from m4l27_manager import RequirementsDiscoveryCrew
        from m4l27_manager import save_session as manager_save

        session_id = str(uuid.uuid4())
        crew = RequirementsDiscoveryCrew(session_id=session_id)
        crew.crew().kickoff(inputs={
            "user_request": "帮我把用户注册流程的产品设计做出来。注册支持邮箱方式，需要邮件验证，不需要社交登录。"
        })
        manager_save(crew, session_id)

        req_file = _M4L27_DIR / "workspace" / "shared" / "needs" / "requirements.md"
        assert req_file.exists(), "requirements.md 应该被写入"
        assert req_file.stat().st_size > 0, "requirements.md 不应为空"


@needs_llm
class TestIntegrationTaskAssign:
    """T_int_2: ManagerAssignCrew 运行后 pm.json 有 task_assign"""

    def test_task_assign_sent_to_pm(self, clean_crewai_hooks) -> None:  # noqa: ARG002
        from m4l27_manager import ManagerAssignCrew
        from m4l27_manager import save_session as manager_save

        # 前置：确保 requirements.md 存在（T_int_1 可能已生成）
        req_file = _M4L27_DIR / "workspace" / "shared" / "needs" / "requirements.md"
        if not req_file.exists():
            req_file.write_text(
                "# 需求文档\n## 目标\n用户注册流程\n## 边界\n支持邮箱注册+邮件验证\n"
                "## 约束\n无\n## 验收标准\n注册后可登录\n",
                encoding="utf-8",
            )
        # 重置 pm.json，防止上次测试残留消息干扰断言
        mailboxes = _M4L27_DIR / "workspace" / "shared" / "mailboxes"
        (mailboxes / "pm.json").write_text("[]", encoding="utf-8")

        session_id = str(uuid.uuid4())
        crew = ManagerAssignCrew(session_id=session_id)
        crew.crew().kickoff(inputs={
            "user_request": (
                "需求已确认：用户注册流程，邮箱注册+邮件验证，无社交登录。\n"
                "SOP 已确认：产品文档写入 /mnt/shared/design/product_spec.md，完成后通知 Manager。\n"
                "请立即使用 mailbox-ops skill 向 PM 发送任务分配邮件：\n"
                "  type=task_assign, subject=产品文档设计任务, "
                "content=请根据需求（邮箱注册+邮件验证）撰写产品规格文档，"
                "写入/mnt/shared/design/product_spec.md，完成后发邮件通知我验收。"
            )
        })
        manager_save(crew, session_id)

        pm_inbox = json.loads((mailboxes / "pm.json").read_text(encoding="utf-8"))
        types = [m["type"] for m in pm_inbox]
        assert "task_assign" in types, f"pm.json 应有 task_assign，实际：{types}"


@needs_llm
class TestIntegrationProductSpec:
    """T_int_3: PMExecuteCrew 运行后 product_spec.md 存在"""

    def test_product_spec_created(self, clean_crewai_hooks) -> None:  # noqa: ARG002
        from m4l27_pm import PMExecuteCrew
        from m4l27_pm import save_session as pm_save

        # 前置：确保 pm.json 有 task_assign（T_int_2 可能已生成）
        mailboxes = _M4L27_DIR / "workspace" / "shared" / "mailboxes"
        pm_inbox_raw = (mailboxes / "pm.json").read_text(encoding="utf-8")
        if '"task_assign"' not in pm_inbox_raw:
            (mailboxes / "pm.json").write_text(
                '[{"id":"stub-001","from":"manager","to":"pm","type":"task_assign",'
                '"subject":"产品文档设计任务","content":"请根据 /mnt/shared/needs/requirements.md 设计产品规格文档","timestamp":"2026-01-01T00:00:00+00:00","read":false}]',
                encoding="utf-8",
            )

        session_id = str(uuid.uuid4())
        crew = PMExecuteCrew(session_id=session_id)
        crew.crew().kickoff(inputs={
            "user_request": "请读取邮箱中的任务，根据需求文档撰写产品规格文档，完成后通知Manager"
        })
        pm_save(crew, session_id)

        spec_file = _M4L27_DIR / "workspace" / "shared" / "design" / "product_spec.md"
        assert spec_file.exists(), "product_spec.md 应该被写入"
        assert spec_file.stat().st_size > 0


@needs_llm
class TestIntegrationReviewResult:
    """T_int_4: ManagerReviewCrew 运行后 review_result.md 存在"""

    def test_review_result_created(self, clean_crewai_hooks) -> None:  # noqa: ARG002
        from m4l27_manager import ManagerReviewCrew
        from m4l27_manager import save_session as manager_save

        # 前置：确保 manager.json 有 task_done（T_int_3 可能已生成）
        mailboxes = _M4L27_DIR / "workspace" / "shared" / "mailboxes"
        mgr_inbox_raw = (mailboxes / "manager.json").read_text(encoding="utf-8")
        if '"task_done"' not in mgr_inbox_raw:
            (mailboxes / "manager.json").write_text(
                '[{"id":"stub-002","from":"pm","to":"manager","type":"task_done",'
                '"subject":"产品文档已完成","content":"product_spec.md 已写入 /mnt/shared/design/product_spec.md","timestamp":"2026-01-01T00:00:00+00:00","read":false}]',
                encoding="utf-8",
            )

        session_id = str(uuid.uuid4())
        crew = ManagerReviewCrew(session_id=session_id)
        crew.crew().kickoff(inputs={
            "user_request": "请读取邮箱中的完成通知，验收产品文档并保存验收结论"
        })
        manager_save(crew, session_id)

        review_file = _M4L27_DIR / "workspace" / "manager" / "review_result.md"
        assert review_file.exists(), "review_result.md 应该被写入"
