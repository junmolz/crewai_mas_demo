---
name: self_retrospective
type: task
description: 数字员工的自我复盘 SOP。当你收到 type=retro_trigger 的邮件、或被用户要求"反思本周工作"/"自我复盘"时，立刻加载此 Skill。按 6 步 SOP 在沙盒里跑 scripts/ 读自己的日志，找出系统性改进点，产出结构化 RetroProposal，通过邮件发给 Manager 审阅。
---

# 自我复盘 SOP（PM / 任意 Agent 视角）

⚠️ 重要：通过 `skill_loader` 加载本 Skill 后，按照下面的 bash 命令**在沙盒里执行**。不要把 scripts 名当作 CrewAI Tool 直接调用。

脚本位置（沙盒内）：`/workspace/skills/self_retrospective/scripts/`
日志根目录（沙盒内）：`/mnt/shared/logs/`
Session 目录（沙盒内）：`/workspace/sessions/`
提案输出目录（沙盒内）：`/mnt/shared/proposals/`

## 安装依赖（首次使用前运行一次）

```bash
pip install filelock pydantic -q
```

## 你是谁

你是数字员工 `{agent_id}`。本次任务是对你自己过去 N 天的工作做复盘，找出系统性可改进项，产出结构化提案，通过邮件发给 Manager 审阅。

## 工作节奏（硬约束）

- **最多 12 次 ReAct 迭代**。超过则必须产出或放弃。
- **每次 bash 调用后必须先解释观察结果再决定下一步**。禁止连续跑 3 个脚本不做推理。
- **禁止一次性读入所有 L3**：永远先跑 `find_low_quality_tasks.py` 拿 id，再按需 `read_l3_steps.py --task-id xxx`。

---

## 六步 SOP

### 步骤 0 — Orient（定位）

先读触发邮件里的 `reason`，再跑本周基数：

```bash
python3 /workspace/skills/self_retrospective/scripts/stats_l2.py \
    --logs-dir /mnt/shared/logs \
    --agent-id {agent_id} \
    --days 7
```

观察项：
- `task_count < 3` → 直接退出，发一封"样本不足"的 summary 邮件
- `avg_quality` 是否显著低于历史（阈值 0.65）
- 是否有高频人类纠正（≥3 次）

### 步骤 1 — Gather Signal（定向窄拉）

**不全读，只读可疑点。**

1. 拿最差 3 条任务 id：
```bash
python3 /workspace/skills/self_retrospective/scripts/find_low_quality_tasks.py \
    --logs-dir /mnt/shared/logs \
    --agent-id {agent_id} --days 7 --top-k 3
```

2. 对每个 task_id，只读失败步骤：
```bash
python3 /workspace/skills/self_retrospective/scripts/read_l3_steps.py \
    --sessions-dir /workspace/sessions \
    --task-id <TASK_ID> --only-failed true
```

3. 关联人类纠正记录：
```bash
python3 /workspace/skills/self_retrospective/scripts/search_l1.py \
    --logs-dir /mnt/shared/logs \
    --days 7
```

### 步骤 2 — Consolidate（归因）

在你的推理中完成：
- 将步骤 1 的观察归类到 root_cause：`ability_gap / tool_defect / prompt_ambiguity / task_design`
- 每个 root_cause 最多保留 **2 条** 最具代表性的提案

### 步骤 3 — Propose（产出提案 + 精确 patch）

对每条提案，先用 propose_patch.py 生成精确 patch：
```bash
python3 /workspace/skills/self_retrospective/scripts/propose_patch.py \
    --target-file <相对路径> \
    --patch-format before_after \
    --description "简要描述要改什么"
```

然后写入 proposal.json：
```bash
python3 /workspace/skills/self_retrospective/scripts/write_proposal.py \
    --proposals-dir /mnt/shared/proposals \
    --initiator {agent_id} \
    --type <tool_fix|sop_update|soul_update|skill_add|memory_update> \
    --target <target_file> \
    --root-cause <root_cause> \
    --current "当前行为描述" \
    --proposed "期望行为描述" \
    --expected-metric "avg_quality >= 0.8" \
    --rollback-plan "回滚方案" \
    --evidence "log_id_1,log_id_2,log_id_3" \
    --priority <low|medium|high> \
    --patch-file /tmp/patch_output.json
```

### 步骤 4 — Validate（自检）

检查每条提案：
- evidence ≥ 1 条 log_id
- patches 里 target_file 不超过 5 个不同文件
- expected_metric 合理（不要写不可测的目标）

### 步骤 5 — Notify（通知 Manager）

```bash
python3 /workspace/skills/mailbox/scripts/mailbox_cli.py send \
    --mailbox-dir /mnt/shared/mailboxes \
    --to manager --from {agent_id} \
    --type retro_proposals_ready \
    --subject "自我复盘完成，{N}条提案待审阅" \
    --content "提案文件: /mnt/shared/proposals/{proposal_ids}"
```

⚠️ **不直接发 Human**。PM 只能发给 Manager，由 Manager 决定是否上报。

---

## 终止条件

- 步骤 5 邮件已发出
- 或步骤 0 判断样本不足，发 summary 邮件后退出
- 迭代次数 ≥12

## 什么不做

- ❌ 不做跨 Agent 比较（那是 Manager 的活）
- ❌ 不直接修改 Skill / soul / 代码（只能提 proposal）
- ❌ 不自评"我做得好"（提案必须指向具体改进）
- ❌ 不追问 Human（你没有交互通道）
- ❌ 不运行 `read_l3_steps.py --only-failed false`（会灌爆上下文）
