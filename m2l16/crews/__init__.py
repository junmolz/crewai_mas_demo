# crews/__init__.py
# 💡 核心点：在 crews 包被导入时，先设置 sys.path，确保 tools 和 llm 可被导入
# m2l16/ 必须在 crewai_mas_demo/ 之前，避免导入冲突
import sys
from pathlib import Path

_M2L16_ROOT = Path(__file__).parent.parent
_PROJECT_ROOT = _M2L16_ROOT.parent
# 先加 m2l16，再加 crewai_mas_demo（顺序很重要）
if str(_M2L16_ROOT) not in sys.path:
    sys.path.insert(0, str(_M2L16_ROOT))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
