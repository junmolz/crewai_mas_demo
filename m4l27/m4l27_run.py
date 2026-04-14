"""
课程：27｜Human as 甲方
示例文件：m4l27_run.py

演示：4步任务链 + 2个人工确认节点
  步骤1（Manager）：需求澄清 → 写 requirements.md
  [人工确认节点1] run.py 以 manager 身份写 human.json:needs_confirm → 等待用户确认
  步骤2（Manager）：读SOP → 向 PM 发送 task_assign
  步骤3（PM）：读邮件 → 写产品文档 → 发 manager.json:task_done
  [人工确认节点2] run.py 以 manager 身份写 human.json:checkpoint_request → 等待用户确认
  步骤4（Manager）：读邮件 → 验收产品文档 → 保存验收结论

核心教学点（对应第27课）：
  - 单一接口原则：human.json 只由 run.py（以 manager 身份）写入，LLM Agent 不直接接触
  - 人工确认节点：run.py 控制时机，不由 LLM 决定何时打扰人
  - wait_for_human()：用 FileLock 读 human.json，模拟异步人机交互
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from filelock import FileLock

# ── 路径设置 ──────────────────────────────────────────────────────────────────
_M4L27_DIR    = Path(__file__).resolve().parent
_PROJECT_ROOT = _M4L27_DIR.parent
for _p in [str(_PROJECT_ROOT), str(_M4L27_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crewai.hooks import clear_before_llm_call_hooks  # noqa: E402
from tools.mailbox_ops import send_mail                # noqa: E402

SHARED_DIR    = _M4L27_DIR / "workspace" / "shared"
MAILBOXES_DIR = SHARED_DIR / "mailboxes"
DESIGN_DIR    = SHARED_DIR / "design"


# ─────────────────────────────────────────────────────────────────────────────
# 人工确认核心函数
# ─────────────────────────────────────────────────────────────────────────────

def wait_for_human(
    human_inbox: Path,
    expected_type: str,
    step_label: str,
) -> bool:
    """
    等待人类确认 human.json 中的特定类型消息。

    1. 用 FileLock 读取 human.json，找到未读的 expected_type 消息
    2. 打印消息 subject + content
    3. input("你的决定 (y/n)：")
    4. y → FileLock 内标记该消息 read=True，返回 True
    5. 其他 → 打印实际内容（debug），返回 False

    Args:
        human_inbox:   human.json 的完整路径
        expected_type: 期望的消息类型（"needs_confirm" | "checkpoint_request"）
        step_label:    打印标签，如"需求确认"

    Returns:
        True 表示用户确认，False 表示拒绝或消息不存在
    """
    lock_path = human_inbox.with_suffix(".lock")

    # ── 步骤1：加锁读取消息（读完立即释放锁）────────────────────────────────
    with FileLock(str(lock_path)):
        if not human_inbox.exists():
            human_inbox.write_text("[]", encoding="utf-8")
        messages = json.loads(human_inbox.read_text(encoding="utf-8"))

    target = next(
        (m for m in messages if m.get("type") == expected_type and not m.get("read", False)),
        None,
    )

    if target is None:
        print(f"\n[debug] ⚠️  human.json 中未找到未读的 '{expected_type}' 消息")
        print(f"[debug] 实际内容：{json.dumps(messages, ensure_ascii=False, indent=2)}")
        return False

    # ── 步骤2：打印消息，等待用户输入（锁已释放）────────────────────────────
    print(f"\n{'='*60}")
    print(f"  ⏸️  [人工确认节点] {step_label}")
    print(f"  来自：{target.get('from', 'manager')}")
    print(f"  主题：{target.get('subject', '')}")
    print(f"  内容：{target.get('content', '')[:300]}")  # 截断避免LLM原始输出太长
    print(f"{'='*60}")

    decision = input("  你的决定 (y/n)：").strip().lower()

    # ── 步骤3：加锁写回已读状态（与读取分开，input()期间不持锁）─────────────
    if decision == "y":
        with FileLock(str(lock_path)):
            # 重新读取以获取最新状态（TOCTOU 窗口可接受，单进程 demo）
            messages = json.loads(human_inbox.read_text(encoding="utf-8"))
            for m in messages:
                if m.get("id") == target["id"]:
                    m["read"] = True
                    break
            human_inbox.write_text(
                json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(f"  ✅ 已确认：{step_label}\n")
        return True
    else:
        print(f"  ❌ 已拒绝：{step_label}，演示终止\n")
        print("  提示：在真实系统中，拒绝会重新触发对应阶段；本 demo 直接退出。\n")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤间结构检查
# ─────────────────────────────────────────────────────────────────────────────

def check_requirements_exists() -> bool:
    return (SHARED_DIR / "needs" / "requirements.md").exists()


def check_pm_inbox_has_task_assign() -> bool:
    pm_inbox = MAILBOXES_DIR / "pm.json"
    if not pm_inbox.exists():
        return False
    messages = json.loads(pm_inbox.read_text(encoding="utf-8"))
    return any(m.get("type") == "task_assign" for m in messages)


def check_product_spec_exists() -> bool:
    return (DESIGN_DIR / "product_spec.md").exists()


def check_manager_inbox_has_task_done() -> bool:
    manager_inbox = MAILBOXES_DIR / "manager.json"
    if not manager_inbox.exists():
        return False
    messages = json.loads(manager_inbox.read_text(encoding="utf-8"))
    return any(m.get("type") == "task_done" for m in messages)


def check_human_confirmed(expected_type: str) -> bool:
    """检查 human.json 中是否有已读的 expected_type 消息（确认标志）"""
    human_inbox = MAILBOXES_DIR / "human.json"
    lock_path   = human_inbox.with_suffix(".lock")
    if not human_inbox.exists():
        return False
    with FileLock(str(lock_path)):
        messages = json.loads(human_inbox.read_text(encoding="utf-8"))
    return any(
        m.get("type") == expected_type and m.get("read", False)
        for m in messages
    )


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────

def run_demo(initial_request: str = "") -> None:
    from m4l27_manager import (  # 延迟导入，避免在测试中加载 CrewAI
        RequirementsDiscoveryCrew,
        ManagerAssignCrew,
        ManagerReviewCrew,
        save_session as manager_save,
    )
    from m4l27_pm import PMExecuteCrew, save_session as pm_save

    session_id = str(uuid.uuid4())
    if not initial_request:
        initial_request = input("请告诉 Manager 你要做什么：").strip()

    print(f"\n{'='*60}")
    print(f"  M4L27 Human as 甲方演示  |  session: {session_id[:8]}...")
    print(f"{'='*60}\n")

    # ── 步骤1：Manager 需求澄清 ────────────────────────────────────────────
    print("【步骤1】Manager 需求澄清中...（RequirementsDiscoveryCrew）\n")
    clear_before_llm_call_hooks()          # 清除上轮残留的全局 hook，防止重复触发
    req_crew = RequirementsDiscoveryCrew(session_id=session_id)
    result1 = req_crew.crew().kickoff(inputs={"user_request": initial_request})
    manager_save(req_crew, session_id)
    result1_text = getattr(result1, "raw", str(result1))
    print(f"\n步骤1 输出：{result1_text[:200]}...\n")

    if not check_requirements_exists():
        print("⚠️  步骤1未完成：requirements.md 未生成，终止运行")
        return

    # ── 人工确认节点1：需求文档确认 ───────────────────────────────────────
    # run.py（编排者）以 manager 身份写 human.json，而非 LLM Agent 直接写
    send_mail(
        MAILBOXES_DIR,
        to="human",
        from_="manager",
        type_="needs_confirm",
        subject="需求文档已整理完毕，请确认",
        content="需求文档路径：shared/needs/requirements.md（已整理完毕，请打开确认后继续）",
    )

    confirmed1 = wait_for_human(
        MAILBOXES_DIR / "human.json",
        expected_type="needs_confirm",
        step_label="需求文档确认",
    )
    if not confirmed1:
        return

    # ── 步骤2：Manager 分配任务 ────────────────────────────────────────────
    print("【步骤2】Manager 按SOP分配任务给PM...（ManagerAssignCrew）\n")
    clear_before_llm_call_hooks()
    assign_crew = ManagerAssignCrew(session_id=session_id)
    result2 = assign_crew.crew().kickoff(inputs={
        "user_request": "请读取需求文档和产品设计SOP，向PM发送产品文档设计任务"
    })
    manager_save(assign_crew, session_id)
    print(f"\n步骤2 输出：{result2}\n")

    if not check_pm_inbox_has_task_assign():
        print("⚠️  步骤2未完成：PM 邮箱中未找到 task_assign，终止运行")
        return
    print("✅ 步骤2检查通过：PM 邮箱已有任务分配邮件\n")

    # ── 步骤3：PM 执行任务 ─────────────────────────────────────────────────
    print("【步骤3】PM 撰写产品文档...（PMExecuteCrew）\n")
    clear_before_llm_call_hooks()
    pm_crew = PMExecuteCrew(session_id=session_id)
    result3 = pm_crew.crew().kickoff(inputs={
        "user_request": "请读取邮箱中的任务，根据需求文档撰写产品规格文档，完成后通知Manager"
    })
    pm_save(pm_crew, session_id)
    print(f"\n步骤3 输出：{result3}\n")

    if not check_product_spec_exists():
        print("⚠️  步骤3未完成：产品文档未生成，终止运行")
        return
    if not check_manager_inbox_has_task_done():
        print("⚠️  步骤3未完成：Manager 邮箱中未找到 task_done，终止运行")
        return
    print("✅ 步骤3检查通过：产品文档已生成，Manager 收到完成通知\n")

    # ── 人工确认节点2：设计文档 Checkpoint ────────────────────────────────
    # 单一接口原则：PM 只发给 Manager，由 run.py（Manager 身份）转告人类
    send_mail(
        MAILBOXES_DIR,
        to="human",
        from_="manager",
        type_="checkpoint_request",
        subject="产品文档已完成，请确认后继续",
        content="产品文档路径：shared/design/product_spec.md（请打开查阅后确认）",
    )

    confirmed2 = wait_for_human(
        MAILBOXES_DIR / "human.json",
        expected_type="checkpoint_request",
        step_label="设计文档 Checkpoint",
    )
    if not confirmed2:
        return

    # ── 步骤4：Manager 验收 ────────────────────────────────────────────────
    print("【步骤4】Manager 验收中...（ManagerReviewCrew）\n")
    clear_before_llm_call_hooks()
    review_crew = ManagerReviewCrew(session_id=session_id)
    result4 = review_crew.crew().kickoff(inputs={
        "user_request": "请读取邮箱中的完成通知，验收产品文档并保存验收结论"
    })
    manager_save(review_crew, session_id)
    print(f"\n步骤4 输出：{result4}\n")

    print(f"\n{'='*60}")
    print("  ✅ 演示完成！")
    print(f"  产品文档：workspace/shared/design/product_spec.md")
    print(f"  验收结论：workspace/manager/review_result.md")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_demo()
