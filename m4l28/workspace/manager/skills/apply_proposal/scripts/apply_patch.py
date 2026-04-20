#!/usr/bin/env python3
"""apply_patch.py — 按提案中的 patches 列表机械应用 patch

支持 patch_format: before_after / append / create
（unified_diff 课后扩展，本课暂不实现）

使用 filelock 防并发。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from filelock import FileLock, Timeout

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from tools.proposal_ops import read_proposal, update_proposal_status

APPLY_LOCK = Path("/mnt/shared/.retro_apply.lock")
LOCK_TIMEOUT = 300


def _apply_single_patch(workspace_root: Path, patch_data: dict) -> dict:
    target = workspace_root / patch_data["target_file"]
    fmt = patch_data["patch_format"]
    content = patch_data["content"]

    if fmt == "before_after":
        if not target.exists():
            return {"ok": False, "error": f"文件不存在: {patch_data['target_file']}"}
        text = target.read_text(encoding="utf-8")
        before = content["before"] if isinstance(content, dict) else ""
        after = content["after"] if isinstance(content, dict) else ""
        if before not in text:
            return {"ok": False, "error": f"before 片段未找到: {before[:50]}..."}
        text = text.replace(before, after, 1)
        target.write_text(text, encoding="utf-8")
        return {"ok": True}

    if fmt == "append":
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(str(content))
        return {"ok": True}

    if fmt == "create":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        return {"ok": True}

    return {"ok": False, "error": f"不支持的 patch_format: {fmt}"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--proposals-dir", required=True)
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--workspace-root", default="/workspace")
    args = p.parse_args()

    proposals_dir = Path(args.proposals_dir)
    proposal = read_proposal(proposals_dir, args.proposal_id)
    if proposal is None:
        print(json.dumps({"errcode": 1, "errmsg": "提案不存在"}))
        return

    try:
        with FileLock(str(APPLY_LOCK), timeout=LOCK_TIMEOUT):
            results: list[dict] = []
            for patch in proposal.patches:
                r = _apply_single_patch(Path(args.workspace_root), patch.model_dump())
                results.append({**r, "target_file": patch.target_file})

            all_ok = all(r["ok"] for r in results)
            if all_ok:
                update_proposal_status(proposals_dir, args.proposal_id, "已实施")

            print(json.dumps({
                "errcode": 0 if all_ok else 3,
                "results": results,
            }, ensure_ascii=False))

    except Timeout:
        print(json.dumps({
            "errcode": 2,
            "errmsg": "apply 锁超时，请稍后重试",
        }))


if __name__ == "__main__":
    main()
