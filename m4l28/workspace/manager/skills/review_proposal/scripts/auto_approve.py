#!/usr/bin/env python3
"""auto_approve.py — memory 类型提案自动批准（检查硬闸门后落地）

输出 JSON：
  {"errcode": 0, "action": "approved", "proposal_id": str}
  或 {"errcode": 1, "errmsg": str}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.proposal_ops import read_proposal, update_proposal_status, can_auto_apply_memory
from tools.mailbox_ops import send_mail


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--proposals-dir", required=True)
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--mailbox-dir", required=True)
    p.add_argument("--workspace-root", default="/workspace")
    args = p.parse_args()

    proposals_dir = Path(args.proposals_dir)
    proposal = read_proposal(proposals_dir, args.proposal_id)

    if proposal is None:
        print(json.dumps({"errcode": 1, "errmsg": f"提案不存在: {args.proposal_id}"}))
        return

    if proposal.type != "memory_update":
        print(json.dumps({"errcode": 1, "errmsg": "非 memory_update 类型，不能自动批准"}))
        return

    ok, reason = can_auto_apply_memory(proposal, proposals_dir, Path(args.workspace_root))
    if not ok:
        print(json.dumps({"errcode": 1, "errmsg": f"硬闸门拦截: {reason}"}))
        return

    update_proposal_status(proposals_dir, args.proposal_id, "已批准", note="memory 自动批准")

    send_mail(
        mailbox_dir=Path(args.mailbox_dir),
        to=proposal.initiator or "pm",
        from_="manager",
        type_="retro_approved",
        subject=f"提案已自动批准: {args.proposal_id}",
        content=json.dumps({"proposal_id": args.proposal_id, "action": "auto_approved"}),
    )

    print(json.dumps({
        "errcode": 0,
        "action": "approved",
        "proposal_id": args.proposal_id,
    }))


if __name__ == "__main__":
    main()
