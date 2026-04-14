#!/usr/bin/env python3
"""
memory-save: 将内容写入指定文件路径（沙盒版）

用法：
    python3 write_file.py --path <目标路径> --content <内容> [--mode w|a]

示例：
    python3 write_file.py --path /workspace/review_result.md --content "# 验收结论\n通过"
    python3 write_file.py --path /mnt/shared/design/product_spec.md --content "# 产品规格..." --mode w
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="写入文件内容到指定路径")
    parser.add_argument("--path", required=True, help="目标文件绝对路径")
    parser.add_argument("--content", required=True, help="要写入的文件内容")
    parser.add_argument("--mode", default="w", choices=["w", "a"],
                        help="写入模式：w=覆盖（默认），a=追加")
    args = parser.parse_args()

    target = Path(args.path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, args.mode, encoding="utf-8") as f:
            f.write(args.content)
        size = target.stat().st_size
        print(json.dumps({
            "errcode": 0,
            "errmsg": "success",
            "path": str(target),
            "bytes_written": size,
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({
            "errcode": 1,
            "errmsg": f"写入失败：{e}",
            "path": str(target),
        }, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
