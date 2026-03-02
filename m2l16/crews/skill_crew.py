"""
课程：16｜Skills 生态：让 Agent 接入大量工具
Sub-Crew 工厂：skill_crew.py

设计要点：
  1. 工厂模式（Factory Pattern）
     - build_skill_crew() 每次返回全新 Crew 实例
     - 💡 核心点：防止多次调用间的状态污染（复用第 8 课 Task 工厂原则）

  2. MCP 原生接入 AIO-Sandbox
     - 使用 MCPServerHTTP 直接挂载沙盒 MCP 端点
     - CrewAI 自动将 MCP 工具转为 BaseTool，无需手写 wrapper
     - 💡 核心点：这里用到第 14 课讲的 create_static_tool_filter 白名单，
       在企业级场景的真实落地

  3. 最小权限原则
     - 只暴露 4 个沙盒工具（bash + code + file + editor）
     - 排除所有 browser_* 工具
"""

import sys
from pathlib import Path

from crewai import Agent, Crew, Process, Task
from crewai.mcp import MCPServerHTTP
from crewai.mcp.filters import create_static_tool_filter

# 将 crewai_mas_demo/ 加入 sys.path，使 llm 包可被 import
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from llm import AliyunLLM  # noqa: E402

# ── 常量 ─────────────────────────────────────────────────────────────────────

# 💡 核心点：端口 8022 对应 docker run -p 8022:8080
SANDBOX_MCP_URL = "http://localhost:8022/mcp"

# 💡 核心点：白名单过滤（来自 m2l10 实测确认的工具名称）
# Skill Agent 只需要执行脚本和读写文件，不需要浏览器
SANDBOX_TOOL_FILTER = create_static_tool_filter(
    allowed_tool_names=[
        "sandbox_execute_bash",       # Shell 命令执行（运行 skill 脚本）
        "sandbox_execute_code",       # Python/JS 代码执行（依赖安装、脚本运行）
        "sandbox_file_operations",    # 统一文件读写（read/write/list/find）
        "sandbox_str_replace_editor", # 专业文件编辑（创建/替换/查看）
    ]
    # 💡 核心点：browser_* 和 sandbox_browser_* 全部排除
    # 遵循最小权限原则：不需要的能力一律不开放
)


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

def build_skill_crew(skill_name: str, skill_instructions: str) -> Crew:
    """
    💡 核心点：工厂函数，每次调用创建全新实例，防止状态污染。
    skill_instructions 通过 Agent backstory 注入，成为 Skill Agent 的"内置知识"。
    沙盒通过 MCP 原生接入，CrewAI 自动处理工具发现和调用。

    Args:
        skill_name: Skill 名称（如 "pdf"、"docx"）
        skill_instructions: 完整 SKILL.md 正文 + 沙盒路径替换指令
    """
    # 每次创建新的 MCP Server 配置（保持实例独立）
    sandbox_mcp = MCPServerHTTP(
        url=SANDBOX_MCP_URL,
        tool_filter=SANDBOX_TOOL_FILTER,
    )

    # 💡 核心点：LLM 在函数内创建（惰性），避免模块导入时要求 API Key
    skill_llm = AliyunLLM(model="qwen3-max", region="cn", temperature=0.3)

    skill_agent = Agent(
        role=f"{skill_name.upper()} Skill 执行专家",
        goal=f"严格按照 {skill_name} Skill 的操作规范，在 AIO-Sandbox 中完成任务",
        backstory=(
            # 💡 核心点：skill_instructions 注入 backstory，
            #    是 Agent 的"内置技能手册"，不是任务描述
            f"你是一位专精于 {skill_name} 文件处理的 AI 专家。\n"
            f"你掌握以下操作规范，请严格遵循：\n\n"
            f"{skill_instructions}"
        ),
        llm=skill_llm,
        mcps=[sandbox_mcp],   # 💡 核心点：MCP 原生接入，不需要手写工具
        verbose=True,
        max_iter=10,
    )

    skill_task = Task(
        description=(
            "根据以下任务要求，使用你掌握的 Skill 操作规范完成任务。\n\n"
            "任务要求：\n{task_context}\n\n"
            "执行要求：\n"
            "1. 如遇依赖缺失，先在沙盒中安装再继续\n"
            "2. 所有文件操作使用沙盒工具，不得操作本地文件系统\n"
            "3. 完成后汇报：输出文件路径、操作摘要、是否成功"
        ),
        expected_output=(
            "一份执行报告，包含：\n"
            "- 是否成功（success: true/false）\n"
            "- 输出文件路径（output_path）\n"
            "- 关键操作步骤摘要\n"
            "- 如有错误，说明原因和已尝试的解决方案"
        ),
        agent=skill_agent,
    )

    return Crew(
        agents=[skill_agent],
        tasks=[skill_task],
        process=Process.sequential,
        verbose=True,
    )
