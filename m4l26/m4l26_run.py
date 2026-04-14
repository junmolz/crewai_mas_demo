"""
课程：26｜任务链与信息传递
示例文件：m4l26_run.py

演示：四步任务链的完整编排
  步骤0（Manager）：初始化共享工作区（create_workspace）——新增
  步骤1（Manager）：读取需求 → 向 PM 发邮件分配任务
  步骤2（PM）：读取邮件 → 读取需求 → 写产品文档 → 发完成通知
  步骤3（Manager）：读取 PM 回邮 → 验收产品文档 → 保存验收结论

核心教学点：
  P4：Manager 是工作区的制定者——步骤0 中 Manager 建立协作基础设施
  P7：三态状态机——每步 Crew 成功后由编排器调用 mark_done_all_in_progress 确认
      unread → in_progress（Crew 内的 read_inbox 工具原子完成）
      in_progress → done（Crew 成功后编排器在此处确认）
      若 Crew 崩溃，消息停在 in_progress，watchdog 可通过 reset_stale 恢复
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

# ── 路径设置 ──────────────────────────────────────────────────────────────────
_M4L26_DIR    = Path(__file__).resolve().parent
_PROJECT_ROOT = _M4L26_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_M4L26_DIR) not in sys.path:
    sys.path.insert(0, str(_M4L26_DIR))

from m4l26_manager import ManagerAssignCrew, ManagerReviewCrew  # noqa: E402
from m4l26_manager import save_session as manager_save          # noqa: E402
from m4l26_pm import PMExecuteCrew                              # noqa: E402
from m4l26_pm import save_session as pm_save                    # noqa: E402

from m4l26_mailbox.workspace_ops import create_workspace        # noqa: E402
from m4l26_mailbox.mailbox_ops import mark_done_all_in_progress # noqa: E402

SHARED_DIR    = _M4L26_DIR / "workspace" / "shared"
MAILBOXES_DIR = SHARED_DIR / "mailboxes"
DESIGN_DIR    = SHARED_DIR / "design"
DEMO_INPUT    = _M4L26_DIR / "demo_input" / "project_requirement.md"


# ─────────────────────────────────────────────────────────────────────────────
# 步骤间结构检查
# ─────────────────────────────────────────────────────────────────────────────
# 检查函数直接读 JSON 文件（不用 FileLock），因为：
# - 检查在对应步骤 Crew 结束之后执行（顺序、非并发）
# - 只做只读确认，不修改状态
# 注意：检查 type 字段，与消息 status 无关——所有状态的消息均可被检查到。

def check_pm_inbox_has_task_assign() -> bool:
    """检查 PM 邮箱是否有 task_assign 类型的消息（步骤1完成标志）"""
    pm_inbox = MAILBOXES_DIR / "pm.json"
    if not pm_inbox.exists():
        return False
    messages = json.loads(pm_inbox.read_text(encoding="utf-8"))
    return any(m.get("type") == "task_assign" for m in messages)


def check_product_spec_exists() -> bool:
    """检查产品文档是否已写入（步骤2完成标志）"""
    return (DESIGN_DIR / "product_spec.md").exists()


def check_manager_inbox_has_task_done() -> bool:
    """检查 Manager 邮箱是否有 task_done 类型的消息（步骤2完成标志）"""
    manager_inbox = MAILBOXES_DIR / "manager.json"
    if not manager_inbox.exists():
        return False
    messages = json.loads(manager_inbox.read_text(encoding="utf-8"))
    return any(m.get("type") == "task_done" for m in messages)


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────

def run_demo() -> None:
    session_id = str(uuid.uuid4())
    print(f"\n{'='*60}")
    print(f"  M4L26 任务链演示  |  session_id: {session_id[:8]}...")
    print(f"{'='*60}\n")

    # ── 步骤0：初始化共享工作区（Manager 职责）────────────────────────────
    print("【步骤0】Manager：初始化共享工作区\n")
    result0 = create_workspace(
        shared_dir=SHARED_DIR,
        roles=["manager", "pm"],
        project_name="XiaoPaw 宠物健康记录",
    )
    # 将演示需求文件复制进工作区（幂等：已存在时跳过覆盖）
    req_dst = SHARED_DIR / "needs" / "requirements.md"
    if not req_dst.exists() and DEMO_INPUT.exists():
        shutil.copy2(DEMO_INPUT, req_dst)
        print(f"  ↳ 需求文件已复制：demo_input/project_requirement.md → needs/requirements.md")
    print(f"  ↳ 新建目录：{result0['created_dirs'] or '（全部已存在）'}")
    print(f"  ↳ 新建文件：{result0['created_files'] or '（全部已存在）'}")
    print(f"  ↳ 跳过文件：{result0['skipped_files']}\n")
    print("✅ 步骤0完成：共享工作区已就绪\n")

    # ── 步骤1：Manager 分配任务 ────────────────────────────────────────────
    print("【步骤1】Manager：读取需求 → 向 PM 发送任务分配邮件\n")
    assign_crew = ManagerAssignCrew(session_id=session_id)
    result1 = assign_crew.crew().kickoff(
        inputs={"user_request": "请读取共享需求文档，向 PM 发送产品文档设计任务"}
    )
    manager_save(assign_crew, session_id)
    print(f"\n步骤1 输出：{result1}\n")

    if not check_pm_inbox_has_task_assign():
        print("⚠️  步骤1未完成：PM 邮箱中未找到 task_assign 邮件，终止运行")
        return
    print("✅ 步骤1检查通过：PM 邮箱已有任务分配邮件\n")

    # ── 步骤2：PM 执行任务 ─────────────────────────────────────────────────
    print("【步骤2】PM：读取邮件 → 读取需求 → 写产品文档 → 通知 Manager\n")
    pm_crew = PMExecuteCrew(session_id=session_id)
    result2 = pm_crew.crew().kickoff(
        inputs={"user_request": "请读取邮箱中的任务，根据需求文档撰写产品规格文档，完成后通知 Manager"}
    )
    pm_save(pm_crew, session_id)
    print(f"\n步骤2 输出：{result2}\n")

    if not check_product_spec_exists():
        print("⚠️  步骤2未完成：产品文档未生成，终止运行")
        return
    if not check_manager_inbox_has_task_done():
        print("⚠️  步骤2未完成：Manager 邮箱中未找到 task_done 邮件，终止运行")
        return

    # PM Crew 成功——将 PM 邮箱中的 in_progress 消息标记为 done（三态确认）
    done_count = mark_done_all_in_progress(MAILBOXES_DIR, "pm")
    print(f"✅ 步骤2检查通过：产品文档已生成，Manager 邮箱已有完成通知")
    print(f"   三态确认：PM 邮箱 {done_count} 条消息 in_progress → done\n")

    # ── 步骤3：Manager 验收 ────────────────────────────────────────────────
    print("【步骤3】Manager：读取完成通知 → 验收产品文档 → 保存验收结论\n")
    review_crew = ManagerReviewCrew(session_id=session_id)
    result3 = review_crew.crew().kickoff(
        inputs={"user_request": "请读取邮箱中的完成通知，验收产品文档并保存验收结论"}
    )
    manager_save(review_crew, session_id)
    print(f"\n步骤3 输出：{result3}\n")

    # Manager Crew 成功——将 Manager 邮箱中的 in_progress 消息标记为 done
    done_count = mark_done_all_in_progress(MAILBOXES_DIR, "manager")
    print(f"   三态确认：Manager 邮箱 {done_count} 条消息 in_progress → done\n")

    print(f"{'='*60}")
    print("  演示完成！")
    print(f"  验收结论：workspace/manager/review_result.md")
    print(f"  产品文档：workspace/shared/design/product_spec.md")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_demo()
