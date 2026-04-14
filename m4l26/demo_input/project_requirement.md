# 演示输入：XiaoPaw 宠物健康记录功能

## 说明

本文件仅用于演示目的。实际运行时，需求已预置于：
`workspace/shared/needs/requirements.md`

Manager 在步骤1中将直接读取上述路径，无需手动传入需求文本。

## 演示流程

```
步骤1 ── Manager 读取 /mnt/shared/needs/requirements.md
             ↓
         Manager 发邮件给 PM（type: task_assign）
             ↓
步骤2 ── PM 读取自己的邮箱（read_inbox）
             ↓
         PM 读取 /mnt/shared/needs/requirements.md
             ↓
         PM 撰写产品文档 → 写入 /mnt/shared/design/product_spec.md
             ↓
         PM 发邮件给 Manager（type: task_done）
             ↓
步骤3 ── Manager 读取自己的邮箱（read_inbox）
             ↓
         Manager 读取 /mnt/shared/design/product_spec.md
             ↓
         Manager 验收 → 写入 /workspace/review_result.md
```

## 启动方式

```bash
cd crewai_mas_demo/m4l26
python m4l26_run.py
```
