"""
课程：16｜Skills 生态：让 Agent 接入大量工具
核心组件：SkillLoaderTool

设计要点：
  1. 渐进式披露（Progressive Disclosure）
     - __init__ 只解析 SKILL.md 的 YAML frontmatter，构建轻量 XML 注入工具 description
     - 主 Agent 通过 description 感知"有哪些 Skill、各自用途"
     - 真正调用时才读取完整 SKILL.md 正文（按需加载）

  2. 参考型 vs 任务型
     - reference：返回指令文本，主 Agent 自行消化，不启动 Sub-Crew
     - task：触发独立 Sub-Crew + AIO-Sandbox 执行，上下文完全隔离

  3. 异步双通道
     - _arun()：FastAPI akickoff() 调用链的主路径，原生 await
     - _run()：同步 fallback，ThreadPoolExecutor 提供独立 event loop，
               规避 "cannot run nested event loop" 错误
"""

import asyncio
import concurrent.futures
import re
import sys
from pathlib import Path

import yaml
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# 将 crewai_mas_demo/ 加入 sys.path，使 llm 包可被 import
# 将 m2l16/ 加入 sys.path，使 crews.skill_crew 可被 import
_TOOLS_DIR = Path(__file__).parent
_M2L16_ROOT = _TOOLS_DIR.parent
_PROJECT_ROOT = _M2L16_ROOT.parent
for _p in [str(_M2L16_ROOT), str(_PROJECT_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crews.skill_crew import build_skill_crew  # noqa: E402

# ── 路径常量 ────────────────────────────────────────────────────────────────
# SKILLS_DIR：共享 skills 目录（crewai_mas_demo/skills/），所有课程共用
# 💡 核心点：__file__ 是 m2l16/tools/skill_loader_tool.py，上三级即 crewai_mas_demo/
SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"

# 沙盒内的 skills 挂载路径（与 docker-compose.yaml 的 volumes 对应）
SANDBOX_SKILLS_MOUNT = "/mnt/skills"


# ── 输入 Schema ─────────────────────────────────────────────────────────────

class SkillLoaderInput(BaseModel):
    skill_name: str = Field(
        description="要加载的 Skill 名称，必须严格来自工具描述 XML 列表中的 <name> 值"
    )
    task_context: str = Field(
        description=(
            "调用此 Skill 要完成的任务的完整描述。"
            "【必须包含以下四项，缺一不可】\n"
            "1. 输入文件的沙盒绝对路径（如 /workspace/data/report.pdf）\n"
            "2. 期望的输出内容结构（如：包含标题、摘要、关键数据三个章节）\n"
            "3. 输出文件的沙盒绝对路径（如 /workspace/output/summary.docx）\n"
            "4. 特殊格式要求（如无则填写'无'）\n"
            "提供信息越完整，Skill 执行越精准。"
        )
    )


# ── 核心工具 ─────────────────────────────────────────────────────────────────

class SkillLoaderTool(BaseTool):
    name: str = "skill_loader"
    description: str = ""           # 在 __init__ 中动态构建
    args_schema: type[BaseModel] = SkillLoaderInput

    # Pydantic 会把普通 dict 属性当作模型字段，用 PrivateAttr 或 ClassVar 绕开
    # 这里用 model_config + 直接赋值实例属性的方式
    _skill_registry: dict = {}
    _instruction_cache: dict = {}

    def __init__(self):
        super().__init__()
        # 实例级属性，避免类级共享
        self._skill_registry = {}
        self._instruction_cache = {}
        self._build_description()

    # ── 阶段 1：元数据解析，构建 XML description ────────────────────────────

    def _build_description(self):
        """
        💡 核心点：渐进式披露第一阶段
        只读 frontmatter，构建轻量 XML 注入 description。
        主 Agent 看到工具 → 知道"什么场景用什么 Skill"，但不加载完整指令。
        """
        manifest_path = SKILLS_DIR / "load_skills.yaml"
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        xml_parts = ["<available_skills>"]
        for skill_conf in manifest["skills"]:
            if not skill_conf.get("enabled", True):
                continue
            name = skill_conf["name"]
            skill_type = skill_conf.get("type", "task")
            skill_path = SKILLS_DIR / name

            skill_md = (skill_path / "SKILL.md").read_text()
            desc = self._extract_frontmatter_description(skill_md)

            self._skill_registry[name] = {
                "type": skill_type,
                "path": skill_path,
            }
            xml_parts.append(
                f"  <skill>\n"
                f"    <name>{name}</name>\n"
                f"    <type>{skill_type}</type>\n"
                f"    <description>{desc}</description>\n"
                f"  </skill>"
            )
        xml_parts.append("</available_skills>")

        # 💡 核心点：约束已在 SkillLoaderInput.task_context 的 Field description 中定义，
        #    这里只展示 Skill 能力清单，保持 description 简洁
        self.description = (
            "当任务涉及文档处理（PDF读取、Word生成、Excel分析等）时，调用此工具。\n"
            "根据下方 XML 列表选择正确的 skill_name，并在 task_context 中提供完整任务信息。\n\n"
            + "\n".join(xml_parts)
        )

    def _extract_frontmatter_description(self, content: str) -> str:
        """从 SKILL.md 的 YAML frontmatter 中提取 description 字段（最多 200 字符）"""
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return ""
        front = yaml.safe_load(match.group(1))
        desc = front.get("description", "")
        if not desc:
            return ""
        return desc[:200] + "..." if len(desc) > 200 else desc

    # ── 阶段 2：按需加载完整指令 ─────────────────────────────────────────────

    def _get_skill_instructions(self, skill_name: str) -> str:
        """
        💡 核心点：渐进式披露第二阶段
        读取完整 SKILL.md，剥离 frontmatter，拼接沙盒路径替换指令。
        结果写入 _instruction_cache，同一 Skill 只读一次文件。
        """
        if skill_name in self._instruction_cache:
            return self._instruction_cache[skill_name]

        skill_path = self._skill_registry[skill_name]["path"]
        content = (skill_path / "SKILL.md").read_text()
        # 剥离 YAML frontmatter（--- ... ---）
        stripped = re.sub(r"^---\n.*?\n---\n?", "", content, flags=re.DOTALL)

        # 拼接沙盒路径替换指令，消灭 LLM 路径幻觉
        sandbox_directive = (
            f"\n\n<sandbox_execution_directive>\n"
            f"【强制约束】所有脚本和文件操作必须在 AIO-Sandbox 中执行，禁止直接操作本地文件系统。\n"
            f"此 Skill 资源已挂载至沙盒绝对路径：{SANDBOX_SKILLS_MOUNT}/{skill_name}/\n"
            f"- scripts/xxx.py → {SANDBOX_SKILLS_MOUNT}/{skill_name}/scripts/xxx.py\n"
            f"- 执行命令示例：sandbox_execute_bash('python {SANDBOX_SKILLS_MOUNT}/{skill_name}/scripts/xxx.py ...')\n"
            f"- 遇到依赖缺失时，先 sandbox_execute_bash('pip install xxx') 再重试。\n"
            f"</sandbox_execution_directive>"
        )

        result = stripped + sandbox_directive
        self._instruction_cache[skill_name] = result
        return result

    # ── Sub-Crew 执行（任务型 Skill）────────────────────────────────────────

    async def _execute_skill_async(self, skill_name: str, task_context: str) -> str:
        """核心执行路径：加载指令，按 type 分流"""
        skill_info = self._skill_registry[skill_name]
        instructions = self._get_skill_instructions(skill_name)

        if skill_info["type"] == "reference":
            # 参考型：直接返回指令文本，不启动 Sub-Crew
            return f"<skill_instructions>\n{instructions}\n</skill_instructions>"

        # 任务型：启动独立 Sub-Crew，在沙盒中执行
        # 💡 核心点：每次 build_skill_crew() 返回新实例，防止状态污染
        crew = build_skill_crew(
            skill_name=skill_name,
            skill_instructions=instructions,
        )
        result = await crew.akickoff(inputs={
            "task_context": task_context,
            "skill_name": skill_name,
        })
        return str(result)

    # ── 异步路径（FastAPI / akickoff 调用链）────────────────────────────────

    async def _arun(self, skill_name: str, task_context: str) -> str:
        """
        💡 核心点：FastAPI 异步调用链的主路径，直接 await Sub-Crew
        CrewAI 在 arun() 内部调用 _arun()，框架自动选路
        """
        if skill_name not in self._skill_registry:
            return f"错误：未找到 Skill '{skill_name}'，可用：{list(self._skill_registry.keys())}"
        return await self._execute_skill_async(skill_name, task_context)

    # ── 同步路径（脚本 / 测试场景 fallback）─────────────────────────────────

    def _run(self, skill_name: str, task_context: str) -> str:
        """
        💡 核心点：用 ThreadPoolExecutor 在新线程中运行独立 event loop，
        规避主线程已有 event loop 时 asyncio.run() 报
        'cannot run nested event loop' 的问题
        """
        if skill_name not in self._skill_registry:
            return f"错误：未找到 Skill '{skill_name}'，可用：{list(self._skill_registry.keys())}"

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                self._execute_skill_async(skill_name, task_context),
            )
            return future.result()
