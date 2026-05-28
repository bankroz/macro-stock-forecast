# -*- coding: utf-8 -*-
"""
数据管理模块
负责 CSV 读写、数据合并、初始化
"""

import pandas as pd
import logging
from pathlib import Path
from src.config import (
    DEPOSITS_CSV, SH_INDEX_CSV,
    MACRO_M2_CSV, MACRO_PMI_CSV, MACRO_ELECTRICITY_CSV,
    MACRO_MARGIN_CSV, MACRO_SHIBOR_CSV, MACRO_LPR_CSV,
    MACRO_CPI_CSV, MACRO_PPI_CSV, MACRO_NORTHBOUND_CSV,
    MACRO_BDI_CSV, MACRO_RETAIL_CSV, MACRO_FISCAL_CSV,
    MACRO_ENTERPRISE_BOOM_CSV, MACRO_CONSUMER_CONFIDENCE_CSV,
    MACRO_LPI_CSV, MACRO_REAL_ESTATE_CSV, MACRO_UNEMPLOYMENT_CSV,
    MACRO_TRADE_CSV, MACRO_INDUSTRY_CSV, MACRO_FA_INVESTMENT_CSV,
    MACRO_INSURANCE_CSV, MACRO_ENTERPRISE_PRICE_CSV, MACRO_GDP_CSV,
    MACRO_VEGETABLE_BASKET_CSV, MACRO_COMMODITY_PRICE_CSV,
    MACRO_CREDIT_CSV, MACRO_USDCNY_CSV,
    MACRO_COLUMNS,
)

logger = logging.getLogger(__name__)


# ============================================================
# 通用 CSV 读写函数
# ============================================================

def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    """通用 CSV 加载函数"""
    if not path.exists():
        logger.warning(f"数据文件不存在: {path}")
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path, parse_dates=["date"], encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _save_csv(df: pd.DataFrame, path: Path, columns: list[str]):
    """通用 CSV 保存函数"""
    path.parent.mkdir(parents=True, exist_ok=True)
    df_out = df[columns].copy()
    df_out["date"] = df_out["date"].dt.strftime("%Y-%m-%d")
    df_out.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info(f"数据已保存: {path} ({len(df_out)} 行)")


def _update_csv(path: Path, columns: list[str], new_rows: list[dict]):
    """通用 CSV 增量更新函数"""
    existing = _load_csv(path, columns)
    new_df = pd.DataFrame(new_rows)
    if "date" in new_df.columns:
        new_df["date"] = pd.to_datetime(new_df["date"])

    if existing.empty:
        _save_csv(new_df, path, columns)
        return

    # 只追加日期大于已有最大日期的行
    max_date = existing["date"].max()
    to_append = new_df[new_df["date"] > max_date]

    if len(to_append) > 0:
        combined = pd.concat([existing, to_append], ignore_index=True)
        combined = combined.sort_values("date").reset_index(drop=True)
        _save_csv(combined, path, columns)
        logger.info(f"新增 {len(to_append)} 条数据到 {path.name}")
    else:
        logger.info(f"无新数据需要追加到 {path.name}")


# ============================================================
# 存款与指数数据（原有）
# ============================================================

def load_deposits() -> pd.DataFrame:
    """加载存款数据 CSV"""
    return _load_csv(DEPOSITS_CSV, ["date", "household_deposit", "non_bank_deposit"])


def load_sh_index() -> pd.DataFrame:
    """加载上证指数数据 CSV（含成交量）"""
    return _load_csv(SH_INDEX_CSV, ["date", "sh_close", "sh_volume"])


def save_deposits(df: pd.DataFrame):
    _save_csv(df, DEPOSITS_CSV, ["date", "household_deposit", "non_bank_deposit"])


def save_sh_index(df: pd.DataFrame):
    _save_csv(df, SH_INDEX_CSV, ["date", "sh_close", "sh_volume"])


def update_deposits(new_rows: list[dict]):
    _update_csv(DEPOSITS_CSV, ["date", "household_deposit", "non_bank_deposit"], new_rows)


def update_sh_index(new_rows: list[dict]):
    _update_csv(SH_INDEX_CSV, ["date", "sh_close", "sh_volume"], new_rows)


# ============================================================
# 宏观指标数据（新增）
# ============================================================

# 宏观指标路径映射
_MACRO_PATHS = {
    "m2": MACRO_M2_CSV,
    "pmi": MACRO_PMI_CSV,
    "electricity": MACRO_ELECTRICITY_CSV,
    "margin": MACRO_MARGIN_CSV,
    "shibor": MACRO_SHIBOR_CSV,
    "lpr": MACRO_LPR_CSV,
    "cpi": MACRO_CPI_CSV,
    "ppi": MACRO_PPI_CSV,
    "northbound": MACRO_NORTHBOUND_CSV,
    # 第三批宏观指标
    "bdi": MACRO_BDI_CSV,
    "retail": MACRO_RETAIL_CSV,
    "fiscal": MACRO_FISCAL_CSV,
    # 第四批冷门宏观指标
    "enterprise_boom": MACRO_ENTERPRISE_BOOM_CSV,
    "consumer_confidence": MACRO_CONSUMER_CONFIDENCE_CSV,
    "lpi": MACRO_LPI_CSV,
    "real_estate": MACRO_REAL_ESTATE_CSV,
    "unemployment": MACRO_UNEMPLOYMENT_CSV,
    "trade": MACRO_TRADE_CSV,
    "industry": MACRO_INDUSTRY_CSV,
    "fa_investment": MACRO_FA_INVESTMENT_CSV,
    "insurance": MACRO_INSURANCE_CSV,
    "enterprise_price": MACRO_ENTERPRISE_PRICE_CSV,
    "gdp": MACRO_GDP_CSV,
    # 周度/日度聚合（先存）
    "vegetable_basket": MACRO_VEGETABLE_BASKET_CSV,
    "commodity_price": MACRO_COMMODITY_PRICE_CSV,
    # 第五批政策情绪指标
    "credit": MACRO_CREDIT_CSV,
    # 第六批汇率指标
    "usdcny": MACRO_USDCNY_CSV,
}


def load_macro(name: str) -> pd.DataFrame:
    """加载宏观指标 CSV（通用）"""
    if name not in _MACRO_PATHS:
        logger.warning(f"未知宏观指标: {name}")
        return pd.DataFrame()
    return _load_csv(_MACRO_PATHS[name], MACRO_COLUMNS[name])


def save_macro(name: str, df: pd.DataFrame):
    """保存宏观指标 CSV（通用）"""
    if name not in _MACRO_PATHS:
        logger.warning(f"未知宏观指标: {name}")
        return
    _save_csv(df, _MACRO_PATHS[name], MACRO_COLUMNS[name])


def update_macro(name: str, new_rows: list[dict]):
    """增量更新宏观指标 CSV（通用）"""
    if name not in _MACRO_PATHS:
        logger.warning(f"未知宏观指标: {name}")
        return
    _update_csv(_MACRO_PATHS[name], MACRO_COLUMNS[name], new_rows)


# ============================================================
# 数据完整性检查
# ============================================================

def check_data_completeness(verbose: bool = True) -> dict:
    """
    检查关键数据的完整性，返回缺失情况字典。
    在 run.py 中调用，运行时自动提醒手动补数。

    Returns:
        {
            "deposits_missing": [...],   # 缺失非银存款的月份列表
            "deposits_stale": bool,      # 存款数据是否过期（超过40天未更新）
            "index_stale": bool,          # 上证指数是否过期
            "macro_missing": {...},       # 各宏观指标最新数据月份
        }
    """
    from datetime import datetime, timedelta
    import numpy as np

    result = {
        "deposits_missing": [],
        "deposits_stale": False,
        "index_stale": False,
        "macro_missing": {},
        "warnings": [],
    }

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # --- 1. 检查 deposits.csv（非银存款缺失） ---
    deposits = load_deposits()
    if not deposits.empty:
        # 检查最近6个月是否有 non_bank_deposit 为 NaN
        recent = deposits.tail(6).copy()
        missing_months = []
        for _, row in recent.iterrows():
            nb = row["non_bank_deposit"]
            # pd.isna 统一处理：np.nan / None / pd.NA / 非数值字符串
            if pd.isna(nb):
                missing_months.append(row["date"].strftime("%Y-%m"))
            else:
                break  # 从最新往前，遇到有数据的就停止

        result["deposits_missing"] = missing_months
        if missing_months:
            result["warnings"].append(
                f"⚠️ 非银存款数据缺失: {', '.join(missing_months)} 月未填入，"
                f"请在 data/deposits.csv 中手动补充 non_bank_deposit 列"
            )

        # 检查是否过期（最新数据距今超过40天）
        last_date = deposits["date"].max()
        days_since = (now - last_date).days
        if days_since > 40:
            result["deposits_stale"] = True
            result["warnings"].append(
                f"⚠️ 存款数据已 {days_since} 天未更新（最新: {last_date.strftime('%Y-%m-%d')}），"
                f"请运行脚本或手动更新 data/deposits.csv"
            )

    # --- 2. 检查 sh_index.csv（上证指数过期） ---
    sh = load_sh_index()
    if not sh.empty:
        last_date = sh["date"].max()
        days_since = (now - last_date).days
        if days_since > 5:  # 非交易日也按5天提醒
            result["index_stale"] = True
            result["warnings"].append(
                f"⚠️ 上证指数数据已 {days_since} 天未更新（最新: {last_date.strftime('%Y-%m-%d')}），"
                f"请运行 python run.py 更新"
            )

    # --- 3. 检查宏观指标（可选，避免输出过多） ---
    stale_macros = []
    for name in ["m2", "pmi", "bdi", "usdcny"]:  # 只检查最重要的几个
        df = load_macro(name)
        if df.empty:
            continue
        last_date = df["date"].max()
        days_since = (now - last_date).days
        # 月度数据按35天算，日度按5天
        threshold = 35 if name in ["m2", "pmi"] else 5
        if days_since > threshold:
            stale_macros.append(f"{name}({last_date.strftime('%Y-%m-%d')})")

    if stale_macros:
        result["macro_missing"] = stale_macros
        result["warnings"].append(
            f"⚠️ 以下宏观指标可能过期: {', '.join(stale_macros)}"
        )

    if verbose and result["warnings"]:
        logger.warning("=" * 60)
        logger.warning("数据完整性检查结果：发现缺失/过期数据")
        logger.warning("=" * 60)
        for w in result["warnings"]:
            logger.warning(w)
        logger.warning("=" * 60)
        logger.warning("提示：运行 python init_macro_data.py 可重新初始化宏观数据")
        logger.warning("=" * 60)

    return result


# ============================================================
# 数据合并
# ============================================================

def load_merged() -> pd.DataFrame:
    """加载并合并所有数据为一个 DataFrame"""
    dfs = []

    # 原有数据
    deposits = load_deposits()
    if not deposits.empty:
        dfs.append(deposits)

    sh = load_sh_index()
    if not sh.empty:
        dfs.append(sh)

    # 宏观指标
    for name in _MACRO_PATHS:
        macro_df = load_macro(name)
        if not macro_df.empty:
            dfs.append(macro_df)

    if not dfs:
        return pd.DataFrame()

    # 逐个 outer join 合并
    df = dfs[0]
    for other in dfs[1:]:
        # 找到共同列（只保留 date）
        common_cols = [c for c in df.columns if c in other.columns and c != "date"]
        other = other.drop(columns=common_cols, errors="ignore")
        df = pd.merge(df, other, on="date", how="outer")

    df = df.sort_values("date").reset_index(drop=True)
    return df
