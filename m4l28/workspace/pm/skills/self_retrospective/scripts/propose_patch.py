#!/usr/bin/env python3
"""propose_patch.py — 生成精确 patch（含 SHA256 checksum_before）

v6 关键脚本：LLM 只决定"改什么"，本脚本构造精确 patch。

输入参数：
  --target-file    相对于 workspace 根的文件路径
  --patch-format   unified_diff | before_after | append | create
  --description    简要描述（仅用于日志，不影响 patch 内容）
  --before         before_after 模式的 before 文本（可选）
  --after          before_after 模式的 after 文本（可选）
  --append-text    append 模式的追加内容（可选）
  --create-text    create 模式的文件内容（可选）

输出 JSON：
  {"target_file": str, "patch_format": str, "content": str|dict,
   "checksum_before": str|null}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _sha256(file_path: Path) -> str | None:
    if not file_path.exists():
        return None
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target-file", required=True)
    p.add_argument("--patch-format", required=True,
                   choices=["unified_diff", "before_after", "append", "create"])
    p.add_argument("--description", default="")
    p.add_argument("--before", default=None)
    p.add_argument("--after", default=None)
    p.add_argument("--append-text", default=None)
    p.add_argument("--create-text", default=None)
    p.add_argument("--workspace-root", default="/workspace")
    args = p.parse_args()

    target = Path(args.workspace_root) / args.target_file
    checksum = _sha256(target)

    if args.patch_format == "before_after":
        if not args.before or not args.after:
            print(json.dumps({"errcode": 1, "errmsg": "before_after 模式需要 --before 和 --after"}))
            sys.exit(0)
        content = {"before": args.before, "after": args.after}
    elif args.patch_format == "append":
        content = args.append_text or ""
    elif args.patch_format == "create":
        content = args.create_text or ""
    else:
        content = ""

    result = {
        "target_file": args.target_file,
        "patch_format": args.patch_format,
        "content": content,
        "checksum_before": checksum,
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
