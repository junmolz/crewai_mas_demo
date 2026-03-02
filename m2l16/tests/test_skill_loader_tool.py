"""
TDD：SkillLoaderTool 单元测试

测试范围：
  - __init__ / _build_description：frontmatter 解析 → XML description 构建
  - _extract_frontmatter_description：描述截断与边界处理
  - _get_skill_instructions：正文提取 + 沙盒指令拼接 + 缓存
  - _run / _arun：未知 skill 错误处理

不涉及：Sub-Crew 实际执行（需要 LLM + 沙盒，属于集成测试范围）
"""
import pytest
from tools.skill_loader_tool import SkillLoaderTool


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def tool():
    """SkillLoaderTool 实例（模块级，只初始化一次）"""
    return SkillLoaderTool()


# ─────────────────────────────────────────────
# 一、__init__ / _build_description
# ─────────────────────────────────────────────

class TestBuildDescription:
    """description 在 __init__ 时动态构建，包含 XML 格式的 Skill 能力清单"""

    def test_description_is_not_empty(self, tool):
        assert len(tool.description) > 0

    def test_description_has_xml_root_tag(self, tool):
        assert "<available_skills>" in tool.description
        assert "</available_skills>" in tool.description

    def test_description_has_skill_tags(self, tool):
        assert "<skill>" in tool.description
        assert "<name>" in tool.description
        assert "<type>" in tool.description
        assert "<description>" in tool.description

    def test_description_contains_pdf_skill(self, tool):
        assert "<name>pdf</name>" in tool.description

    def test_description_contains_docx_skill(self, tool):
        assert "<name>docx</name>" in tool.description

    def test_description_skill_type_is_task(self, tool):
        # 两个 skill 都是 task 类型
        assert "<type>task</type>" in tool.description


# ─────────────────────────────────────────────
# 二、_skill_registry
# ─────────────────────────────────────────────

class TestSkillRegistry:
    """_skill_registry 在 __init__ 时填充，记录每个 Skill 的 type 和 path"""

    def test_registry_has_pdf(self, tool):
        assert "pdf" in tool._skill_registry

    def test_registry_has_docx(self, tool):
        assert "docx" in tool._skill_registry

    def test_pdf_type_is_task(self, tool):
        assert tool._skill_registry["pdf"]["type"] == "task"

    def test_docx_type_is_task(self, tool):
        assert tool._skill_registry["docx"]["type"] == "task"

    def test_registry_has_path(self, tool):
        # path 指向真实的 skills 目录
        pdf_path = tool._skill_registry["pdf"]["path"]
        assert pdf_path.exists(), f"skills/pdf 目录不存在：{pdf_path}"


# ─────────────────────────────────────────────
# 三、_extract_frontmatter_description
# ─────────────────────────────────────────────

class TestExtractFrontmatter:
    """从 SKILL.md 的 YAML frontmatter 中提取 description 字段"""

    def test_extracts_description(self, tool):
        content = "---\nname: test\ndescription: This is a test skill\n---\n\n# Body"
        result = tool._extract_frontmatter_description(content)
        assert result == "This is a test skill"

    def test_truncates_long_description(self, tool):
        long_desc = "x" * 300
        content = f"---\nname: test\ndescription: {long_desc}\n---\n"
        result = tool._extract_frontmatter_description(content)
        # 超过 200 字符时截断并追加 "..."
        assert result.endswith("...")
        assert len(result) <= 203   # 200 + len("...") = 203

    def test_short_description_not_truncated(self, tool):
        content = "---\nname: test\ndescription: Short desc\n---\n"
        result = tool._extract_frontmatter_description(content)
        assert result == "Short desc"
        assert not result.endswith("...")

    def test_returns_empty_for_no_frontmatter(self, tool):
        result = tool._extract_frontmatter_description("No frontmatter here")
        assert result == ""

    def test_returns_empty_for_missing_description_key(self, tool):
        content = "---\nname: test\n---\n\n# Body"
        result = tool._extract_frontmatter_description(content)
        assert result == ""


# ─────────────────────────────────────────────
# 四、_get_skill_instructions
# ─────────────────────────────────────────────

class TestGetSkillInstructions:
    """读取完整 SKILL.md，剥离 frontmatter，拼接沙盒路径替换指令"""

    def test_strips_frontmatter(self, tool):
        result = tool._get_skill_instructions("pdf")
        # frontmatter 的 --- 分隔行不应出现在输出中
        assert not result.startswith("---")
        assert "name: pdf" not in result

    def test_contains_original_body(self, tool):
        result = tool._get_skill_instructions("pdf")
        # SKILL.md 正文应当存在（PDF SKILL.md 有 "Quick Start" section）
        assert len(result) > 100

    def test_contains_sandbox_directive(self, tool):
        result = tool._get_skill_instructions("pdf")
        assert "<sandbox_execution_directive>" in result
        assert "</sandbox_execution_directive>" in result

    def test_sandbox_directive_has_correct_path(self, tool):
        result = tool._get_skill_instructions("pdf")
        assert "/mnt/skills/pdf/" in result

    def test_docx_directive_has_correct_path(self, tool):
        result = tool._get_skill_instructions("docx")
        assert "/mnt/skills/docx/" in result

    def test_caches_result(self, tool):
        # 💡 核心点：两次调用返回同一个对象（缓存命中）
        result1 = tool._get_skill_instructions("pdf")
        result2 = tool._get_skill_instructions("pdf")
        assert result1 is result2


# ─────────────────────────────────────────────
# 五、_run / _arun 错误处理
# ─────────────────────────────────────────────

class TestErrorHandling:
    """未知 Skill 名称时，返回包含错误信息的字符串，不抛异常"""

    def test_run_unknown_skill(self, tool):
        result = tool._run(skill_name="nonexistent", task_context="任务")
        assert "错误" in result
        assert "nonexistent" in result

    @pytest.mark.asyncio
    async def test_arun_unknown_skill(self, tool):
        result = await tool._arun(skill_name="nonexistent", task_context="任务")
        assert "错误" in result
        assert "nonexistent" in result
