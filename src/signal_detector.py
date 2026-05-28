# -*- coding: utf-8 -*-
"""
信号检测引擎
检测非银存款增幅回落、顶背离等股市见顶信号
+ 宏观经济指标信号（信用周期、资金面、价格信号）
"""

import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass, field
from enum import Enum

from src.config import (
    YOY_LOOKBACK_MONTHS, YOY_DECLINE_THRESHOLD, YOY_HIGH_WATERMARK,
    MOM_LOOKBACK_MONTHS, MOM_DECLINE_THRESHOLD, MOM_HIGH_WATERMARK, MOM_RATIO_TO_PEAK,
    DIVERGENCE_A_CONSECUTIVE, DIVERGENCE_B_CONSECUTIVE,
    M2_MA_WINDOW, PMI_CONTRACTION_MONTHS,
    MARGIN_HIGH_WATERMARK, MARGIN_DECLINE_THRESHOLD,
    SHIBOR_SPIKE_THRESHOLD, CPI_PPI_DIVERGENCE_MONTHS,
    NORTHBOUND_OUTFLOW_MONTHS,
    BDI_EXTREME_HIGH, BDI_EXTREME_LOW, BDI_REVERSAL_WINDOW, BDI_REVERSAL_RATIO,
    RETAIL_DECLINE_MONTHS, FISCAL_TURNING_WINDOW,
    KNOWN_MARKET_TOPS, KNOWN_MARKET_BOTTOMS,
    RISK_CRITICAL_THRESHOLD, RISK_HIGH_REQUIRE_OTHER,
)

logger = logging.getLogger(__name__)


class SignalLevel(Enum):
    """信号严重程度"""
    PRIMARY = "PRIMARY"      # 主要信号
    SECONDARY = "SECONDARY"  # 次要信号
    WARNING = "WARNING"      # 预警信号


class RiskLevel(Enum):
    """综合风险等级"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Signal:
    """单个信号"""
    name: str                          # 信号名称
    level: SignalLevel                 # 严重程度
    date: str                          # 检测到的日期
    detail: str                        # 详细描述
    value: float = 0.0                 # 关键数值（如降幅百分比）


@dataclass
class DetectionResult:
    """检测结果"""
    risk_level: RiskLevel
    signals: list[Signal] = field(default_factory=list)
    summary: str = ""


# ============================================================
# 存款信号（原有 4 个）
# ============================================================

def _check_yoy_decline(df: pd.DataFrame) -> list[Signal]:
    """
    信号1: YoY 增速从高位快速回落
    条件:
      - 近 N 个月内 YoY 峰值曾经 > YOY_HIGH_WATERMARK（处于高位）
      - 当前 YoY 相对峰值下降超过阈值
      - 且当前 YoY 仍在正区间（增速虽然回落但存款还在增长）
    排除: 峰值本身就很低的情况（底部区域的"回落"无意义）
    """
    signals = []
    window = df.tail(YOY_LOOKBACK_MONTHS + 1)

    if len(window) < YOY_LOOKBACK_MONTHS:
        return signals

    yoy_series = window["non_bank_yoy"].dropna()
    if len(yoy_series) < YOY_LOOKBACK_MONTHS:
        return signals

    peak = yoy_series.max()
    latest = yoy_series.iloc[-1]

    # 关键改进: 峰值必须处于高位（> YOY_HIGH_WATERMARK%）才有"回落"的意义
    # 排除底部区域从 -15% 回落到 -20% 的无效信号
    if peak > YOY_HIGH_WATERMARK and latest > 0 and latest < peak:
        decline_ratio = (peak - latest) / peak
        decline_pct = (peak - latest)  # 绝对降幅（百分点）
        if decline_ratio >= YOY_DECLINE_THRESHOLD:
            signals.append(Signal(
                name="非银存款YoY增速从高位回落",
                level=SignalLevel.PRIMARY,
                date=str(df["date"].iloc[-1].strftime("%Y-%m")),
                detail=(
                    f"近{YOY_LOOKBACK_MONTHS}个月YoY峰值 {peak:.1f}%（高位），"
                    f"当前 {latest:.1f}%，绝对降幅 {decline_pct:.1f}个百分点，"
                    f"相对降幅 {decline_ratio*100:.1f}%"
                ),
                value=decline_ratio * 100,
            ))
    return signals


def _check_mom_decline(df: pd.DataFrame) -> list[Signal]:
    """
    信号2: MoM 增速从高位快速回落
    条件: 近 N 个月内 MoM 峰值 > 3%（处于上升通道），当前下降超过阈值
    """
    signals = []
    window = df.tail(MOM_LOOKBACK_MONTHS + 1)

    if len(window) < MOM_LOOKBACK_MONTHS:
        return signals

    mom_series = window["non_bank_mom"].dropna()
    if len(mom_series) < MOM_LOOKBACK_MONTHS:
        return signals

    peak = mom_series.max()
    latest = mom_series.iloc[-1]

    # 改进: 峰值必须 > MOM_HIGH_WATERMARK%（确认资金在快速入场），且当前下降明显
    if peak > MOM_HIGH_WATERMARK and latest < peak * MOM_RATIO_TO_PEAK:
        decline_ratio = (peak - latest) / peak
        decline_pct = (peak - latest)
        signals.append(Signal(
            name="非银存款MoM增速从高位急跌",
            level=SignalLevel.SECONDARY,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"近{MOM_LOOKBACK_MONTHS}个月MoM峰值 {peak:.2f}%（高位），"
                f"当前 {latest:.2f}%，降幅 {decline_pct:.2f}个百分点"
            ),
            value=decline_ratio * 100,
        ))
    return signals


def _check_divergence_a(df: pd.DataFrame) -> list[Signal]:
    """
    信号3: 顶背离-A
    非银存款连续 N 月上升 + 上证指数连续 N 月下降
    """
    signals = []
    n = DIVERGENCE_A_CONSECUTIVE

    if len(df) < n + 1:
        return signals

    tail = df.tail(n + 1)

    deposit_rising = all(
        tail["non_bank_deposit"].iloc[i] > tail["non_bank_deposit"].iloc[i - 1]
        for i in range(1, n + 1)
    )
    index_falling = all(
        tail["sh_close"].iloc[i] < tail["sh_close"].iloc[i - 1]
        for i in range(1, n + 1)
    )

    if deposit_rising and index_falling:
        deposit_change = (
            (tail["non_bank_deposit"].iloc[-1] / tail["non_bank_deposit"].iloc[-n-1] - 1) * 100
        )
        index_change = (
            (tail["sh_close"].iloc[-1] / tail["sh_close"].iloc[-n-1] - 1) * 100
        )
        signals.append(Signal(
            name="顶背离-A（存款涨+指数跌）",
            level=SignalLevel.PRIMARY,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"非银存款连续{n}月上升（+{deposit_change:.2f}%），"
                f"上证指数连续{n}月下降（{index_change:.2f}%）"
            ),
            value=deposit_change,
        ))
    return signals


def _check_divergence_b(df: pd.DataFrame) -> list[Signal]:
    """
    信号4: 顶背离-B
    非银存款 MoM 加速（连续上升） + 指数 MoM 减速（连续下降）
    """
    signals = []
    n = DIVERGENCE_B_CONSECUTIVE

    if len(df) < n + 2:
        return signals

    tail = df.tail(n + 2).copy()
    if tail["non_bank_mom"].isna().any() or tail["sh_mom"].isna().any():
        return signals

    mom_series = tail["non_bank_mom"].iloc[1:]
    sh_mom_series = tail["sh_mom"].iloc[1:]

    mom_accelerating = all(
        mom_series.iloc[i] > mom_series.iloc[i - 1]
        for i in range(1, len(mom_series))
    )
    sh_mom_decelerating = all(
        sh_mom_series.iloc[i] < sh_mom_series.iloc[i - 1]
        for i in range(1, len(sh_mom_series))
    )

    if mom_accelerating and sh_mom_decelerating:
        signals.append(Signal(
            name="顶背离-B（存款加速+指数减速）",
            level=SignalLevel.WARNING,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"非银存款MoM连续{n}月加速，"
                f"上证指数MoM连续{n}月减速"
            ),
        ))
    return signals


# ============================================================
# 宏观指标信号（新增 6 个）
# ============================================================

def _check_m2_inflection(df: pd.DataFrame) -> list[Signal]:
    """
    宏观信号1: M2增速拐点下行
    条件: M2 YoY 的3月移动平均从上升转下降（拐头）
    预测性: M2增速拐头下行后6-12月股市大概率转弱
    """
    signals = []

    if "m2_yoy_ma3" not in df.columns:
        return signals

    series = df["m2_yoy_ma3"].dropna()
    if len(series) < M2_MA_WINDOW + 3:
        return signals

    tail = series.tail(4)
    # 前3个月MA在上升，最近1个月MA下降 → 拐头
    if tail.iloc[-2] > tail.iloc[-3] and tail.iloc[-2] > tail.iloc[-1]:
        current = tail.iloc[-1]
        peak = tail.iloc[-2]
        signals.append(Signal(
            name="M2增速拐点下行",
            level=SignalLevel.WARNING,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"M2增速3月均线拐头下行：{peak:.1f}% → {current:.1f}%，"
                f"信用扩张边际减弱，未来6-12月股市承压"
            ),
            value=current,
        ))
    return signals


def _check_pmi_contraction(df: pd.DataFrame) -> list[Signal]:
    """
    宏观信号2: PMI持续收缩
    条件: 制造业PMI连续 N 月 < 50
    预测性: PMI连续收缩领先企业利润下滑1-2季度
    """
    signals = []

    if "pmi_manufacturing" not in df.columns:
        return signals

    series = df["pmi_manufacturing"].dropna()
    if len(series) < PMI_CONTRACTION_MONTHS:
        return signals

    tail = series.tail(PMI_CONTRACTION_MONTHS)
    if all(v < 50 for v in tail):
        avg_pmi = tail.mean()
        signals.append(Signal(
            name="PMI持续收缩",
            level=SignalLevel.SECONDARY,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"制造业PMI连续{PMI_CONTRACTION_MONTHS}月低于50"
                f"（近{PMI_CONTRACTION_MONTHS}月均值 {avg_pmi:.1f}），"
                f"实体经济景气度下行，领先企业利润1-2季度"
            ),
            value=avg_pmi,
        ))
    return signals


def _check_margin_peak(df: pd.DataFrame) -> list[Signal]:
    """
    宏观信号3: 两融余额增速见顶
    条件: 两融余额YoY峰值 > 20%（高位），当前相对峰值下降 >= 30%
    预测性: 散户杠杆退潮是牛市见顶的同步/略领先信号
    """
    signals = []

    if "margin_yoy" not in df.columns:
        return signals

    series = df["margin_yoy"].dropna()
    if len(series) < 12:
        return signals

    window = series.tail(13)
    peak = window.max()
    latest = window.iloc[-1]

    if peak > MARGIN_HIGH_WATERMARK and latest < peak:
        decline_ratio = (peak - latest) / peak
        if decline_ratio >= MARGIN_DECLINE_THRESHOLD:
            signals.append(Signal(
                name="两融余额增速见顶",
                level=SignalLevel.SECONDARY,
                date=str(df["date"].iloc[-1].strftime("%Y-%m")),
                detail=(
                    f"两融余额YoY从峰值 {peak:.1f}% 降至 {latest:.1f}%，"
                    f"降幅 {decline_ratio*100:.1f}%，散户杠杆退潮"
                ),
                value=decline_ratio * 100,
            ))
    return signals


def _check_shibor_spike(df: pd.DataFrame) -> list[Signal]:
    """
    宏观信号4: SHIBOR 隔夜利率飙升
    条件: SHIBOR隔夜月均值 > 前月 × 150%
    预测性: 资金面骤紧直接压制估值，1-2周内市场承压
    """
    signals = []

    if "shibor_on_avg" not in df.columns:
        return signals

    series = df["shibor_on_avg"].dropna()
    if len(series) < 2:
        return signals

    current = series.iloc[-1]
    prev = series.iloc[-2]

    if prev > 0 and current > prev * SHIBOR_SPIKE_THRESHOLD:
        signals.append(Signal(
            name="SHIBOR隔夜利率飙升",
            level=SignalLevel.WARNING,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"SHIBOR隔夜月均值 {current:.3f}% 较前月 {prev:.3f}% 飙升 "
                f"{(current/prev - 1)*100:.1f}%，资金面骤紧"
            ),
            value=current,
        ))
    return signals


def _check_cpi_ppi_divergence(df: pd.DataFrame) -> list[Signal]:
    """
    宏观信号5: CPI-PPI 剪刀差扩大
    条件: CPI YoY - PPI YoY 连续 N 月扩大
    预测性: 上游挤压下游利润，中下游消费板块承压
    """
    signals = []

    if "cpi_ppi_spread_change" not in df.columns:
        return signals

    series = df["cpi_ppi_spread_change"].dropna()
    if len(series) < CPI_PPI_DIVERGENCE_MONTHS:
        return signals

    tail = series.tail(CPI_PPI_DIVERGENCE_MONTHS)
    if all(v > 0 for v in tail):
        if "cpi_ppi_spread" in df.columns:
            current_spread = df["cpi_ppi_spread"].dropna().iloc[-1]
        else:
            current_spread = 0

        signals.append(Signal(
            name="CPI-PPI剪刀差扩大",
            level=SignalLevel.WARNING,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"CPI-PPI剪刀差连续{CPI_PPI_DIVERGENCE_MONTHS}月扩大"
                f"（当前剪刀差 {current_spread:.2f}个百分点），"
                f"上游挤压下游利润，消费板块承压"
            ),
            value=current_spread,
        ))
    return signals


def _check_northbound_outflow(df: pd.DataFrame) -> list[Signal]:
    """
    宏观信号6: 北向资金持续净流出
    条件: 月度净买入连续 N 月为负
    预测性: 外资撤退往往领先或同步于指数下跌
    """
    signals = []

    if "northbound_net_buy" not in df.columns:
        return signals

    series = df["northbound_net_buy"].dropna()
    if len(series) < NORTHBOUND_OUTFLOW_MONTHS:
        return signals

    tail = series.tail(NORTHBOUND_OUTFLOW_MONTHS)
    if all(v < 0 for v in tail):
        total_outflow = tail.sum()
        signals.append(Signal(
            name="北向资金持续净流出",
            level=SignalLevel.SECONDARY,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"北向资金连续{NORTHBOUND_OUTFLOW_MONTHS}月净流出，"
                f"累计流出 {abs(total_outflow):.0f} 亿元，外资撤退信号"
            ),
            value=total_outflow,
        ))
    return signals


# ============================================================
# 第三批宏观指标信号（新增 3 个）
# ============================================================

def _check_bdi_extreme_reversal(df: pd.DataFrame) -> list[Signal]:
    """
    第三批信号1: BDI极端值反转（趋势确认信号）
    条件: BDI YoY 近 N 月内曾处于极端高位(>+80%)或极端低位(<-40%)，
          当前开始向均值回归
    """
    signals = []

    if "bdi_yoy" not in df.columns:
        return signals

    series = df["bdi_yoy"].dropna()
    if len(series) < BDI_REVERSAL_WINDOW + 3:
        return signals

    # 检查窗口内是否出现过极端值
    window = series.tail(BDI_REVERSAL_WINDOW + 3)
    max_val = window.max()
    min_val = window.min()
    current = series.iloc[-1]

    # 从极端高位回归
    if max_val > BDI_EXTREME_HIGH:
        # 找到极端高点的位置
        peak_idx = window.idxmax()
        current_idx = window.index[-1]
        if current < max_val * (1 - BDI_REVERSAL_RATIO):  # 已从高位回落 50%+
            signals.append(Signal(
                name="BDI极端高位反转（趋势确认）",
                level=SignalLevel.WARNING,
                date=str(df["date"].iloc[-1].strftime("%Y-%m")),
                detail=(
                    f"BDI YoY 从极端高位 {max_val:.1f}% 回落至 {current:.1f}%，"
                    f"全球需求过热信号消退，同步确认市场拐点"
                ),
                value=current,
            ))

    # 从极端低位回归（底部反转信号）
    if min_val < BDI_EXTREME_LOW:
        if current > min_val * (1 - BDI_REVERSAL_RATIO):  # 已从低位回升 50%+（绝对值减小）
            signals.append(Signal(
                name="BDI极端低位反转（趋势确认）",
                level=SignalLevel.WARNING,
                date=str(df["date"].iloc[-1].strftime("%Y-%m")),
                detail=(
                    f"BDI YoY 从极端低位 {min_val:.1f}% 回升至 {current:.1f}%，"
                    f"全球需求衰退触底信号"
                ),
                value=current,
            ))

    return signals


def _check_retail_sustained_decline(df: pd.DataFrame) -> list[Signal]:
    """
    第三批信号2: 社消零售持续下降（预测信号）
    条件: 社消零售 YoY 连续 N 月下降
    预测性: 领先10月负相关(r=-0.50)，社零持续下降约10月后市场可能见底
    """
    signals = []

    if "retail_yoy" not in df.columns:
        return signals

    series = df["retail_yoy"].dropna()
    if len(series) < RETAIL_DECLINE_MONTHS + 1:
        return signals

    tail = series.tail(RETAIL_DECLINE_MONTHS + 1)

    # 检查连续下降（每期都低于前期）
    is_declining = all(
        tail.iloc[i] < tail.iloc[i - 1]
        for i in range(1, len(tail))
    )

    if is_declining:
        start_val = tail.iloc[0]
        end_val = tail.iloc[-1]
        decline = start_val - end_val
        signals.append(Signal(
            name="社消零售持续下降（预测信号）",
            level=SignalLevel.WARNING,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"社消零售 YoY 连续{RETAIL_DECLINE_MONTHS}月下降"
                f"（{start_val:.1f}% → {end_val:.1f}%，降幅 {decline:.1f}个百分点），"
                f"领先指标持续走弱，约10个月后可能形成市场底部（政策宽松预期）"
            ),
            value=decline,
        ))
    return signals


def _check_fiscal_turning_point(df: pd.DataFrame) -> list[Signal]:
    """
    第三批信号3: 财政收入拐点（预测信号）
    条件: 财政收入 YoY 在近 N 月窗口内从下降转为上升
    预测性: 领先10月负相关(r=-0.37)，财政触底反弹→政策空间打开→市场看涨
    """
    signals = []

    if "fiscal_yoy" not in df.columns:
        return signals

    series = df["fiscal_yoy"].dropna()
    if len(series) < FISCAL_TURNING_WINDOW:
        return signals

    tail = series.tail(FISCAL_TURNING_WINDOW)

    # 找到窗口内的最小值（拐点）
    min_idx = tail.idxmin()
    min_val = tail.min()
    current = tail.iloc[-1]
    min_position = tail.index.get_loc(min_idx)

    # 拐点在窗口前半部分，且之后确实回升了
    if min_position < len(tail) - 2 and current > min_val:
        recovery = current - min_val
        signals.append(Signal(
            name="财政收入拐点回升（预测信号）",
            level=SignalLevel.WARNING,
            date=str(df["date"].iloc[-1].strftime("%Y-%m")),
            detail=(
                f"财政收入 YoY 在近{FISCAL_TURNING_WINDOW}月内触底 {min_val:.1f}% 后"
                f"回升至 {current:.1f}%（+{recovery:.1f}个百分点），"
                f"经济基本面改善信号，但负相关性意味着市场可能在10个月后承压"
            ),
            value=recovery,
        ))
    return signals


# ============================================================
# 第五批政策情绪/技术面信号（新增 2 个）
# ============================================================

def _check_credit_pulse_spike(df: pd.DataFrame) -> list[Signal]:
    """
    第五批信号1: 信贷脉冲飙升（政策刺激信号）
    条件: 新增信贷同比连续2月大幅上升（从低位快速回升）
    预测性: 信贷脉冲是政策宽松的同步指标，大幅飙升领先经济复苏
    """
    signals = []

    if "new_credit_yoy" not in df.columns:
        return signals

    series = df["new_credit_yoy"].dropna()
    if len(series) < 3:
        return signals

    tail = series.tail(3).values
    # 最近2个月信贷同比快速上升且当前值为正
    if len(tail) >= 3 and tail[-1] > 0 and tail[-2] > 0:
        rise = tail[-1] - tail[-3]
        if rise > 30:  # 同比增速30个百分点以上跳升
            signals.append(Signal(
                name="信贷脉冲飙升（政策刺激）",
                level=SignalLevel.WARNING,
                date=str(df["date"].iloc[-1].strftime("%Y-%m")),
                detail=(
                    f"新增信贷同比从 {tail[-3]:.1f}% 飙升至 {tail[-1]:.1f}%（+{rise:.1f}个百分点），"
                    f"政策宽松信号，可能领先市场反弹3-6个月"
                ),
                value=rise,
            ))

    return signals


def _check_volume_divergence(df: pd.DataFrame) -> list[Signal]:
    """
    第五批信号2: 量价背离（技术面确认信号）
    条件: 指数3月连续上升 + 成交量连续2月下降
    预测性: 上涨缩量是顶部区域的经典技术信号
    """
    signals = []

    if "sh_close" not in df.columns or "sh_volume" not in df.columns:
        return signals

    n = 3
    if len(df) < n + 1:
        return signals

    tail = df.tail(n + 1)

    # 指数连续3月上升
    index_rising = all(
        tail["sh_close"].iloc[i] > tail["sh_close"].iloc[i - 1]
        for i in range(1, n + 1)
    )
    if not index_rising:
        return signals

    # 成交量连续2月下降
    vol_declining = all(
        tail["sh_volume"].iloc[-i] < tail["sh_volume"].iloc[-i - 1]
        for i in range(1, min(2, n))
    )
    if not vol_declining:
        return signals

    # 确保成交量有效
    if tail["sh_volume"].iloc[-1] <= 0 or tail["sh_volume"].iloc[-3] <= 0:
        return signals

    vol_change = (tail["sh_volume"].iloc[-1] / tail["sh_volume"].iloc[-3] - 1) * 100
    idx_change = (tail["sh_close"].iloc[-1] / tail["sh_close"].iloc[-3] - 1) * 100

    signals.append(Signal(
        name="量价背离（涨缩量）",
        level=SignalLevel.WARNING,
        date=str(df["date"].iloc[-1].strftime("%Y-%m")),
        detail=(
            f"上证指数连续{n}月上升（+{idx_change:.1f}%），"
            f"但成交量下降{abs(vol_change):.1f}%，量价背离暗示上涨动力不足"
        ),
        value=vol_change,
    ))

    return signals


# ============================================================
# 信号汇总与风险判定
# ============================================================

def detect_signals(df: pd.DataFrame) -> DetectionResult:
    """
    执行所有信号检测，返回综合结果
    df: 包含衍生指标的 DataFrame（由 indicators.compute_indicators 生成）
    """
    all_signals = []

    # 存款信号（原有 4 个）
    all_signals.extend(_check_yoy_decline(df))
    all_signals.extend(_check_mom_decline(df))
    all_signals.extend(_check_divergence_a(df))
    all_signals.extend(_check_divergence_b(df))

    # 宏观信号（第二批 6 个）
    all_signals.extend(_check_m2_inflection(df))
    all_signals.extend(_check_pmi_contraction(df))
    all_signals.extend(_check_margin_peak(df))
    all_signals.extend(_check_shibor_spike(df))
    all_signals.extend(_check_cpi_ppi_divergence(df))
    all_signals.extend(_check_northbound_outflow(df))

    # 第三批宏观信号（3 个）
    all_signals.extend(_check_bdi_extreme_reversal(df))
    all_signals.extend(_check_retail_sustained_decline(df))
    all_signals.extend(_check_fiscal_turning_point(df))

    # 第五批政策情绪/技术面信号（2 个）
    all_signals.extend(_check_credit_pulse_spike(df))
    all_signals.extend(_check_volume_divergence(df))

    # 判定风险等级（阈值从配置读取）
    primary_count = sum(1 for s in all_signals if s.level == SignalLevel.PRIMARY)
    secondary_count = sum(1 for s in all_signals if s.level == SignalLevel.SECONDARY)
    warning_count = sum(1 for s in all_signals if s.level == SignalLevel.WARNING)

    if primary_count >= RISK_CRITICAL_THRESHOLD:
        risk = RiskLevel.CRITICAL
    elif primary_count >= 1 and RISK_HIGH_REQUIRE_OTHER and (secondary_count >= 1 or warning_count >= 1):
        risk = RiskLevel.HIGH
    elif primary_count >= 1 and not RISK_HIGH_REQUIRE_OTHER:
        risk = RiskLevel.HIGH
    elif secondary_count >= 1 or warning_count >= 1:
        risk = RiskLevel.MEDIUM
    else:
        risk = RiskLevel.LOW

    # 生成摘要
    if all_signals:
        signal_names = "、".join(s.name for s in all_signals)
        summary = f"检测到 {len(all_signals)} 个信号：{signal_names}"
    else:
        summary = "当前无风险信号，市场状态正常"

    return DetectionResult(
        risk_level=risk,
        signals=all_signals,
        summary=summary,
    )


def backtest_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    历史回测：对每一行数据做信号检测，标记历史信号
    用于验证信号在历史顶部的有效性
    """
    results = []

    # 至少需要 24 个月数据才能做回测（12个月用于YoY）
    min_rows = 24

    for i in range(min_rows, len(df)):
        window = df.iloc[:i + 1]
        detection = detect_signals(window)

        for signal in detection.signals:
            results.append({
                "date": signal.date,
                "signal_name": signal.name,
                "level": signal.level.value,
                "detail": signal.detail,
            })

    return pd.DataFrame(results) if results else pd.DataFrame()
