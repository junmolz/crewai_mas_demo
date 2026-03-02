"""
课程：16｜Skills 生态：让 Agent 接入大量工具
演示入口：main.py

运行前提：
  1. AIO-Sandbox 已启动（docker run -p 8022:8080 ...）
  2. QWEN_API_KEY 环境变量已设置
  3. data/quarterly_report.pdf 已放入 m2l16/data/ 目录

运行方式：
  cd code/crewai_mas_demo/m2l16
  QWEN_API_KEY=<your_key> python3 main.py
"""

import asyncio
import sys
from pathlib import Path

# 将 crewai_mas_demo/ 和 m2l16/ 加入 sys.path
_M2L16_ROOT = Path(__file__).parent
_PROJECT_ROOT = _M2L16_ROOT.parent
for _p in [str(_M2L16_ROOT), str(_PROJECT_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crews.main_crew import build_main_crew  # noqa: E402

# ── Demo 用户请求 ─────────────────────────────────────────────────────────────
USER_REQUEST = (
    "请将 /workspace/data/quarterly_report.pdf 里的关键数据提炼出来，"
    "生成一份格式规范的 Word 文档，保存到 /workspace/output/summary.docx。"
    "Word 文档需要包含：标题、执行摘要、关键数据表格。"
)


def main():
    """同步入口：适用于命令行直接运行"""
    print("=" * 60)
    print("16课 Skills 生态 Demo：PDF → DOCX")
    print("=" * 60)
    print(f"\n用户请求：{USER_REQUEST}\n")

    crew = build_main_crew()
    result = crew.kickoff(inputs={"user_request": USER_REQUEST})

    print("\n" + "=" * 60)
    print("执行结果：")
    print(result)
    print("=" * 60)


async def main_async():
    """异步入口：与 FastAPI 调用链一致，用于验证 akickoff 路径"""
    from crews.main_crew import run_doc_flow

    print("=" * 60)
    print("16课 Skills 生态 Demo（异步模式）：PDF → DOCX")
    print("=" * 60)

    result, error = await run_doc_flow(USER_REQUEST)

    if error:
        print(f"\n执行失败：{error}")
    else:
        print(f"\n执行结果：\n{result}")


if __name__ == "__main__":
    # 默认同步运行；传入 --async 参数则用异步模式
    if "--async" in sys.argv:
        asyncio.run(main_async())
    else:
        main()
