"""
第26课·任务链与信息传递
m4l26_mailbox/workspace_ops.py

共享工作区初始化：create_workspace

核心教学点（对应 P4 扩展）：
  - Manager 是工作区的制定者——项目启动时由 Manager 负责建立结构。
  - 幂等设计：已存在的目录和文件不会被覆盖，安全重复调用。
  - 完成后返回创建清单，便于验证和测试。

课程叙事：
  在第25课，Manager 定义了角色；在第26课，Manager 初始化协作基础设施。
  create_workspace 对应人类项目经理在项目启动时创建 Confluence 空间、
  设定文件夹结构、初始化 Jira 项目的动作——这一步完成后，团队才真正
  可以开始协作。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# ── 默认工作区规则模板 ────────────────────────────────────────────────────────

_WORKSPACE_RULES_TEMPLATE = """\
# 共享工作区访问规范
> 由 Manager 制定。数字员工启动时通过 workspace-rules skill 加载本文档。

**项目名称**：{project_name}
**创建时间**：{created_at}
**参与角色**：{roles_str}

---

## 目录结构

```
shared/
├── needs/         需求文档（甲方/Manager 提供，所有人只读）
├── design/        产品文档（PM 写入，其他人只读）
└── mailboxes/     邮箱（通过 mailbox-ops 工具读写，不直接操作文件）
```

## 权限规范

| 角色    | needs/     | design/    | mailboxes/ |
|---------|-----------|-----------|------------|
| Manager | 读写       | 只读       | 收发邮件   |
| PM      | 只读       | 读写       | 收发邮件   |

## 操作约定

1. **只通过工具访问**：使用 `read_shared_file` / `write_shared_file`，不直接操作文件路径
2. **邮件只传路径**：邮件正文只写文档路径引用，不复制文档全文
3. **写前检查权限**：越权写入会被 `write_shared_file` 工具拒绝，不要尝试
4. **标记消息完成**：处理完邮件后，通过编排器确认 mark_done，避免重复处理
"""


# ── create_workspace ──────────────────────────────────────────────────────────

def create_workspace(
    shared_dir: Path,
    roles: list[str],
    project_name: str = "XiaoPaw 项目",
) -> dict:
    """
    初始化共享工作区目录结构。幂等——已存在的内容不会被覆盖。

    创建内容：
    - shared/needs/       需求文档目录
    - shared/design/      产品文档目录
    - shared/mailboxes/   邮箱目录（含各角色的 {role}.json，初始为 []）
    - shared/WORKSPACE_RULES.md  访问规范（由 Manager 填写）

    Args:
        shared_dir:   共享工作区根目录（如 workspace/shared/）
        roles:        参与角色列表（如 ["manager", "pm"]）
        project_name: 项目名称，写入 WORKSPACE_RULES.md 标题

    Returns:
        {
            "created_dirs":  [...]  # 本次新建的目录（已存在则不计入）
            "created_files": [...]  # 本次新建的文件（已存在则不计入）
            "skipped_files": [...]  # 已存在、跳过的文件
        }
    """
    created_dirs:  list[str] = []
    created_files: list[str] = []
    skipped_files: list[str] = []

    def _rel(p: Path) -> str:
        return str(p.relative_to(shared_dir))

    def _mkdir(path: Path) -> None:
        if not path.exists():
            path.mkdir(parents=True)
            created_dirs.append(_rel(path))

    def _write_if_missing(path: Path, content: str) -> None:
        if path.exists():
            skipped_files.append(_rel(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created_files.append(_rel(path))

    # 确保根目录存在
    shared_dir.mkdir(parents=True, exist_ok=True)

    # 1. 子目录
    for subdir in ("needs", "design", "mailboxes"):
        _mkdir(shared_dir / subdir)

    # 2. 各角色邮箱（空 JSON 数组，三态状态机从此处起点）
    for role in roles:
        _write_if_missing(shared_dir / "mailboxes" / f"{role}.json", "[]\n")

    # 3. WORKSPACE_RULES.md
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rules = _WORKSPACE_RULES_TEMPLATE.format(
        project_name=project_name,
        created_at=now,
        roles_str="、".join(r.upper() for r in roles),
    )
    _write_if_missing(shared_dir / "WORKSPACE_RULES.md", rules)

    return {
        "created_dirs":  created_dirs,
        "created_files": created_files,
        "skipped_files": skipped_files,
    }
