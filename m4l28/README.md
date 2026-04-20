# 第28课：数字员工的自我进化

本课在第27课四步任务链基础上，新增**三层日志系统**和**两种复盘机制**，让数字团队越用越好。

> **核心教学点**：三层日志（L1/L2/L3）、复盘即 Skill（Agent 读邮件 → 加载 Skill → 生成提案）、Scheduler 双条件触发、三档 HITL 审批、Pydantic Schema 约束、ProposalPatch + 校验和 + blast_radius ≤ 5

---

## 目录结构

```
m4l28/
├── main.py                       # Manager 入口（v3 DigitalWorkerCrew）
├── start_pm.py                   # PM 入口（v3 DigitalWorkerCrew）
├── run.py                        # 端到端演示脚本（四步任务链 + 日志 + Scheduler 触发）
├── schemas.py                    # Pydantic 模型（L2LogRecord / ProposalPatch / ValidationCheck / RetroProposal）
├── seed_logs.py                  # 预置7天模拟历史日志（L2 + L3 session + L1）
├── scheduler.py                  # 极薄 Scheduler（≤40 行有效代码，双条件判断）
├── run_validation.py             # 周期验证 + 48h 僵尸态巡检
├── hooks/
│   ├── __init__.py               # 导出 make_l2_task_callback
│   └── l2_task_callback.py       # L2 日志 task_callback 工厂（CrewAI hook）
├── tools/
│   ├── mailbox_ops.py            # 邮箱操作（to=human 自动写 L1 + type 白名单校验）
│   ├── log_ops.py                # 三层日志读写（L1 只读 / L2 读写 / L3 读写+清理 + session 索引）
│   └── proposal_ops.py           # 提案 CRUD + 状态机 + can_auto_apply_memory 硬门控
├── sandbox-docker-compose.yaml   # 双沙盒（Manager:8027, PM:8028）
├── test_m4l28.py                 # 单元测试（34 tests）
├── test_m4l28_integration.py     # 集成测试（需要 ALIYUN_API_KEY + Docker 沙盒）
├── conftest.py                   # pytest fixtures + 模块解析
└── workspace/
    ├── manager/                  # Manager workspace（soul + agent + skills）
    │   └── skills/
    │       ├── team_retrospective/   # 团队复盘 Skill（全员概览→瓶颈归因→提案→周报）
    │       ├── review_proposal/      # 提案审阅 Skill（三档路由：memory/skill+sop/soul+code）
    │       └── apply_proposal/       # 补丁落地 Skill（机械操作，不调 LLM）
    ├── pm/                       # PM workspace（soul + agent + skills）
    │   └── skills/
    │       ├── self_retrospective/   # 自我复盘 Skill（6步 SOP + 7个脚本）
    │       └── apply_proposal/       # 补丁落地 Skill（与 Manager 共享）
    └── shared/
        ├── mailboxes/            # 邮箱（manager.json / pm.json / human.json）
        ├── sop/                  # SOP 模板
        ├── logs/                 # 三层日志（运行时生成）
        │   ├── l1_human/         # L1：send_mail(to=human) 自动写入
        │   ├── l2_task/          # L2：task_callback hook 自动写入
        │   └── l3_react/         # L3（旧格式）：seed_logs 预置
        └── proposals/            # 改进提案（复盘后生成，每个提案一个 JSON 文件）
```

---

## 架构设计

### v3 DigitalWorkerCrew（与 m4l25-m4l27 一致）

| 维度 | 说明 |
|------|------|
| 框架类 | `DigitalWorkerCrew`（通用，零角色特异性代码） |
| 角色身份 | 由 `workspace/{role}/soul.md + agent.md` 驱动 |
| 通信 | mailbox Skill（CLI in Docker sandbox） |
| 模型 | `glm-5.1` |

### 第28课新增：复盘即 Skill

v6 的核心设计：复盘不是 Python 函数，而是 **Skill**。Agent 收到 `retro_trigger` 邮件后，加载对应 Skill，在沙盒中执行复盘脚本。

| 机制 | 主体 | 触发方式 | Skill | 输出 |
|------|------|---------|-------|------|
| 自我复盘 | 每个 Agent | Scheduler → retro_trigger 邮件 | self_retrospective | RetroProposal JSON → retro_proposals_ready 邮件 |
| 团队复盘 | Manager | Scheduler → team_retro_trigger 邮件 | team_retrospective | 周报 → human.json + 瓶颈级联触发 |
| 提案审阅 | Manager | retro_proposals_ready 邮件 | review_proposal | 三档路由（auto/LLM预审/Human必审） |
| 补丁落地 | Agent | retro_approved 邮件 | apply_proposal | 校验和验证 → 应用补丁 → git commit |

### Scheduler 双条件触发

```
tick() 每次执行：
  for agent in (pm, manager):
    ① 距离上次复盘 >= 24h？  否 → 跳过
    ② 最近24h L2 任务数 >= 5？ 否 → 跳过
    ③ 发送 retro_trigger / team_retro_trigger 邮件
```

### 三档 HITL 审批

| 档位 | 提案类型 | 审批路径 | 硬门控 |
|------|---------|---------|--------|
| Tier 1 | memory_update | Manager 自动批准 | 3条/天/Agent，目标文件 ≤200行 |
| Tier 2 | skill_add / sop_update | Manager LLM预审 → Human | blast_radius ≤ 5 |
| Tier 3 | soul_update / tool_fix | 直接转 Human | 必须 Dry Run |

---

## 快速开始

### 步骤 0：清理环境（支持重跑）

```bash
cd /path/to/crewai_mas_demo/m4l28

# 重置邮箱
echo '[]' > workspace/shared/mailboxes/manager.json
echo '[]' > workspace/shared/mailboxes/pm.json
echo '[]' > workspace/shared/mailboxes/human.json

# 清理运行时产出
rm -rf workspace/shared/logs workspace/shared/proposals
rm -f workspace/shared/design/product_spec.md
rm -f workspace/shared/needs/requirements.md
rm -f workspace/manager/review_result.md
rm -rf workspace/manager/sessions workspace/pm/sessions
rm -f workspace/shared/.last_retro.json
```

### 步骤 1：启动沙盒

```bash
docker compose -f sandbox-docker-compose.yaml up -d

# 等待沙盒就绪
curl -s -o /dev/null -w '%{http_code}' http://localhost:8027/   # Manager → 200
curl -s -o /dev/null -w '%{http_code}' http://localhost:8028/   # PM → 200
```

### 步骤 2：端到端演示

```bash
export ALIYUN_API_KEY=sk-xxx
python3 run.py "帮我设计一个宠物健康记录App，支持多宠物管理和疫苗提醒"
```

演示流程：
1. Manager 需求澄清 → [人工确认]
2. Manager 分配任务给 PM
3. PM 撰写产品文档 → [人工确认 Checkpoint]
4. Manager 验收
5. 预置历史日志（模拟运行7天：PM 8条 L2 含3条低质量 + L3 session + L1 人类纠正3条）
6. Scheduler.tick() 检查双条件 → 发 retro_trigger 邮件

### 步骤 3：运行测试

```bash
# 单元测试（34 tests，不需要 API Key）
python3 -m pytest test_m4l28.py -v

# 集成测试（需要 ALIYUN_API_KEY + Docker 沙盒）
ALIYUN_API_KEY=sk-xxx python3 -m pytest test_m4l28_integration.py -v -s -m integration
```

### 步骤 4：查看产出

```bash
# 三层日志
ls workspace/shared/logs/l1_human/    # L1：人类纠正记录
ls workspace/shared/logs/l2_task/     # L2：任务质量记录
ls workspace/shared/logs/l3_react/    # L3（旧格式）：ReAct 步骤

# Session 日志（v6 格式 = L3）
cat workspace/pm/sessions/index.jsonl

# Scheduler 状态
cat workspace/shared/.last_retro.json

# 邮箱（包含 retro_trigger 邮件）
cat workspace/shared/mailboxes/pm.json | python3 -m json.tool
```

---

## 三层日志

| 层级 | 写入方式 | 路径 | 用途 |
|------|---------|------|------|
| L1 | `send_mail(to="human")` 自动写入（AOP） | `logs/l1_human/{msg_id}.json` | 人类纠正记录（最有价值） |
| L2 | `task_callback` hook 自动写入 | `logs/l2_task/{agent}_{task}.json` | 任务质量、耗时、异常 |
| L3 | 复用 `DigitalWorkerCrew.append_session_raw` | `{agent}/sessions/{session}_raw.jsonl` + `index.jsonl` | ReAct 每步推理-行动（零重复写入） |

---

## 改进提案 Schema（v6）

```python
class RetroProposal(BaseModel):
    type:            Literal["tool_fix", "sop_update", "soul_update", "skill_add", "memory_update"]
    target:          str
    root_cause:      Literal["ability_gap", "tool_defect", "prompt_ambiguity", "task_design"]
    current:         str
    proposed:        str
    expected_metric: str      # 不允许为空
    rollback_plan:   str
    evidence:        list[str]   # 至少1条
    priority:        Literal["low", "medium", "high"]
    patches:         list[ProposalPatch] = []   # blast_radius ≤ 5
    validation_check: ValidationCheck | None = None
    status:          Literal["待审批","LLM预审中","已批准","已拒绝","已实施","验证中","已验证","已回滚"] = "待审批"

class ProposalPatch(BaseModel):
    target_file:     str          # 不允许为空
    patch_format:    Literal["unified_diff", "before_after", "append", "create"]
    content:         str | dict
    checksum_before: str | None = None   # SHA256

class ValidationCheck(BaseModel):
    script:    Literal["stats_l2", "find_low_quality_tasks", "tool_call_stats", "stats_all_agents"]
    args:      dict
    metric:    str
    op:        Literal[">=", "<=", ">", "<", "==", "!="]
    threshold: float
```
