"""
第26课·任务链与信息传递
m4l26_mailbox/mailbox_tools.py

CrewAI 工具包装：
  - MailboxSendTool     : send_mail（写入 unread 消息）
  - MailboxReadTool     : read_inbox（取走 unread → in_progress）
  - MarkDoneTool        : mark_done（确认处理完成 → done）
  - WriteSharedFileTool : 写共享工作区文件（权限控制）
  - ReadSharedFileTool  : 读共享工作区文件
  - WriteWorkspaceTool  : 写个人工作区文件
  - CreateWorkspaceTool : 初始化共享工作区（Manager 专属）

使用方式：
    from m4l26.m4l26_mailbox.mailbox_tools import (
        make_mailbox_tools, WriteSharedFileTool, ReadSharedFileTool,
        WriteWorkspaceTool, CreateWorkspaceTool,
    )
"""

from __future__ import annotations

import json
from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from .mailbox_ops import (
    send_mail, read_inbox, mark_done, mark_done_all_in_progress,
    STATUS_UNREAD, STATUS_IN_PROGRESS, STATUS_DONE,
)
from .workspace_ops import create_workspace


# ── send_mail 工具 ────────────────────────────────────────────────────────────

class SendMailInput(BaseModel):
    to: str = Field(description="收件人角色：manager 或 pm")
    from_: str = Field(alias="from", description="发件人角色：manager 或 pm")
    type: str = Field(
        description="消息类型：task_assign（任务分配）/ task_done（任务完成）/ broadcast（广播）"
    )
    subject: str = Field(description="邮件标题（15字以内）")
    content: str = Field(description="邮件正文（包含任务说明、文档路径等，不要复制文档全文）")

    model_config = {"populate_by_name": True}


class MailboxSendTool(BaseTool):
    """向指定角色的邮箱发送结构化消息（写入 status=unread）"""
    name: str = "send_mail"
    description: str = (
        "向指定角色（manager 或 pm）的邮箱发送消息。消息初始状态为 unread。\n"
        "参数：to（收件人）、from（发件人）、type（task_assign/task_done/broadcast）、"
        "subject（标题）、content（正文，只传路径引用，不要复制文档全文）。\n"
        "返回：{\"errcode\": 0, \"errmsg\": \"success\", \"msg_id\": \"<uuid>\"}"
    )
    args_schema: type[BaseModel] = SendMailInput

    _mailbox_dir: Path = None

    def __init__(self, mailbox_dir: Path) -> None:
        super().__init__()
        self._mailbox_dir = mailbox_dir

    def _run(self, to: str, from_: str, type: str, subject: str, content: str) -> str:
        try:
            msg_id = send_mail(
                mailbox_dir=self._mailbox_dir,
                to=to, from_=from_, type_=type, subject=subject, content=content,
            )
            return json.dumps({"errcode": 0, "errmsg": "success", "msg_id": msg_id},
                              ensure_ascii=False)
        except ValueError as e:
            return json.dumps({"errcode": 1, "errmsg": str(e)}, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"errcode": 2, "errmsg": f"邮件发送失败：{e}"}, ensure_ascii=False)


# ── read_inbox 工具 ───────────────────────────────────────────────────────────

class ReadInboxInput(BaseModel):
    role: str = Field(description="要读取邮箱的角色：manager 或 pm")


class MailboxReadTool(BaseTool):
    """
    读取指定角色邮箱中的 unread 消息，原子标记为 in_progress。

    注意：不会直接标记为 done——处理成功后需由编排器调用 mark_done 确认。
    这是三态状态机的第一步：unread → in_progress。
    """
    name: str = "read_inbox"
    description: str = (
        "读取指定角色（manager 或 pm）邮箱中的 unread 消息，并原子标记为 in_progress。\n"
        "注意：消息变为 in_progress 后不会被重复取走；处理完成后编排器会标记为 done。\n"
        "参数：role（自己的角色）。\n"
        "返回：{\"errcode\": 0, \"errmsg\": \"success\", \"messages\": [...]}"
    )
    args_schema: type[BaseModel] = ReadInboxInput

    _mailbox_dir: Path = None

    def __init__(self, mailbox_dir: Path) -> None:
        super().__init__()
        self._mailbox_dir = mailbox_dir

    def _run(self, role: str) -> str:
        try:
            messages = read_inbox(mailbox_dir=self._mailbox_dir, role=role)
            return json.dumps({"errcode": 0, "errmsg": "success", "messages": messages},
                              ensure_ascii=False)
        except ValueError as e:
            return json.dumps({"errcode": 1, "errmsg": str(e)}, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"errcode": 2, "errmsg": f"读取邮箱失败：{e}"}, ensure_ascii=False)


# ── mark_done 工具 ────────────────────────────────────────────────────────────

class MarkDoneInput(BaseModel):
    role: str    = Field(description="角色名：manager 或 pm")
    msg_ids: list[str] = Field(description="已处理完成的消息 ID 列表")


class MarkDoneTool(BaseTool):
    """
    将指定消息从 in_progress 标记为 done（处理完成确认）。

    三态状态机第二步：in_progress → done。
    通常由编排器在 Crew 成功完成后调用，也可由 Agent 主动调用。
    """
    name: str = "mark_done"
    description: str = (
        "将已处理完成的消息标记为 done（三态状态机最终态）。\n"
        "参数：role（角色名）、msg_ids（消息 ID 列表，来自 read_inbox 返回的 id 字段）。\n"
        "返回：{\"errcode\": 0, \"errmsg\": \"success\", \"marked\": <数量>}"
    )
    args_schema: type[BaseModel] = MarkDoneInput

    _mailbox_dir: Path = None

    def __init__(self, mailbox_dir: Path) -> None:
        super().__init__()
        self._mailbox_dir = mailbox_dir

    def _run(self, role: str, msg_ids: list[str]) -> str:
        try:
            count = mark_done(mailbox_dir=self._mailbox_dir, role=role, msg_ids=msg_ids)
            return json.dumps({"errcode": 0, "errmsg": "success", "marked": count},
                              ensure_ascii=False)
        except ValueError as e:
            return json.dumps({"errcode": 1, "errmsg": str(e)}, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"errcode": 2, "errmsg": f"mark_done 失败：{e}"}, ensure_ascii=False)


# ── create_workspace 工具 ─────────────────────────────────────────────────────

class CreateWorkspaceInput(BaseModel):
    project_name: str = Field(
        default="XiaoPaw 项目",
        description="项目名称，写入 WORKSPACE_RULES.md 标题",
    )
    roles: list[str] = Field(
        default=["manager", "pm"],
        description="参与角色列表，为每个角色初始化邮箱文件",
    )


class CreateWorkspaceTool(BaseTool):
    """
    Manager 专属工具：初始化共享工作区目录结构。

    创建 needs/、design/、mailboxes/ 目录，
    初始化各角色邮箱（空 JSON 数组），
    生成 WORKSPACE_RULES.md 访问规范。
    幂等——已存在的内容不会被覆盖。
    """
    name: str = "create_workspace"
    description: str = (
        "初始化共享工作区（Manager 专属，项目启动时调用）。\n"
        "创建目录结构（needs/、design/、mailboxes/）和各角色邮箱，"
        "生成 WORKSPACE_RULES.md 访问规范。幂等，可安全重复调用。\n"
        "参数：project_name（项目名称）、roles（参与角色列表）。\n"
        "返回：{\"errcode\": 0, \"errmsg\": \"success\", \"result\": {...}}"
    )
    args_schema: type[BaseModel] = CreateWorkspaceInput

    _shared_dir: Path = None

    def __init__(self, shared_dir: Path) -> None:
        super().__init__()
        self._shared_dir = shared_dir

    def _run(self, project_name: str = "XiaoPaw 项目",
             roles: list[str] | None = None) -> str:
        if roles is None:
            roles = ["manager", "pm"]
        try:
            result = create_workspace(
                shared_dir=self._shared_dir,
                roles=roles,
                project_name=project_name,
            )
            return json.dumps({"errcode": 0, "errmsg": "success", "result": result},
                              ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"errcode": 2, "errmsg": f"工作区初始化失败：{e}"},
                              ensure_ascii=False)


# ── write_shared_file 工具 ────────────────────────────────────────────────────

class WriteSharedFileInput(BaseModel):
    relative_path: str = Field(
        description=(
            "相对于 /mnt/shared/ 的文件路径，如 'design/product_spec.md'。"
            "只允许写入 design/ 目录下的文件。"
        )
    )
    content: str = Field(description="要写入文件的完整文本内容（Markdown 格式）")


class WriteSharedFileTool(BaseTool):
    """将内容写入共享工作区（/mnt/shared/）的文件"""
    name: str = "write_shared_file"
    description: str = (
        "将产品文档等内容写入共享工作区文件。\n"
        "参数：relative_path（相对于 /mnt/shared/ 的路径，如 'design/product_spec.md'）、"
        "content（文件的完整 Markdown 内容）。\n"
        "只允许写入 design/ 目录下的文件（不允许修改 needs/ 或 mailboxes/）。\n"
        "返回：{\"errcode\": 0, \"errmsg\": \"success\", \"path\": \"<写入路径>\"}"
    )
    args_schema: type[BaseModel] = WriteSharedFileInput

    _shared_dir: Path = None

    def __init__(self, shared_dir: Path) -> None:
        super().__init__()
        self._shared_dir = shared_dir

    def _run(self, relative_path: str, content: str) -> str:
        if not relative_path.startswith("design/"):
            return json.dumps(
                {"errcode": 1, "errmsg": f"禁止写入路径 '{relative_path}'，只允许 design/ 目录"},
                ensure_ascii=False,
            )
        full_path = self._shared_dir / relative_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            return json.dumps({"errcode": 0, "errmsg": "success", "path": str(full_path)},
                              ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"errcode": 2, "errmsg": f"写入失败：{e}"}, ensure_ascii=False)


# ── read_shared_file 工具 ─────────────────────────────────────────────────────

class ReadSharedFileInput(BaseModel):
    relative_path: str = Field(
        description="相对于 /mnt/shared/ 的文件路径，如 'design/product_spec.md'"
    )


class ReadSharedFileTool(BaseTool):
    """读取共享工作区（/mnt/shared/）的文件内容"""
    name: str = "read_shared_file"
    description: str = (
        "读取共享工作区文件内容。\n"
        "参数：relative_path（相对于 /mnt/shared/ 的路径，"
        "如 'design/product_spec.md' 或 'needs/requirements.md'）。\n"
        "返回：{\"errcode\": 0, \"errmsg\": \"success\", \"content\": \"<文件内容>\"}"
    )
    args_schema: type[BaseModel] = ReadSharedFileInput

    _shared_dir: Path = None

    def __init__(self, shared_dir: Path) -> None:
        super().__init__()
        self._shared_dir = shared_dir

    def _run(self, relative_path: str) -> str:
        full_path = self._shared_dir / relative_path
        if not full_path.exists():
            return json.dumps({"errcode": 1, "errmsg": f"文件不存在：{relative_path}"},
                              ensure_ascii=False)
        try:
            content = full_path.read_text(encoding="utf-8")
            return json.dumps({"errcode": 0, "errmsg": "success", "content": content},
                              ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"errcode": 2, "errmsg": f"读取失败：{e}"}, ensure_ascii=False)


# ── write_workspace_file 工具（Manager 个人区）───────────────────────────────

class WriteWorkspaceFileInput(BaseModel):
    filename: str = Field(
        description="文件名，如 'review_result.md'。将写入 Manager 的个人工作区 /workspace/"
    )
    content: str = Field(description="要写入文件的完整文本内容（Markdown 格式）")


class WriteWorkspaceTool(BaseTool):
    """将内容写入 Manager 个人工作区（/workspace/）的文件"""
    name: str = "write_workspace_file"
    description: str = (
        "将内容写入 Manager 个人工作区文件（如验收报告）。\n"
        "参数：filename（文件名，如 'review_result.md'）、content（文件完整内容）。\n"
        "返回：{\"errcode\": 0, \"errmsg\": \"success\", \"path\": \"<写入路径>\"}"
    )
    args_schema: type[BaseModel] = WriteWorkspaceFileInput

    _workspace_dir: Path = None

    def __init__(self, workspace_dir: Path) -> None:
        super().__init__()
        self._workspace_dir = workspace_dir

    def _run(self, filename: str, content: str) -> str:
        if "/" in filename or "\\" in filename:
            return json.dumps(
                {"errcode": 1, "errmsg": f"filename 不能包含路径分隔符：'{filename}'"},
                ensure_ascii=False,
            )
        full_path = self._workspace_dir / filename
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            return json.dumps({"errcode": 0, "errmsg": "success", "path": str(full_path)},
                              ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"errcode": 2, "errmsg": f"写入失败：{e}"}, ensure_ascii=False)


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

def make_mailbox_tools(mailbox_dir: Path) -> list[BaseTool]:
    """返回 [MailboxSendTool, MailboxReadTool, MarkDoneTool]"""
    return [
        MailboxSendTool(mailbox_dir=mailbox_dir),
        MailboxReadTool(mailbox_dir=mailbox_dir),
        MarkDoneTool(mailbox_dir=mailbox_dir),
    ]
