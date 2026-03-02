"""
pytest conftest：配置 sys.path，让测试可以直接 import tools/crews/models
"""
import os
import sys
from pathlib import Path

# 将 m2l16/ 加入 sys.path → 可以 import tools.xxx / crews.xxx
M2L16_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(M2L16_ROOT))

# 将 crewai_mas_demo/ 加入 sys.path → 可以 import llm（共享 LLM 配置）
sys.path.insert(0, str(M2L16_ROOT.parent))

# 单元测试不需要真实 API key，设置 dummy 值让 AliyunLLM 能完成实例化
# 实际 LLM 调用只在集成测试中触发
os.environ.setdefault("QWEN_API_KEY", "dummy-key-for-unit-tests")
