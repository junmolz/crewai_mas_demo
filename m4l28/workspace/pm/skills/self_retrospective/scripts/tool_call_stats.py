#!/usr/bin/env python3
"""tool_call_stats.py — 统计 Agent 的工具调用分布（从 session 日志）

输出 JSON：
  {"total_calls": int, "by_tool": {"tool_name": count, ...},
   "error_rate": float}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.log_ops import read_l3_from_sessions


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sessions-dir", required=True)
    p.add_argument("--agent-id", default=None)
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()

    steps = read_l3_from_sessions(
        sessions_dir=Path(args.sessions_dir),
        agent_id=args.agent_id,
    )

    by_tool: dict[str, int] = {}
    error_count = 0

    for s in steps:
        content = str(s.get("content", ""))
        tool_match = re.search(r"Action:\s*(\w+)", content)
        if tool_match:
            tool_name = tool_match.group(1)
            by_tool[tool_name] = by_tool.get(tool_name, 0) + 1

        if any(kw in content.lower() for kw in ("error", "fail", "exception")):
            error_count += 1

    total = sum(by_tool.values()) or 1

    print(json.dumps({
        "total_calls": sum(by_tool.values()),
        "by_tool": by_tool,
        "error_rate": round(error_count / max(len(steps), 1), 3),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
