"""
课程：26｜任务链与信息传递
示例文件：m4l26_pm.py

演示：PM 角色的单阶段运行
  步骤2：读取 Manager 邮件（task_assign）→ 读取需求文档 → 写产品文档 → 发完成通知给 Manager

与 m4l25 的复用关系：
  - build_bootstrap_prompt()：完全复用，zero change
  - SkillLoaderTool：完全复用，传入 m4l26 的沙盒挂载描述
  - prune_tool_results / maybe_compress：完全复用

第26课新增：
  - workspace/shared/ 挂载进沙盒（PM 可读 needs/，可写 design/）
  - workspace-rules（reference skill）：注入工作区访问规范
  - mailbox-ops（script skill）：读邮件（PM 自己的邮箱）/ 发邮件（给 Manager）
"""

from __future__ import annotations

import sys
from pathlib import Path

from crewai import Agent, Crew, Task
from crewai.hooks import LLMCallHookContext, before_llm_call
from crewai.project import CrewBase, agent, crew, task

# ── 路径设置 ──────────────────────────────────────────────────────────────────
_M4L26_DIR    = Path(__file__).resolve().parent
_PROJECT_ROOT = _M4L26_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
# 同 m4l26_manager.py：只插入 PROJECT_ROOT，避免 m4l26/tools/ 遮蔽 skill_loader_tool。

from llm import aliyun_llm                           # noqa: E402
from tools.skill_loader_tool import SkillLoaderTool  # noqa: E402
from m4l26.m4l26_mailbox.mailbox_tools import (  # noqa: E402
    make_mailbox_tools,
    WriteSharedFileTool,
    ReadSharedFileTool,
)

from m3l20.m3l20_file_memory import (                # noqa: E402
    build_bootstrap_prompt,
    load_session_ctx,
    save_session_ctx,
    append_session_raw,
    prune_tool_results,
    maybe_compress,
)


# ─────────────────────────────────────────────────────────────────────────────
# 路径常量
# ─────────────────────────────────────────────────────────────────────────────

WORKSPACE_DIR  = _M4L26_DIR / "workspace" / "pm"
SESSIONS_DIR   = WORKSPACE_DIR / "sessions"
SHARED_DIR     = _M4L26_DIR / "workspace" / "shared"
MAILBOXES_DIR  = SHARED_DIR / "mailboxes"

# m4l26 PM 沙盒端口（sandbox-docker-compose.yaml profile: pm → 8026）
# 定义为模块变量，测试时可通过 monkeypatch 替换
PM_SANDBOX_MCP_URL = "http://localhost:8026/mcp"


# ─────────────────────────────────────────────────────────────────────────────
# 沙盒挂载描述（PM）
# ─────────────────────────────────────────────────────────────────────────────

M4L26_PM_SANDBOX_MOUNT_DESC = (
    "1. 所有的操作必须在沙盒中执行，不得操作本地文件系统。\n"
    "   当前已挂载的目录：\n"
    "   - ./workspace/pm:/workspace:rw（PM 个人区，可读写）\n"
    "   - ./workspace/shared:/mnt/shared:rw（共享工作区，含邮箱，可读写）\n"
    "   - ../skills:/mnt/skills:ro（共享 skills 目录，只读）\n\n"
    "2. 记忆文件读写规范：\n"
    "   - 个人区读写：/workspace/<filename>\n"
    "   - 共享区需求文档：/mnt/shared/needs/requirements.md（只读）\n"
    "   - 共享区产品文档：/mnt/shared/design/product_spec.md（PM 负责写入）\n"
    "   - 邮箱：/mnt/shared/mailboxes/（通过 mailbox-ops skill 操作）\n\n"
    "3. 参考型 Skill（type: reference）：内容直接注入上下文，无需沙盒\n\n"
    "4. 如遇依赖缺失，先在沙盒中安装再继续"
)


# ─────────────────────────────────────────────────────────────────────────────
# PM Crew — 步骤2：执行任务
# ─────────────────────────────────────────────────────────────────────────────

@CrewBase
class PMExecuteCrew:
    """
    PM 步骤2：读取 Manager 任务邮件 → 读需求 → 写产品文档 → 发完成通知

    核心教学点（对应第26课 P5/P6）：
    - mailbox-ops read_inbox：读取未读邮件并自动标记已读（幂等保护）
    - 路径引用传递：邮件 content 中只写路径，不复制文档全文
    - 同步通知：PM 完成即发邮件，触发 Manager 验收，不等轮询
    """

    def __init__(self, session_id: str) -> None:
        self.session_id      = session_id
        self._session_loaded = False
        self._last_msgs: list[dict] = []
        self._history_len    = 0

    @agent
    def pm_agent(self) -> Agent:
        backstory = build_bootstrap_prompt(WORKSPACE_DIR)
        return Agent(
            role      = "产品经理（PM）",
            goal      = "读取任务邮件，根据需求写出规范的产品文档，并通知 Manager 验收",
            backstory = backstory,
            llm       = aliyun_llm.AliyunLLM(
                model       = "qwen-plus",
                temperature = 0.3,
            ),
            tools = [
                SkillLoaderTool(
                    sandbox_mount_desc=M4L26_PM_SANDBOX_MOUNT_DESC,
                    sandbox_mcp_url=PM_SANDBOX_MCP_URL,
                ),
                *make_mailbox_tools(MAILBOXES_DIR),
                WriteSharedFileTool(shared_dir=SHARED_DIR),
                ReadSharedFileTool(shared_dir=SHARED_DIR),
            ],
            verbose  = True,
            max_iter = 20,
        )

    @task
    def execute_task(self) -> Task:
        return Task(
            description     = "{user_request}",
            expected_output = (
                "完成以下四步：\n"
                "1. 用 read_inbox 读取 PM 邮箱，获取 Manager 的任务分配邮件（type: task_assign）\n"
                "2. 用 skill_loader 加载 workspace-rules 了解工作区权限，"
                "然后用 skill_loader 读取 /mnt/shared/needs/requirements.md 理解功能需求\n"
                "3. 根据需求撰写产品文档，用 write_shared_file 写入 'design/product_spec.md'\n"
                "   文档必须包含：产品概述 + 用户故事 + 功能规格（F-01/F-02）+ 验收标准\n"
                "4. 用 send_mail 向 Manager 发送完成通知邮件：\n"
                "   - type: task_done\n"
                "   - subject: 产品文档已完成\n"
                "   - content: 完成说明（只写路径引用：/mnt/shared/design/product_spec.md）\n"
                "确认邮件发送成功后输出：「产品文档已完成，已通知 Manager 验收」"
            ),
            agent = self.pm_agent(),
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents  = self.agents,
            tasks   = self.tasks,
            verbose = True,
        )

    @before_llm_call
    def before_llm_hook(self, context: LLMCallHookContext) -> bool | None:
        if not self._session_loaded:
            self._restore_session(context)
            self._session_loaded = True
        self._last_msgs = context.messages
        prune_tool_results(context.messages)
        maybe_compress(context.messages, context)
        return None

    def _restore_session(self, context: LLMCallHookContext) -> None:
        history = load_session_ctx(self.session_id, SESSIONS_DIR)
        self._history_len = len(history)
        if not history:
            return
        current_user_msg = next(
            (m for m in reversed(context.messages) if m.get("role") == "user"), None
        )
        context.messages.clear()
        context.messages.extend(history)
        if current_user_msg is not None:
            context.messages.append(current_user_msg)


# ─────────────────────────────────────────────────────────────────────────────
# 公共辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def save_session(crew_instance: PMExecuteCrew, session_id: str) -> None:
    """保存 session 上下文（复用 m3l20 逻辑）"""
    if crew_instance._last_msgs:
        new_msgs = list(crew_instance._last_msgs)[crew_instance._history_len:]
        append_session_raw(session_id, new_msgs, SESSIONS_DIR)
        save_session_ctx(session_id, list(crew_instance._last_msgs), SESSIONS_DIR)
