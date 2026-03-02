"""
生成演示用季度报告 PDF：data/quarterly_report.pdf

内容：某虚构科技公司 2025 年 Q3 季度报告
  - 标题页
  - 执行摘要
  - 财务数据表
  - 各业务线表现
  - 风险与展望
"""

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)

OUTPUT_PATH = Path(__file__).parent / "data" / "quarterly_report.pdf"

# 注册 WQY ZenHei 中文字体
_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
pdfmetrics.registerFont(TTFont("WQY", _FONT_PATH))
pdfmetrics.registerFont(TTFont("WQY-Bold", _FONT_PATH))
_CN_FONT = "WQY"


def build_pdf():
    doc = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"],
        fontSize=24, spaceAfter=12, alignment=TA_CENTER,
        fontName=_CN_FONT,
    )
    h1_style = ParagraphStyle(
        "H1", parent=styles["Heading1"],
        fontSize=16, spaceBefore=18, spaceAfter=8,
        textColor=colors.HexColor("#1a3a5c"),
        fontName=_CN_FONT,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=13, spaceBefore=12, spaceAfter=6,
        textColor=colors.HexColor("#2e6da4"),
        fontName=_CN_FONT,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=10, leading=16, spaceAfter=6,
        fontName=_CN_FONT,
    )
    caption_style = ParagraphStyle(
        "Caption", parent=styles["Normal"],
        fontSize=9, leading=14, textColor=colors.grey, alignment=TA_CENTER,
        fontName=_CN_FONT,
    )

    story = []

    # ── 标题页 ────────────────────────────────────────────────
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph("星云科技股份有限公司", title_style))
    story.append(Paragraph("2025 年第三季度业绩报告", title_style))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("报告期间：2025 年 7 月 1 日 — 2025 年 9 月 30 日", body_style))
    story.append(Paragraph("发布日期：2025 年 10 月 28 日 | 机密等级：内部使用", body_style))
    story.append(Spacer(1, 1.5 * cm))

    # ── 执行摘要 ──────────────────────────────────────────────
    story.append(Paragraph("一、执行摘要", h1_style))
    story.append(Paragraph(
        "2025 年 Q3，星云科技实现营业收入 <b>42.7 亿元</b>，同比增长 <b>23.4%</b>，"
        "环比增长 8.1%，超出市场预期 5.2 个百分点。净利润 <b>6.3 亿元</b>，"
        "净利率 14.8%，同比提升 2.1 个百分点。",
        body_style,
    ))
    story.append(Paragraph(
        "本季度云计算业务首次突破百亿年化营收里程碑，AI 大模型 API 调用量环比增长 "
        "156%，企业客户数量达到 12,847 家，较上季度净增 1,203 家。"
        "海外市场收入占比提升至 18.3%，东南亚区域增速达 67%。",
        body_style,
    ))
    story.append(Paragraph(
        "董事会决议：Q3 不派发中期股息，利润留存用于 AI 基础设施建设，"
        "预计全年资本开支 28 亿元，同比增加 40%。",
        body_style,
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ── 核心财务数据 ──────────────────────────────────────────
    story.append(Paragraph("二、核心财务数据", h1_style))

    fin_data = [
        ["指标", "Q3 2025", "Q2 2025", "Q3 2024", "同比变化"],
        ["营业收入（亿元）", "42.7", "39.5", "34.6", "▲ 23.4%"],
        ["毛利润（亿元）", "19.8", "18.1", "15.4", "▲ 28.6%"],
        ["毛利率", "46.4%", "45.8%", "44.5%", "▲ 1.9pp"],
        ["净利润（亿元）", "6.3", "5.7", "4.8", "▲ 31.3%"],
        ["净利率", "14.8%", "14.4%", "13.9%", "▲ 0.9pp"],
        ["经营现金流（亿元）", "8.1", "7.4", "6.2", "▲ 30.6%"],
        ["研发投入（亿元）", "5.4", "5.1", "4.0", "▲ 35.0%"],
        ["研发投入占收入比", "12.6%", "12.9%", "11.6%", "▲ 1.0pp"],
    ]
    fin_table = Table(fin_data, colWidths=[4.5 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm])
    fin_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), _CN_FONT),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f5fa")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c0c0c0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TEXTCOLOR", (4, 1), (4, -1), colors.HexColor("#1a7a3a")),
    ]))
    story.append(fin_table)
    story.append(Paragraph("表 1：季度核心财务指标对比（pp = 百分点）", caption_style))
    story.append(Spacer(1, 0.5 * cm))

    # ── 业务线表现 ────────────────────────────────────────────
    story.append(Paragraph("三、各业务线表现", h1_style))

    story.append(Paragraph("3.1 云计算与基础设施", h2_style))
    story.append(Paragraph(
        "云计算业务实现收入 <b>21.3 亿元</b>，同比增长 <b>41.2%</b>，占总收入 49.9%，"
        "首次成为公司最大收入来源。核心产品「星云云」月活跃企业用户达 8,421 家，"
        "IaaS 毛利率提升至 38.2%，PaaS 层产品 ARR 突破 50 亿元里程碑。",
        body_style,
    ))

    story.append(Paragraph("3.2 AI 大模型与 API 服务", h2_style))
    story.append(Paragraph(
        "AI 业务收入 <b>9.8 亿元</b>，同比增长 <b>187%</b>，环比增长 34%，是增速最快的业务线。"
        "本季度推出 Xingyun-3 系列模型，文本推理性能在 MMLU 基准测试中达到 87.3 分，"
        "多模态版本支持图文混合输入，已集成至 3,200+ 企业客户的生产系统。",
        body_style,
    ))

    story.append(Paragraph("3.3 企业软件与 SaaS", h2_style))
    story.append(Paragraph(
        "企业软件收入 <b>8.6 亿元</b>，同比增长 <b>12.3%</b>，增速相对平稳。"
        "ERP 产品续约率 94.1%，NPS 评分达到历史最高 72 分。"
        "新签大客户 47 家（合同金额 >500 万元），包括 3 家央企和 8 家 A 股上市公司。",
        body_style,
    ))

    story.append(Paragraph("3.4 专业服务与咨询", h2_style))
    story.append(Paragraph(
        "专业服务收入 <b>3.0 亿元</b>，同比增长 <b>8.7%</b>。毛利率 35.2%，"
        "略低于上季度（36.1%），主要因为 Q3 新招聘 AI 咨询顾问 120 人，"
        "人员成本短期上升。预计 Q4 起毛利率将恢复至 38% 以上。",
        body_style,
    ))

    biz_data = [
        ["业务线", "Q3 收入（亿元）", "收入占比", "同比增速", "毛利率"],
        ["云计算与基础设施", "21.3", "49.9%", "+41.2%", "38.2%"],
        ["AI 大模型与 API", "9.8", "22.9%", "+187.0%", "52.4%"],
        ["企业软件与 SaaS", "8.6", "20.1%", "+12.3%", "61.7%"],
        ["专业服务与咨询", "3.0", "7.0%", "+8.7%", "35.2%"],
        ["合计", "42.7", "100%", "+23.4%", "46.4%"],
    ]
    biz_table = Table(biz_data, colWidths=[4.8 * cm, 3.0 * cm, 2.4 * cm, 2.4 * cm, 2.4 * cm])
    biz_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e6da4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), _CN_FONT),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f5fa")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c0c0c0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("FONTNAME", (0, -1), (-1, -1), _CN_FONT),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8f0fa")),
    ]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(biz_table)
    story.append(Paragraph("表 2：Q3 各业务线财务表现", caption_style))
    story.append(Spacer(1, 0.5 * cm))

    # ── 风险与展望 ────────────────────────────────────────────
    story.append(Paragraph("四、主要风险与 Q4 展望", h1_style))

    story.append(Paragraph("4.1 主要风险项", h2_style))
    risks = [
        "宏观经济压力：企业 IT 预算收紧，部分中小客户推迟采购决策，预计影响 Q4 收入约 1.5 亿元。",
        "竞争加剧：国内大模型赛道竞争白热化，API 单价有下降压力，毛利率可能承压 1-2pp。",
        "人才成本上升：AI 工程师薪资水平持续上涨，Q3 人力成本同比增长 38%。",
        "海外合规：东南亚市场数据本地化法规趋严，需追加合规投入约 0.8 亿元。",
    ]
    for i, risk in enumerate(risks, 1):
        story.append(Paragraph(f"{i}. {risk}", body_style))

    story.append(Paragraph("4.2 Q4 业绩指引", h2_style))
    story.append(Paragraph(
        "公司预计 Q4 2025 营业收入区间为 <b>45.0 — 47.5 亿元</b>（同比增长 19% — 26%），"
        "净利润区间 <b>6.5 — 7.2 亿元</b>。全年收入指引上调至 <b>162 — 165 亿元</b>，"
        "较年初指引上调约 8%。",
        body_style,
    ))

    q4_data = [
        ["指标", "Q4 2025 指引（低端）", "Q4 2025 指引（高端）", "Q4 2024 实际"],
        ["营业收入（亿元）", "45.0", "47.5", "37.8"],
        ["净利润（亿元）", "6.5", "7.2", "5.1"],
        ["净利率", "14.4%", "15.2%", "13.5%"],
        ["研发投入（亿元）", "5.8", "6.2", "4.3"],
    ]
    q4_table = Table(q4_data, colWidths=[4.5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm])
    q4_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), _CN_FONT),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f5fa")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c0c0c0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(q4_table)
    story.append(Paragraph("表 3：Q4 2025 业绩指引", caption_style))
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph(
        "本报告包含前瞻性陈述，实际结果可能因市场变化、竞争格局调整等因素与预期产生差异。"
        "投资者应谨慎参考。",
        caption_style,
    ))

    doc.build(story)
    print(f"PDF 已生成：{OUTPUT_PATH}")
    print(f"文件大小：{OUTPUT_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    build_pdf()
