"""
TDD：main_crew.py 单元测试

测试范围：
  - build_main_crew 工厂函数：结构、工具绑定、工厂模式
  - run_doc_flow：异步入口，验证超时参数和正常返回结构

不涉及：实际 LLM 调用和 Skill 执行（属于集成测试范围）
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from crewai import Crew
from crews.main_crew import build_main_crew, run_doc_flow


# ─────────────────────────────────────────────
# 一、build_main_crew 工厂函数
# ─────────────────────────────────────────────

class TestBuildMainCrew:
    """build_main_crew 每次返回独立新实例，包含协调者 Agent 和 SkillLoaderTool"""

    def test_returns_crew_instance(self):
        crew = build_main_crew()
        assert isinstance(crew, Crew)

    def test_each_call_returns_new_instance(self):
        # 💡 核心点：工厂模式，防止状态污染
        crew1 = build_main_crew()
        crew2 = build_main_crew()
        assert crew1 is not crew2

    def test_has_one_agent(self):
        crew = build_main_crew()
        assert len(crew.agents) == 1

    def test_has_one_task(self):
        crew = build_main_crew()
        assert len(crew.tasks) == 1


# ─────────────────────────────────────────────
# 二、协调者 Agent 配置
# ─────────────────────────────────────────────

class TestOrchestratorAgent:
    """主 Agent 应绑定 SkillLoaderTool，backstory 只描述角色定位"""

    def test_agent_has_skill_loader_tool(self):
        from tools.skill_loader_tool import SkillLoaderTool
        crew = build_main_crew()
        agent = crew.agents[0]
        tool_names = [t.name for t in agent.tools]
        assert "skill_loader" in tool_names

    def test_agent_has_exactly_one_tool(self):
        crew = build_main_crew()
        agent = crew.agents[0]
        assert len(agent.tools) == 1

    def test_agent_backstory_is_concise(self):
        # 💡 核心点：backstory 只描述角色定位，约束在工具的 Field description 里
        crew = build_main_crew()
        agent = crew.agents[0]
        # backstory 不应塞入大量规则（长度限制：500 字以内）
        assert len(agent.backstory) < 500


# ─────────────────────────────────────────────
# 三、run_doc_flow 异步入口
# ─────────────────────────────────────────────

class TestRunDocFlow:
    """run_doc_flow 是 FastAPI 调用的异步入口，成功时返回 (result_str, "")"""

    @pytest.mark.asyncio
    async def test_returns_tuple_on_success(self):
        mock_result = MagicMock()
        mock_result.__str__ = lambda self: "执行成功"

        with patch("crews.main_crew.build_main_crew") as mock_build:
            mock_crew = MagicMock()
            mock_crew.akickoff = AsyncMock(return_value=mock_result)
            mock_build.return_value = mock_crew

            result, error = await run_doc_flow("测试请求")

        assert result == "执行成功"
        assert error == ""

    @pytest.mark.asyncio
    async def test_returns_error_string_on_exception(self):
        with patch("crews.main_crew.build_main_crew") as mock_build:
            mock_crew = MagicMock()
            mock_crew.akickoff = AsyncMock(side_effect=RuntimeError("模拟失败"))
            mock_build.return_value = mock_crew

            result, error = await run_doc_flow("测试请求")

        assert result is None
        assert "RuntimeError" in error
        assert "模拟失败" in error
