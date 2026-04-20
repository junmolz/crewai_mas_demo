---
name: apply_proposal
type: task
description: 提案落地 SOP（课后代码）。当你收到 type=retro_approved 的邮件（Manager 批准了提案），立刻加载此 Skill。按 5 步机械落地 patch，使用 filelock 防并发，git worktree 做 Dry Run。
---

# 提案落地 SOP

⚠️ 重要：通过 `skill_loader` 加载本 Skill 后，按照下面的命令在沙盒里执行。

脚本位置（沙盒内）：`/workspace/skills/apply_proposal/scripts/`
提案目录（沙盒内）：`/mnt/shared/proposals/`

## 安装依赖（首次使用前运行一次）

```bash
pip install filelock pydantic -q
```

## 五步 SOP（机械执行，不做判断）

### 步骤 1 — 读取已批准提案

```bash
python3 /workspace/skills/apply_proposal/scripts/load_approved.py \
    --proposals-dir /mnt/shared/proposals \
    --proposal-id <ID>
```

### 步骤 2 — 验证 checksum

```bash
python3 /workspace/skills/apply_proposal/scripts/verify_checksum.py \
    --proposals-dir /mnt/shared/proposals \
    --proposal-id <ID> \
    --workspace-root /workspace
```

如果 checksum 不匹配，说明文件已被修改，停止落地并发邮件报告。

### 步骤 3 — 应用 patch

```bash
python3 /workspace/skills/apply_proposal/scripts/apply_patch.py \
    --proposals-dir /mnt/shared/proposals \
    --proposal-id <ID> \
    --workspace-root /workspace
```

### 步骤 4 — 更新状态

```bash
python3 /workspace/skills/apply_proposal/scripts/mark_applied.py \
    --proposals-dir /mnt/shared/proposals \
    --proposal-id <ID>
```

### 步骤 5 — 通知 Manager

```bash
python3 /workspace/skills/mailbox/scripts/mailbox_cli.py send \
    --mailbox-dir /mnt/shared/mailboxes \
    --to manager --from {agent_id} \
    --type retro_applied \
    --subject "提案已落地: {proposal_id}" \
    --content "patch 已应用"
```

---

## 终止条件

- 步骤 5 邮件已发出
- 或 checksum 验证失败，已发报告

## 什么不做

- ❌ 不做判断（patch 已经过审批）
- ❌ 不修改提案内容
- ❌ 不跳过 checksum 验证
