#!/usr/bin/env python3
"""find_low_quality_tasks.py — 找出最差 N 条任务（按 result_quality 升序）

输出 JSON：
  {"tasks": [{"task_id": str, "result_quality": float, "task_desc": str}, ...]}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.log_ops import read_l2


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--logs-dir", required=True)
    p.add_argument("--agent-id", required=True)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--top-k", type=int, default=3)
    args = p.parse_args()

    records = read_l2(Path(args.logs_dir), args.agent_id, days=args.days)
    sorted_records = sorted(records, key=lambda r: r.get("result_quality", 1.0))
    worst = sorted_records[: args.top_k]

    tasks = [
        {
            "task_id": r.get("task_id", "unknown"),
            "result_quality": r.get("result_quality", 0.0),
            "task_desc": r.get("task_desc", "")[:100],
        }
        for r in worst
    ]

    print(json.dumps({"tasks": tasks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
