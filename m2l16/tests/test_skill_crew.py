"""
TDD：skill_crew.py 单元测试

测试范围：
  - build_skill_crew 工厂函数
  - 返回类型、工厂模式（每次新实例）、Agent 配置正确性

不涉及：实际 MCP 连接和 Sub-Crew 执行（属于集成测试范围）
"""
import pytest
from crewai import Crew
from crews.skill_crew import build_skill_crew


SAMPLE_INSTRUCTIONS = "## 操作规范\n1. 使用 pypdf 读取 PDF\n2. 提取文本内容"


# ─────────────────────────────────────────────
# 一、工厂函数基础行为
# ─────────────────────────────────────────────

class TestBuildSkillCrewFactory:
    """build_skill_crew 是工厂函数，每次调用返回独立的新实例"""

    def test_returns_crew_instance(self):
        crew = build_skill_crew("pdf", SAMPLE_INSTRUCTIONS)
        assert isinstance(crew, Crew)

    def test_each_call_returns_new_instance(self):
        # 💡 核心点：防止状态污染——工厂模式，不复用对象
        crew1 = build_skill_crew("pdf", SAMPLE_INSTRUCTIONS)
        crew2 = build_skill_crew("pdf", SAMPLE_INSTRUCTIONS)
        assert crew1 is not crew2

    def test_different_skills_return_independent_crews(self):
        pdf_crew = build_skill_crew("pdf", SAMPLE_INSTRUCTIONS)
        docx_crew = build_skill_crew("docx", SAMPLE_INSTRUCTIONS)
        assert pdf_crew is not docx_crew


# ─────────────────────────────────────────────
# 二、Crew 结构
# ─────────────────────────────────────────────

class TestCrewStructure:
    """Crew 应包含恰好一个 Agent 和一个 Task"""

    def test_has_one_agent(self):
        crew = build_skill_crew("pdf", SAMPLE_INSTRUCTIONS)
        assert len(crew.agents) == 1

    def test_has_one_task(self):
        crew = build_skill_crew("pdf", SAMPLE_INSTRUCTIONS)
        assert len(crew.tasks) == 1


# ─────────────────────────────────────────────
# 三、Skill Agent 配置
# ─────────────────────────────────────────────

class TestSkillAgentConfig:
    """Skill Agent 的 role 和 backstory 应包含 skill 相关信息"""

    def test_agent_role_contains_skill_name(self):
        crew = build_skill_crew("pdf", SAMPLE_INSTRUCTIONS)
        agent = crew.agents[0]
        # role 中应包含 skill 名称（大写或小写均可）
        assert "pdf" in agent.role.lower()

    def test_agent_backstory_contains_instructions(self):
        # 💡 核心点：skill 操作指令通过 backstory 注入，是 Agent 的"内置知识"
        unique_marker = "UNIQUE_MARKER_XYZ_12345"
        crew = build_skill_crew("pdf", unique_marker)
        agent = crew.agents[0]
        assert unique_marker in agent.backstory

    def test_different_skills_have_different_roles(self):
        pdf_crew = build_skill_crew("pdf", SAMPLE_INSTRUCTIONS)
        docx_crew = build_skill_crew("docx", SAMPLE_INSTRUCTIONS)
        assert pdf_crew.agents[0].role != docx_crew.agents[0].role
