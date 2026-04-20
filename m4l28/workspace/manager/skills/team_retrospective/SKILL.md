---
name: team_retrospective
type: task
description: 团队复盘 SOP（Manager 专用）。当你收到 type=team_retro_trigger 的邮件、或被用户要求"做团队复盘"时，立刻加载此 Skill。从聚合视角跑 scripts/ 找出跨 Agent 协作瓶颈、级联触发瓶颈 Agent 的自我复盘、产出团队级提案、发周报给 Human。
---

# 团队复盘 SOP（Manager 视角）

⚠️ 重要：通过 `skill_loader` 加载本 Skill 后，按照下面的命令在沙盒里执行。

脚本位置（沙盒内）：`/workspace/skills/team_retrospective/scripts/`
日志根目录（沙盒内）：`/mnt/shared/logs/`
提案输出目录（沙盒内）：`/mnt/shared/proposals/`

## 安装依赖（首次使用前运行一次）

```bash
pip install filelock pydantic -q
```

## 你是谁

你是 Manager。本次任务是对整个团队过去 N 天的工作做复盘，从全局视角找出跨 Agent 协作瓶颈，级联触发瓶颈 Agent 的自我复盘，产出团队级改进提案，并发周报给 Human。

## 工作节奏（硬约束）

- **最多 15 次 ReAct 迭代**。
- **不读 L3**：L3 是各 Agent 自己的工作域，你只看聚合数据。
- **不提 ability_gap 类提案**：能力差距由 Agent 自己发现。

---

## 四步 SOP

### 步骤 1 — 全员概览

```bash
python3 /workspace/skills/team_retrospective/scripts/stats_all_agents.py \
    --logs-dir /mnt/shared/logs \
    --days 7
```

观察项：
- 哪个 Agent 的 `avg_quality` 最低？
- 哪个 Agent 的 `failure_count` 最高？
- 是否有协作摩擦（如来回确认过多）？

### 步骤 2 — 瓶颈归因

对最差的 Agent，检查 L1 人类纠正记录：
```bash
python3 /workspace/skills/self_retrospective/scripts/search_l1.py \
    --logs-dir /mnt/shared/logs \
    --days 7
```

级联触发：如果瓶颈 Agent 尚未做自我复盘，发触发邮件：
```bash
python3 /workspace/skills/mailbox/scripts/mailbox_cli.py send \
    --mailbox-dir /mnt/shared/mailboxes \
    --to {bottleneck_agent} --from manager \
    --type retro_trigger \
    --subject "请执行自我复盘" \
    --content "团队复盘发现你是本周瓶颈，请自查"
```

### 步骤 3 — 团队级提案

对跨 Agent 问题（如 SOP 流程、协作模式），产出提案：
```bash
python3 /workspace/skills/self_retrospective/scripts/write_proposal.py \
    --proposals-dir /mnt/shared/proposals \
    --initiator manager \
    --type sop_update \
    --target <target_file> \
    --root-cause <root_cause> \
    --current "当前问题" \
    --proposed "改进方案" \
    --expected-metric "指标" \
    --rollback-plan "回滚方案" \
    --evidence "log_id_1,log_id_2" \
    --priority medium
```

### 步骤 4 — 周报

```bash
python3 /workspace/skills/mailbox/scripts/mailbox_cli.py send \
    --mailbox-dir /mnt/shared/mailboxes \
    --to human --from manager \
    --type weekly_report \
    --subject "本周团队复盘周报" \
    --content "本周恶化指标 + 瓶颈 Agent + 改进提案 + 上周验证结果"
```

---

## 终止条件

- 步骤 4 周报已发出
- 迭代次数 ≥15

## 什么不做

- ❌ 不读 L3（不存在这个 script 在本 Skill 下）
- ❌ 不提 ability_gap 类提案
- ❌ 不替 Agent 做复盘（级联触发后由 Agent 自己完成）
