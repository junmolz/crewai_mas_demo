"""
mailbox-ops Skill 脚本
用于数字员工之间的邮箱通信（send_mail / read_inbox）

在 AIO-Sandbox 中通过命令行调用：
  python3 mailbox_ops.py send_mail --mailbox-dir /mnt/shared/mailboxes --to pm --from manager ...
  python3 mailbox_ops.py read_inbox --mailbox-dir /mnt/shared/mailboxes --role pm
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from filelock import FileLock, Timeout as FileLockTimeout
    _HAS_FILELOCK = True
except ImportError:
    _HAS_FILELOCK = False

_VALID_ROLES = {"manager", "pm", "dev", "qa"}
_LOCK_TIMEOUT = 10  # 秒


def _ok(data: dict) -> None:
    print(json.dumps({"errcode": 0, "errmsg": "success", **data}, ensure_ascii=False))


def _err(code: int, msg: str) -> None:
    print(json.dumps({"errcode": code, "errmsg": msg}, ensure_ascii=False))
    sys.exit(1)


def _inbox_path(mailbox_dir: Path, role: str) -> Path:
    return mailbox_dir / f"{role}.json"


def _lock_path(inbox: Path) -> Path:
    return inbox.with_suffix(".lock")


def _read_file(inbox: Path) -> list[dict]:
    """读取邮箱文件，不存在时自动创建"""
    inbox.parent.mkdir(parents=True, exist_ok=True)
    if not inbox.exists():
        inbox.write_text("[]", encoding="utf-8")
        return []
    return json.loads(inbox.read_text(encoding="utf-8"))


def cmd_send_mail(args: argparse.Namespace) -> None:
    mailbox_dir = Path(args.mailbox_dir)
    to = args.to.lower()
    from_ = getattr(args, "from").lower()

    if to not in _VALID_ROLES:
        _err(1, f"无效的收件人角色 '{to}'，允许值：{_VALID_ROLES}")
    if from_ not in _VALID_ROLES:
        _err(1, f"无效的发件人角色 '{from_}'，允许值：{_VALID_ROLES}")

    inbox = _inbox_path(mailbox_dir, to)
    lock  = _lock_path(inbox)
    msg_id = str(uuid.uuid4())

    message = {
        "id":        msg_id,
        "from":      from_,
        "to":        to,
        "type":      args.type,
        "subject":   args.subject,
        "content":   args.content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read":      False,
    }

    if _HAS_FILELOCK:
        try:
            with FileLock(str(lock), timeout=_LOCK_TIMEOUT):
                messages = _read_file(inbox)
                messages.append(message)
                inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        except FileLockTimeout:
            _err(2, f"获取文件锁超时（>{_LOCK_TIMEOUT}s），请稍后重试")
    else:
        # filelock 未安装时降级为非并发安全写入（教学演示用）
        messages = _read_file(inbox)
        messages.append(message)
        inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    _ok({"msg_id": msg_id})


def cmd_read_inbox(args: argparse.Namespace) -> None:
    mailbox_dir = Path(args.mailbox_dir)
    role = args.role.lower()

    if role not in _VALID_ROLES:
        _err(1, f"无效的角色 '{role}'，允许值：{_VALID_ROLES}")

    inbox = _inbox_path(mailbox_dir, role)
    lock  = _lock_path(inbox)

    if _HAS_FILELOCK:
        try:
            with FileLock(str(lock), timeout=_LOCK_TIMEOUT):
                messages = _read_file(inbox)
                unread = [dict(m) for m in messages if not m["read"]]
                for m in messages:
                    if not m["read"]:
                        m["read"] = True
                inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        except FileLockTimeout:
            _err(2, f"获取文件锁超时（>{_LOCK_TIMEOUT}s），请稍后重试")
    else:
        messages = _read_file(inbox)
        unread = [dict(m) for m in messages if not m["read"]]
        for m in messages:
            if not m["read"]:
                m["read"] = True
        inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    _ok({"messages": unread})


def main() -> None:
    parser = argparse.ArgumentParser(description="mailbox-ops: 数字员工邮箱操作")
    sub = parser.add_subparsers(dest="command")

    # send_mail 子命令
    p_send = sub.add_parser("send_mail", help="发送消息到指定角色的邮箱")
    p_send.add_argument("--mailbox-dir",  required=True, help="邮箱目录路径")
    p_send.add_argument("--to",           required=True, help="收件人角色")
    p_send.add_argument("--from",         required=True, dest="from", help="发件人角色")
    p_send.add_argument("--type",         required=True, help="消息类型（task_assign/task_done/broadcast）")
    p_send.add_argument("--subject",      required=True, help="邮件标题")
    p_send.add_argument("--content",      required=True, help="邮件正文")

    # read_inbox 子命令
    p_read = sub.add_parser("read_inbox", help="读取自己邮箱中的未读消息")
    p_read.add_argument("--mailbox-dir",  required=True, help="邮箱目录路径")
    p_read.add_argument("--role",         required=True, help="自己的角色")

    args = parser.parse_args()

    if args.command == "send_mail":
        cmd_send_mail(args)
    elif args.command == "read_inbox":
        cmd_read_inbox(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
