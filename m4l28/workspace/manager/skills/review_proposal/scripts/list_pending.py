#!/usr/bin/env python3
"""list_pending.py — 列出所有待审批的提案

输出 JSON：
  {"proposals": [{"id": str, "type": str, "target": str, "priority": str,
                   "initiator": str, "root_cause": str}, ...],
   "total": int}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.proposal_ops import list_proposals


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--proposals-dir", required=True)
    p.add_argument("--status", default="待审批")
    args = p.parse_args()

    all_proposals = list_proposals(Path(args.proposals_dir))
    pending = [
        (pid, prop) for pid, prop in all_proposals
        if prop.status == args.status
    ]

    output = [
        {
            "id": pid,
            "type": prop.type,
            "target": prop.target,
            "priority": prop.priority,
            "initiator": prop.initiator,
            "root_cause": prop.root_cause,
        }
        for pid, prop in pending
    ]

    print(json.dumps({"proposals": output, "total": len(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
