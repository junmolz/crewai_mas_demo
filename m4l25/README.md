# 第25课示例代码：团队角色体系——分工设计与行为规范

本课演示 Manager（项目经理）和 Dev（开发工程师）两个角色的独立运行。
每个角色有自己的 workspace、soul.md、独立沙盒，互不干扰。

> 两个角色**不通信**——任务清单由人工传递。角色间通信在第26课实现。

---

## 目录结构

```
m4l25/
├── m4l25_manager.py          # Manager 角色演示
├── m4l25_dev.py              # Dev 角色演示
├── sandbox-docker-compose.yaml
├── demo_input/
│   ├── project_requirement.md   # Manager 的输入（项目需求）
│   └── feature_requirement.md  # Dev 的输入（功能需求）
└── workspace/
    ├── manager/              # Manager 的 workspace（soul/agent/memory）
    └── dev/                  # Dev 的 workspace（soul/agent/memory）
```

---

## 运行步骤

### 第一步：启动沙盒

两个角色各用独立沙盒（独立端口），**按需启动**：

```bash
cd /path/to/crewai_mas_demo/m4l25

# 运行 Manager 时启动（端口 8023）
docker compose -f sandbox-docker-compose.yaml --profile manager up -d

# 运行 Dev 时启动（端口 8024）
docker compose -f sandbox-docker-compose.yaml --profile dev up -d
```

验证沙盒是否正常：
```bash
curl http://localhost:8023/mcp   # Manager 沙盒
curl http://localhost:8024/mcp   # Dev 沙盒
```

---

### 第二步：运行演示

从 `crewai_mas_demo/` 目录执行（确保模块路径正确）：

```bash
cd /path/to/crewai_mas_demo

# 演示 1：Manager 角色（项目经理）
python m4l25/m4l25_manager.py

# 演示 2：Dev 角色（开发工程师）
python m4l25/m4l25_dev.py
```

---

## 两个演示说明

### 演示 1：Manager（`m4l25_manager.py`）

| 项目 | 说明 |
|------|------|
| 输入 | `demo_input/project_requirement.md`（XiaoPaw 智能日程助手需求） |
| Skill | `sop_manager`（参考型，注入任务拆解流程） |
| 沙盒端口 | 8023 |
| 输出 | `workspace/manager/task_breakdown.md` |

**观察重点**：Manager 读取 `soul.md` + `agent.md`（含团队名册），将业务需求拆解为可分配的任务清单，NEVER 越界做技术设计。

---

### 演示 2：Dev（`m4l25_dev.py`）

| 项目 | 说明 |
|------|------|
| 输入 | `demo_input/feature_requirement.md`（T-01 自然语言日程解析模块） |
| Skill | `sop_dev`（参考型，注入技术设计流程） |
| 沙盒端口 | 8024 |
| 输出 | `workspace/dev/tech_design.md` |

**观察重点**：Dev 读取自己的 `soul.md`（技术是唯一权威），输出四段式技术设计文档。**如果输入没有验收标准，Dev 会触发 NEVER 规则，输出澄清请求而非直接执行**——这是本课的核心演示点。

---

## 运行测试（不需要沙盒）

```bash
cd /path/to/crewai_mas_demo
python -m pytest m4l25/test_m4l25.py -v
```

---

## 常见问题

**Q：运行报 `ConnectionError` 或 `MCP` 相关错误？**
检查沙盒是否已启动：`docker ps | grep sandbox`

**Q：报 `ModuleNotFoundError`？**
确认从 `crewai_mas_demo/` 目录运行，不要在 `m4l25/` 目录内直接运行。

**Q：想重新跑一遍（清除历史 session）？**
```bash
rm -f workspace/manager/sessions/*.json workspace/manager/sessions/*.jsonl
rm -f workspace/dev/sessions/*.json workspace/dev/sessions/*.jsonl
```
