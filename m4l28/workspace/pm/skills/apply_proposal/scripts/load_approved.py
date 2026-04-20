#!/usr/bin/env python3
"""load_approved.py — 读取已批准提案的详细信息"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.proposal_ops import read_proposal


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--proposals-dir", required=True)
    p.add_argument("--proposal-id", required=True)
    args = p.parse_args()

    proposal = read_proposal(Path(args.proposals_dir), args.proposal_id)
    if proposal is None:
        print(json.dumps({"errcode": 1, "errmsg": f"提案不存在: {args.proposal_id}"}))
        return

    if proposal.status != "已批准":
        print(json.dumps({"errcode": 1, "errmsg": f"提案状态非已批准: {proposal.status}"}))
        return

    print(json.dumps({"errcode": 0, "proposal": proposal.model_dump()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
