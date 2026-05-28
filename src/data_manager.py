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
    """加载上证指数数据 CSV"""
    return _load_csv(SH_INDEX_CSV, ["date", "sh_close"])


def save_deposits(df: pd.DataFrame):
    _save_csv(df, DEPOSITS_CSV, ["date", "household_deposit", "non_bank_deposit"])


def save_sh_index(df: pd.DataFrame):
    _save_csv(df, SH_INDEX_CSV, ["date", "sh_close"])


def update_deposits(new_rows: list[dict]):
    _update_csv(DEPOSITS_CSV, ["date", "household_deposit", "non_bank_deposit"], new_rows)


def update_sh_index(new_rows: list[dict]):
    _update_csv(SH_INDEX_CSV, ["date", "sh_close"], new_rows)


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
