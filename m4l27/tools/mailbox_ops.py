"""
第27课·Human as 甲方
tools/mailbox_ops.py

数字员工邮箱操作：send_mail / read_inbox
在第26课基础上新增：
  - human.json 邮箱支持（human 只能作为收件人）
  - 单一接口约束：to=human 时 from_ 必须是 manager，否则 raise ValueError
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

# 允许的收件角色（to 字段）
_VALID_TO_ROLES = {"manager", "pm", "human"}

# 允许的发件角色（agent 间通信）
# human 不作为发件角色；manager 可写 human.json（单一接口约束在 send_mail 中校验）
_VALID_FROM_ROLES = {"manager", "pm"}


def _inbox_path(mailbox_dir: Path, role: str) -> Path:
    if role not in _VALID_TO_ROLES:
        raise ValueError(f"未知收件角色 '{role}'，允许值：{_VALID_TO_ROLES}")
    return mailbox_dir / f"{role}.json"


def _lock_path(inbox: Path) -> Path:
    return inbox.with_suffix(".lock")


def _read_inbox_file(inbox: Path) -> list[dict]:
    inbox.parent.mkdir(parents=True, exist_ok=True)
    if not inbox.exists():
        inbox.write_text("[]", encoding="utf-8")
        return []
    return json.loads(inbox.read_text(encoding="utf-8"))


def send_mail(
    mailbox_dir: Path,
    to: str,
    from_: str,
    type_: str,
    subject: str,
    content: str,
) -> str:
    """
    发送消息到目标角色的邮箱。

    单一接口约束：
      to=human 时，from_ 必须是 manager。
      PM / Dev 等执行层不得直接写 human.json。

    Args:
        mailbox_dir: mailboxes/ 目录路径
        to:          收件人角色（"manager" | "pm" | "human"）
        from_:       发件人角色
        type_:       消息类型（"task_assign" | "task_done" | "needs_confirm" |
                               "checkpoint_request" | "broadcast"）
        subject:     标题
        content:     正文内容

    Returns:
        新消息的唯一 ID
    """
    # ── 发件人校验 ────────────────────────────────────────────────────────────
    if from_ not in _VALID_FROM_ROLES:
        raise ValueError(
            f"未知发件角色 '{from_}'，允许值：{_VALID_FROM_ROLES}"
        )

    # ── 单一接口约束 ──────────────────────────────────────────────────────────
    if to == "human" and from_ != "manager":
        raise ValueError(
            f"单一接口约束：to=human 时 from_ 必须是 'manager'，"
            f"当前 from_='{from_}'。"
            f"执行层（PM/Dev等）只能发给 manager，由 Manager 决定是否上报给人类。"
        )

    inbox  = _inbox_path(mailbox_dir, to)
    lock   = _lock_path(inbox)
    msg_id = str(uuid.uuid4())

    message = {
        "id":        msg_id,
        "from":      from_,
        "to":        to,
        "type":      type_,
        "subject":   subject,
        "content":   content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read":      False,
    }

    with FileLock(str(lock)):
        messages = _read_inbox_file(inbox)
        messages.append(message)
        inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")

    return msg_id


def read_inbox(mailbox_dir: Path, role: str) -> list[dict]:
    """
    读取指定角色的未读消息，并将其标记为已读。

    Args:
        mailbox_dir: mailboxes/ 目录路径
        role:        目标角色（"manager" | "pm" | "human"）

    Returns:
        未读消息列表（已在文件中标记为已读）
    """
    inbox = _inbox_path(mailbox_dir, role)
    lock  = _lock_path(inbox)

    with FileLock(str(lock)):
        messages = _read_inbox_file(inbox)
        unread   = [dict(m) for m in messages if not m.get("read", False)]  # 返回拷贝
        for m in messages:
            if not m.get("read", False):
                m["read"] = True
        inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")

    return unread
