#!/usr/bin/env python3
"""stats_all_agents.py — 全员 L2 聚合统计（Manager 团队复盘用）

输出 JSON：
  {"pm": {"task_count": int, "avg_quality": float, "failure_count": int},
   "manager": {...}}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.log_ops import read_l2

AGENT_IDS = ("pm", "manager")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--logs-dir", required=True)
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()

    logs_dir = Path(args.logs_dir)
    result: dict[str, dict] = {}

    for agent_id in AGENT_IDS:
        records = read_l2(logs_dir, agent_id, days=args.days)
        qualities = [r.get("result_quality", 0.0) for r in records]
        result[agent_id] = {
            "task_count": len(records),
            "avg_quality": round(sum(qualities) / max(len(qualities), 1), 3),
            "failure_count": sum(1 for q in qualities if q < 0.5),
        }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
