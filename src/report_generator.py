# -*- coding: utf-8 -*-
"""
报告生成模块
生成 Markdown 格式的分析报告
"""

import pandas as pd
import logging
from datetime import datetime
from pathlib import Path

from src.config import REPORTS_DIR, PREDICTION_HORIZON
from src.indicators import get_latest_metrics
from src.signal_detector import DetectionResult, RiskLevel

logger = logging.getLogger(__name__)


def _fmt(val, fmt_str=".2f", default="-"):
    """安全格式化数值"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return f"{float(val):{fmt_str}}"
    except (ValueError, TypeError):
        return default


def generate_report(
    df: pd.DataFrame,
    indicators_df: pd.DataFrame,
    result: DetectionResult,
    backtest_df: pd.DataFrame,
    prediction_result=None,
    prediction_report_text="",
    deviation_report_text="",
) -> Path:
    """
    生成 Markdown 分析报告
    """
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = REPORTS_DIR / f"{today}_report.md"

    metrics = get_latest_metrics(indicators_df)
    latest_date = metrics["date"].strftime("%Y-%m") if pd.notna(metrics.get("date")) else "N/A"
    latest = indicators_df.iloc[-1]

    # 各数据源最新数据的实际日期（用于数据新鲜度检查）
    source_dates = {}
    for col in ["non_bank_deposit", "household_deposit", "sh_close", "m2_yoy", "pmi_manufacturing",
                "electricity_total_yoy", "margin_balance", "shibor_on_avg", "lpr_1y", "cpi_yoy",
                "ppi_yoy", "northbound_net_buy", "bdi_yoy", "retail_yoy", "fiscal_yoy"]:
        if col in indicators_df.columns:
            last_valid = indicators_df[col].last_valid_index()
            if last_valid is not None:
                source_dates[col] = indicators_df.loc[last_valid, "date"]
            else:
                source_dates[col] = None
        else:
            source_dates[col] = None

    # 风险等级 Emoji
    risk_emoji = {
        RiskLevel.LOW: "🟢",
        RiskLevel.MEDIUM: "🟡",
        RiskLevel.HIGH: "🟠",
        RiskLevel.CRITICAL: "🔴",
    }

    lines = []
    lines.append(f"# 股市宏观分析报告")
    lines.append(f"\n> 生成时间：{today} | 数据截止：{latest_date}")
    lines.append(f"\n## 综合风险评级：{risk_emoji.get(result.risk_level, '')} {result.risk_level.value}")
    lines.append(f"\n{result.summary}")
    lines.append("")

    # 数据来源与更新频率
    lines.append("## 数据来源与更新频率")
    lines.append("")
    lines.append("| 指标 | 原始出处 | 接口 | 原始频率 | 建议更新 | 数据截止 |")
    lines.append("|------|---------|------|---------|---------|---------|")

    def _src_date(col):
        """获取某指标最新有效数据的日期"""
        d = source_dates.get(col)
        if d is not None and pd.notna(d):
            return d.strftime("%Y-%m")
        return "-"

    # 非银/居民存款
    lines.append("| 非银/居民存款 | 央行官网 | 手动CSV `deposits.csv` | 月度 | 每月15日后 | "
                 f"{_src_date('non_bank_deposit')} |")
    # 上证指数
    lines.append("| 上证指数 | 上海证券交易所 | akshare `stock_zh_index_daily` | 日度 | 每个交易日 | "
                 f"{_src_date('sh_close')} |")
    # M2
    lines.append("| M2/M1/M0 | 央行统计数据 | akshare `macro_china_money_supply` | 月度 | 每月10-15日 | "
                 f"{_src_date('m2_yoy')} |")
    # PMI
    lines.append("| PMI | 国家统计局 | akshare `macro_china_pmi` | 月度 | 每月最后一天 | "
                 f"{_src_date('pmi_manufacturing')} |")
    # 用电量
    lines.append("| 全社会用电量 | 国家能源局 | akshare `macro_china_society_electricity` | 月度 | 每月15-20日 | "
                 f"{_src_date('electricity_total_yoy')} |")
    # 两融
    lines.append("| 两融余额 | 上交所/深交所 | akshare `macro_china_market_margin_sh` | 日度 | 每个交易日 | "
                 f"{_src_date('margin_balance')} |")
    # SHIBOR
    lines.append("| SHIBOR隔夜 | 上海银行间同业拆放利率 | akshare `macro_china_shibor_all` | 日度 | 每个交易日 | "
                 f"{_src_date('shibor_on_avg')} |")
    # LPR
    lines.append("| LPR 1年/5年 | 全国银行间同业拆借中心 | akshare `macro_china_lpr` | 月度(20日公布) | 每月20日后 | "
                 f"{_src_date('lpr_1y')} |")
    # CPI
    lines.append("| CPI | 国家统计局 | akshare `macro_china_cpi` | 月度 | 每月9-12日 | "
                 f"{_src_date('cpi_yoy')} |")
    # PPI
    lines.append("| PPI | 国家统计局 | akshare `macro_china_ppi` | 月度 | 每月9-12日 | "
                 f"{_src_date('ppi_yoy')} |")
    # 北向资金
    lines.append("| 北向资金 | 港交所 | akshare `stock_hsgt_hist_em` | 日度 | 每个交易日(注意2024.08后缺失) | "
                 f"{_src_date('northbound_net_buy')} |")
    # BDI
    lines.append("| BDI干散货指数 | 波罗的海交易所 | akshare `macro_china_freight_index` | 日度 | 每个交易日 | "
                 f"{_src_date('bdi_yoy')} |")
    # 社零
    lines.append("| 社消零售总额 | 国家统计局 | akshare `macro_china_consumer_goods_retail` | 月度 | 每月15-17日 | "
                 f"{_src_date('retail_yoy')} |")
    # 财政收入
    lines.append("| 财政收入 | 财政部 | akshare `macro_china_czsr` | 月度 | 每月15-20日 | "
                 f"{_src_date('fiscal_yoy')} |")
    lines.append("")

    lines.append("**建议定时运行频率**：")
    lines.append("")
    lines.append("- **月度指标为主**（M2/PMI/CPI/PPI/社零/财政/用电量/LPR）：均在每月中旬（10-20日）陆续发布")
    lines.append("- **日度指标**（上证指数/两融/SHIBOR/BDI/北向）：每个交易日更新，但本系统按月聚合")
    lines.append("- **推荐频率**：**每周一运行一次**（或每月15日和月底各运行一次）")
    lines.append("- **关键时间点**：每月 **15日-20日** 是大部分月度数据发布窗口，此时运行可获得最完整数据")
    lines.append("- **非银/居民存款**：需手动从央行官网下载更新 `data/deposits.csv`，akshare 无此接口")
    lines.append("")

    # 一、最新数据概览
    lines.append("## 一、最新数据概览")
    lines.append("")
    lines.append("| 指标 | 最新值 | MoM | YoY | 预测性说明 |")
    lines.append("|------|--------|-----|-----|----------|")
    lines.append(f"| 非银金融机构存款 | {_fmt(metrics.get('non_bank_deposit'))} 万亿元 | "
                 f"{_fmt(metrics.get('non_bank_mom'))}% | "
                 f"{_fmt(metrics.get('non_bank_yoy'))}% | 资金入场速度 |")
    lines.append(f"| 居民存款 | {_fmt(metrics.get('household_deposit'))} 万亿元 | "
                 f"{_fmt(latest.get('household_mom'))}% | "
                 f"{_fmt(latest.get('household_yoy'))}% | 慢变量，领先5-7月 |")
    lines.append(f"| 上证指数 | {_fmt(metrics.get('sh_close'))} 点 | "
                 f"{_fmt(metrics.get('sh_mom'))}% | "
                 f"{_fmt(metrics.get('sh_yoy'))}% | — |")
    lines.append(f"| M2同比增速 | {_fmt(metrics.get('m2_yoy'))}% | — | — | 信用周期核心，领先6-12月 |")
    lines.append(f"| 制造业PMI | {_fmt(metrics.get('pmi_manufacturing'))} | — | — | 景气先行，领先利润1-2季度 |")
    lines.append(f"| 全社会用电量同比 | {_fmt(metrics.get('electricity_total_yoy'))}% | — | — | GDP高频替代 |")
    lines.append(f"| 两融余额 | {_fmt(metrics.get('margin_balance'), '.0f')} 亿元 | — | "
                 f"{_fmt(metrics.get('margin_yoy'))}% | 散户杠杆，见顶前1-2月放缓 |")
    lines.append(f"| SHIBOR隔夜(月均) | {_fmt(metrics.get('shibor_on_avg'), '.3f')}% | — | — | 资金面紧张→市场承压 |")
    lines.append(f"| LPR 1年期 | {_fmt(metrics.get('lpr_1y'), '.2f')}% | — | — | 货币政策风向标 |")
    lines.append(f"| CPI同比 | {_fmt(metrics.get('cpi_yoy'))}% | — | — | 通缩(<1%)压制盈利 |")
    lines.append(f"| PPI同比 | {_fmt(metrics.get('ppi_yoy'))}% | — | — | 上游周期股领先1-2月 |")
    if metrics.get("northbound_net_buy") is not None and pd.notna(metrics.get("northbound_net_buy")):
        lines.append(f"| 北向资金月净买入 | {_fmt(metrics.get('northbound_net_buy'), '.0f')} 亿元 | — | — | 外资风向标 |")
    # 第三批宏观指标
    if metrics.get("bdi_yoy") is not None and pd.notna(metrics.get("bdi_yoy")):
        lines.append(f"| BDI干散货指数YoY | {_fmt(metrics.get('bdi_yoy'))}% | — | — | 全球需求同步确认(r=+0.36) |")
    if metrics.get("retail_yoy") is not None and pd.notna(metrics.get("retail_yoy")):
        lines.append(f"| 社消零售YoY | {_fmt(metrics.get('retail_yoy'))}% | — | — | **最强预测指标**(r=-0.50,领先10月) |")
    if metrics.get("fiscal_yoy") is not None and pd.notna(metrics.get("fiscal_yoy")):
        lines.append(f"| 财政收入YoY | {_fmt(metrics.get('fiscal_yoy'))}% | — | — | 预测指标(r=-0.37,领先10月) |")
    lines.append("")

    # 二、宏观信用周期
    lines.append("## 二、宏观信用周期")
    lines.append("")

    m2_yoy = metrics.get("m2_yoy")
    pmi_val = metrics.get("pmi_manufacturing")
    elec_yoy = metrics.get("electricity_total_yoy")

    lines.append("### M2增速（信用周期核心锚定）")
    lines.append("")
    if m2_yoy is not None:
        if m2_yoy > 10:
            lines.append(f"- M2同比 **{m2_yoy:.1f}%**（>10%，宽松环境，利好股市）")
        elif m2_yoy > 8:
            lines.append(f"- M2同比 **{m2_yoy:.1f}%**（8-10%，中性偏松）")
        else:
            lines.append(f"- M2同比 **{m2_yoy:.1f}%**（<8%，偏紧环境，需警惕）")
    else:
        lines.append("- 数据暂无")
    lines.append("")

    lines.append("### PMI（景气先行指标）")
    lines.append("")
    if pmi_val is not None:
        status = "扩张" if pmi_val >= 50 else "收缩"
        lines.append(f"- 制造业PMI **{pmi_val:.1f}**（{status}区间{'✅' if pmi_val >= 50 else '⚠️'}）")
        if "pmi_non_manufacturing" in latest.index and pd.notna(latest.get("pmi_non_manufacturing")):
            lines.append(f"- 非制造业PMI **{latest['pmi_non_manufacturing']:.1f}**")
    else:
        lines.append("- 数据暂无")
    lines.append("")

    lines.append("### 用电量（实体经济高频）")
    lines.append("")
    if elec_yoy is not None:
        ind_elec = metrics.get("electricity_industrial_yoy")
        lines.append(f"- 全社会用电量同比 **{elec_yoy:.1f}%**")
        if ind_elec is not None:
            lines.append(f"- 工业用电量同比 **{ind_elec:.1f}%**（领先工业利润1-2季度）")
    else:
        lines.append("- 数据暂无")
    lines.append("")

    # 三、市场流动性
    lines.append("## 三、市场流动性")
    lines.append("")

    margin_yoy_val = metrics.get("margin_yoy")
    shibor_val = metrics.get("shibor_on_avg")
    northbound_val = metrics.get("northbound_net_buy")

    lines.append("### 两融余额（散户杠杆）")
    lines.append("")
    if metrics.get("margin_balance") is not None:
        lines.append(f"- 两融余额：**{metrics['margin_balance']:.0f} 亿元**")
        if margin_yoy_val is not None:
            if margin_yoy_val > 20:
                lines.append(f"- 同比 **{margin_yoy_val:.1f}%**（高杠杆区间，需关注增速变化）")
            elif margin_yoy_val > 0:
                lines.append(f"- 同比 **{margin_yoy_val:.1f}%**（杠杆温和增长）")
            else:
                lines.append(f"- 同比 **{margin_yoy_val:.1f}%**（杠杆萎缩，市场偏弱）")
    else:
        lines.append("- 数据暂无")
    lines.append("")

    lines.append("### SHIBOR 隔夜利率（资金面）")
    lines.append("")
    if shibor_val is not None:
        lines.append(f"- 隔夜月均值：**{shibor_val:.3f}%**")
    else:
        lines.append("- 数据暂无")
    lines.append("")

    lines.append("### 北向资金（外资流向）")
    lines.append("")
    if northbound_val is not None and pd.notna(northbound_val):
        direction = "净流入" if northbound_val >= 0 else "净流出"
        icon = "🟢" if northbound_val >= 0 else "🔴"
        lines.append(f"- 本月{direction}：**{abs(northbound_val):.0f} 亿元** {icon}")
    else:
        lines.append("- 数据暂无（注意：akshare接口2024.08后数据缺失）")
    lines.append("")

    lines.append("### CPI-PPI 剪刀差（利润分配）")
    lines.append("")
    cpi_val = metrics.get("cpi_yoy")
    ppi_val = metrics.get("ppi_yoy")
    if cpi_val is not None and ppi_val is not None:
        spread = cpi_val - ppi_val
        lines.append(f"- CPI同比 **{cpi_val:.1f}%** / PPI同比 **{ppi_val:.1f}%**")
        lines.append(f"- 剪刀差：**{spread:.2f}** 个百分点", )
        if spread > 3:
            lines.append("- 剪刀差偏大，上游挤压下游利润，消费板块承压")
        elif spread < -2:
            lines.append("- 倒挂剪刀差，上游让利下游，消费板块相对受益")
    else:
        lines.append("- 数据暂无")
    lines.append("")

    # 四、活跃信号详情
    if result.signals:
        lines.append("## 四、活跃信号详情")
        lines.append("")
        for s in result.signals:
            level_icon = {"PRIMARY": "🔴", "SECONDARY": "🟡", "WARNING": "🟠"}
            lines.append(f"### {level_icon.get(s.level.value, '')} {s.name}")
            lines.append(f"- **等级**：{s.level.value}")
            lines.append(f"- **触发时间**：{s.date}")
            lines.append(f"- **详情**：{s.detail}")
            lines.append("")
    else:
        lines.append("## 四、信号状态")
        lines.append("")
        lines.append("当前无任何风险信号触发。")
        lines.append("")

    # 五、近6个月非银存款趋势
    lines.append("## 五、近6个月非银存款趋势")
    lines.append("")
    lines.append("| 月份 | 非银存款(万亿) | MoM(%) | YoY(%) | M2 YoY(%) | PMI | 上证指数 |")
    lines.append("|------|---------------|--------|--------|-----------|-----|---------|")
    tail = indicators_df.tail(6)
    for _, row in tail.iterrows():
        date_str = row["date"].strftime("%Y-%m") if pd.notna(row["date"]) else "N/A"
        pmi_str = _fmt(row.get("pmi_manufacturing"), ".1f")
        m2_str = _fmt(row.get("m2_yoy"), ".1f")
        lines.append(
            f"| {date_str} | {_fmt(row.get('non_bank_deposit'))} | "
            f"{_fmt(row.get('non_bank_mom'))} | { _fmt(row.get('non_bank_yoy'))} | "
            f"{m2_str} | {pmi_str} | {_fmt(row.get('sh_close'))} |"
        )
    lines.append("")

    # 六、历史信号回测
    lines.append("## 六、历史信号回测（验证有效性）")
    lines.append("")

    if not backtest_df.empty:
        from src.config import KNOWN_MARKET_TOPS
        lines.append("### 已知市场顶部 vs 信号触发")
        lines.append("")
        lines.append("| 已知顶部 | 信号是否提前触发 | 超前月数 | 触发的信号 |")
        lines.append("|---------|----------------|---------|-----------|")

        for top in KNOWN_MARKET_TOPS:
            top_dt = pd.to_datetime(top["date"])
            triggered = False
            advance_months = 0
            triggered_signals = []

            for m in range(0, 7):
                check_date = (top_dt - pd.DateOffset(months=m)).strftime("%Y-%m")
                matches = backtest_df[backtest_df["date"] == check_date]
                # 匹配 PRIMARY 优先，其次 SECONDARY，最后 WARNING
                for level in ["PRIMARY", "SECONDARY", "WARNING"]:
                    level_matches = matches[matches["level"] == level]
                    if not level_matches.empty:
                        triggered = True
                        advance_months = m
                        triggered_signals = level_matches["signal_name"].tolist()
                        break
                if triggered:
                    break

            status = "✅ 是" if triggered else "❌ 否"
            advance_str = f"{advance_months} 个月" if triggered else "-"
            sig_str = "、".join(triggered_signals) if triggered_signals else "-"
            lines.append(f"| {top['label']}({top['date']}) | {status} | {advance_str} | {sig_str} |")
        lines.append("")

        # 最近信号列表
        lines.append("### 最近触发的信号（近12个月）")
        lines.append("")
        lines.append("| 日期 | 信号名称 | 等级 | 详情 |")
        lines.append("|------|---------|------|------|")
        recent = backtest_df.tail(20)
        for _, row in recent.iterrows():
            lines.append(f"| {row['date']} | {row['signal_name']} | {row['level']} | {row['detail']} |")
        lines.append("")
    else:
        lines.append("回测数据不足，暂无法生成历史验证。")
        lines.append("")

    # 七、分析建议
    lines.append("## 七、分析建议")
    lines.append("")
    if result.risk_level == RiskLevel.CRITICAL:
        lines.append("⚠️ **高风险警报**：多个主要信号同时触发。")
        lines.append("- 建议大幅降低仓位，锁定利润")
        lines.append("- 存款信号+宏观信号共振，历史上往往对应股市阶段性顶部")
        lines.append("- 考虑增加避险资产配置")
    elif result.risk_level == RiskLevel.HIGH:
        lines.append("🟠 **中高风险**：检测到主要信号，需提高警惕。")
        lines.append("- 建议适度降低仓位")
        lines.append("- 关注M2增速和PMI是否继续恶化")
        lines.append("- 设置止损位")
    elif result.risk_level == RiskLevel.MEDIUM:
        lines.append("🟡 **中等风险**：存在次要预警信号，建议关注。")
        lines.append("- 暂不需要大幅调整仓位")
        lines.append("- 持续跟踪存款和宏观指标的变化趋势")
    else:
        lines.append("🟢 **低风险**：当前无见顶信号，市场处于正常状态。")
        lines.append("- 可以维持当前策略")
        lines.append("- 继续关注数据变化，本报告将自动更新")
    lines.append("")

    # 八、预测系统
    if prediction_result is not None:
        lines.append("## 八、预测系统")
        lines.append("")

        # 预测指标面板
        lines.append("### 预测指标面板（领先型）")
        lines.append("")
        lines.append("| 指标 | 当前值 | 权重 | 方向 | 贡献分数 | 类型 |")
        lines.append("|------|--------|------|------|---------|------|")
        for col, detail in prediction_result.indicator_details.items():
            val_str = _fmt(detail.get("value"), ".1f") if detail.get("value") is not None else "-"
            score_str = f"{detail.get('score', 0):+.3f}"
            dir_label = "负相关" if detail.get("direction") == "negative" else "正相关"
            status = detail.get("status", "-")
            weight = detail.get("weight", 0)
            lines.append(f"| {detail.get('label', col)} | {val_str} | {weight:.0%} | {dir_label} | {score_str} | {status} |")
        lines.append("")

        # 综合预测
        pred_icon = {"看涨": "🟢", "看跌": "🔴", "中性": "🟡"}
        lines.append("### 综合预测结论")
        lines.append("")
        lines.append(f"- **预测方向**：{pred_icon.get(prediction_result.direction, '')} **{prediction_result.direction}**")
        lines.append(f"- **预测分数**：{prediction_result.score:+.3f}（范围 -1 到 +1）")
        lines.append(f"- **置信度**：{prediction_result.confidence:.1%}")
        lines.append(f"- **预测窗口**：未来 {PREDICTION_HORIZON} 个月")
        lines.append("")

        # 趋势确认
        lines.append("### 趋势确认面板（同步型）")
        lines.append("")
        lines.append("| 指标 | 当前值 | 状态 | 与预测一致性 |")
        lines.append("|------|--------|------|------------|")
        for col, detail in prediction_result.confirming_details.items():
            val_str = _fmt(detail.get("value"), ".2f") if detail.get("value") is not None else "-"
            status = detail.get("status", "-")
            match = "✅" if (
                (prediction_result.direction == "看涨" and status == "看涨") or
                (prediction_result.direction == "看跌" and status == "看跌")
            ) else ("🟡" if status == "中性" else "❌")
            lines.append(f"| {detail.get('label', col)} | {val_str} | {status} | {match} |")
        lines.append("")

        if prediction_result.confirming_pct >= 0.70:
            lines.append(f"**确认度：{prediction_result.confirming_pct:.0%}（高度确认）**")
        elif prediction_result.confirming_pct >= 0.40:
            lines.append(f"**确认度：{prediction_result.confirming_pct:.0%}（部分确认）**")
        else:
            lines.append(f"**确认度：{prediction_result.confirming_pct:.0%}（矛盾信号，需谨慎）**")
        lines.append("")

    # 预测验证历史
    if prediction_report_text:
        lines.append(prediction_report_text)

    # 偏差分析报告（自学习）
    if deviation_report_text:
        lines.append(deviation_report_text)

    # 写入文件
    report_content = "\n".join(lines)
    report_path.write_text(report_content, encoding="utf-8")
    logger.info(f"报告已生成: {report_path}")
    return report_path
