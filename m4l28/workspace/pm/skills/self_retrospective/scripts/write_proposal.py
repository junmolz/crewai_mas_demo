#!/usr/bin/env python3
"""write_proposal.py — 写入结构化 RetroProposal 到 proposals/ 目录

输出 JSON：
  {"errcode": 0, "proposal_id": str, "path": str}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from schemas import RetroProposal, ProposalPatch, ValidationCheck
from tools.proposal_ops import write_proposal


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--proposals-dir", required=True)
    p.add_argument("--initiator", required=True)
    p.add_argument("--type", required=True,
                   choices=["tool_fix", "sop_update", "soul_update", "skill_add", "memory_update"])
    p.add_argument("--target", required=True)
    p.add_argument("--root-cause", required=True,
                   choices=["ability_gap", "tool_defect", "prompt_ambiguity", "task_design"])
    p.add_argument("--current", required=True)
    p.add_argument("--proposed", required=True)
    p.add_argument("--expected-metric", required=True)
    p.add_argument("--rollback-plan", required=True)
    p.add_argument("--evidence", required=True, help="逗号分隔的 log_id 列表")
    p.add_argument("--priority", default="medium", choices=["low", "medium", "high"])
    p.add_argument("--patch-file", default=None, help="propose_patch.py 的输出 JSON 文件路径")
    args = p.parse_args()

    patches: list[ProposalPatch] = []
    if args.patch_file:
        patch_path = Path(args.patch_file)
        if patch_path.exists():
            patch_data = json.loads(patch_path.read_text(encoding="utf-8"))
            patches.append(ProposalPatch(**patch_data))

    evidence = [e.strip() for e in args.evidence.split(",") if e.strip()]

    proposal = RetroProposal(
        type=args.type,
        target=args.target,
        root_cause=args.root_cause,
        current=args.current,
        proposed=args.proposed,
        expected_metric=args.expected_metric,
        rollback_plan=args.rollback_plan,
        evidence=evidence,
        priority=args.priority,
        initiator=args.initiator,
        patches=patches,
    )

    proposal_id = f"retro_{uuid4().hex[:8]}"
    path = write_proposal(Path(args.proposals_dir), proposal, proposal_id)

    print(json.dumps({
        "errcode": 0,
        "proposal_id": proposal_id,
        "path": str(path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
