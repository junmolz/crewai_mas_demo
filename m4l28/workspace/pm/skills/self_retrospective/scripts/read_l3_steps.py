#!/usr/bin/env python3
"""read_l3_steps.py — 按 task_id 读取 L3 ReAct 步骤（v6：从 session 日志读）

输出 JSON：
  {"steps": [{"role": str, "content": str, "ts": str}, ...]}
  或 {"errcode": 1, "errmsg": "..."}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.log_ops import read_l3_from_sessions


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sessions-dir", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--only-failed", default="true")
    args = p.parse_args()

    only_failed = args.only_failed.lower() in ("true", "1", "yes")

    steps = read_l3_from_sessions(
        sessions_dir=Path(args.sessions_dir),
        task_id=args.task_id,
        only_failed=only_failed,
    )

    if not steps:
        print(json.dumps({"errcode": 1, "errmsg": f"task_id 不存在或无匹配步骤: {args.task_id}"}))
        return

    output = [
        {
            "role": s.get("role", "unknown"),
            "content": str(s.get("content", ""))[:500],
            "ts": s.get("ts", ""),
        }
        for s in steps
    ]

    print(json.dumps({"steps": output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
