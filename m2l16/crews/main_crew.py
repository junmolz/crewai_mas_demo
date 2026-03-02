"""
课程：16｜Skills 生态：让 Agent 接入大量工具
主 Crew：main_crew.py

设计要点：
  1. 协调者 Agent（Orchestrator）
     - 只持有 SkillLoaderTool 一个工具
     - backstory 只描述角色定位，不塞约束规则
     - 💡 核心点：约束写在 SkillLoaderTool 的 task_context Field description 里，
       跟着工具参数走，比写在 backstory 里更精准

  2. 工厂模式
     - build_main_crew() 每次返回新实例，与 Sub-Crew 保持同一设计风格

  3. 异步入口
     - run_doc_flow() 供 FastAPI service 层 await 调用
     - asyncio.wait_for 加 300s 超时，应对文档处理耗时场景
"""

import asyncio
import sys
from pathlib import Path

from crewai import Agent, Crew, Process, Task

# 💡 核心点：m2l16/ 必须在 crewai_mas_demo/ 之前，
# 否则会导入 crewai_mas_demo/tools/ 而非 m2l16/tools/
_M2L16_ROOT = Path(__file__).parent.parent
_PROJECT_ROOT = _M2L16_ROOT.parent
# 先加 m2l16，再加 crewai_mas_demo（顺序很重要）
if str(_M2L16_ROOT) not in sys.path:
    sys.path.insert(0, str(_M2L16_ROOT))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from llm import AliyunLLM                          # noqa: E402

# 💡 核心点：使用绝对路径导入，避免与 crewai_mas_demo/tools/ 冲突
import importlib.util
_tool_spec = importlib.util.spec_from_file_location(
    "skill_loader_tool",
    _M2L16_ROOT / "tools" / "skill_loader_tool.py"
)
_tool_module = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_module)
SkillLoaderTool = _tool_module.SkillLoaderTool


def build_main_crew() -> Crew:
    """
    💡 核心点：工厂函数，每次调用创建全新实例。
    SkillLoaderTool 在此实例化，__init__ 会自动解析 skills 元数据、构建 XML description。
    """
    skill_loader = SkillLoaderTool()

    orchestrator = Agent(
        role="文档处理协调者",
        goal="理解用户的文档处理需求，通过 Skill 系统协调完成 PDF 读取和 Word 生成任务",
        backstory=(
            # 💡 核心点：backstory 只描述角色定位，不塞约束规则
            # 约束已在 SkillLoaderTool 的 task_context Field description 里定义
            "你是一位文档处理流程的架构师，擅长将复杂的文档任务"
            "拆解为清晰的步骤，并调用正确的专业 Skill 来执行。"
        ),
        llm=AliyunLLM(model="qwen3-max", region="cn", temperature=0.3),
        tools=[skill_loader],
        verbose=True,
    )

    main_task = Task(
        description="{user_request}",
        expected_output=(
            "完整的任务执行报告，包含：\n"
            "- 每个 Skill 的执行结果\n"
            "- 最终输出文件路径\n"
            "- 任务是否成功完成"
        ),
        agent=orchestrator,
    )

    return Crew(
        agents=[orchestrator],
        tasks=[main_task],
        process=Process.sequential,
        verbose=True,
    )


# ── FastAPI 调用入口 ──────────────────────────────────────────────────────────

async def run_doc_flow(user_request: str) -> tuple[str | None, str]:
    """
    💡 核心点：对外异步入口，供 FastAPI service 层 await 调用。
    asyncio.wait_for 加 300s 超时，防止文档处理任务无限阻塞。

    Returns:
        (result_str, "")        成功时
        (None, error_message)   失败时
    """
    crew = build_main_crew()
    try:
        result = await asyncio.wait_for(
            crew.akickoff(inputs={"user_request": user_request}),
            timeout=300,
        )
        return str(result), ""
    except Exception as exc:
        return None, f"流程执行失败: {type(exc).__name__}: {exc}"
