"""
第26课·任务链与信息传递
m4l26_mailbox/mailbox_ops.py

数字员工邮箱操作：send_mail / read_inbox / mark_done / reset_stale

核心教学点（对应 P5/P6/P7）：
  - 消息三态状态机：unread → in_progress → done
      unread:      消息写入，尚未被任何 Agent 取走
      in_progress: 已被取走，正在处理（read_inbox 原子标记）
      done:        处理完成，由编排器或 Agent 调用 mark_done 确认
  - 为什么不在 read_inbox 直接标 done？
      因为 Agent 在取走消息后可能崩溃——消息已被取走但未被处理。
      先标 in_progress，成功后再标 done，崩溃时通过 reset_stale 恢复。
      这与 AWS SQS Visibility Timeout 思路完全相同。
  - 文件锁（filelock）保护并发写入：所有 read-modify-write 在同一锁内完成
  - processing_since：记录进入 in_progress 的时间，供 reset_stale 计算超时
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

# ── 状态常量 ──────────────────────────────────────────────────────────────────
STATUS_UNREAD      = "unread"       # 新写入，等待被取
STATUS_IN_PROGRESS = "in_progress"  # 已取走，正在处理
STATUS_DONE        = "done"         # 处理完成

# 允许的角色名（防止 LLM 幻觉注入非法路径）
_VALID_ROLES = {"manager", "pm"}


# ── 内部辅助 ──────────────────────────────────────────────────────────────────

def _inbox_path(mailbox_dir: Path, role: str) -> Path:
    """返回指定角色的邮箱文件路径"""
    if role not in _VALID_ROLES:
        raise ValueError(f"未知角色 '{role}'，允许值：{_VALID_ROLES}")
    return mailbox_dir / f"{role}.json"


def _lock_path(inbox: Path) -> Path:
    return inbox.with_suffix(".lock")


def _read_inbox_file(inbox: Path) -> list[dict]:
    """读取邮箱文件；文件不存在时自动初始化为空列表"""
    inbox.parent.mkdir(parents=True, exist_ok=True)
    if not inbox.exists():
        inbox.write_text("[]", encoding="utf-8")
        return []
    return json.loads(inbox.read_text(encoding="utf-8"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 核心操作 ──────────────────────────────────────────────────────────────────

def send_mail(
    mailbox_dir: Path,
    to: str,
    from_: str,
    type_: str,
    subject: str,
    content: str,
) -> str:
    """
    发送消息到目标角色的邮箱（写入 status="unread"）。

    所有读写操作在同一 FileLock 块内完成，消除 last-write-wins 竞争。

    Args:
        mailbox_dir: mailboxes/ 目录路径
        to:          收件人角色（"manager" | "pm"）
        from_:       发件人角色
        type_:       消息类型（"task_assign" | "task_done" | "broadcast"）
        subject:     标题
        content:     正文（只传路径引用，不复制文档全文）

    Returns:
        新消息的唯一 ID
    """
    inbox  = _inbox_path(mailbox_dir, to)
    lock   = _lock_path(inbox)
    msg_id = str(uuid.uuid4())

    message = {
        "id":               msg_id,
        "from":             from_,
        "to":               to,
        "type":             type_,
        "subject":          subject,
        "content":          content,
        "timestamp":        _now_iso(),
        "status":           STATUS_UNREAD,   # ← 三态起点：unread
        "processing_since": None,            # ← 进入 in_progress 时填写
    }

    with FileLock(str(lock)):
        messages = _read_inbox_file(inbox)
        messages.append(message)
        inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    return msg_id


def read_inbox(
    mailbox_dir: Path,
    role: str,
) -> list[dict]:
    """
    取走指定角色的 unread 消息，原子标记为 in_progress。

    教学重点（对应 P7）：
    - 此处不标 done——Agent 可能取走消息后崩溃。
    - 标 in_progress 让并发的轮询器跳过本消息（互斥）。
    - 成功处理后，由编排器调用 mark_done 完成确认（显式二步提交）。

    Args:
        mailbox_dir: mailboxes/ 目录路径
        role:        角色名（"manager" | "pm"）

    Returns:
        原本处于 unread 状态的消息快照列表（现已变为 in_progress）
    """
    inbox = _inbox_path(mailbox_dir, role)
    lock  = _lock_path(inbox)

    with FileLock(str(lock)):
        messages = _read_inbox_file(inbox)
        # 快照 unread 消息（副本），防止调用方意外修改原始数据
        unread = [dict(m) for m in messages if m.get("status") == STATUS_UNREAD]
        # 原位标记 in_progress
        now = _now_iso()
        for m in messages:
            if m.get("status") == STATUS_UNREAD:
                m["status"]           = STATUS_IN_PROGRESS
                m["processing_since"] = now
        inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    return unread


def mark_done(
    mailbox_dir: Path,
    role: str,
    msg_ids: list[str],
) -> int:
    """
    将指定消息标记为 done（处理完成确认）。

    调用时机：编排器在 Crew.kickoff() 成功返回后调用，
    确认这批消息已被可靠处理——对应 SQS 的 DeleteMessage。

    Args:
        mailbox_dir: mailboxes/ 目录路径
        role:        角色名（"manager" | "pm"）
        msg_ids:     需要确认完成的消息 ID 列表

    Returns:
        实际标记为 done 的消息数量
    """
    inbox   = _inbox_path(mailbox_dir, role)
    lock    = _lock_path(inbox)
    id_set  = set(msg_ids)
    count   = 0

    with FileLock(str(lock)):
        messages = _read_inbox_file(inbox)
        for m in messages:
            if m.get("id") in id_set and m.get("status") == STATUS_IN_PROGRESS:
                m["status"] = STATUS_DONE
                count += 1
        inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    return count


def mark_done_all_in_progress(
    mailbox_dir: Path,
    role: str,
) -> int:
    """
    将该角色邮箱中所有 in_progress 消息标记为 done。

    便捷版 mark_done，供顺序演示场景使用：
    当编排器确认某角色的 Crew 已成功完成，直接全量确认，
    无需跟踪具体 msg_id。

    Returns:
        实际标记为 done 的消息数量
    """
    inbox = _inbox_path(mailbox_dir, role)
    lock  = _lock_path(inbox)
    count = 0

    with FileLock(str(lock)):
        messages = _read_inbox_file(inbox)
        for m in messages:
            if m.get("status") == STATUS_IN_PROGRESS:
                m["status"] = STATUS_DONE
                count += 1
        inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    return count


def reset_stale(
    mailbox_dir: Path,
    role: str,
    timeout_seconds: int = 900,
) -> int:
    """
    将超时未完成的 in_progress 消息恢复为 unread（崩溃恢复）。

    调用场景：后台 Watchdog 定期巡检，发现某条消息在
    in_progress 状态停留超过 timeout_seconds 秒，说明
    处理该消息的 Agent 已崩溃，将消息重置为可重新处理的 unread。

    对应 AWS SQS Visibility Timeout 到期后消息重新可见的机制。

    Args:
        mailbox_dir:      mailboxes/ 目录路径
        role:             角色名（"manager" | "pm"）
        timeout_seconds:  超时阈值（默认 900 秒 = 15 分钟）

    Returns:
        实际重置的消息数量
    """
    inbox = _inbox_path(mailbox_dir, role)
    lock  = _lock_path(inbox)
    count = 0
    now   = datetime.now(timezone.utc)

    with FileLock(str(lock)):
        messages = _read_inbox_file(inbox)
        for m in messages:
            if m.get("status") != STATUS_IN_PROGRESS:
                continue
            since_str = m.get("processing_since")
            if not since_str:
                # processing_since 未记录，保守处理：直接重置
                m["status"]           = STATUS_UNREAD
                m["processing_since"] = None
                count += 1
                continue
            since = datetime.fromisoformat(since_str)
            if (now - since).total_seconds() >= timeout_seconds:
                m["status"]           = STATUS_UNREAD
                m["processing_since"] = None
                count += 1
        inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    return count
