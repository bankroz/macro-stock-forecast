# -*- coding: utf-8 -*-
"""
HTML 报告构建器
生成单文件自包含 HTML 分析报告，图表以 Base64 内嵌
"""

import base64
import pandas as pd
import logging
from pathlib import Path
from datetime import datetime

from src.config import REPORTS_DIR, PREDICTION_HORIZON
from src.indicators import get_latest_metrics
from src.signal_detector import DetectionResult, RiskLevel

logger = logging.getLogger(__name__)


# ============================================================
# 工具函数
# ============================================================

def img_to_base64(img_path) -> str:
    """将图片文件转为 Base64 data URI"""
    if img_path is None:
        return ""
    p = Path(img_path)
    if not p.exists():
        return ""
    with open(p, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{data}"


def _fmt(val, fmt_str=".2f", default="-"):
    """安全格式化数值"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return f"{float(val):{fmt_str}}"
    except (ValueError, TypeError):
        return default


def _value_class(val) -> str:
    """根据数值正负返回 CSS 类名（中国股市：涨红跌绿）"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    try:
        v = float(val)
        if v > 0:
            return "value-up"
        elif v < 0:
            return "value-down"
        return ""
    except (ValueError, TypeError):
        return ""


def _esc(text) -> str:
    """HTML 转义"""
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _chart_html(base64_str, caption="") -> str:
    """生成图表容器 HTML"""
    if not base64_str:
        return '<div class="chart-container chart-missing"><p class="text-secondary">[图表暂不可用]</p></div>'
    cap = f'<p class="chart-caption">{_esc(caption)}</p>' if caption else ""
    return f'<div class="chart-container"><img src="{base64_str}" alt="{_esc(caption)}" loading="lazy">{cap}</div>'


# ============================================================
# CSS 样式
# ============================================================

CSS = """
/* === 基础重置与主题变量 === */
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --accent-red: #e15241;
    --accent-green: #3fb950;
    --accent-gold: #d2991d;
    --accent-blue: #58a6ff;
    --border: #30363d;
    --radius: 8px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 14px; scroll-behavior: smooth; }
body {
    font-family: -apple-system, "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.7;
    padding: 20px;
}

/* === 容器 === */
.container { max-width: 1100px; margin: 0 auto; }

/* === 头部 === */
.report-header {
    text-align: center;
    padding: 48px 24px 36px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 40px;
}
.report-header h1 {
    font-size: 2em;
    font-weight: 700;
    margin-bottom: 8px;
    letter-spacing: 2px;
}
.report-header .meta {
    color: var(--text-secondary);
    font-size: 0.9em;
    margin-bottom: 20px;
}

/* === 风险等级徽章 === */
.risk-badge {
    display: inline-block;
    padding: 8px 24px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 1.1em;
    letter-spacing: 1px;
}
.risk-badge.low { background: rgba(63,185,80,0.12); color: var(--accent-green); border: 1px solid var(--accent-green); }
.risk-badge.medium { background: rgba(210,153,29,0.12); color: var(--accent-gold); border: 1px solid var(--accent-gold); }
.risk-badge.high { background: rgba(225,82,65,0.12); color: var(--accent-red); border: 1px solid var(--accent-red); }
.risk-badge.critical { background: rgba(225,82,65,0.25); color: #ff6b6b; border: 1px solid #ff6b6b; animation: pulse 2s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } }
.summary-text { margin-top: 16px; color: var(--text-secondary); font-size: 0.95em; max-width: 800px; margin-left: auto; margin-right: auto; }

/* === 章节卡片 === */
.section-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    margin-bottom: 32px;
}
.section-title {
    font-size: 1.4em;
    font-weight: 600;
    padding-bottom: 12px;
    margin-bottom: 20px;
    border-bottom: 2px solid var(--accent-red);
    color: var(--text-primary);
}
.sub-title {
    font-size: 1.1em;
    font-weight: 600;
    color: var(--accent-blue);
    margin: 16px 0 8px;
}

/* === 表格 === */
.table-wrapper { overflow-x: auto; margin: 12px 0; }
table {
    width: auto;
    border-collapse: collapse;
    font-size: 0.92em;
}
th {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    font-weight: 600;
    text-align: left;
    padding: 10px 12px;
    white-space: nowrap;
    position: sticky;
    top: 0;
    vertical-align: middle;
    line-height: 1.4;
    height: 1px;
}
td {
    padding: 8px 12px;
    border-top: 1px solid var(--border);
    vertical-align: middle;
    line-height: 1.4;
    height: 1px;
}
tr:nth-child(even) td { background: rgba(33,38,45,0.4); }
tr:hover td { background: rgba(88,166,255,0.06); }
td.num { text-align: left; font-variant-numeric: tabular-nums; }

/* === Markdown 表格（prediction_report 转换） === */
.md-table {
    width: auto;
    margin: 12px 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}
.md-table th {
    background: var(--bg-tertiary);
    color: var(--accent-blue);
    font-weight: 600;
    text-align: left;
    padding: 8px 16px;
    white-space: nowrap;
    position: static;
    vertical-align: middle;
    line-height: 1.4;
    height: 1px;
}
.md-table td {
    text-align: left;
    padding: 6px 16px;
    border-top: 1px solid var(--border);
    vertical-align: middle;
    line-height: 1.4;
    height: 1px;
    font-variant-numeric: tabular-nums;
}
.md-table tr:first-child td { border-top: none; }
.md-table tr:nth-child(even) td { background: rgba(33,38,45,0.4); }

/* === 涨跌着色 === */
.value-up { color: var(--accent-red); font-weight: 500; }
.value-down { color: var(--accent-green); font-weight: 500; }

/* === 信号标签 === */
.signal-tag {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 0.85em;
    font-weight: 600;
    margin: 2px 4px 2px 0;
}
.signal-tag.primary { background: rgba(225,82,65,0.2); color: var(--accent-red); }
.signal-tag.secondary { background: rgba(210,153,29,0.2); color: var(--accent-gold); }
.signal-tag.warning { background: rgba(210,153,29,0.12); color: var(--accent-gold); }

/* === 图表容器 === */
.chart-container {
    text-align: center;
    margin: 24px 0;
    border-radius: var(--radius);
    overflow: hidden;
}
.chart-container img {
    max-width: 100%;
    height: auto;
    border-radius: var(--radius);
    box-shadow: 0 2px 12px rgba(0,0,0,0.3);
}
.chart-caption { color: var(--text-secondary); font-size: 0.85em; margin-top: 8px; }
.chart-missing { padding: 40px; background: var(--bg-tertiary); border-radius: var(--radius); }

/* === 要点列表 === */
.bullet-list { list-style: none; padding: 0; }
.bullet-list li {
    padding: 4px 0 4px 20px;
    position: relative;
    color: var(--text-secondary);
}
.bullet-list li::before {
    content: ">";
    position: absolute;
    left: 0;
    color: var(--accent-red);
    font-weight: bold;
}
.bullet-list li strong, .bullet-list li b { color: var(--text-primary); }

/* === 预测卡片 === */
.prediction-card {
    background: var(--bg-tertiary);
    border-radius: var(--radius);
    padding: 20px;
    margin: 16px 0;
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    justify-content: center;
}
.prediction-item { text-align: center; min-width: 120px; }
.prediction-item .label { font-size: 0.8em; color: var(--text-secondary); margin-bottom: 4px; }
.prediction-item .value { font-size: 1.4em; font-weight: 700; }
.prediction-item .value.bull { color: var(--accent-red); }
.prediction-item .value.bear { color: var(--accent-green); }
.prediction-item .value.neutral { color: var(--accent-gold); }

/* === 确认度进度条 === */
.confirm-bar-wrap { margin: 12px 0 8px; }
.confirm-bar-label { font-size: 0.85em; color: var(--text-secondary); margin-bottom: 4px; }
.confirm-bar { height: 8px; background: var(--bg-tertiary); border-radius: 4px; overflow: hidden; }
.confirm-bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.confirm-bar-fill.high { background: var(--accent-red); }
.confirm-bar-fill.partial { background: var(--accent-gold); }
.confirm-bar-fill.low { background: var(--accent-green); }

/* === 页脚 === */
.report-footer {
    text-align: center;
    padding: 24px;
    color: var(--text-secondary);
    font-size: 0.8em;
    border-top: 1px solid var(--border);
    margin-top: 40px;
}

/* === 响应式 === */
@media (max-width: 768px) {
    body { padding: 12px; }
    .report-header h1 { font-size: 1.5em; }
    .section-card { padding: 16px; }
    .prediction-card { flex-direction: column; align-items: center; }
}
@media (max-width: 480px) {
    html { font-size: 13px; }
    .report-header { padding: 32px 16px 24px; }
}

/* === 打印优化 === */
@media print {
    body { background: #fff; color: #1a1a1a; }
    .section-card { border-color: #ddd; background: #fafafa; }
    .report-header { border-color: #ddd; }
    .risk-badge { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
    .chart-container img { box-shadow: none; border: 1px solid #ddd; }
}
"""


# ============================================================
# 章节构建函数
# ============================================================

def build_header(date_str, latest_date, risk_level, summary) -> str:
    """报告标题区"""
    risk_emoji = {RiskLevel.LOW: "LOW", RiskLevel.MEDIUM: "MEDIUM", RiskLevel.HIGH: "HIGH", RiskLevel.CRITICAL: "CRITICAL"}
    risk_cn = {RiskLevel.LOW: "低风险", RiskLevel.MEDIUM: "中等风险", RiskLevel.HIGH: "中高风险", RiskLevel.CRITICAL: "高风险"}
    return f"""
<div class="report-header">
    <h1>股市宏观分析报告</h1>
    <div class="meta">生成时间：{_esc(date_str)} | 数据截止：{_esc(latest_date)}</div>
    <div class="risk-badge {_esc(risk_level.value)}">
        {_esc(risk_cn.get(risk_level, risk_level.value))} / {_esc(risk_emoji.get(risk_level, ""))}
    </div>
    <div class="summary-text">{_esc(summary)}</div>
</div>"""


def build_data_source_table(source_dates: dict) -> str:
    """数据来源与更新频率表格"""
    def _sd(col):
        d = source_dates.get(col)
        if d is not None and pd.notna(d):
            return d.strftime("%Y-%m")
        return "-"

    sources = [
        ("非银/居民存款", "央行统计", "居民自动/非银手动", "月度", _sd("non_bank_deposit")),
        ("上证指数", "上交所", "akshare", "日度", _sd("sh_close")),
        ("M2/M1/M0", "央行统计", "akshare", "月度", _sd("m2_yoy")),
        ("PMI", "国家统计局", "akshare", "月度", _sd("pmi_manufacturing")),
        ("全社会用电量", "国家能源局", "akshare", "月度", _sd("electricity_total_yoy")),
        ("两融余额", "上交所/深交所", "akshare", "日度", _sd("margin_balance")),
        ("SHIBOR隔夜", "上海银行间拆放利率", "akshare", "日度", _sd("shibor_on_avg")),
        ("LPR 1年/5年", "全国银行间同业拆借中心", "akshare", "月度", _sd("lpr_1y")),
        ("CPI", "国家统计局", "akshare", "月度", _sd("cpi_yoy")),
        ("PPI", "国家统计局", "akshare", "月度", _sd("ppi_yoy")),
        ("北向资金", "港交所", "akshare (2024-08后缺失)", "日度", _sd("northbound_net_buy")),
        ("BDI干散货指数", "波罗的海交易所", "akshare", "日度", _sd("bdi_yoy")),
        ("社消零售总额", "国家统计局", "akshare", "月度", _sd("retail_yoy")),
        ("财政收入", "财政部", "akshare", "月度", _sd("fiscal_yoy")),
    ]

    rows = ""
    for name, src, api, freq, cutoff in sources:
        rows += f"<tr><td>{name}</td><td>{src}</td><td>{api}</td><td>{freq}</td><td class='num'>{cutoff}</td></tr>\n"

    return f"""
<div class="section-card">
    <div class="section-title">数据来源与更新频率</div>
    <div class="table-wrapper">
        <table>
            <thead><tr><th>指标</th><th>原始出处</th><th>接口</th><th>原始频率</th><th>数据截止</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    <div style="margin-top:16px;color:var(--text-secondary);font-size:0.85em;">
        <strong>建议定时运行频率：</strong>月度指标（M2/PMI/CPI/PPI/社零/财政/用电量/LPR）均在每月中旬发布，推荐每周一运行一次。
        非银/居民存款需手动从央行官网下载更新。
    </div>
</div>"""


def build_overview_table(metrics, latest) -> str:
    """第一章：最新数据概览"""
    def _row(name, val, mom="", yoy="", note="", fmt_val=".2f", fmt_mom=".2f", fmt_yoy=".2f"):
        vc = _value_class(yoy if yoy else mom)
        return f'<tr><td>{name}</td><td class="num">{_fmt(val, fmt_val)}</td><td class="num {vc}">{_fmt(mom, fmt_mom)}</td><td class="num {vc}">{_fmt(yoy, fmt_yoy)}</td><td>{note}</td></tr>'

    rows = _row("非银金融机构存款", metrics.get("non_bank_deposit"), metrics.get("non_bank_mom"), metrics.get("non_bank_yoy"), "资金入场速度")
    rows += _row("居民存款", metrics.get("household_deposit"), latest.get("household_mom"), latest.get("household_yoy"), "慢变量，领先5-7月")
    rows += _row("上证指数(点)", metrics.get("sh_close"), metrics.get("sh_mom"), metrics.get("sh_yoy"), "", ".0f", ".2f", ".2f")
    rows += _row("M2同比增速(%)", metrics.get("m2_yoy"), note="信用周期核心，领先6-12月")
    rows += _row("制造业PMI", metrics.get("pmi_manufacturing"), note="景气先行，领先利润1-2季度", fmt_val=".1f")
    rows += _row("全社会用电量同比(%)", metrics.get("electricity_total_yoy"), note="GDP高频替代")
    rows += _row("两融余额(亿元)", metrics.get("margin_balance"), yoy=metrics.get("margin_yoy"), note="散户杠杆", fmt_val=".0f", fmt_yoy=".1f")
    rows += _row("SHIBOR隔夜(%)", metrics.get("shibor_on_avg"), note="资金面温度", fmt_val=".3f")
    rows += _row("LPR 1年期(%)", metrics.get("lpr_1y"), note="货币政策风向标", fmt_val=".2f")
    rows += _row("CPI同比(%)", metrics.get("cpi_yoy"), note="通缩(&lt;1%)压制盈利")
    rows += _row("PPI同比(%)", metrics.get("ppi_yoy"), note="上游周期股领先1-2月")

    # 条件行：北向、BDI、社零、财政
    if metrics.get("northbound_net_buy") is not None and pd.notna(metrics.get("northbound_net_buy")):
        vc = _value_class(metrics["northbound_net_buy"])
        rows += f'<tr><td>北向资金月净买入(亿元)</td><td class="num {vc}">{_fmt(metrics["northbound_net_buy"], ".0f")}</td><td></td><td></td><td>外资风向标</td></tr>'
    if metrics.get("bdi_yoy") is not None and pd.notna(metrics.get("bdi_yoy")):
        rows += _row("BDI干散货指数YoY(%)", metrics.get("bdi_yoy"), note="全球需求同步(r=+0.36)")
    if metrics.get("retail_yoy") is not None and pd.notna(metrics.get("retail_yoy")):
        rows += _row("社消零售YoY(%)", metrics.get("retail_yoy"), note="<strong>最强预测指标</strong>(r=-0.50,领先10月)")
    if metrics.get("fiscal_yoy") is not None and pd.notna(metrics.get("fiscal_yoy")):
        rows += _row("财政收入YoY(%)", metrics.get("fiscal_yoy"), note="预测指标(r=-0.37,领先10月)")

    return f"""
<div class="section-card">
    <div class="section-title">一、最新数据概览</div>
    <div class="table-wrapper">
        <table>
            <thead><tr><th>指标</th><th>最新值</th><th>MoM(%)</th><th>YoY(%)</th><th>预测性说明</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
</div>"""


def build_credit_cycle_section(metrics, latest, chart_b64="") -> str:
    """第二章：宏观信用周期"""
    m2_yoy = metrics.get("m2_yoy")
    pmi_val = metrics.get("pmi_manufacturing")
    elec_yoy = metrics.get("electricity_total_yoy")

    # M2 分析
    if m2_yoy is not None:
        if m2_yoy > 10:
            m2_text = f'M2同比 <span class="value-up"><b>{m2_yoy:.1f}%</b></span>（>10%，宽松环境，利好股市）'
        elif m2_yoy > 8:
            m2_text = f'M2同比 <b>{m2_yoy:.1f}%</b>（8-10%，中性偏松）'
        else:
            m2_text = f'M2同比 <span class="value-down"><b>{m2_yoy:.1f}%</b></span>（&lt;8%，偏紧环境，需警惕）'
    else:
        m2_text = "数据暂无"

    # PMI 分析
    if pmi_val is not None:
        status = "扩张" if pmi_val >= 50 else "收缩"
        pmi_cls = "value-up" if pmi_val >= 50 else "value-down"
        pmi_text = f'制造业PMI <span class="{pmi_cls}"><b>{pmi_val:.1f}</b></span>（{status}区间）'
        if "pmi_non_manufacturing" in latest.index and pd.notna(latest.get("pmi_non_manufacturing")):
            pmi_text += f'，非制造业PMI <b>{latest["pmi_non_manufacturing"]:.1f}</b>'
    else:
        pmi_text = "数据暂无"

    # 用电量分析
    if elec_yoy is not None:
        elec_text = f'全社会用电量同比 <b>{elec_yoy:.1f}%</b>'
        ind_elec = metrics.get("electricity_industrial_yoy")
        if ind_elec is not None:
            elec_text += f'，工业用电量同比 <b>{ind_elec:.1f}%</b>（领先工业利润1-2季度）'
    else:
        elec_text = "数据暂无"

    return f"""
<div class="section-card">
    <div class="section-title">二、宏观信用周期</div>
    <div class="sub-title">M2增速（信用周期核心锚定）</div>
    <ul class="bullet-list"><li>{m2_text}</li></ul>

    <div class="sub-title">PMI（景气先行指标）</div>
    <ul class="bullet-list"><li>{pmi_text}</li></ul>

    <div class="sub-title">用电量（实体经济高频）</div>
    <ul class="bullet-list"><li>{elec_text}</li></ul>

    {_chart_html(chart_b64, "宏观信用周期全景：M2增速 + PMI + 上证指数")}
</div>"""


def build_liquidity_section(metrics, chart_b64="") -> str:
    """第三章：市场流动性"""
    # 两融
    margin_text = "数据暂无"
    if metrics.get("margin_balance") is not None:
        margin_text = f'两融余额：<b>{metrics["margin_balance"]:.0f} 亿元</b>'
        margin_yoy = metrics.get("margin_yoy")
        if margin_yoy is not None:
            if margin_yoy > 20:
                margin_text += f'，同比 <span class="value-up"><b>{margin_yoy:.1f}%</b></span>（高杠杆区间，需关注）'
            elif margin_yoy > 0:
                margin_text += f'，同比 <b>{margin_yoy:.1f}%</b>（杠杆温和增长）'
            else:
                margin_text += f'，同比 <span class="value-down"><b>{margin_yoy:.1f}%</b></span>（杠杆萎缩）'

    # SHIBOR
    shibor_text = "数据暂无"
    if metrics.get("shibor_on_avg") is not None:
        shibor_text = f'隔夜月均值：<b>{metrics["shibor_on_avg"]:.3f}%</b>'

    # 北向
    nb_text = "数据暂无（注意：akshare接口2024.08后数据缺失）"
    nb_val = metrics.get("northbound_net_buy")
    if nb_val is not None and pd.notna(nb_val) and nb_val != 0:
        direction = "净流入" if nb_val >= 0 else "净流出"
        cls = "value-up" if nb_val >= 0 else "value-down"
        nb_text = f'本月{direction}：<span class="{cls}"><b>{abs(nb_val):.0f} 亿元</b></span>'
    elif nb_val is not None and nb_val == 0:
        nb_text = '<span style="color:var(--text-secondary)">数据不可用（akshare接口自2024-08起当日成交净买额为空）</span>'

    # CPI-PPI 剪刀差
    spread_text = "数据暂无"
    cpi_val = metrics.get("cpi_yoy")
    ppi_val = metrics.get("ppi_yoy")
    if cpi_val is not None and ppi_val is not None:
        spread = cpi_val - ppi_val
        spread_text = f'CPI同比 <b>{cpi_val:.1f}%</b> / PPI同比 <b>{ppi_val:.1f}%</b>，剪刀差 <b>{spread:.2f}</b> 个百分点'
        if spread > 3:
            spread_text += "（偏大，上游挤压下游利润）"
        elif spread < -2:
            spread_text += "（倒挂，上游让利下游）"

    return f"""
<div class="section-card">
    <div class="section-title">三、市场流动性</div>
    <div class="sub-title">两融余额（散户杠杆）</div>
    <ul class="bullet-list"><li>{margin_text}</li></ul>

    <div class="sub-title">SHIBOR 隔夜利率（资金面）</div>
    <ul class="bullet-list"><li>{shibor_text}</li></ul>

    <div class="sub-title">北向资金（外资流向）</div>
    <ul class="bullet-list"><li>{nb_text}</li></ul>

    <div class="sub-title">CPI-PPI 剪刀差（利润分配）</div>
    <ul class="bullet-list"><li>{spread_text}</li></ul>

    {_chart_html(chart_b64, "市场流动性全景：两融 + SHIBOR + 北向资金 + 上证指数")}
</div>"""


def build_signals_section(result, chart_b64="") -> str:
    """第四章：活跃信号详情"""
    if not result.signals:
        signals_html = '<p style="color:var(--text-secondary);">当前无任何风险信号触发。</p>'
    else:
        cards = ""
        for s in result.signals:
            level_cls = s.level.value.lower()
            cards += f"""
        <div style="background:var(--bg-tertiary);border-radius:var(--radius);padding:16px;margin-bottom:12px;border-left:3px solid var(--accent-{'red' if s.level.value == 'PRIMARY' else 'gold'});">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                <span class="signal-tag {level_cls}">{s.level.value}</span>
                <strong>{_esc(s.name)}</strong>
            </div>
            <div style="color:var(--text-secondary);font-size:0.9em;">
                触发时间：{_esc(s.date)}<br>
                {_esc(s.detail)}
            </div>
        </div>"""
        signals_html = cards

    return f"""
<div class="section-card">
    <div class="section-title">四、活跃信号详情</div>
    {signals_html}
    {_chart_html(chart_b64, "走势预测仪表盘")}
</div>"""


def build_deposit_trend_section(indicators_df, chart_b64="") -> str:
    """第五章：近6个月非银存款趋势"""
    tail = indicators_df.tail(6)
    rows = ""
    for _, row in tail.iterrows():
        date_str = row["date"].strftime("%Y-%m") if pd.notna(row["date"]) else "N/A"
        mom_cls = _value_class(row.get("non_bank_mom"))
        yoy_cls = _value_class(row.get("non_bank_yoy"))
        rows += f"""<tr>
            <td>{date_str}</td>
            <td class="num">{_fmt(row.get("non_bank_deposit"))}</td>
            <td class="num {mom_cls}">{_fmt(row.get("non_bank_mom"))}</td>
            <td class="num {yoy_cls}">{_fmt(row.get("non_bank_yoy"))}</td>
            <td class="num">{_fmt(row.get("m2_yoy"), ".1f")}</td>
            <td class="num">{_fmt(row.get("pmi_manufacturing"), ".1f")}</td>
            <td class="num">{_fmt(row.get("sh_close"), ".0f")}</td>
        </tr>\n"""

    return f"""
<div class="section-card">
    <div class="section-title">五、近6个月非银存款趋势</div>
    <div class="table-wrapper">
        <table>
            <thead><tr><th>月份</th><th>非银存款(万亿)</th><th>MoM(%)</th><th>YoY(%)</th><th>M2 YoY(%)</th><th>PMI</th><th>上证指数</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    {_chart_html(chart_b64, "非银存款与上证指数趋势对比")}
</div>"""


def build_backtest_section(backtest_df, chart_b64="") -> str:
    """第六章：历史信号回测"""
    if backtest_df.empty:
        return """
<div class="section-card">
    <div class="section-title">六、历史信号回测</div>
    <p style="color:var(--text-secondary);">回测数据不足，暂无法生成历史验证。</p>
</div>"""

    from src.config import KNOWN_MARKET_TOPS

    # 已知顶部 vs 信号触发
    top_rows = ""
    for top in KNOWN_MARKET_TOPS:
        top_dt = pd.to_datetime(top["date"])
        triggered = False
        advance_months = 0
        triggered_signals = []
        for m in range(0, 7):
            check_date = (top_dt - pd.DateOffset(months=m)).strftime("%Y-%m")
            matches = backtest_df[backtest_df["date"] == check_date]
            for level in ["PRIMARY", "SECONDARY", "WARNING"]:
                level_matches = matches[matches["level"] == level]
                if not level_matches.empty:
                    triggered = True
                    advance_months = m
                    triggered_signals = level_matches["signal_name"].tolist()
                    break
            if triggered:
                break

        status_cls = "value-up" if triggered else "value-down"
        status = "是" if triggered else "否"
        adv = f"{advance_months} 个月" if triggered else "-"
        sigs = "、".join(triggered_signals) if triggered_signals else "-"
        top_rows += f'<tr><td>{top["label"]}({top["date"]})</td><td class="{status_cls}">{status}</td><td class="num">{adv}</td><td>{sigs}</td></tr>\n'

    # 最近信号列表
    recent_rows = ""
    recent = backtest_df.tail(20)
    for _, row in recent.iterrows():
        recent_rows += f'<tr><td>{row["date"]}</td><td>{row["signal_name"]}</td><td><span class="signal-tag {row["level"].lower()}">{row["level"]}</span></td><td>{_esc(row["detail"])}</td></tr>\n'

    return f"""
<div class="section-card">
    <div class="section-title">六、历史信号回测（验证有效性）</div>

    <div class="sub-title">已知市场顶部 vs 信号触发</div>
    <div class="table-wrapper">
        <table>
            <thead><tr><th>已知顶部</th><th>信号是否提前触发</th><th>超前月数</th><th>触发的信号</th></tr></thead>
            <tbody>{top_rows}</tbody>
        </table>
    </div>

    <div class="sub-title">最近触发的信号（近12个月）</div>
    <div class="table-wrapper">
        <table>
            <thead><tr><th>日期</th><th>信号名称</th><th>等级</th><th>详情</th></tr></thead>
            <tbody>{recent_rows}</tbody>
        </table>
    </div>

    {_chart_html(chart_b64, "历史信号回测标注")}
</div>"""


def build_advice_section(risk_level) -> str:
    """第七章：分析建议"""
    advice = {
        RiskLevel.CRITICAL: [
            ("<span style='color:var(--accent-red);font-weight:bold;'>高风险警报</span>：多个主要信号同时触发。", ""),
            ("建议大幅降低仓位，锁定利润", ""),
            ("存款信号+宏观信号共振，历史上往往对应股市阶段性顶部", ""),
            ("考虑增加避险资产配置", ""),
        ],
        RiskLevel.HIGH: [
            ("<span style='color:var(--accent-gold);font-weight:bold;'>中高风险</span>：检测到主要信号，需提高警惕。", ""),
            ("建议适度降低仓位", ""),
            ("关注M2增速和PMI是否继续恶化", ""),
            ("设置止损位", ""),
        ],
        RiskLevel.MEDIUM: [
            ("<span style='color:var(--accent-gold);font-weight:bold;'>中等风险</span>：存在次要预警信号，建议关注。", ""),
            ("暂不需要大幅调整仓位", ""),
            ("持续跟踪存款和宏观指标的变化趋势", ""),
        ],
        RiskLevel.LOW: [
            ("<span style='color:var(--accent-green);font-weight:bold;'>低风险</span>：当前无见顶信号，市场处于正常状态。", ""),
            ("可以维持当前策略", ""),
            ("继续关注数据变化，本报告将自动更新", ""),
        ],
    }

    items = advice.get(risk_level, advice[RiskLevel.LOW])
    list_html = "".join(f"<li><b>{item[0]}</b></li>" for item in items)

    return f"""
<div class="section-card">
    <div class="section-title">七、分析建议</div>
    <ul class="bullet-list">{list_html}</ul>
</div>"""


def build_prediction_section(prediction_result, prediction_report_text="", deviation_report_text="", chart_b64="") -> str:
    """第八章：预测系统"""
    if prediction_result is None:
        return ""

    # 预测指标面板
    ind_rows = ""
    for col, detail in prediction_result.indicator_details.items():
        val_str = _fmt(detail.get("value"), ".1f") if detail.get("value") is not None else "-"
        score_str = f"{detail.get('score', 0):+.3f}"
        score_cls = "value-up" if detail.get("score", 0) > 0 else ("value-down" if detail.get("score", 0) < 0 else "")
        dir_label = "负相关" if detail.get("direction") == "negative" else "正相关"
        weight = detail.get("weight", 0)
        status = detail.get("status", "-")
        ind_rows += f'<tr><td>{_esc(detail.get("label", col))}</td><td class="num">{val_str}</td><td class="num">{weight:.0%}</td><td>{dir_label}</td><td class="num {score_cls}">{score_str}</td><td>{status}</td></tr>\n'

    # 综合预测
    dir_cls = {"看涨": "bull", "看跌": "bear", "中性": "neutral"}
    cls = dir_cls.get(prediction_result.direction, "neutral")

    # v3.0: 自适应阈值和看跌确认状态
    adaptive_html = ""
    bear_html = ""
    correction_html = ""
    if hasattr(prediction_result, 'adaptive_info') and prediction_result.adaptive_info:
        ai = prediction_result.adaptive_info
        adaptive_html = f'<div style="font-size:0.85em;margin-top:4px;color:var(--accent);">市场状态: {ai.get("market_state", "-")} (波动率={ai.get("volatility", 0):.2%}, 阈值±{abs(ai.get("bull_adj", 0.2) - 0.2):.2f})</div>'
    if hasattr(prediction_result, 'bear_confirm_info') and prediction_result.bear_confirm_info:
        bi = prediction_result.bear_confirm_info
        if bi.get("downgraded"):
            bear_html = f'<div style="font-size:0.85em;margin-top:4px;color:var(--accent-gold);">⚠ 看跌确认不足({bi.get("confirming_pct", 0):.0%} < {bi.get("required_pct", 0):.0%})，已降级为中性</div>'
    if hasattr(prediction_result, 'correction_info') and prediction_result.correction_info:
        ci = prediction_result.correction_info
        if ci.get("triggered"):
            anomaly_pct = ci.get("anomaly_pct", 0)
            checked = ci.get("total_checked", 0)
            anomaly_n = ci.get("anomaly_count", 0)
            if ci.get("downgrade"):
                correction_html = f'<div style="font-size:0.85em;margin-top:4px;color:var(--danger);">⚠ 修正机制触发: {anomaly_n}/{checked}指标反向({anomaly_pct:.0%})，预测已降级为中性</div>'
            else:
                correction_html = f'<div style="font-size:0.85em;margin-top:4px;color:var(--muted);">修正检查: {anomaly_n}/{checked}指标反向({anomaly_pct:.0%})，未达阈值</div>'

    pred_card = f"""
    <div class="prediction-card">
        <div class="prediction-item">
            <div class="label">预测方向</div>
            <div class="value {cls}">{_esc(prediction_result.direction)}</div>
        </div>
        <div class="prediction-item">
            <div class="label">预测分数</div>
            <div class="value">{prediction_result.score:+.3f}</div>
        </div>
        <div class="prediction-item">
            <div class="label">置信度</div>
            <div class="value">{prediction_result.confidence:.1%}</div>
        </div>
        <div class="prediction-item">
            <div class="label">预测窗口</div>
            <div class="value">{PREDICTION_HORIZON} 个月</div>
        </div>
        {adaptive_html}
        {bear_html}
        {correction_html}
    </div>"""

    # 趋势确认
    conf_rows = ""
    for col, detail in prediction_result.confirming_details.items():
        val_str = _fmt(detail.get("value"), ".2f") if detail.get("value") is not None else "-"
        status = detail.get("status", "-")
        match = ""
        if (prediction_result.direction == "看涨" and status == "看涨") or (prediction_result.direction == "看跌" and status == "看跌"):
            match = '<span class="value-up">✓ 一致</span>'
        elif status == "中性":
            match = '<span style="color:var(--accent-gold);">~ 中性</span>'
        else:
            match = '<span class="value-down">✗ 矛盾</span>'
        conf_rows += f'<tr><td>{_esc(detail.get("label", col))}</td><td class="num">{val_str}</td><td>{status}</td><td>{match}</td></tr>\n'

    # 确认度条
    pct = prediction_result.confirming_pct
    bar_cls = "high" if pct >= 0.70 else ("partial" if pct >= 0.40 else "low")
    if pct >= 0.70:
        conf_label = f"确认度：{pct:.0%}（高度确认）"
    elif pct >= 0.40:
        conf_label = f"确认度：{pct:.0%}（部分确认）"
    else:
        conf_label = f"确认度：{pct:.0%}（矛盾信号，需谨慎）"

    # 预测报告和偏差报告（Markdown → 简单 HTML 段落）
    extra_html = ""
    if prediction_report_text:
        extra_html += _md_to_simple_html(prediction_report_text)
    if deviation_report_text:
        extra_html += _md_to_simple_html(deviation_report_text)

    return f"""
<div class="section-card">
    <div class="section-title">八、预测系统</div>

    <div class="sub-title">预测指标面板（领先型）</div>
    <div class="table-wrapper">
        <table>
            <thead><tr><th>指标</th><th>当前值</th><th>权重</th><th>方向</th><th>贡献分数</th><th>类型</th></tr></thead>
            <tbody>{ind_rows}</tbody>
        </table>
    </div>

    <div class="sub-title">综合预测结论</div>
    {pred_card}

    <div class="sub-title">趋势确认面板（同步型）</div>
    <div class="table-wrapper">
        <table>
            <thead><tr><th>指标</th><th>当前值</th><th>状态</th><th>与预测一致性</th></tr></thead>
            <tbody>{conf_rows}</tbody>
        </table>
    </div>
    <div class="confirm-bar-wrap">
        <div class="confirm-bar-label">{conf_label}</div>
        <div class="confirm-bar"><div class="confirm-bar-fill {bar_cls}" style="width:{pct:.0%}"></div></div>
    </div>

    {_chart_html(chart_b64, "MoM/YoY 增速对比")}
    {extra_html}
</div>"""


def _md_to_simple_html(md_text: str) -> str:
    """将简单的 Markdown 文本（报告生成的）转为 HTML 段落"""
    import re
    html = _esc(md_text)
    # 标题
    html = re.sub(r'^### (.+)$', r'<div class="sub-title">\1</div>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<div class="section-title">\1</div>', html, flags=re.MULTILINE)
    # 加粗
    html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
    # 表格：将 Markdown 表格转换为 HTML <table>
    # 匹配连续的 |...| 行块（含分隔行 |---|---|）
    def _convert_md_table(match):
        table_lines = match.group(0).strip().split("\n")
        rows = []
        headers = []
        for line in table_lines:
            line = line.strip()
            if not line.startswith("|"):
                continue
            # 去掉首尾 |
            cells = [c.strip() for c in line.strip("|").split("|")]
            # 跳过分隔行（|---|---|）
            if all(re.match(r'^[-:]+$', c) for c in cells):
                continue
            tag = "th" if not rows else "td"
            if not rows:
                headers = cells
            # 给特定列加宽度样式
            cells_html = ""
            for i, c in enumerate(cells):
                style = ""
                if i < len(headers) and headers[i] in ("误判原因", "原因推测", "详情"):
                    style = ' style="min-width: 280px;"'
                cells_html += f"<{tag}{style}>{c}</{tag}>"
            rows.append(f"<tr>{cells_html}</tr>")
        if not rows:
            return ""
        return f'<table class="md-table">{"".join(rows)}</table>'
    html = re.sub(
        r'(?:^[ |]*\|.*\|[ ]*$\n?)+',
        _convert_md_table,
        html,
        flags=re.MULTILINE
    )
    # 列表项
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'((?:<li>.*</li>\n?)+)', r'<ul class="bullet-list">\1</ul>', html)
    # 段落（连续非空行，跳过已有的 table/div/ul/li/p 标签）
    lines = html.split("\n")
    result_lines = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if (stripped.startswith("<li>") or stripped.startswith("<ul") or stripped.startswith("</ul")
                or stripped.startswith("<div") or stripped.startswith("<table") or stripped.startswith("<tr")
                or stripped.startswith("</table") or stripped == ""):
            in_list = stripped.startswith("<li>") or stripped.startswith("<ul") and not stripped.startswith("</ul")
            result_lines.append(line)
        else:
            if not in_list:
                result_lines.append(f"<p>{line}</p>")
            else:
                result_lines.append(line)
    return "\n".join(result_lines)


# ============================================================
# 主构建函数
# ============================================================

def build_html(
    df: pd.DataFrame,
    indicators_df: pd.DataFrame,
    result: DetectionResult,
    backtest_df: pd.DataFrame,
    chart_paths: dict,
    prediction_result=None,
    prediction_report_text="",
    deviation_report_text="",
) -> str:
    """
    组装完整 HTML 文档

    Args:
        df: 原始合并数据
        indicators_df: 计算后的指标数据
        result: 信号检测结果
        backtest_df: 回测数据
        chart_paths: {"main_trend": Path, "rate_comparison": Path, ...}
        prediction_result: 预测结果
        prediction_report_text: 预测报告文本（Markdown）
        deviation_report_text: 偏差报告文本（Markdown）
    """
    today = datetime.now().strftime("%Y-%m-%d")
    metrics = get_latest_metrics(indicators_df)
    latest_date = metrics["date"].strftime("%Y-%m") if pd.notna(metrics.get("date")) else "N/A"
    latest = indicators_df.iloc[-1]

    # 数据源日期
    source_dates = {}
    for col in ["non_bank_deposit", "household_deposit", "sh_close", "m2_yoy", "pmi_manufacturing",
                "electricity_total_yoy", "margin_balance", "shibor_on_avg", "lpr_1y", "cpi_yoy",
                "ppi_yoy", "northbound_net_buy", "bdi_yoy", "retail_yoy", "fiscal_yoy"]:
        if col in indicators_df.columns:
            last_valid = indicators_df[col].last_valid_index()
            if last_valid is not None:
                source_dates[col] = indicators_df.loc[last_valid, "date"]

    # Base64 编码图表
    charts = {
        "main_trend": img_to_base64(chart_paths.get("main_trend")),
        "rate_comparison": img_to_base64(chart_paths.get("rate_comparison")),
        "signal_backtest": img_to_base64(chart_paths.get("signal_backtest")),
        "macro_credit": img_to_base64(chart_paths.get("macro_credit")),
        "macro_liquidity": img_to_base64(chart_paths.get("macro_liquidity")),
        "prediction_dashboard": img_to_base64(chart_paths.get("prediction_dashboard")),
    }

    # 组装各章节
    sections = ""
    sections += build_header(today, latest_date, result.risk_level, result.summary)
    sections += build_data_source_table(source_dates)
    sections += build_overview_table(metrics, latest)
    sections += build_credit_cycle_section(metrics, latest, charts["macro_credit"])
    sections += build_liquidity_section(metrics, charts["macro_liquidity"])
    sections += build_signals_section(result, charts["prediction_dashboard"])
    sections += build_deposit_trend_section(indicators_df, charts["main_trend"])
    sections += build_backtest_section(backtest_df, charts["signal_backtest"])
    sections += build_advice_section(result.risk_level)
    sections += build_prediction_section(prediction_result, prediction_report_text, deviation_report_text, charts["rate_comparison"])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>股市宏观分析报告 - {today}</title>
    <style>{CSS}</style>
</head>
<body>
    <div class="container">
        {sections}
        <div class="report-footer">
            股市宏观分析系统 | 生成于 {today} | 数据仅供参考，不构成投资建议
        </div>
    </div>
</body>
</html>"""
    return html
