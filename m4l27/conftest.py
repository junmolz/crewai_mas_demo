"""
m4l27 conftest.py

解决 tools.mailbox_ops 命名冲突：
  crewai_mas_demo/tools/ 没有 mailbox_ops，
  但 pytest 在 m4l27/ 下运行时 sys.path 顺序可能导致
  tools 包解析到错误位置。

修复策略：
  - 保留父包 crewai_mas_demo/tools/ 为 sys.modules["tools"]
    （其他模块 BaiduSearchTool、SkillLoaderTool 等仍可正常导入）
  - 只把 tools.mailbox_ops 显式指向 m4l27/tools/mailbox_ops.py

Hook 清理：
  - CrewAI @before_llm_call 全局累积，每次测试前必须清除
"""

import importlib.util as _util
import sys
from pathlib import Path

_here         = Path(__file__).resolve().parent          # m4l27/
_project_root = _here.parent                             # crewai_mas_demo/

# 1. 确保路径：m4l27/ 在前，crewai_mas_demo/ 在后
for _p in [str(_project_root), str(_here)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_from(module_name: str, file_path: Path) -> None:
    spec = _util.spec_from_file_location(module_name, str(file_path))
    if spec is None:
        raise ImportError(f"Cannot find {file_path}")
    mod = _util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)


# 2. 确保父包 tools 已加载（crewai_mas_demo/tools/）
if "tools" not in sys.modules:
    _load_from("tools", _project_root / "tools" / "__init__.py")

# 3. 只替换 tools.mailbox_ops → m4l27/tools/mailbox_ops.py
#    其余子模块（skill_loader_tool、BaiduSearchTool 等）不受影响
_load_from("tools.mailbox_ops", _here / "tools" / "mailbox_ops.py")


# ─────────────────────────────────────────────────────────────────────────────
# Fixture：每次集成测试前清除 CrewAI 全局 before_llm_call hooks
# （@before_llm_call 在 __init__ 时注册，不清除会在多 Crew 顺序执行时叠加）
# autouse=False：只有显式 use 的测试才会清理，避免干扰单元测试
# ─────────────────────────────────────────────────────────────────────────────

import pytest


@pytest.fixture
def clean_crewai_hooks():
    """集成测试使用：清除残留 hooks，测试结束后再次清除。"""
    from crewai.hooks import clear_before_llm_call_hooks
    clear_before_llm_call_hooks()
    yield
    clear_before_llm_call_hooks()
