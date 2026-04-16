# 第28课：数字员工的自我进化

本课在第27课四步任务链基础上，新增**三层日志系统**和**两种复盘机制**，让数字团队越用越好。

> **核心教学点**：三层日志（L1/L2/L3）、自我复盘（直接 LLM 调用 + Pydantic 校验）、团队复盘（聚合统计 + 瓶颈识别）、人工审批门控

---

## 目录结构

```
m4l28/
├── main.py                       # Manager 入口（v3 DigitalWorkerCrew）
├── start_pm.py                   # PM 入口（v3 DigitalWorkerCrew）
├── run.py                        # 端到端演示脚本（四步任务链 + 日志 + 复盘）
├── schemas.py                    # Pydantic 模型（L2LogRecord + RetroProposal）
├── seed_logs.py                  # 预置7天模拟历史日志
├── retro/
│   ├── self_retrospective.py     # Agent 自我复盘（直接 LLM 调用，不走 CrewAI）
│   └── team_retrospective.py     # Manager 团队复盘（直接 LLM 调用）
├── tools/
│   ├── mailbox_ops.py            # 邮箱操作（新增：to=human 时自动写 L1 日志）
│   └── log_ops.py                # 三层日志读写（L1 只读 / L2 读写 / L3 读写+清理）
├── sandbox-docker-compose.yaml   # 双沙盒（Manager:8027, PM:8028）
├── test_m4l28.py                 # 单元测试（16 tests）
├── test_m4l28_integration.py     # 集成测试（需要 ALIYUN_API_KEY）
├── conftest.py                   # pytest fixtures
└── workspace/
    ├── manager/                  # Manager workspace（soul + agent + skills）
    ├── pm/                       # PM workspace（soul + agent + skills）
    └── shared/
        ├── mailboxes/            # 邮箱（manager.json / pm.json / human.json）
        ├── sop/                  # SOP 模板
        ├── logs/                 # 三层日志（运行时生成）
        │   ├── l1_human/         # L1：send_mail(to=human) 自动写入
        │   ├── l2_task/          # L2：run.py 手动写入
        │   └── l3_react/         # L3：seed_logs 预置
        └── proposals/            # 改进提案（复盘后生成）
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

### 第28课新增：复盘机制

复盘是"元操作"——分析已完成任务，不是执行新任务，所以**不走 CrewAI Crew，直接调用 LLM**。

| 机制 | 主体 | 数据源 | 输出 |
|------|------|--------|------|
| 自我复盘 | 每个 Agent | L2 + L3 + L1 | 改进提案 → proposals.json + human.json |
| 团队复盘 | Manager | L1 全量 + 所有 Agent L2 | 周报 + 瓶颈触发 → human.json |

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
```

### 步骤 1：启动沙盒

```bash
docker compose -f sandbox-docker-compose.yaml up -d

# 等待沙盒就绪
curl -s -o /dev/null -w '%{http_code}' http://localhost:8027/   # Manager → 200
curl -s -o /dev/null -w '%{http_code}' http://localhost:8028/   # PM → 200
```

### 步骤 2：端到端演示（推荐）

```bash
export ALIYUN_API_KEY=sk-xxx   # 复盘需要调用 LLM
python3 run.py "帮我设计一个宠物健康记录App，支持多宠物管理和疫苗提醒"
```

演示流程：
1. Manager 需求澄清 → [人工确认]
2. Manager 分配任务给 PM
3. PM 撰写产品文档 → [人工确认 Checkpoint]
4. Manager 验收
5. 写入 PM 的 L2 日志
6. 预置历史日志（模拟运行7天）
7. PM 自我复盘 → 生成改进提案
8. Manager 团队复盘 → 识别瓶颈 + 发周报

### 步骤 2b：分步运行（三终端）

```bash
# Terminal 1 — Manager
python3 main.py "帮我设计一个宠物健康记录App"

# Terminal 2 — Human 确认
python3 human_cli.py

# Terminal 1 — Manager 继续
python3 main.py "需求已确认，请选择 SOP 并分配任务"

# Terminal 3 — PM
python3 start_pm.py

# Terminal 1 — Manager 验收
python3 main.py "设计已确认，请审核产品文档"
```

### 步骤 3：运行测试

```bash
# 单元测试（不需要 API Key）
python3 -m pytest test_m4l28.py -v

# 集成测试（需要 ALIYUN_API_KEY）
ALIYUN_API_KEY=sk-xxx python3 -m pytest test_m4l28_integration.py -v -s -m integration
```

### 步骤 4：查看产出

```bash
# 三层日志
ls workspace/shared/logs/l1_human/
ls workspace/shared/logs/l2_task/
ls workspace/shared/logs/l3_react/

# 改进提案
cat workspace/shared/proposals/proposals.json

# 人类待审批队列 + 周报
cat workspace/shared/mailboxes/human.json
```

---

## 三层日志

| 层级 | 写入方式 | 路径 | 用途 |
|------|---------|------|------|
| L1 | `send_mail(to="human")` 自动写入 | `logs/l1_human/{msg_id}.json` | 人类纠正记录（最有价值） |
| L2 | `run.py` 手动调用 `write_l2()` | `logs/l2_task/{agent}_{task}.json` | 任务质量、耗时、异常 |
| L3 | `seed_logs.py` 预置 | `logs/l3_react/{agent}/{task}/step_N.json` | ReAct 每步推理-行动 |

---

## 改进提案 Schema

```python
class RetroProposal(BaseModel):
    type:            Literal["tool_fix", "sop_update", "soul_update", "skill_add"]
    target:          str    # 具体文件/方法名
    root_cause:      Literal["ability_gap", "tool_defect", "prompt_ambiguity", "task_design"]
    current:         str    # 当前问题
    proposed:        str    # 具体改动
    expected_metric: str    # 可测量效果
    rollback_plan:   str    # 回滚方案
    evidence:        list[str]   # 至少1条日志 ID
    priority:        Literal["low", "medium", "high"]
    status:          Literal["待审批","已批准","已实施","验证中","已验证","已回滚"] = "待审批"
```
