"""
课程：26｜任务链与信息传递
示例文件：m4l26_manager.py

演示：Manager 角色的两阶段运行
  阶段一（步骤1）：读取共享工作区需求 → 通过邮箱向 PM 分配任务
  阶段二（步骤3）：读取 PM 回邮 → 读取产品文档 → 验收并保存结果

与 m4l25 的复用关系：
  - build_bootstrap_prompt()：完全复用，zero change
  - SkillLoaderTool：完全复用，传入 m4l26 的沙盒挂载描述
  - prune_tool_results / maybe_compress：完全复用

第26课新增：
  - workspace/shared/ 挂载进沙盒（Manager 可读全部，可写 needs/）
  - workspace-rules（reference skill）：注入工作区访问规范
  - mailbox-ops（script skill）：发邮件 / 读邮件
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
# 注意：此文件只需要 PROJECT_ROOT（用于 tools.skill_loader_tool / llm / m3l20 等）。
# m4l26/tools/（mailbox_ops）由 conftest.py 在测试时注入，或在运行时通过 Skill 脚本执行。
# 不在此插入 _M4L26_DIR，避免 m4l26/tools/ 遮蔽 crewai_mas_demo/tools/ 中的 skill_loader_tool。

from llm import aliyun_llm                           # noqa: E402
from tools.skill_loader_tool import SkillLoaderTool  # noqa: E402
from m4l26.m4l26_mailbox.mailbox_tools import (  # noqa: E402
    make_mailbox_tools,
    ReadSharedFileTool,
    WriteWorkspaceTool,
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

WORKSPACE_DIR  = _M4L26_DIR / "workspace" / "manager"
SESSIONS_DIR   = WORKSPACE_DIR / "sessions"
SHARED_DIR     = _M4L26_DIR / "workspace" / "shared"
MAILBOXES_DIR  = SHARED_DIR / "mailboxes"

# m4l26 Manager 沙盒端口（sandbox-docker-compose.yaml profile: manager → 8025）
# 定义为模块变量，测试时可通过 monkeypatch 替换
MANAGER_SANDBOX_MCP_URL = "http://localhost:8025/mcp"


# ─────────────────────────────────────────────────────────────────────────────
# 沙盒挂载描述（Manager）
# ─────────────────────────────────────────────────────────────────────────────

M4L26_MANAGER_SANDBOX_MOUNT_DESC = (
    "1. 所有的操作必须在沙盒中执行，不得操作本地文件系统。\n"
    "   当前已挂载的目录：\n"
    "   - ./workspace/manager:/workspace:rw（Manager 个人区，可读写）\n"
    "   - ./workspace/shared:/mnt/shared:rw（共享工作区，含邮箱，可读写）\n"
    "   - ../skills:/mnt/skills:ro（共享 skills 目录，只读）\n\n"
    "2. 记忆文件读写规范：\n"
    "   - 个人区读写：/workspace/<filename>\n"
    "   - 共享区读取：/mnt/shared/needs/requirements.md\n"
    "   - 共享区产品文档：/mnt/shared/design/product_spec.md（只读）\n"
    "   - 邮箱：/mnt/shared/mailboxes/（通过 mailbox-ops skill 操作）\n\n"
    "3. 参考型 Skill（type: reference）：内容直接注入上下文，无需沙盒\n\n"
    "4. 如遇依赖缺失，先在沙盒中安装再继续"
)


# ─────────────────────────────────────────────────────────────────────────────
# Manager Crew — 阶段一：分配任务
# ─────────────────────────────────────────────────────────────────────────────

@CrewBase
class ManagerAssignCrew:
    """
    Manager 阶段一：读取需求 → 向 PM 发邮件分配产品文档任务

    核心教学点（对应第26课 P3/P4/P5）：
    - workspace-rules（reference skill）注入工作区访问规范
    - mailbox-ops（script skill）发送结构化邮件（from/to/type/subject/content）
    - 邮件内容只传路径引用，不传需求全文
    """

    def __init__(self, session_id: str) -> None:
        self.session_id      = session_id
        self._session_loaded = False
        self._last_msgs: list[dict] = []
        self._history_len    = 0

    @agent
    def manager_agent(self) -> Agent:
        backstory = build_bootstrap_prompt(WORKSPACE_DIR)
        return Agent(
            role      = "项目经理（Manager）",
            goal      = "读取项目需求，通过邮箱向 PM 发送产品文档设计任务",
            backstory = backstory,
            llm       = aliyun_llm.AliyunLLM(
                model       = "qwen-plus",
                temperature = 0.3,
            ),
            tools = [
                SkillLoaderTool(
                    sandbox_mount_desc=M4L26_MANAGER_SANDBOX_MOUNT_DESC,
                    sandbox_mcp_url=MANAGER_SANDBOX_MCP_URL,
                ),
                *make_mailbox_tools(MAILBOXES_DIR),
            ],
            verbose  = True,
            max_iter = 20,
        )

    @task
    def assign_task(self) -> Task:
        return Task(
            description     = "{user_request}",
            expected_output = (
                "完成以下两步：\n"
                "1. 读取 /mnt/shared/needs/requirements.md 理解项目需求\n"
                "2. 通过 mailbox-ops skill 向 PM 发送任务分配邮件，包含：\n"
                "   - type: task_assign\n"
                "   - subject: 产品文档设计任务\n"
                "   - content: 任务说明（包含需求文档路径和验收标准，不要复制全文）\n"
                "确认邮件已写入 PM 邮箱后输出：「任务已发送给 PM」"
            ),
            agent = self.manager_agent(),
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
# Manager Crew — 阶段二：验收
# ─────────────────────────────────────────────────────────────────────────────

@CrewBase
class ManagerReviewCrew:
    """
    Manager 阶段二：读取 PM 回邮 → 验收产品文档

    核心教学点（对应第26课 P7）：
    - 同步通知：PM 完成后发邮件，Manager 收到即验收（无需等待轮询周期）
    - 邮件 read 字段：read_inbox 返回未读消息并标记已读（幂等保护）
    """

    def __init__(self, session_id: str) -> None:
        self.session_id      = session_id
        self._session_loaded = False
        self._last_msgs: list[dict] = []
        self._history_len    = 0

    @agent
    def manager_agent(self) -> Agent:
        backstory = build_bootstrap_prompt(WORKSPACE_DIR)
        return Agent(
            role      = "项目经理（Manager）",
            goal      = "读取 PM 回邮，验收产品文档，保存验收结论",
            backstory = backstory,
            llm       = aliyun_llm.AliyunLLM(
                model       = "qwen-plus",
                temperature = 0.3,
            ),
            tools = [
                SkillLoaderTool(
                    sandbox_mount_desc=M4L26_MANAGER_SANDBOX_MOUNT_DESC,
                    sandbox_mcp_url=MANAGER_SANDBOX_MCP_URL,
                ),
                *make_mailbox_tools(MAILBOXES_DIR),
                ReadSharedFileTool(shared_dir=SHARED_DIR),
                WriteWorkspaceTool(workspace_dir=WORKSPACE_DIR),
            ],
            verbose  = True,
            max_iter = 20,
        )

    @task
    def review_task(self) -> Task:
        return Task(
            description = (
                "{user_request}\n\n"
                "【强制要求】必须依次完成以下三步工具调用：\n"
                "Step 1: 调用 read_inbox(role='manager') 获取 PM 发来的 task_done 通知\n"
                "Step 2: 调用 read_shared_file(relative_path='design/product_spec.md') 读取产品文档\n"
                "Step 3: 调用 write_workspace_file(filename='review_result.md', content='<验收报告>') 保存验收结论\n"
                "不调用 write_workspace_file 则任务视为未完成。"
            ),
            expected_output = (
                "已完成三步：\n"
                "1. read_inbox 获取 task_done 通知 ✓\n"
                "2. read_shared_file 读取产品文档 ✓\n"
                "3. write_workspace_file 写入 review_result.md ✓\n"
                "输出验收结论摘要（通过/需返工 + 关键检查项）"
            ),
            agent = self.manager_agent(),
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

def save_session(crew_instance: ManagerAssignCrew | ManagerReviewCrew,
                 session_id: str) -> None:
    """保存 session 上下文（复用 m3l20 逻辑）"""
    if crew_instance._last_msgs:
        new_msgs = list(crew_instance._last_msgs)[crew_instance._history_len:]
        append_session_raw(session_id, new_msgs, SESSIONS_DIR)
        save_session_ctx(session_id, list(crew_instance._last_msgs), SESSIONS_DIR)
