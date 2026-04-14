---
name: mailbox-ops
description: >
  数字员工邮箱操作：向指定角色的邮箱发送消息（send_mail），
  或读取自己邮箱中的未读消息（read_inbox）。
  邮箱文件位于共享工作区 /mnt/shared/mailboxes/。
  适用场景：Manager 向 PM/Dev/QA 分配任务、发完成通知、广播消息；
  各角色读取自己的未读任务邮件。
type: task
---

# mailbox-ops Skill

## 功能概述

本 Skill 提供数字员工之间的邮箱通信能力，包含两个操作：
1. **send_mail**：向指定角色的邮箱发送消息
2. **read_inbox**：读取自己邮箱中的未读消息（并标记为已读）

邮箱文件路径：`/mnt/shared/mailboxes/{role}.json`（已挂载到沙盒）

## 操作规范

### send_mail — 发送消息

**脚本路径**：`/mnt/skills/mailbox-ops/scripts/mailbox_ops.py`

**调用方式**：

```bash
# 先确保 filelock 已安装
pip install filelock -q

# 调用 send_mail
python3 /mnt/skills/mailbox-ops/scripts/mailbox_ops.py send_mail \
  --mailbox-dir /mnt/shared/mailboxes \
  --to pm \
  --from manager \
  --type task_assign \
  --subject "产品文档设计" \
  --content "请根据 /mnt/shared/needs/requirements.md 设计产品规格文档，完成后写入 /mnt/shared/design/product_spec.md，并发邮件通知我验收"
```

**参数说明**：
- `--mailbox-dir`：邮箱目录路径（固定为 `/mnt/shared/mailboxes`）
- `--to`：收件人角色，允许值：`manager` | `pm` | `dev` | `qa`
- `--from`：发件人角色（即你自己的角色）
- `--type`：消息类型
  - `task_assign`：任务分配（Manager 发给执行者）
  - `task_done`：任务完成通知（执行者发给 Manager）
  - `broadcast`：广播通知（发给多个角色时逐个调用）
- `--subject`：邮件标题（简短，15 字以内）
- `--content`：邮件正文（包含任务描述、文档路径等）

**输出格式**（JSON）：
```json
{
  "errcode": 0,
  "errmsg": "success",
  "msg_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

### read_inbox — 读取未读消息

**调用方式**：

```bash
pip install filelock -q

python3 /mnt/skills/mailbox-ops/scripts/mailbox_ops.py read_inbox \
  --mailbox-dir /mnt/shared/mailboxes \
  --role pm
```

**参数说明**：
- `--mailbox-dir`：邮箱目录路径（固定为 `/mnt/shared/mailboxes`）
- `--role`：你自己的角色（读取自己的邮箱）

**输出格式**（JSON）：
```json
{
  "errcode": 0,
  "errmsg": "success",
  "messages": [
    {
      "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "from": "manager",
      "to": "pm",
      "type": "task_assign",
      "subject": "产品文档设计",
      "content": "请根据需求文档...",
      "timestamp": "2026-04-10T10:00:00+00:00",
      "read": false
    }
  ]
}
```

**注意**：read_inbox 读取后会自动将所有返回消息标记为已读（幂等保护）。

## ⚠️ 强制执行要求（CRITICAL）

**你必须通过 `sandbox_execute_bash` 实际运行 Python 脚本。**
- 禁止直接返回任何"成功"输出，必须先执行脚本再读取脚本的实际输出
- 禁止根据 task_context 中的 `expected_output` 字段猜测结果
- 执行后必须读取脚本输出的 JSON（含 errcode），将其原文包含在回复中
- 若脚本报错（errcode != 0），必须如实汇报，不得篡改结果

## 错误处理

- 若 `--to` 或 `--role` 不在允许列表（manager/pm/dev/qa），输出 errcode=1
- 若邮箱文件不存在，自动创建空邮箱后继续（不报错）
- 若 filelock 获取超时（默认 10 秒），输出 errcode=2，errmsg 说明原因
