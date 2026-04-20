#!/usr/bin/env python3
"""reject_proposal.py — 拒绝提案

输出 JSON：
  {"errcode": 0, "action": "rejected", "proposal_id": str}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.proposal_ops import update_proposal_status
from tools.mailbox_ops import send_mail


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--proposals-dir", required=True)
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--mailbox-dir", default=None)
    p.add_argument("--notify-initiator", default=None)
    args = p.parse_args()

    result = update_proposal_status(
        Path(args.proposals_dir), args.proposal_id, "已拒绝", note=args.reason,
    )

    if result is None:
        print(json.dumps({"errcode": 1, "errmsg": f"提案不存在: {args.proposal_id}"}))
        return

    if args.mailbox_dir and args.notify_initiator:
        send_mail(
            mailbox_dir=Path(args.mailbox_dir),
            to=args.notify_initiator,
            from_="manager",
            type_="retro_decision",
            subject=f"提案已拒绝: {args.proposal_id}",
            content=json.dumps({
                "proposal_id": args.proposal_id,
                "decision": "rejected",
                "reason": args.reason,
            }),
        )

    print(json.dumps({
        "errcode": 0,
        "action": "rejected",
        "proposal_id": args.proposal_id,
    }))


if __name__ == "__main__":
    main()
