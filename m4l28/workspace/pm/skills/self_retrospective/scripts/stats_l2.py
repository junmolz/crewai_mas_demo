#!/usr/bin/env python3
"""stats_l2.py — L2 日志摘要统计（供 self_retrospective Skill 沙盒调用）

输出 JSON：
  {"task_count": int, "avg_quality": float, "failure_count": int,
   "human_correction_count": int}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.log_ops import read_l2, read_l1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--logs-dir", required=True)
    p.add_argument("--agent-id", required=True)
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()

    logs_dir = Path(args.logs_dir)
    records = read_l2(logs_dir, args.agent_id, days=args.days)

    task_count = len(records)
    if task_count == 0:
        print(json.dumps({
            "task_count": 0, "avg_quality": 0.0,
            "failure_count": 0, "human_correction_count": 0,
        }))
        return

    qualities = [r.get("result_quality", 0.0) for r in records]
    avg_quality = sum(qualities) / len(qualities)
    failure_count = sum(1 for q in qualities if q < 0.5)

    l1_records = read_l1(logs_dir, days=args.days)
    human_correction_count = sum(
        1 for r in l1_records
        if r.get("type") in ("checkpoint_rejected", "retro_decision")
    )

    print(json.dumps({
        "task_count": task_count,
        "avg_quality": round(avg_quality, 3),
        "failure_count": failure_count,
        "human_correction_count": human_correction_count,
    }))


if __name__ == "__main__":
    main()
