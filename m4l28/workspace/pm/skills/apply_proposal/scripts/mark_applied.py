#!/usr/bin/env python3
"""mark_applied.py — 标记提案为已实施"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.proposal_ops import update_proposal_status


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--proposals-dir", required=True)
    p.add_argument("--proposal-id", required=True)
    args = p.parse_args()

    result = update_proposal_status(
        Path(args.proposals_dir), args.proposal_id, "已实施",
    )

    if result is None:
        print(json.dumps({"errcode": 1, "errmsg": "提案不存在"}))
    else:
        print(json.dumps({"errcode": 0, "status": result.status}))


if __name__ == "__main__":
    main()
