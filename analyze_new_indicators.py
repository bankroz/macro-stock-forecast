"""
对11个新数据源跑滞后交叉相关分析
新指标 × 上证指数，0-12月滞后，输出 Pearson r 和 p-value
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from scipy import stats
import logging

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import DATA_DIR
from src.data_manager import load_macro, load_sh_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 新指标列表：(name, csv_path, date_col, value_col, freq)
NEW_INDICATORS = [
    ("enterprise_boom",      "enterprise_boom_index",     "quarterly"),
    ("consumer_confidence",   "confidence_index",          "monthly"),
    ("lpi",                 "lpi_index",                 "monthly"),
    ("real_estate",          "re_prosperity_index",       "monthly"),
    ("unemployment",         "unemployment_rate",          "monthly"),
    ("trade",                "export_yoy",                 "monthly"),
    ("industry",             "industrial_production_yoy", "monthly"),
    ("fa_investment",        "fa_investment_yoy",         "monthly"),
    ("insurance",             "insurance_premium_yoy",     "monthly"),
    ("enterprise_price",      "enterprise_price_yoy",      "monthly"),
    ("gdp",                  "gdp_yoy",                   "quarterly"),
]

def resample_to_monthly(s: pd.Series, method: str = "last") -> pd.Series:
    """将季度/日度数据聚合为月度"""
    if method == "last":
        return s.resample("ME").last()
    elif method == "mean":
        return s.resample("ME").mean()
    elif method == "sum":
        return s.resample("ME").sum()
    return s.resample("ME").last()

def cross_corr(series_a: pd.Series, series_b: pd.Series, lags: range = range(0, 13)) -> list[dict]:
    """
    计算 series_a 相对于 series_b 在滞后 lags 月的交叉相关
    series_a 是指标，series_b 是上证指数（收益率）
    返回：[{lag, r, p_value, n}]
    """
    # 对齐到共同月份
    merged = pd.concat([series_a, series_b], axis=1, join="inner").dropna()
    if len(merged) < 20:
        return []
    col_a, col_b = merged.columns[0], merged.columns[1]
    results = []
    for lag in lags:
        if lag == 0:
            a_vals = merged[col_a].values
            b_vals = merged[col_b].values
        else:
            shifted = merged[col_a].shift(-lag)  # 指标领先 lag 月
            _df = pd.DataFrame({col_a: shifted, col_b: merged[col_b]}).dropna()
            a_vals = _df[col_a].values
            b_vals = _df[col_b].values
        if len(a_vals) < 20:
            results.append({"lag": lag, "r": np.nan, "p": np.nan, "n": 0})
            continue
        r, p = stats.pearsonr(a_vals, b_vals)
        results.append({"lag": lag, "r": round(r, 4), "p": round(p, 4), "n": len(a_vals)})
    return results

def main():
    # 加载上证指数，计算月度收益率
    sh = load_sh_index()
    if sh.empty:
        logger.error("上证指数数据为空")
        return
    sh["date"] = pd.to_datetime(sh["date"])
    sh = sh.set_index("date").sort_index()
    sh_monthly = sh["sh_close"].resample("ME").last()
    sh_return = sh_monthly.pct_change() * 100  # 月度收益率 %

    logger.info(f"上证指数: {len(sh_monthly)} 个月度数据点, "
                f"{sh_monthly.index.min().strftime('%Y-%m')} ~ {sh_monthly.index.max().strftime('%Y-%m')}")

    results_all = {}

    for name, value_col, freq in NEW_INDICATORS:
        df = load_macro(name)
        if df is None or df.empty:
            logger.warning(f"{name}: 无数据，跳过")
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        if value_col not in df.columns:
            # 尝试找包含 yoy 的列
            yoy_cols = [c for c in df.columns if "yoy" in c.lower() or "index" in c.lower() or "rate" in c.lower()]
            if yoy_cols:
                value_col = yoy_cols[0]
                logger.info(f"{name}: 使用列 {value_col}")
            else:
                logger.warning(f"{name}: 找不到值列（尝试过 {value_col}），跳过")
                continue

        series = df[value_col]
        if series.isna().all():
            logger.warning(f"{name}: 全是 NaN，跳过")
            continue

        # 转换为月度
        if freq == "quarterly":
            series_monthly = resample_to_monthly(series, "last")
        else:
            series_monthly = series.resample("ME").last() if series.index.freq is None else series

        # 对齐到上证月份
        series_monthly = series_monthly.dropna()
        if len(series_monthly) < 10:
            logger.warning(f"{name}: 只有 {len(series_monthly)} 个有效数据点，跳过")
            continue

        # 计算交叉相关（指标领先 vs 上证收益率）
        corr_results = cross_corr(series_monthly, sh_return, range(0, 13))
        if corr_results:
            results_all[name] = {
                "value_col": value_col,
                "freq": freq,
                "n_points": len(series_monthly),
                "date_range": f"{series_monthly.index.min().strftime('%Y-%m')} ~ {series_monthly.index.max().strftime('%Y-%m')}",
                "correlations": corr_results,
            }
            # 找最佳滞后
            valid = [r for r in corr_results if not np.isnan(r["r"]) and r["n"] >= 20]
            if valid:
                best = max(valid, key=lambda x: abs(x["r"]))
                sig = "**" if best["p"] < 0.05 else ("*" if best["p"] < 0.1 else "")
                logger.info(f"  {name}: 最佳滞后={best['lag']}月, r={best['r']:.3f}{sig}, p={best['p']:.3f}, n={best['n']}")
            else:
                logger.info(f"  {name}: 无有效相关")
        else:
            logger.warning(f"{name}: 交叉相关计算失败（数据不足）")

    # 打印汇总表
    print("\n" + "="*90)
    print("新指标 × 上证指数 — 滞后交叉相关分析汇总")
    print("="*90)
    print(f"{'指标':<22} {'最佳滞后':>8} {'r':>8} {'p':>8} {'显著?':>6} {'数据点':>8} {'频率':>10}")
    print("-"*90)
    for name, info in sorted(results_all.items(), key=lambda x: -abs(max(
        [r["r"] for r in x[1]["correlations"] if not np.isnan(r["r"])], default=0))):
        corrs = info["correlations"]
        valid = [r for r in corrs if not np.isnan(r["r"]) and r["n"] >= 20]
        if not valid:
            continue
        best = max(valid, key=lambda x: abs(x["r"]))
        sig = "YES" if best["p"] < 0.05 else ("marginal" if best["p"] < 0.1 else "no")
        print(f"{name:<22} {best['lag']:>6}月   {best['r']:>8.3f} {best['p']:>8.4f} {sig:>6} {info['n_points']:>8} {info['freq']:>10}")

    print("\n详细滞后相关矩阵：")
    print("-"*90)
    for name, info in results_all.items():
        corrs = info["correlations"]
        print(f"\n{name} ({info['value_col']}, {info['freq']}, {info['n_points']}pts, {info['date_range']}):")
        header = f"  {'滞后':>6}"
        for r in corrs:
            header += f"  {r['lag']:>5}月"
        print(header)
        row_r = f"  {'r':>6}"
        row_p = f"  {'p':>6}"
        for r in corrs:
            if np.isnan(r["r"]):
                row_r += f"  {'--':>5}"
                row_p += f"  {'--':>5}"
            else:
                s = "**" if r["p"] < 0.01 else ("*" if r["p"] < 0.05 else "")
                row_r += f"  {r['r']:>5.3f}{s}"
                row_p += f"  {r['p']:>5.3f}"
        print(row_r)
        print(row_p)

    # 保存结果到 JSON
    import json
    output_file = DATA_DIR.parent / "docs" / "new_indicators_correlation.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    # numpy types 转 Python 原生
    def to_py(obj):
        if isinstance(obj, dict):
            return {k: to_py(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [to_py(i) for i in obj]
        elif isinstance(obj, (np.floating, np.integer)):
            return float(obj) if isinstance(obj, np.floating) else int(obj)
        elif isinstance(obj, (float, int, str, type(None))):
            return obj
        return obj
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(to_py(results_all), f, ensure_ascii=False, indent=2)
    logger.info(f"\n结果已保存: {output_file}")

    return results_all

if __name__ == "__main__":
    main()
