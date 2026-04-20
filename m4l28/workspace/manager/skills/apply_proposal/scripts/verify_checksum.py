#!/usr/bin/env python3
"""verify_checksum.py — 验证提案中所有 patch 的 checksum_before"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.proposal_ops import read_proposal


def _sha256(file_path: Path) -> str | None:
    if not file_path.exists():
        return None
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--proposals-dir", required=True)
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--workspace-root", default="/workspace")
    args = p.parse_args()

    proposal = read_proposal(Path(args.proposals_dir), args.proposal_id)
    if proposal is None:
        print(json.dumps({"errcode": 1, "errmsg": "提案不存在"}))
        return

    mismatches: list[dict] = []
    for patch in proposal.patches:
        if patch.checksum_before is None:
            continue
        target = Path(args.workspace_root) / patch.target_file
        actual = _sha256(target)
        if actual != patch.checksum_before:
            mismatches.append({
                "target_file": patch.target_file,
                "expected": patch.checksum_before,
                "actual": actual,
            })

    if mismatches:
        print(json.dumps({
            "errcode": 2,
            "errmsg": "checksum 不匹配，文件已被修改",
            "mismatches": mismatches,
        }, ensure_ascii=False))
    else:
        print(json.dumps({"errcode": 0, "msg": "所有 checksum 验证通过"}))


if __name__ == "__main__":
    main()
