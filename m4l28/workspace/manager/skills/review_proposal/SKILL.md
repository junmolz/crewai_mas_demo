---
name: review_proposal
type: task
description: 提案审阅 SOP（Manager 专用）。当你收到 type=retro_proposals_ready 的邮件（PM 提交了复盘提案），立刻加载此 Skill。按 HITL 三档路由决定每条提案的处理方式：memory 自动落地 / skill+sop LLM 预审 / soul+code 必须人类审批。
---

# 提案审阅 SOP（Manager 视角）

⚠️ 重要：通过 `skill_loader` 加载本 Skill 后，按照下面的命令在沙盒里执行。

脚本位置（沙盒内）：`/workspace/skills/review_proposal/scripts/`
提案目录（沙盒内）：`/mnt/shared/proposals/`

## 安装依赖（首次使用前运行一次）

```bash
pip install filelock pydantic -q
```

## 你是谁

你是 Manager。PM 提交了复盘提案，你需要按三档分流决定每条提案的命运。

## 三档路由规则（硬约束）

| 提案类型 | 路由 | 说明 |
|---------|------|------|
| `memory_update` | 自动落地 | 直接批准，发 retro_approved 给 PM |
| `skill_add` / `sop_update` | LLM 预审 | 你自己审阅后决定转发 Human 或直接拒绝 |
| `soul_update` / `tool_fix` | 必须人类审批 | 直接转发给 Human，等 retro_decision |

---

## 三步 SOP

### 步骤 1 — 读取提案

```bash
python3 /workspace/skills/review_proposal/scripts/list_pending.py \
    --proposals-dir /mnt/shared/proposals
```

### 步骤 2 — 分流

对每条提案，根据 `type` 字段判断路由。

**路由 A（memory 自动落地）**：
```bash
python3 /workspace/skills/review_proposal/scripts/auto_approve.py \
    --proposals-dir /mnt/shared/proposals \
    --proposal-id <ID> \
    --mailbox-dir /mnt/shared/mailboxes
```

**路由 B（LLM 预审）**：
自己阅读提案内容，判断：
- patches 是否合理？target_file 是否存在？
- expected_metric 是否可测？
- 决定：forward（转发 Human）或 reject（拒绝）

Forward:
```bash
python3 /workspace/skills/mailbox/scripts/mailbox_cli.py send \
    --mailbox-dir /mnt/shared/mailboxes \
    --to human --from manager \
    --type retro_proposal \
    --subject "提案待审批: {proposal_id}" \
    --content "提案详情: ..."
```

Reject:
```bash
python3 /workspace/skills/review_proposal/scripts/reject_proposal.py \
    --proposals-dir /mnt/shared/proposals \
    --proposal-id <ID> \
    --reason "拒绝理由"
```

**路由 C（必须人类审批）**：
直接转发给 Human，不做预审判断。

### 步骤 3 — 汇报

所有提案处理完毕后，如有转发给 Human 的提案，不需要额外操作——等待 Human 的 retro_decision。

---

## 终止条件

- 所有待审批提案都已分流
- 迭代次数 ≥10

## 什么不做

- ❌ 不自己落地 patch（那是 apply_proposal Skill 的活）
- ❌ 不修改提案内容（只做路由决策）
