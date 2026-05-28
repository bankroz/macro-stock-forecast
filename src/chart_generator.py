# -*- coding: utf-8 -*-
"""
图表生成模块
生成趋势对比图、增速对比图、信号标注图、宏观指标图表
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import logging
from pathlib import Path
from datetime import datetime

from src.config import (
    OUTPUT_DIR, CHART_DPI, CHART_FIGSIZE, FONT_FAMILY,
    KNOWN_MARKET_TOPS, KNOWN_MARKET_BOTTOMS,
)
from src.signal_detector import DetectionResult, RiskLevel

logger = logging.getLogger(__name__)

# 字体配置
plt.rcParams["font.sans-serif"] = FONT_FAMILY
plt.rcParams["axes.unicode_minus"] = False


def generate_main_chart(df: pd.DataFrame, result: DetectionResult = None):
    """
    主图：存款余额 + 上证指数趋势对比（带信号标注）
    """
    chart_date = datetime.now().strftime("%Y-%m-%d")
    fig, ax1 = plt.subplots(figsize=CHART_FIGSIZE)

    # 左轴：存款
    ax1.plot(df["date"], df["household_deposit"], color="#1f77b4", linewidth=3.0,
             label="居民存款余额")
    ax1.plot(df["date"], df["non_bank_deposit"], color="#ff7f0e", linewidth=3.0,
             label="非银金融机构存款余额")
    ax1.set_xlabel("日期", fontsize=16, labelpad=15)
    ax1.set_ylabel("存款余额（万亿元）", fontsize=16, labelpad=15)
    ax1.tick_params(axis="y", labelsize=14)
    ax1.tick_params(axis="x", labelsize=14)
    ax1.grid(True, alpha=0.3)

    # 右轴：上证指数
    ax2 = ax1.twinx()
    ax2.plot(df["date"], df["sh_close"], color="#d62728", linewidth=2.5,
             linestyle="--", label="上证指数收盘")
    ax2.set_ylabel("上证指数（点）", fontsize=16, labelpad=15)
    ax2.tick_params(axis="y", labelsize=14)

    # 标注历史顶部
    for top in KNOWN_MARKET_TOPS:
        t = pd.to_datetime(top["date"])
        mask = (df["date"].dt.year == t.year) & (df["date"].dt.month == t.month)
        if mask.any():
            idx_val = df.loc[mask, "sh_close"].values[0]
            ax2.annotate(
                top["label"],
                xy=(t, idx_val),
                xytext=(15, 15),
                textcoords="offset points",
                fontsize=12,
                bbox=dict(boxstyle="round,pad=0.4", fc="yellow", alpha=0.6),
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0", linewidth=1.2),
            )

    # 标注当前风险等级
    if result and result.risk_level != RiskLevel.LOW:
        risk_colors = {
            RiskLevel.MEDIUM: "#FFA500",
            RiskLevel.HIGH: "#FF4500",
            RiskLevel.CRITICAL: "#FF0000",
        }
        color = risk_colors.get(result.risk_level, "#FFA500")
        ax1.text(
            0.98, 0.98,
            f"风险等级: {result.risk_level.value}",
            transform=ax1.transAxes,
            fontsize=18, fontweight="bold", color=color,
            ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=color, linewidth=2),
        )

    # 图例
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=14)

    # X轴格式
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    plt.xticks(rotation=45)

    plt.title(f"居民存款、非银金融机构存款与上证指数趋势对比 [{chart_date}]", fontsize=22, pad=30)
    plt.tight_layout()

    output_path = OUTPUT_DIR / f"main_trend_{chart_date}.png"
    plt.savefig(output_path, dpi=CHART_DPI, bbox_inches="tight")
    plt.close()
    logger.info(f"主图已保存: {output_path}")
    return output_path


def generate_rate_chart(df: pd.DataFrame):
    """
    增速对比图：非银存款 MoM/YoY vs 上证指数 MoM/YoY
    """
    chart_date = datetime.now().strftime("%Y-%m-%d")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=CHART_FIGSIZE, sharex=True)

    # 上图：MoM 对比
    ax1.plot(df["date"], df["non_bank_mom"], color="#ff7f0e", linewidth=2.0,
             label="非银存款 MoM(%)")
    ax1.plot(df["date"], df["sh_mom"], color="#d62728", linewidth=2.0,
             linestyle="--", label="上证指数 MoM(%)")
    ax1.axhline(y=0, color="gray", linewidth=0.5, linestyle="-")
    ax1.set_ylabel("环比变化率 (%)", fontsize=14)
    ax1.legend(loc="upper left", fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.set_title("环比变化率（MoM）对比", fontsize=16)

    # 下图：YoY 对比
    ax2.plot(df["date"], df["non_bank_yoy"], color="#ff7f0e", linewidth=2.0,
             label="非银存款 YoY(%)")
    ax2.plot(df["date"], df["sh_yoy"], color="#d62728", linewidth=2.0,
             linestyle="--", label="上证指数 YoY(%)")
    ax2.axhline(y=0, color="gray", linewidth=0.5, linestyle="-")
    ax2.set_ylabel("同比变化率 (%)", fontsize=14)
    ax2.set_xlabel("日期", fontsize=14)
    ax2.legend(loc="upper left", fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.set_title("同比变化率（YoY）对比", fontsize=16)

    # X轴格式
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    plt.xticks(rotation=45)

    plt.tight_layout()

    output_path = OUTPUT_DIR / f"rate_comparison_{chart_date}.png"
    plt.savefig(output_path, dpi=CHART_DPI, bbox_inches="tight")
    plt.close()
    logger.info(f"增速对比图已保存: {output_path}")
    return output_path


def generate_signal_chart(df: pd.DataFrame, backtest_df: pd.DataFrame):
    """
    信号回测图：在趋势图上标注历史信号触发点
    """
    if backtest_df.empty:
        logger.info("无历史信号数据，跳过回测图")
        return None

    chart_date = datetime.now().strftime("%Y-%m-%d")
    fig, ax1 = plt.subplots(figsize=CHART_FIGSIZE)

    # 绘制非银存款
    ax1.plot(df["date"], df["non_bank_deposit"], color="#ff7f0e", linewidth=2.5,
             label="非银金融机构存款余额")
    ax1.set_ylabel("非银存款余额（万亿元）", fontsize=14)
    ax1.tick_params(axis="y", labelsize=12)
    ax1.grid(True, alpha=0.3)

    # 右轴：上证指数
    ax2 = ax1.twinx()
    ax2.plot(df["date"], df["sh_close"], color="#d62728", linewidth=2.0,
             linestyle="--", label="上证指数收盘")
    ax2.set_ylabel("上证指数（点）", fontsize=14)
    ax2.tick_params(axis="y", labelsize=12)

    # 标注信号触发点
    signal_dates = pd.to_datetime(backtest_df["date"].unique())
    for sd in signal_dates:
        mask = df["date"].dt.year == sd.year
        mask = mask & (df["date"].dt.month == sd.month)
        if mask.any():
            row = df.loc[mask].iloc[0]
            level = backtest_df.loc[backtest_df["date"] == str(sd.strftime("%Y-%m")), "level"].values[0]
            color = "#FF0000" if level == "PRIMARY" else "#FFA500" if level == "SECONDARY" else "#FFD700"
            ax1.axvline(x=sd, color=color, alpha=0.4, linewidth=1.5, linestyle=":")

    # 标注已知顶部
    for top in KNOWN_MARKET_TOPS:
        t = pd.to_datetime(top["date"])
        ax2.annotate(
            top["label"], xy=(t, top["index"]),
            xytext=(10, -30), textcoords="offset points", fontsize=10,
            bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", alpha=0.7),
            arrowprops=dict(arrowstyle="->", linewidth=0.8),
        )

    # 图例
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=12)

    # X轴格式
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    plt.xticks(rotation=45)

    plt.title(f"历史信号回测（竖线=信号触发点，红=PRIMARY，橙=SECONDARY，黄=WARNING） [{chart_date}]", fontsize=18, pad=20)
    plt.tight_layout()

    output_path = OUTPUT_DIR / f"signal_backtest_{chart_date}.png"
    plt.savefig(output_path, dpi=CHART_DPI, bbox_inches="tight")
    plt.close()
    logger.info(f"信号回测图已保存: {output_path}")
    return output_path


# ============================================================
# 宏观指标图表（新增）
# ============================================================

def generate_macro_credit_chart(df: pd.DataFrame):
    """
    宏观信用周期全景图：M2 YoY + PMI + 上证指数
    预测性展示：信用周期如何领先股市
    """
    if "m2_yoy" not in df.columns or "pmi_manufacturing" not in df.columns:
        logger.info("缺少M2或PMI数据，跳过信用周期图")
        return None

    chart_date = datetime.now().strftime("%Y-%m-%d")
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=CHART_FIGSIZE, sharex=True)

    # 上图：M2 YoY
    ax1.plot(df["date"], df["m2_yoy"], color="#1f77b4", linewidth=2.0, label="M2同比增速(%)")
    if "m2_yoy_ma3" in df.columns:
        ax1.plot(df["date"], df["m2_yoy_ma3"], color="#1f77b4", linewidth=2.5,
                 linestyle="--", label="M2 YoY 3月均线")
    ax1.axhline(y=10, color="gray", linewidth=0.8, linestyle=":", alpha=0.5, label="10% 牛熊分界线")
    ax1.set_ylabel("M2同比增速 (%)", fontsize=14)
    ax1.legend(loc="upper left", fontsize=11)
    ax1.grid(True, alpha=0.3)
    ax1.set_title("信用周期全景：M2增速 → PMI景气 → 股市", fontsize=16, fontweight="bold")

    # 中图：PMI
    ax2.plot(df["date"], df["pmi_manufacturing"], color="#2ca02c", linewidth=2.0, label="制造业PMI")
    if "pmi_non_manufacturing" in df.columns:
        ax2.plot(df["date"], df["pmi_non_manufacturing"], color="#98df8a", linewidth=1.5,
                 linestyle="--", label="非制造业PMI")
    ax2.axhline(y=50, color="red", linewidth=1.0, linestyle=":", alpha=0.7, label="荣枯线(50)")
    ax2.fill_between(df["date"], 50, df["pmi_manufacturing"],
                     where=df["pmi_manufacturing"] < 50, alpha=0.15, color="red")
    ax2.fill_between(df["date"], 50, df["pmi_manufacturing"],
                     where=df["pmi_manufacturing"] >= 50, alpha=0.15, color="green")
    ax2.set_ylabel("PMI指数", fontsize=14)
    ax2.legend(loc="upper left", fontsize=11)
    ax2.grid(True, alpha=0.3)

    # 下图：上证指数
    if "sh_close" in df.columns:
        ax3.plot(df["date"], df["sh_close"], color="#d62728", linewidth=2.0, label="上证指数")
        ax3.set_ylabel("上证指数（点）", fontsize=14)
        ax3.legend(loc="upper left", fontsize=11)

    ax3.set_xlabel("日期", fontsize=14)
    ax3.grid(True, alpha=0.3)

    # X轴格式
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax3.xaxis.set_major_locator(mdates.YearLocator())
    plt.xticks(rotation=45)

    plt.tight_layout()

    output_path = OUTPUT_DIR / f"macro_credit_cycle_{chart_date}.png"
    plt.savefig(output_path, dpi=CHART_DPI, bbox_inches="tight")
    plt.close()
    logger.info(f"信用周期图已保存: {output_path}")
    return output_path


def generate_macro_liquidity_chart(df: pd.DataFrame):
    """
    市场流动性全景图：两融余额 + SHIBOR + 北向资金 + 上证指数
    预测性展示：资金面如何影响股市
    """
    has_margin = "margin_balance" in df.columns
    has_shibor = "shibor_on_avg" in df.columns
    has_northbound = "northbound_net_buy" in df.columns
    has_index = "sh_close" in df.columns

    if not any([has_margin, has_shibor, has_northbound]):
        logger.info("缺少流动性数据，跳过流动性全景图")
        return None

    chart_date = datetime.now().strftime("%Y-%m-%d")
    fig, axes = plt.subplots(4, 1, figsize=CHART_FIGSIZE, sharex=True)

    # 上图：两融余额
    ax1 = axes[0]
    if has_margin:
        ax1.plot(df["date"], df["margin_balance"] / 1e4, color="#9467bd", linewidth=2.0,
                 label="两融余额（万亿元）")
        ax1.set_ylabel("两融余额（万亿元）", fontsize=12)
    ax1.legend(loc="upper left", fontsize=11)
    ax1.grid(True, alpha=0.3)
    ax1.set_title("市场流动性全景：杠杆 + 资金面 + 外资 → 股市", fontsize=16, fontweight="bold")

    # 中图1：SHIBOR
    ax2 = axes[1]
    if has_shibor:
        ax2.plot(df["date"], df["shibor_on_avg"], color="#ff7f0e", linewidth=2.0,
                 label="SHIBOR隔夜月均值(%)")
        ax2.set_ylabel("SHIBOR(%)", fontsize=12)
    ax2.legend(loc="upper left", fontsize=11)
    ax2.grid(True, alpha=0.3)

    # 中图2：北向资金
    ax3 = axes[2]
    if has_northbound:
        colors = ["#e74c3c" if v < 0 else "#2ecc71" for v in df["northbound_net_buy"].fillna(0)]
        ax3.bar(df["date"], df["northbound_net_buy"], color=colors, width=20, alpha=0.7,
                label="北向月度净买入（亿元）")
        ax3.axhline(y=0, color="gray", linewidth=0.5)
        ax3.set_ylabel("北向资金（亿元）", fontsize=12)
    ax3.legend(loc="upper left", fontsize=11)
    ax3.grid(True, alpha=0.3)

    # 下图：上证指数
    ax4 = axes[3]
    if has_index:
        ax4.plot(df["date"], df["sh_close"], color="#d62728", linewidth=2.0, label="上证指数")
        ax4.set_ylabel("上证指数（点）", fontsize=12)
    ax4.set_xlabel("日期", fontsize=14)
    ax4.legend(loc="upper left", fontsize=11)
    ax4.grid(True, alpha=0.3)

    # X轴格式
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax4.xaxis.set_major_locator(mdates.YearLocator())
    plt.xticks(rotation=45)

    plt.tight_layout()

    output_path = OUTPUT_DIR / f"macro_liquidity_{chart_date}.png"
    plt.savefig(output_path, dpi=CHART_DPI, bbox_inches="tight")
    plt.close()
    logger.info(f"流动性全景图已保存: {output_path}")
    return output_path


def generate_prediction_dashboard(prediction_result) -> Path | None:
    """
    生成预测仪表盘图表
    左侧：预测指标雷达图
    右侧：趋势确认状态条
    """
    if prediction_result is None:
        return None

    chart_date = datetime.now().strftime("%Y-%m-%d")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    fig.suptitle(f"走势预测仪表盘 [{chart_date}]", fontsize=18, fontweight="bold")

    # ---- 左侧：预测指标条形图 ----
    indicators = prediction_result.indicator_details
    names = []
    scores = []
    colors = []

    for col, detail in indicators.items():
        names.append(detail.get("label", col))
        score = detail.get("score", 0)
        scores.append(score)
        if score > 0.1:
            colors.append("#e74c3c")  # 红色=看涨
        elif score < -0.1:
            colors.append("#2ecc71")  # 绿色=看跌
        else:
            colors.append("#95a5a6")  # 灰色=中性

    y_pos = range(len(names))
    ax1.barh(y_pos, scores, color=colors, height=0.6, alpha=0.8)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(names, fontsize=12)
    ax1.set_xlim(-1.2, 1.2)
    ax1.axvline(x=0, color="black", linewidth=0.5)
    ax1.set_xlabel("贡献分数 (-1=强看跌, +1=强看涨)", fontsize=12)
    ax1.set_title(f"预测指标 → {prediction_result.direction}（分数 {prediction_result.score:+.3f}）",
                  fontsize=14, fontweight="bold")

    # 标注数值
    for i, (s, w) in enumerate(zip(scores,
            [d.get("weight", 0) for d in indicators.values()])):
        ax1.text(s + (0.05 if s >= 0 else -0.05), i, f"{s:+.2f}(w={w:.0%})",
                va="center", ha="left" if s >= 0 else "right", fontsize=10)

    ax1.grid(True, axis="x", alpha=0.3)

    # ---- 右侧：趋势确认状态条 ----
    confirming = prediction_result.confirming_details
    c_names = []
    c_values = []  # 1=看涨, -1=看跌, 0=中性
    c_colors = []

    for col, detail in confirming.items():
        c_names.append(detail.get("label", col))
        status = detail.get("status", "中性")
        if status == "看涨":
            c_values.append(1)
            c_colors.append("#e74c3c")
        elif status == "看跌":
            c_values.append(-1)
            c_colors.append("#2ecc71")
        else:
            c_values.append(0)
            c_colors.append("#95a5a6")

    y_pos2 = range(len(c_names))
    ax2.barh(y_pos2, c_values, color=c_colors, height=0.6, alpha=0.8)
    ax2.set_yticks(y_pos2)
    ax2.set_yticklabels(c_names, fontsize=12)
    ax2.set_xlim(-1.5, 1.5)
    ax2.axvline(x=0, color="black", linewidth=0.5)
    ax2.set_xlabel("方向 (-1=看跌, 0=中性, +1=看涨)", fontsize=12)

    # 确认度
    pct = prediction_result.confirming_pct
    if pct >= 0.70:
        confirm_text = f"确认度 {pct:.0%}（高度确认）"
    elif pct >= 0.40:
        confirm_text = f"确认度 {pct:.0%}（部分确认）"
    else:
        confirm_text = f"确认度 {pct:.0%}（矛盾信号）"
    ax2.set_title(f"趋势确认面板 — {confirm_text}", fontsize=14, fontweight="bold")
    ax2.grid(True, axis="x", alpha=0.3)

    # 标注
    for i, (v, s) in enumerate(zip(c_values, [d.get("status", "") for d in confirming.values()])):
        ax2.text(v + (0.05 if v >= 0 else -0.05), i, s,
                va="center", ha="left" if v >= 0 else "right", fontsize=10)

    plt.tight_layout()
    output_path = OUTPUT_DIR / f"prediction_dashboard_{chart_date}.png"
    plt.savefig(output_path, dpi=CHART_DPI, bbox_inches="tight")
    plt.close()
    logger.info(f"预测仪表盘已保存: {output_path}")
    return output_path


def generate_all_charts(indicators_df, result, backtest_df, prediction_result) -> dict:
    """
    生成全部图表，返回 {chart_name: Path} 字典。

    返回键名：
      main_trend, rate_comparison, signal_backtest,
      macro_credit, macro_liquidity, prediction_dashboard

    如果某图表生成失败，对应值为 None。
    """
    charts = {}

    try:
        charts["main_trend"] = generate_main_chart(indicators_df, result)
    except Exception as e:
        logger.error(f"主图生成失败: {e}")
        charts["main_trend"] = None

    try:
        charts["rate_comparison"] = generate_rate_chart(indicators_df)
    except Exception as e:
        logger.error(f"增速对比图生成失败: {e}")
        charts["rate_comparison"] = None

    try:
        c = generate_macro_credit_chart(indicators_df)
        charts["macro_credit"] = c if c else None
    except Exception as e:
        logger.error(f"信用周期图生成失败: {e}")
        charts["macro_credit"] = None

    try:
        c = generate_macro_liquidity_chart(indicators_df)
        charts["macro_liquidity"] = c if c else None
    except Exception as e:
        logger.error(f"流动性全景图生成失败: {e}")
        charts["macro_liquidity"] = None

    try:
        c = generate_prediction_dashboard(prediction_result)
        charts["prediction_dashboard"] = c if c else None
    except Exception as e:
        logger.error(f"预测仪表盘生成失败: {e}")
        charts["prediction_dashboard"] = None

    try:
        if not backtest_df.empty:
            c = generate_signal_chart(indicators_df, backtest_df)
            charts["signal_backtest"] = c if c else None
        else:
            charts["signal_backtest"] = None
    except Exception as e:
        logger.error(f"信号回测图生成失败: {e}")
        charts["signal_backtest"] = None

    return charts
