"""
第28课：数字员工的自我进化 — 端到端演示脚本

在第27课四步任务链基础上，新增三层日志记录 + 两种复盘演示。
使用 DigitalWorkerCrew（v3），角色行为由 workspace/ 文件驱动。

【复用 m4l27 四步（DigitalWorkerCrew 驱动）】
  步骤1（Manager）：需求澄清 → 写 requirements.md → 通知 Human
  [人工确认节点1] 需求文档确认
  步骤2（Manager）：读SOP → 向 PM 发送 task_assign
  步骤3（PM）：读邮件 → 写产品文档 → 发 manager.json:task_done
  [人工确认节点2] 设计文档 Checkpoint
  步骤4（Manager）：验收产品文档

【第28课新增】
  [日志写入演示]     步骤3结束后写 PM 的 L2 日志；human.json 写入时自动写 L1
  [预置历史数据]     seed_logs() 预置7天模拟运行数据（含3次 checkpoint 退回）
  [L3 滚动清理]      purge_old_l3() 清理30天前的 L3 日志
  [自我复盘演示]     直接调用 run_self_retrospective()（不走 CrewAI）
  [团队复盘演示]     直接调用 run_team_retrospective()（不走 CrewAI）

核心教学点（对应第28课）：
  P2 三层日志：L1 自动写入（mailbox_ops 内置），L2 run.py 手动写
  P4 自我复盘：结构化 prompt + json_object 模式 + Pydantic 校验
  P5 团队复盘：聚合统计 + 识别瓶颈 + 触发下级复盘
  P7 反模式：最小样本量保护、L3 滚动清理

运行方式：
  python run.py
  python run.py "帮我设计一个宠物健康记录App"
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

_M4L28_DIR    = Path(__file__).resolve().parent
_PROJECT_ROOT = _M4L28_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from crewai.hooks import clear_before_llm_call_hooks   # noqa: E402
from shared.digital_worker import DigitalWorkerCrew     # noqa: E402

# DigitalWorkerCrew 加载了 crewai_mas_demo/tools（含 skill_loader_tool）。
# m4l28 自己的 tools/（log_ops、mailbox_ops）在同名子包下，需要替换模块缓存。
for _k in [k for k in sys.modules if k == "tools" or k.startswith("tools.")]:
    del sys.modules[_k]
sys.path.insert(0, str(_M4L28_DIR))

from tools.log_ops import write_l2, purge_old_l3        # noqa: E402
from tools.mailbox_ops import send_mail                 # noqa: E402

SHARED_DIR    = _M4L28_DIR / "workspace" / "shared"
MAILBOXES_DIR = SHARED_DIR / "mailboxes"
LOGS_DIR      = SHARED_DIR / "logs"
DESIGN_DIR    = SHARED_DIR / "design"

MANAGER_WORKSPACE = _M4L28_DIR / "workspace" / "manager"
PM_WORKSPACE      = _M4L28_DIR / "workspace" / "pm"
MANAGER_PORT      = 8027
PM_PORT           = 8028


# ─────────────────────────────────────────────────────────────────────────────
# 人工确认（复用 m4l27 逻辑）
# ─────────────────────────────────────────────────────────────────────────────

def wait_for_human(human_inbox: Path, expected_type: str, step_label: str) -> bool:
    lock_path = human_inbox.with_suffix(".lock")

    with FileLock(str(lock_path)):
        if not human_inbox.exists():
            human_inbox.write_text("[]", encoding="utf-8")
        messages = json.loads(human_inbox.read_text(encoding="utf-8"))

    target = next(
        (m for m in messages if m.get("type") == expected_type and not m.get("read", False)),
        None,
    )

    if target is None:
        print(f"\n[debug] human.json 中未找到未读的 '{expected_type}' 消息")
        print(f"[debug] 实际内容：{json.dumps(messages, ensure_ascii=False, indent=2)}")
        return False

    print(f"\n{'='*60}")
    print(f"  [人工确认节点] {step_label}")
    print(f"  来自：{target.get('from', 'manager')}")
    print(f"  主题：{target.get('subject', '')}")
    print(f"  内容：{target.get('content', '')[:300]}")
    print(f"{'='*60}")

    decision = input("  你的决定 (y/n)：").strip().lower()

    if decision == "y":
        with FileLock(str(lock_path)):
            messages = json.loads(human_inbox.read_text(encoding="utf-8"))
            for m in messages:
                if m.get("id") == target["id"]:
                    m["read"] = True
                    break
            human_inbox.write_text(
                json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(f"  已确认：{step_label}\n")
        return True
    else:
        print(f"  已拒绝：{step_label}，演示终止\n")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 步骤检查
# ─────────────────────────────────────────────────────────────────────────────

def check_requirements_exists() -> bool:
    return (SHARED_DIR / "needs" / "requirements.md").exists()


def check_pm_inbox_has_task_assign() -> bool:
    pm_inbox = MAILBOXES_DIR / "pm.json"
    if not pm_inbox.exists():
        return False
    return any(m.get("type") == "task_assign"
               for m in json.loads(pm_inbox.read_text(encoding="utf-8")))


def check_product_spec_exists() -> bool:
    return (DESIGN_DIR / "product_spec.md").exists()


def check_manager_inbox_has_task_done() -> bool:
    manager_inbox = MAILBOXES_DIR / "manager.json"
    if not manager_inbox.exists():
        return False
    return any(m.get("type") == "task_done"
               for m in json.loads(manager_inbox.read_text(encoding="utf-8")))


# ─────────────────────────────────────────────────────────────────────────────
# v3 Worker 工厂
# ─────────────────────────────────────────────────────────────────────────────

def _make_manager(session_id: str) -> DigitalWorkerCrew:
    return DigitalWorkerCrew(
        workspace_dir=MANAGER_WORKSPACE,
        sandbox_port=MANAGER_PORT,
        session_id=session_id,
        model="glm-5.1",
        has_shared=True,
    )


def _make_pm(session_id: str) -> DigitalWorkerCrew:
    return DigitalWorkerCrew(
        workspace_dir=PM_WORKSPACE,
        sandbox_port=PM_PORT,
        session_id=session_id,
        model="glm-5.1",
        has_shared=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 主演示流程
# ─────────────────────────────────────────────────────────────────────────────

def run_demo(initial_request: str = "") -> None:
    from seed_logs import seed_logs
    from retro.self_retrospective import run_self_retrospective
    from retro.team_retrospective import run_team_retrospective

    session_id = "demo_m4l28"
    if not initial_request:
        initial_request = input("请告诉 Manager 你要做什么：").strip()

    print(f"\n{'='*60}")
    print(f"  M4L28 数字员工的自我进化演示  |  session: {session_id}")
    print(f"{'='*60}\n")

    # ══════════════════════════════════════════════════════════════════════════
    # 【复用 m4l27 四步（v3 DigitalWorkerCrew 驱动）】
    # ══════════════════════════════════════════════════════════════════════════

    # 步骤1：Manager 需求澄清
    print("【步骤1】Manager 需求澄清中...\n")
    clear_before_llm_call_hooks()
    manager = _make_manager(session_id)
    result1 = manager.kickoff(
        f"你是团队的 Manager，收到了以下新项目需求：\n\n{initial_request}\n\n"
        "请按照你的工作规范（agent.md）完成：\n"
        "1. 初始化共享工作区（init_project Skill，包含 human 角色）\n"
        "2. 使用 requirements_discovery Skill 进行需求澄清，将结果写入 needs/requirements.md\n"
        "3. 使用 notify_human Skill 通知 Human 确认需求文档（type: needs_confirm）\n"
        "4. 完成本轮"
    )
    print(f"\n步骤1 输出：{result1[:200]}...\n")

    if not check_requirements_exists():
        print("步骤1未完成：requirements.md 未生成，终止运行")
        return

    if not wait_for_human(MAILBOXES_DIR / "human.json", "needs_confirm", "需求文档确认"):
        return

    # 步骤2：Manager 按SOP分配任务给PM
    print("【步骤2】Manager 按SOP分配任务给PM...\n")
    clear_before_llm_call_hooks()
    manager = _make_manager(session_id)
    manager.kickoff(
        "需求已确认，请选择 SOP 并分配任务给 PM。\n"
        "1. 读取 /mnt/shared/sop/ 下的 SOP 文件\n"
        "2. 通过 mailbox Skill 向 PM 发送 task_assign 邮件（路径引用，不复制内容）"
    )

    if not check_pm_inbox_has_task_assign():
        print("步骤2未完成：PM 邮箱中未找到 task_assign，终止运行")
        return
    print("步骤2检查通过：PM 邮箱已有任务分配邮件\n")

    # 步骤3：PM 撰写产品文档
    print("【步骤3】PM 撰写产品文档...\n")
    clear_before_llm_call_hooks()
    pm = _make_pm(session_id)
    pm.kickoff(
        "请检查你的邮箱。如果有新的任务邮件（task_assign），\n"
        "请按照你的工作规范（agent.md）完成任务。\n"
        "完成后通过邮箱通知 Manager（task_done）。"
    )

    if not check_product_spec_exists() or not check_manager_inbox_has_task_done():
        print("步骤3未完成：产品文档未生成或 Manager 未收到完成通知，终止运行")
        return
    print("步骤3检查通过：产品文档已生成\n")

    # ── 第28课新增：写入本次 PM 任务的 L2 日志 ────────────────────────────────
    task_id = f"live_{session_id}"
    write_l2(
        logs_dir = LOGS_DIR,
        agent_id = "pm",
        task_id  = task_id,
        record   = {
            "agent_id":       "pm",
            "task_id":        task_id,
            "task_desc":      "产品规格文档设计任务（步骤3）",
            "result_quality": 0.75,
            "duration_sec":   0,
            "error_type":     None,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        },
    )
    print("第28课：PM L2 日志已写入\n")

    # 人工确认节点2（send_mail 自动写 L1）
    send_mail(MAILBOXES_DIR, to="human", from_="manager",
              type_="checkpoint_request", subject="产品文档已完成，请确认后继续",
              content="产品文档路径：shared/design/product_spec.md")

    if not wait_for_human(MAILBOXES_DIR / "human.json", "checkpoint_request", "设计文档 Checkpoint"):
        return

    # 步骤4：Manager 验收
    print("【步骤4】Manager 验收中...\n")
    clear_before_llm_call_hooks()
    manager = _make_manager(session_id)
    manager.kickoff(
        "设计已确认，请审核产品文档。\n"
        "1. 读取 mailbox 中的 task_done 消息\n"
        "2. 读取 /mnt/shared/design/product_spec.md\n"
        "3. 对照 /mnt/shared/needs/requirements.md 进行验收\n"
        "4. 将验收报告写入 /workspace/review_result.md"
    )

    print(f"\n{'='*60}")
    print("  m4l27 四步任务链演示完成！")
    print(f"{'='*60}\n")

    # ══════════════════════════════════════════════════════════════════════════
    # 【第28课新增：日志 + 复盘演示】
    # ══════════════════════════════════════════════════════════════════════════

    print(f"\n{'='*60}")
    print("  第28课新增：预置历史日志 + 触发复盘")
    print(f"{'='*60}\n")

    # 清理 30 天前的 L3 日志（演示 L3 滚动清理）
    deleted = purge_old_l3(LOGS_DIR, retention_days=30)
    if deleted > 0:
        print(f"[清理] 已删除 {deleted} 条 30 天前的 L3 日志\n")

    # 预置 7 天历史数据
    print("预置历史日志（模拟团队已运行 7 天）...\n")
    seed_logs(base_dir=_M4L28_DIR / "workspace")

    # 自我复盘（直接调用 Python 函数，不走 CrewAI —— 复盘是"元操作"）
    print(f"\n{'─'*50}")
    print("  触发 PM Agent 自我复盘（直接 LLM 调用）")
    print(f"{'─'*50}\n")
    proposals = run_self_retrospective(
        agent_id    = "pm",
        logs_dir    = LOGS_DIR,
        mailbox_dir = MAILBOXES_DIR,
        days        = 7,
        min_tasks   = 5,
    )
    print(f"  PM 自我复盘完成，生成 {len(proposals)} 条提案\n")

    # 团队复盘（直接调用 Python 函数）
    print(f"\n{'─'*50}")
    print("  触发 Manager 团队复盘（直接 LLM 调用）")
    print(f"{'─'*50}\n")
    result = run_team_retrospective(
        manager_id  = "manager",
        agent_ids   = ["pm", "manager"],
        logs_dir    = LOGS_DIR,
        mailbox_dir = MAILBOXES_DIR,
        days        = 7,
    )
    print(f"  团队复盘完成，瓶颈 Agent：{result.get('bottleneck_agent', '无')}\n")

    print(f"\n{'='*60}")
    print("  第28课演示完成！")
    print(f"  查看以下文件了解完整闭环：")
    print(f"  - workspace/shared/logs/    （三层日志）")
    print(f"  - workspace/shared/proposals/proposals.json  （改进提案）")
    print(f"  - workspace/shared/mailboxes/human.json       （待审批队列+周报）")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    req = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""
    run_demo(req)
