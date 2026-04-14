"""
第28课·数字员工的自我进化
retro/self_retrospective.py — Agent 自我复盘

教学要点（对应第28课 P4）：
  自我复盘是 Agent 的自我学习机制，按以下步骤执行：
    1. 检查样本量（< min_tasks 时跳过，避免低质量复盘）
    2. 读取 L2 日志，识别质量最低的任务
    3. 读取对应 L3 日志，找到具体失败节点
    4. 读取 L1 中涉及该 Agent 的人类纠正记录
    5. 用结构化 prompt 调用 LLM（强制 json_object 输出）
    6. Pydantic 校验提案，写入 proposals.json + 发 human.json

设计决策：直接用 openai SDK 调用（不走 CrewAI Crew）。
复盘是"元操作"——分析已完成任务的执行记录，不是在执行新任务。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from filelock import FileLock
from openai import OpenAI

# 路径处理
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from schemas import RetroProposal          # noqa: E402
from tools.log_ops import read_l1, read_l2, read_l3  # noqa: E402
from tools.mailbox_ops import send_mail    # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# LLM 配置
# ─────────────────────────────────────────────────────────────────────────────

def _get_llm_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["ALIYUN_API_KEY"],
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt（强制根因分析，禁止空洞反思）
# ─────────────────────────────────────────────────────────────────────────────

_SELF_RETRO_SYSTEM_PROMPT = """\
你是一个 Agent 自我复盘分析器。根据提供的日志摘要，生成结构化改进提案。

## 输出要求

必须输出合法的 JSON 对象，格式如下（proposals 数组，1-3条）：

{
  "proposals": [
    {
      "type": "tool_fix | sop_update | soul_update | skill_add",
      "target": "具体文件或方法名，如 pm/skills/design_spec_sop.md",
      "root_cause": "ability_gap | tool_defect | prompt_ambiguity | task_design",
      "current": "当前存在的具体问题",
      "proposed": "具体改动内容（可操作的，不能是模糊描述）",
      "expected_metric": "可测量的预期效果，必须有具体指标，如：checkpoint通过率从45%提升到75%",
      "rollback_plan": "如果效果变差，具体如何回滚",
      "evidence": ["log_id_1", "log_id_2"],
      "priority": "low | medium | high"
    }
  ]
}

## 严格禁止

- proposed 写"下次要更小心"等无效行动
- expected_metric 写模糊描述（必须有可验证的具体指标）
- evidence 为空数组（必须引用至少1条日志）
- root_cause 超出枚举范围（只能是 ability_gap/tool_defect/prompt_ambiguity/task_design）
"""


# ─────────────────────────────────────────────────────────────────────────────
# 核心函数
# ─────────────────────────────────────────────────────────────────────────────

def run_self_retrospective(
    agent_id:    str,
    logs_dir:    Path,
    mailbox_dir: Path,
    days:        int = 7,
    min_tasks:   int = 5,
) -> list[RetroProposal]:
    """
    执行 Agent 自我复盘，返回生成的改进提案列表。

    Args:
        agent_id:    Agent 标识，如 "pm"
        logs_dir:    workspace/shared/logs/ 根目录
        mailbox_dir: workspace/shared/mailboxes/ 目录
        days:        回看多少天的日志
        min_tasks:   最小任务量阈值，低于此值跳过复盘

    Returns:
        通过 Pydantic 校验的 RetroProposal 列表；样本不足时返回 []
    """
    # ── 1. 样本量检查 ────────────────────────────────────────────────────────
    l2_records = read_l2(logs_dir, agent_id, days=days)
    if len(l2_records) < min_tasks:
        print(
            f"[SKIP] {agent_id} 过去 {days} 天任务数 = {len(l2_records)}，"
            f"低于最小样本量 {min_tasks}，跳过自我复盘"
        )
        return []

    print(f"[RETRO] {agent_id} 开始自我复盘，分析 {len(l2_records)} 条任务记录...")

    # ── 2. 找质量最低的 3 条任务 ─────────────────────────────────────────────
    sorted_records = sorted(l2_records, key=lambda r: r.get("result_quality", 1.0))
    worst_tasks    = sorted_records[:3]
    worst_ids      = [r.get("task_id", "") for r in worst_tasks]

    print(f"[RETRO] 质量最低任务：{worst_ids}，质量分：{[r.get('result_quality') for r in worst_tasks]}")

    # ── 3. 读取对应 L3 日志（找失败节点）────────────────────────────────────
    l3_data: dict[str, list[dict]] = {}
    for task_id in worst_ids:
        if task_id:
            steps = read_l3(logs_dir, agent_id, task_id)
            if steps:
                l3_data[task_id] = steps

    # ── 4. 读取 L1 中该 Agent 相关的人类纠正记录 ─────────────────────────────
    l1_records = read_l1(logs_dir, days=days)
    l1_related = [
        r for r in l1_records
        if agent_id in r.get("content", "") or agent_id in r.get("subject", "")
    ]

    # ── 5. 组装 prompt ────────────────────────────────────────────────────────
    log_summary = _build_log_summary(agent_id, worst_tasks, l3_data, l1_related)

    # ── 6. 调用 LLM ───────────────────────────────────────────────────────────
    proposals = _call_llm_for_proposals(log_summary, agent_id)

    # ── 7. 写入 proposals.json + 发 human.json ───────────────────────────────
    if proposals:
        _save_proposals(proposals, mailbox_dir.parent / "proposals" / "proposals.json")
        _notify_human(proposals, agent_id, mailbox_dir)

    return proposals


# ─────────────────────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _build_log_summary(
    agent_id:    str,
    worst_tasks: list[dict],
    l3_data:     dict[str, list[dict]],
    l1_related:  list[dict],
) -> str:
    """将日志数据组装成 LLM prompt 的 user message。"""
    lines = [f"## {agent_id} 自我复盘日志摘要\n"]

    lines.append("### 质量最低任务（L2 日志）")
    for r in worst_tasks:
        lines.append(
            f"- task_id={r.get('task_id')} | desc={r.get('task_desc')} "
            f"| quality={r.get('result_quality')} | error={r.get('error_type')}"
        )

    if l3_data:
        lines.append("\n### 失败任务的 ReAct 步骤（L3 日志）")
        for task_id, steps in l3_data.items():
            lines.append(f"\n**{task_id}**（{len(steps)} 步）：")
            # 只显示出错/未收敛的步骤，避免 prompt 过长
            failed = [s for s in steps if not s.get("converged", True)]
            for s in (failed or steps)[:5]:
                lines.append(
                    f"  step {s.get('step_idx')}: action={s.get('action')} "
                    f"| obs={str(s.get('observation', ''))[:100]}"
                )

    if l1_related:
        lines.append("\n### 人类纠正记录（L1 日志）")
        for r in l1_related[:5]:
            lines.append(f"- [{r.get('type')}] {r.get('subject')} | {str(r.get('content', ''))[:100]}")

    return "\n".join(lines)


def _call_llm_for_proposals(log_summary: str, agent_id: str) -> list[RetroProposal]:
    """
    调用 LLM 分析日志，返回经 Pydantic 校验的提案列表。
    解析失败时打印原始输出并返回 []（保护演示不崩溃）。
    """
    raw_response = ""
    try:
        client   = _get_llm_client()
        response = client.chat.completions.create(
            model    = "qwen-plus",
            messages = [
                {"role": "system", "content": _SELF_RETRO_SYSTEM_PROMPT},
                {"role": "user",   "content": log_summary},
            ],
            response_format = {"type": "json_object"},
            temperature     = 0.3,
        )
        raw_response = response.choices[0].message.content or ""
        data         = json.loads(raw_response)
        proposals    = []
        for p in data.get("proposals", []):
            try:
                proposals.append(RetroProposal(**p))
            except Exception as e:
                print(f"[RETRO] 提案校验失败，跳过：{e}\n  原始：{p}")
        print(f"[RETRO] {agent_id} 生成 {len(proposals)} 条通过校验的改进提案")
        return proposals

    except Exception as e:
        print(f"[RETRO] LLM 调用或解析失败：{e}")
        if raw_response:
            print(f"[RETRO] 原始 LLM 输出：{raw_response[:500]}")
        return []


def _save_proposals(proposals: list[RetroProposal], proposals_file: Path) -> None:
    """将提案追加写入 proposals.json（不覆盖已有记录）。"""
    proposals_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = proposals_file.with_suffix(".lock")

    with FileLock(str(lock_path)):
        existing: list[dict] = []
        if proposals_file.exists():
            existing = json.loads(proposals_file.read_text(encoding="utf-8"))

        for p in proposals:
            record = p.model_dump()
            record["proposal_id"] = str(uuid.uuid4())[:8]
            existing.append(record)

        proposals_file.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _notify_human(
    proposals:   list[RetroProposal],
    agent_id:    str,
    mailbox_dir: Path,
) -> None:
    """发送改进提案到 human.json 等待审批。"""
    summary_lines = []
    for i, p in enumerate(proposals, 1):
        summary_lines.append(
            f"{i}. [{p.priority}] {p.type} — {p.target}\n"
            f"   根因：{p.root_cause} | 预期效果：{p.expected_metric}"
        )

    send_mail(
        mailbox_dir = mailbox_dir,
        to          = "human",
        from_       = "manager",
        type_       = "retrospective_proposal",
        subject     = f"[自我复盘] {agent_id} 提交 {len(proposals)} 条改进提案",
        content     = "\n".join(summary_lines),
    )
    print(f"[RETRO] 提案已发送至 human.json，等待审批")
