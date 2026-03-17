---
name: skill-creator
description: >
  Use this skill when the user wants to save a reusable procedure, SOP, or
  multi-step workflow as a new Skill so it can be reliably executed in the
  future.

  Activate when:
  - User says "save this as a skill", "create a skill for...", "I want to
    be able to reuse this workflow"
  - User describes a multi-step process they want executed consistently
  - User wants to turn a successful one-off workflow into a repeatable capability

  Do NOT activate for: one-time tasks, simple facts or preferences (use
  memory-save instead), code snippets that don't represent a full workflow.

  Rule of thumb: if it's "how to do something" with multiple steps that need
  to run reliably every time → skill-creator. If it's "what something is" or
  a preference → memory-save.
allowed-tools:
  - Read
  - Write
  - Bash
---

# skill-creator：将工作流固化为可复用 Skill

## 概述

将对话中产生的多步骤工作流固化为 SKILL.md，写入 `/mnt/skills/` 目录，
并注册到 `/mnt/skills/load_skills.yaml`，让 SkillLoaderTool 在下次 Bootstrap 时自动加载。

**为什么用 Skill 而不是 memory：**
memory 里的 SOP 是自然语言，模型"参考"但自由发挥，执行质量不一致。
SKILL.md 有 frontmatter，SkillLoaderTool 精准路由；正文有结构、有 CRITICAL 规则——
模型理解了"为什么不能这样做"，边缘情况也能做出正确判断。

## 步骤

### 第一步：确认 Skill 名称和范围

- name 命名：`{动词}-{名词}`，kebab-case 全小写（如 `analyze-hk-stock`、`generate-weekly-report`）
- 确认这个 Skill 做什么、不做什么（边界清晰是 SKILL.md 质量的关键）
- 检查 `/mnt/skills/load_skills.yaml`，确认不与现有 Skill 重叠

### 第二步：起草 SKILL.md

按以下格式生成 SKILL.md：

```yaml
---
name: {skill-name}
description: >
  Use this skill when {触发场景，要 "a little bit pushy"，具体列举触发条件}.
  Activate whenever {关键词列表}.
  Do NOT activate for: {反例，防止过度触发}.
allowed-tools:
  - Read
  - Write
  # 最小化原则：只列实际需要的工具
---
```

**description 怎么写（关键）：**

模型有"undertriggering"倾向——场景符合却不触发。
description 是 SkillLoaderTool 路由的唯一依据，必须写得主动、具体：

```
❌ 被动：
"A skill for analyzing stocks."

✅ Pushy（正确）：
"Use this skill when the user asks to analyze Hong Kong stocks, research HK
companies, review 港股 performance, or evaluate HK investment opportunities.
Activate whenever 港股 or HK stock analysis is needed."
```

**正文规范（explain the why）：**

解释每步背后的原因，而不是堆叠 MUST/NEVER：

```markdown
### 第一步：查实时行情
通过 [数据源] 获取当前价格和成交量。
**为什么先查行情**：技术分析以最新价格为基准，用30分钟前的数据会导致趋势判断偏差。

## CRITICAL 规则
- NEVER 在行情数据超过 30 分钟的情况下做技术分析
  （原因：过时数据导致错误信号，比没有分析更危险）
```

### 第三步：写入文件系统

1. 创建目录：`/mnt/skills/{skill-name}/`
2. 写入：`/mnt/skills/{skill-name}/SKILL.md`
3. 读取 `/mnt/skills/load_skills.yaml`，追加注册：

```yaml
  - name: {skill-name}
    path: ./{skill-name}
    type: task       # 需要代码执行
    enabled: true
```

**CRITICAL：写入后验证**
读取刚写的 SKILL.md，确认内容与预期一致。
读取 load_skills.yaml，确认新条目正确追加、YAML 格式合法。
原因：写入失败不会抛异常，只有读取验证才能确认文件实际落盘。
