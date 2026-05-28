# -*- coding: utf-8 -*-
"""
指标计算模块
计算 MoM（环比）、YoY（同比）、滚动均值等衍生指标
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    在合并数据上计算所有衍生指标
    输入 df 列: date, household_deposit, non_bank_deposit, sh_close,
                m2_amount, m2_yoy, pmi_manufacturing, ..., northbound_net_buy
    输出新增列: 所有 _mom, _yoy 指标
    """
    result = df.copy()

    # ========== 存款与指数（原有） ==========

    # MoM 环比变化率 (%)
    if "household_deposit" in result.columns:
        result["household_mom"] = result["household_deposit"].pct_change() * 100
    if "non_bank_deposit" in result.columns:
        result["non_bank_mom"] = result["non_bank_deposit"].pct_change() * 100
    if "sh_close" in result.columns:
        result["sh_mom"] = result["sh_close"].pct_change() * 100

    # YoY 同比变化率 (%)
    if "household_deposit" in result.columns:
        result["household_yoy"] = result["household_deposit"].pct_change(periods=12) * 100
    if "non_bank_deposit" in result.columns:
        result["non_bank_yoy"] = result["non_bank_deposit"].pct_change(periods=12) * 100
    if "sh_close" in result.columns:
        result["sh_yoy"] = result["sh_close"].pct_change(periods=12) * 100

    # 3/6 月滚动均值
    if "non_bank_mom" in result.columns:
        result["non_bank_mom_ma3"] = result["non_bank_mom"].rolling(3).mean()
        result["non_bank_mom_ma6"] = result["non_bank_mom"].rolling(6).mean()
    if "sh_mom" in result.columns:
        result["sh_mom_ma3"] = result["sh_mom"].rolling(3).mean()
        result["sh_mom_ma6"] = result["sh_mom"].rolling(6).mean()

    # ========== M2（宏观信用周期核心） ==========
    # m2_yoy 已在原始数据中，只需确保是 float
    if "m2_yoy" in result.columns:
        result["m2_yoy"] = pd.to_numeric(result["m2_yoy"], errors="coerce")
        result["m2_yoy_ma3"] = result["m2_yoy"].rolling(3).mean()
        # M2 YoY 的 MoM 变化（增速的加速度）
        result["m2_yoy_mom"] = result["m2_yoy"].diff()

    # ========== PMI（景气先行指标） ==========
    # PMI 本身是环比扩散指数，直接使用即可
    if "pmi_manufacturing" in result.columns:
        result["pmi_manufacturing"] = pd.to_numeric(result["pmi_manufacturing"], errors="coerce")
        result["pmi_ma3"] = result["pmi_manufacturing"].rolling(3).mean()

    # ========== 用电量（实体经济高频） ==========
    # electricity_total_yoy 等已在原始数据中
    for col in ["electricity_total_yoy", "electricity_industrial_yoy"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    # ========== 两融余额（市场杠杆） ==========
    # margin_yoy 已在 scraper 中计算
    if "margin_balance" in result.columns:
        result["margin_balance"] = pd.to_numeric(result["margin_balance"], errors="coerce")
    if "margin_yoy" in result.columns:
        result["margin_yoy"] = pd.to_numeric(result["margin_yoy"], errors="coerce")
    elif "margin_balance" in result.columns:
        result["margin_yoy"] = result["margin_balance"].pct_change(periods=12) * 100

    # ========== SHIBOR（资金面） ==========
    # shibor_on_avg 已在原始数据中
    if "shibor_on_avg" in result.columns:
        result["shibor_on_avg"] = pd.to_numeric(result["shibor_on_avg"], errors="coerce")
        result["shibor_on_mom"] = result["shibor_on_avg"].pct_change() * 100

    # ========== LPR（货币政策风向标） ==========
    if "lpr_1y" in result.columns:
        result["lpr_1y"] = pd.to_numeric(result["lpr_1y"], errors="coerce")
        # LPR 用差值表示变化，不用百分比
        result["lpr_1y_change"] = result["lpr_1y"].diff()

    # ========== CPI / PPI（价格信号） ==========
    if "cpi_yoy" in result.columns:
        result["cpi_yoy"] = pd.to_numeric(result["cpi_yoy"], errors="coerce")
    if "ppi_yoy" in result.columns:
        result["ppi_yoy"] = pd.to_numeric(result["ppi_yoy"], errors="coerce")
    # CPI-PPI 剪刀差
    if "cpi_yoy" in result.columns and "ppi_yoy" in result.columns:
        result["cpi_ppi_spread"] = result["cpi_yoy"] - result["ppi_yoy"]
        result["cpi_ppi_spread_change"] = result["cpi_ppi_spread"].diff()

    # ========== 北向资金（外资流向） ==========
    if "northbound_net_buy" in result.columns:
        result["northbound_net_buy"] = pd.to_numeric(result["northbound_net_buy"], errors="coerce")
        # 标记净流出月份
        result["northbound_outflow"] = (result["northbound_net_buy"] < 0).astype(int)

    # ========== 第三批宏观指标 ==========
    # BDI 干散货指数
    if "bdi_yoy" in result.columns:
        result["bdi_yoy"] = pd.to_numeric(result["bdi_yoy"], errors="coerce")
        result["bdi_yoy_ma3"] = result["bdi_yoy"].rolling(3).mean()

    # 社消零售总额
    if "retail_yoy" in result.columns:
        result["retail_yoy"] = pd.to_numeric(result["retail_yoy"], errors="coerce")
        result["retail_yoy_ma3"] = result["retail_yoy"].rolling(3).mean()
        # 方向标记：1=上升, -1=下降, 0=持平
        result["retail_yoy_direction"] = np.sign(result["retail_yoy"].diff())

    # 财政收入
    if "fiscal_yoy" in result.columns:
        result["fiscal_yoy"] = pd.to_numeric(result["fiscal_yoy"], errors="coerce")
        result["fiscal_yoy_ma3"] = result["fiscal_yoy"].rolling(3).mean()
        # 方向标记
        result["fiscal_yoy_direction"] = np.sign(result["fiscal_yoy"].diff())

    # ========== 第四批冷门宏观指标 ==========
    for col in ["enterprise_boom_index", "entrepreneur_confidence_index",
                "confidence_index", "lpi_index", "re_prosperity_index",
                "unemployment_rate", "export_yoy", "import_yoy",
                "industrial_production_yoy", "fa_investment_yoy",
                "insurance_premium_yoy", "enterprise_price_yoy",
                "gdp_yoy", "vegetable_basket_yoy", "commodity_price_yoy"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    return result


def get_latest_metrics(df: pd.DataFrame) -> dict:
    """获取最新月份的关键指标（优先选择有存款和指数数据的行）"""
    # 尝试找到最后有核心数据（存款+指数）的行
    core_mask = df["household_deposit"].notna() & df["sh_close"].notna()
    if core_mask.any():
        latest = df[core_mask].iloc[-1]
    else:
        latest = df.iloc[-1]
    prev_idx = df.index.get_loc(latest.name) - 1
    prev = df.iloc[prev_idx] if prev_idx >= 0 else None

    metrics = {
        "date": latest["date"],
    }

    # 存款与指数
    for key in ["household_deposit", "non_bank_deposit", "sh_close",
                "non_bank_mom", "non_bank_yoy", "sh_mom", "sh_yoy"]:
        if key in latest.index and pd.notna(latest.get(key)):
            metrics[key] = latest[key]

    # 宏观指标
    for key in ["m2_yoy", "pmi_manufacturing", "electricity_total_yoy",
                "margin_balance", "margin_yoy", "shibor_on_avg",
                "lpr_1y", "cpi_yoy", "ppi_yoy", "northbound_net_buy"]:
        if key in latest.index and pd.notna(latest.get(key)):
            metrics[key] = latest[key]

    if prev is not None:
        if "non_bank_mom" in latest.index and pd.notna(latest.get("non_bank_mom")):
            metrics["non_bank_mom_change"] = latest["non_bank_mom"] - prev.get("non_bank_mom", 0)
        if "sh_mom" in latest.index and pd.notna(latest.get("sh_mom")):
            metrics["sh_mom_change"] = latest["sh_mom"] - prev.get("sh_mom", 0)

    return metrics
