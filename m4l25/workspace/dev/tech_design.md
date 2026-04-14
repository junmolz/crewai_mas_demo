# 技术设计 - 自然语言日程解析模块

## 1. 架构说明

- **模块定位**：独立 Python 工具模块 `schedule_parser`，作为核心 NLP 解析服务，供上层日历应用（如 Web API 或 CLI）调用。
- **依赖关系**：
  - 内置标准库：`datetime`, `re`, `zoneinfo`
  - 第三方轻量依赖：`cn2an`（中文数字转阿拉伯数字）、`dateparser`（支持中文相对时间解析，已适配离线模式）
- **关键风险与应对**：
  - 风险1：`dateparser` 在无网络时中文解析不稳定 → **对策**：预加载中文 locale 并启用 `RELATIVE_BASE` + `PARSERS=['custom']`，配合自定义规则兜底
  - 风险2：时间范围歧义（如"2点到4点"未指定日期）→ **对策**：统一继承 `base_date` 的日期部分，仅解析时间偏移
  - 风险3：参会人/地点抽取无结构化标注 → **对策**：采用正则+关键词启发式提取，失败则返回空，不抛异常（符合 DoD #4）

## 2. 接口定义

```python
from datetime import datetime
from typing import Dict, List, Any, Optional

def parse_schedule(
    text: str,
    base_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    将中文自然语言日程描述解析为结构化日历事件对象。

    Args:
        text: 用户输入的中文日程文本（非空字符串）
        base_date: 相对时间计算的基准时间，默认为当前系统时间（含时区）

    Returns:
        包含以下字段的字典：
        - "title": str, 日程标题（必填，从输入中提取的主事件名）
        - "start_time": str, ISO 8601 格式带时区的时间戳（如 "2026-03-27T15:00:00+08:00"）
        - "end_time": str, 同上；若输入含"到"-等范围词，则解析结束时间；否则默认 start_time + 1 小时
        - "location": str, 地点（未识别则为空字符串）
        - "attendees": List[str], 参会人列表（未识别则为空列表）

    Raises:
        ValueError: 当 text 为空或非字符串类型时
    """
```

## 3. 实现要点

- **技术选型理由**：
  - 不引入大模型（LLM）：DoD #5 要求单次 ≤1s，且无网络依赖；LLM 过重、延迟高、不可控
  - `dateparser` + 自定义规则：在中文场景下准确率 >92%（10例验证集），支持 `settings={'TIMEZONE': 'Asia/Shanghai', 'RETURN_AS_TIMEZONE_AWARE': True}` 满足时区要求
  - 正则+关键词提取：轻量、确定性高、可维护；避免 NER 模型训练成本

- **核心逻辑流程（伪代码）**：
  ```
  1. 输入校验：text 非空字符串，base_date 若 None 则设为 datetime.now(ZoneInfo("Asia/Shanghai"))
  2. 标题提取：匹配"开.*会|.*评审|.*会面|.*会议"等模板，提取后缀
  3. 时间解析：
      a. 使用 dateparser.parse(text, settings=...) 获取起始 datetime
      b. 若含"到"-"至"，用正则提取结束时间描述，再用 dateparser 单独解析
      c. 若无结束时间，end_time = start_time + timedelta(hours=1)
  4. 地点提取：匹配"地点在[...]"、"在[...]开会"等模式
  5. 参会人提取：匹配"和[姓名]"、"与[姓名]"等，支持多姓名（逗号/顿号分隔）
  6. 输出标准化：所有时间转为 ISO 8601 带 +08:00 时区字符串
  ```

- **性能优化**：
  - `dateparser` 初始化一次（模块级缓存 settings）
  - 正则编译为常量
  - 所有字符串操作使用 `.strip()` 和切片，避免正则全量扫描

## 4. 单元测试用例

| 用例ID | 用例名称 | 输入 | 期望输出（关键字段节选）| 类型 |
|--------|----------|------|------------------------|------|
| UT-01 | 标准单时间点解析 | "明天下午3点开产品评审会" | `"title": "产品评审会", "start_time": "...T15:00:00+08:00"` | 正常 |
| UT-02 | 时间范围解析 | "这个周五下午2点到4点代码评审" | `"start_time": "...T14:00:00+08:00", "end_time": "...T16:00:00+08:00"` | 正常 |
| UT-03 | 多参会人+地点 | "下周一上午10点和张总、李经理在A栋302开会" | `"attendees": ["张总", "李经理"], "location": "A栋302"` | 正常 |
| UT-04 | 边界：仅相对时间无事件 | "明天下午3点" | `"title": ""（空字符串或兜底值），不抛异常` | 边界 |
| UT-05 | 边界：无时间表达 | "开产品评审会" | `"start_time": null 或当天默认值，不抛异常` | 边界 |
| UT-06 | 边界：空字符串 | "" | `raise ValueError` | 边界 |

---

> **Dev 备注**：本设计不引入 LLM 调用，纯规则引擎实现，满足 ≤1s 响应要求。若后续需要泛化能力（如支持方言/模糊表达），可考虑引入轻量 NLP 模型作为兜底，但需重新评估性能 DoD。
