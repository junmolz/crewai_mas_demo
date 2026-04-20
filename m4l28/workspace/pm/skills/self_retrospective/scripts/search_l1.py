#!/usr/bin/env python3
"""search_l1.py — 搜索 L1 人类交互日志（纠正记录）

输出 JSON：
  {"records": [{"id": str, "type": str, "subject": str, "timestamp": str}, ...],
   "total": int}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.log_ops import read_l1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--logs-dir", required=True)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--keyword", default=None)
    args = p.parse_args()

    records = read_l1(Path(args.logs_dir), days=args.days)

    if args.keyword:
        kw = args.keyword.lower()
        records = [
            r for r in records
            if kw in str(r.get("subject", "")).lower()
            or kw in str(r.get("content", "")).lower()
        ]

    output = [
        {
            "id": r.get("id", ""),
            "type": r.get("type", ""),
            "subject": r.get("subject", ""),
            "timestamp": r.get("timestamp", ""),
        }
        for r in records
    ]

    print(json.dumps({"records": output, "total": len(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
