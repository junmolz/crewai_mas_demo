"""
第28课·数字员工的自我进化
retro/team_retrospective.py — Manager 团队复盘

教学要点（对应第28课 P5）：
  团队复盘是 Manager 的管理动作，按以下步骤执行：
    1. 读取 L1 日志，统计人类纠正事件和 checkpoint 退回率
    2. 读取所有 Agent 的 L2 日志，按 Agent 计算平均质量分和失败率
    3. 定位瓶颈 Agent（质量分最低者），发邮件触发其自我复盘
    4. 调用 LLM 生成团队级改进提案（可选）
    5. 向 human.json 发送周报（让人类了解团队整体状态）

Manager 的分工：不做 L3 级别的精细分析（那是 Agent 自己的工作），
只做聚合统计和系统性问题识别——在各自擅长的粒度上工作。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from schemas import RetroProposal                          # noqa: E402
from tools.log_ops import read_l1, read_l2                 # noqa: E402
from tools.mailbox_ops import send_mail                    # noqa: E402
from retro.self_retrospective import (                     # noqa: E402
    get_llm_client,
    save_proposals,
)


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────────────────────

_TEAM_RETRO_SYSTEM_PROMPT = """\
你是一个 Agent 团队复盘分析器（Manager 视角）。根据提供的团队统计摘要，
识别系统性问题并生成团队级改进提案。

## 输出要求

输出合法的 JSON 对象，包含：

{
  "analysis": "2-3句话的宏观诊断（说明最大瓶颈在哪里、为什么）",
  "proposals": [
    {
      "type": "sop_update | tool_fix | soul_update | skill_add",
      "target": "具体文件或协作节点名称",
      "root_cause": "ability_gap | tool_defect | prompt_ambiguity | task_design",
      "current": "当前团队层面的问题",
      "proposed": "具体改动内容",
      "expected_metric": "可测量的团队级预期效果",
      "rollback_plan": "如何回滚",
      "evidence": ["数据依据，如：PM_avg_quality=0.45"],
      "priority": "low | medium | high"
    }
  ]
}

## 注意

- 团队复盘关注**跨 Agent 的系统性问题**（协作摩擦、SOP设计问题），不是追究某个 Agent 的责任
- proposals 可以为空数组（[]），如果统计数据没有明显问题
- evidence 写具体的统计数据值，而不是日志 ID
"""


# ─────────────────────────────────────────────────────────────────────────────
# 核心函数
# ─────────────────────────────────────────────────────────────────────────────

def run_team_retrospective(
    manager_id:  str,
    agent_ids:   list[str],
    logs_dir:    Path,
    mailbox_dir: Path,
    days:        int = 7,
) -> dict:
    """
    执行 Manager 团队复盘。

    Args:
        manager_id:  Manager 的 agent_id
        agent_ids:   所有需要统计的 Agent ID 列表
        logs_dir:    workspace/shared/logs/ 根目录
        mailbox_dir: workspace/shared/mailboxes/ 目录
        days:        回看多少天的日志

    Returns:
        统计摘要 dict（包含各 Agent 指标、分析结论、提案列表）
    """
    print(f"[TEAM RETRO] Manager 开始团队复盘，统计 {agent_ids}，过去 {days} 天...")

    # ── 1. 统计 L1：人类纠正事件 ─────────────────────────────────────────────
    l1_records       = read_l1(logs_dir, days=days)
    correction_count = len([r for r in l1_records if "correction" in r.get("type", "")])
    checkpoint_count = len([r for r in l1_records if "checkpoint" in r.get("type", "")])

    print(f"[TEAM RETRO] L1 统计：纠正事件={correction_count}，checkpoint={checkpoint_count}")

    # ── 2. 统计各 Agent L2 ───────────────────────────────────────────────────
    agent_stats: dict[str, dict] = {}
    for aid in agent_ids:
        records = read_l2(logs_dir, aid, days=days)
        if not records:
            agent_stats[aid] = {"task_count": 0, "avg_quality": None, "failure_rate": None}
            continue
        qualities    = [r.get("result_quality", 0.0) for r in records]
        failed       = [r for r in records if (r.get("result_quality", 1.0) or 1.0) < 0.5]
        agent_stats[aid] = {
            "task_count":   len(records),
            "avg_quality":  round(sum(qualities) / len(qualities), 3),
            "failure_rate": round(len(failed) / len(records), 3),
        }
        print(
            f"[TEAM RETRO] {aid}: 任务数={len(records)}, "
            f"平均质量={agent_stats[aid]['avg_quality']}, "
            f"失败率={agent_stats[aid]['failure_rate']}"
        )

    # ── 3. 定位瓶颈 Agent ─────────────────────────────────────────────────────
    bottleneck = find_bottleneck(agent_stats)
    if bottleneck:
        print(f"[TEAM RETRO] 识别瓶颈 Agent：{bottleneck}，发邮件触发其自我复盘")
        _trigger_agent_self_retro(bottleneck, agent_stats[bottleneck], mailbox_dir)

    # ── 4. 调用 LLM 生成团队级提案 ────────────────────────────────────────────
    summary_text = _build_team_summary(agent_ids, agent_stats, l1_records, correction_count)
    proposals    = _call_team_llm(summary_text)

    if proposals:
        proposals_file = mailbox_dir.parent / "proposals" / "proposals.json"
        save_proposals(proposals, proposals_file)

    # ── 5. 发周报给 human.json ────────────────────────────────────────────────
    result = {
        "agent_stats":      agent_stats,
        "bottleneck_agent": bottleneck,
        "l1_corrections":   correction_count,
        "l1_checkpoints":   checkpoint_count,
        "team_proposals":   [p.model_dump() for p in proposals],
    }
    _send_weekly_report(result, manager_id, mailbox_dir)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def find_bottleneck(agent_stats: dict[str, dict]) -> str | None:
    """找出平均质量分最低的 Agent（任务数 > 0）。若全员无任务返回 None。"""
    eligible = {
        aid: stats
        for aid, stats in agent_stats.items()
        if stats["task_count"] > 0 and stats["avg_quality"] is not None
    }
    if not eligible:
        return None
    return min(eligible, key=lambda aid: eligible[aid]["avg_quality"])


def _trigger_agent_self_retro(
    agent_id:    str,
    stats:       dict,
    mailbox_dir: Path,
) -> None:
    """
    向瓶颈 Agent 发邮件，附上统计上下文，触发其临时自我复盘。
    直接使用 send_mail()——Manager → Agent 的消息走相同的 mailbox 接口。
    """
    content = (
        f"Manager 团队复盘发现你是本周质量瓶颈：\n"
        f"  任务数：{stats['task_count']}\n"
        f"  平均质量分：{stats['avg_quality']}\n"
        f"  失败率：{stats['failure_rate']}\n\n"
        f"请触发自我复盘（self-retrospective），分析 L2+L3 日志，\n"
        f"生成改进提案后发至 human.json 等待审批。"
    )
    send_mail(
        mailbox_dir = mailbox_dir,
        to          = agent_id,
        from_       = "manager",
        type_       = "retro_trigger",
        subject     = "[团队复盘] 请立即执行自我复盘",
        content     = content,
    )


def _build_team_summary(
    agent_ids:        list[str],
    agent_stats:      dict[str, dict],
    l1_records:       list[dict],
    correction_count: int,
) -> str:
    """将团队统计数据组装成 LLM prompt 的 user message。"""
    lines = ["## 团队周报统计摘要\n"]

    lines.append("### Agent 质量指标")
    for aid in agent_ids:
        s = agent_stats.get(aid, {})
        lines.append(
            f"- {aid}: 任务数={s.get('task_count', 0)}, "
            f"平均质量={s.get('avg_quality', 'N/A')}, "
            f"失败率={s.get('failure_rate', 'N/A')}"
        )

    lines.append(f"\n### L1 人类交互")
    lines.append(f"- 纠正事件：{correction_count} 次")
    for r in l1_records[:5]:
        lines.append(f"  [{r.get('type')}] {r.get('subject', '')[:60]}")

    return "\n".join(lines)


def _call_team_llm(summary_text: str) -> list[RetroProposal]:
    """调用 LLM 生成团队级提案，解析失败返回 []。"""
    raw_response = ""
    try:
        client   = get_llm_client()
        response = client.chat.completions.create(
            model    = "glm-5.1",
            messages = [
                {"role": "system", "content": _TEAM_RETRO_SYSTEM_PROMPT},
                {"role": "user",   "content": summary_text},
            ],
            response_format = {"type": "json_object"},
            temperature     = 0.3,
        )
        raw_response = response.choices[0].message.content or ""
        data         = json.loads(raw_response)

        analysis = data.get("analysis", "")
        if analysis:
            print(f"[TEAM RETRO] LLM 分析：{analysis}")

        proposals = []
        for p in data.get("proposals", []):
            try:
                proposals.append(RetroProposal(**p))
            except Exception as e:
                print(f"[TEAM RETRO] 团队提案校验失败，跳过：{e}")
        print(f"[TEAM RETRO] 生成 {len(proposals)} 条团队级提案")
        return proposals

    except Exception as e:
        print(f"[TEAM RETRO] LLM 调用或解析失败：{e}")
        if raw_response:
            print(f"[TEAM RETRO] 原始输出：{raw_response[:300]}")
        return []


def _send_weekly_report(result: dict, manager_id: str, mailbox_dir: Path) -> None:
    """向 human.json 发送团队周报。"""
    stats_lines = []
    for aid, s in result["agent_stats"].items():
        stats_lines.append(
            f"  {aid}: 任务数={s['task_count']}, "
            f"平均质量={s.get('avg_quality', 'N/A')}, "
            f"失败率={s.get('failure_rate', 'N/A')}"
        )

    content_parts = [
        "=== 团队周报 ===\n",
        "【Agent 指标】\n" + "\n".join(stats_lines),
        f"\n【瓶颈 Agent】{result.get('bottleneck_agent') or '无明显瓶颈'}",
        f"【L1 统计】纠正={result['l1_corrections']} | checkpoint={result['l1_checkpoints']}",
        f"【团队提案数】{len(result['team_proposals'])} 条（见 proposals.json）",
    ]

    send_mail(
        mailbox_dir = mailbox_dir,
        to          = "human",
        from_       = "manager",
        type_       = "team_retrospective_report",
        subject     = "[团队周报] Manager 团队复盘完成",
        content     = "\n".join(content_parts),
    )
    print(f"[TEAM RETRO] 周报已发送至 human.json")
