# 共享工作区访问规范

> 由 Manager 制定。所有数字员工访问共享工作区前必读。
> 本规范以 reference skill（workspace-rules）形式注入每个 Agent 的上下文。

---

## 工作区目录结构

```
/mnt/shared/
├── WORKSPACE_RULES.md      # 本文件（所有人只读）
├── mailboxes/              # 邮箱目录（通过 mailbox-ops skill 操作）
│   ├── manager.json        # Manager 邮箱
│   └── pm.json             # PM 邮箱
├── needs/                  # 需求目录
│   └── requirements.md     # 项目需求文档（Manager 写入，其他角色只读）
└── design/                 # 产品设计目录
    └── product_spec.md     # 产品规格文档（PM 写入，其他角色只读）
```

---

## 访问权限表

| 角色 | needs/ | design/ | mailboxes/ |
|------|--------|---------|-----------|
| Manager | 读写 | 只读 | 通过 mailbox-ops 读写 |
| PM | 只读 | 读写 | 通过 mailbox-ops 读写 |

**权限控制原则**：
1. 每个目录有且只有一个角色负责写入
2. 邮箱操作统一通过 `mailbox-ops` skill，不直接读写 JSON 文件
3. 跨越权限边界的操作必须通过 Manager 协调

---

## 邮箱使用规范

- 发邮件：调用 `mailbox-ops` → `send_mail`，写入对方的 `.json` 文件
- 读邮件：调用 `mailbox-ops` → `read_inbox`，读取自己的 `.json` 文件
- 邮件内容只传路径引用，不传文档全文（防止 token 浪费 + 保持邮件简洁）

---

## 工作流说明

```
Manager 读需求
    ↓
Manager 发邮件给 PM（任务分配，type: task_assign）
    ↓
PM 读邮件 → 读需求 → 写产品文档
    ↓
PM 发邮件给 Manager（任务完成，type: task_done，只写路径）
    ↓
Manager 读邮件 → 读产品文档 → 验收
```
