# -*- coding: utf-8 -*-
"""
指标预测能力深度分析脚本

分析目标:
1. 对每个可用指标计算 0-12 月滞后与 3 个月后上证指数收益率的相关性
2. 找到每个指标的最优滞后期和最大相关性
3. 计算方向准确率（指标值 > 中位数 → 看涨，3月后收益率是否 > 0）
4. 输出排名表格
5. 找出历史预测失败月份中，哪些其他指标给出了正确信号

用法:
    python analyze_indicators.py
"""

import sys
sys.path.insert(0, ".")

import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

from src.data_manager import load_merged
from src.indicators import compute_indicators


# ============================================================
# 配置
# ============================================================

TARGET_HORIZON = 3  # 预测 3 个月后的收益率
MAX_LAG = 12        # 最大滞后月数
MIN_SAMPLES = 30    # 最少样本数要求

# 不需要分析的列
EXCLUDE_COLS = {
    "date", "sh_close", "sh_volume", "sh_mom", "sh_mom_ma3", "sh_mom_ma6",
    "sh_ma3", "sh_ma20_approx", "sh_ma_slope", "sh_yoy",
    "sh_volume_mom", "sh_volume_ma3_ratio",
}


# ============================================================
# 1. 加载数据
# ============================================================

print("=" * 80)
print("指标预测能力深度分析")
print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)

print("\n[1/6] 加载数据...")
df = load_merged()
df = compute_indicators(df)

# 计算 3 个月后的收益率作为目标变量
df = df.sort_values("date").reset_index(drop=True)
df["future_3m_return"] = df["sh_close"].pct_change(periods=TARGET_HORIZON) * 100

print(f"  数据行数: {len(df)}")
print(f"  日期范围: {df['date'].min().strftime('%Y-%m')} ~ {df['date'].max().strftime('%Y-%m')}")

# 获取所有可用指标列
all_cols = df.columns.tolist()
indicator_cols = [c for c in all_cols if c not in EXCLUDE_COLS
                  and df[c].dropna().shape[0] >= MIN_SAMPLES
                  and c != "future_3m_return"]

# 排除纯标识列
for c in list(indicator_cols):
    if c.startswith("confirm_") or c.endswith("_direction") or c == "northbound_outflow":
        indicator_cols.remove(c)

print(f"  有效指标数: {len(indicator_cols)}")

# 打印所有指标名称
print(f"\n  指标列表:")
for i, col in enumerate(indicator_cols):
    non_nan = df[col].dropna().shape[0]
    print(f"    {i+1:3d}. {col:<40s} (非空: {non_nan})")


# ============================================================
# 2. 计算每个指标在 0-12 月滞后下的相关性
# ============================================================

print(f"\n[2/6] 计算滞后相关性 (lag 0-{MAX_LAG} 月)...")

# 存储结果
lag_results = []  # 每条记录: (indicator, lag, r, p_value, n_samples, 最优标记)

for col in indicator_cols:
    target = df["future_3m_return"].dropna()
    indicator_series = df[col]

    best_r = 0
    best_lag = 0
    best_p = 1.0
    best_n = 0

    for lag in range(0, MAX_LAG + 1):
        # 创建滞后序列
        lagged = indicator_series.shift(lag)

        # 对齐有效数据
        combined = pd.DataFrame({
            "indicator": lagged,
            "target": target
        }).dropna()

        if len(combined) < MIN_SAMPLES:
            continue

        r, p = stats.pearsonr(combined["indicator"], combined["target"])
        n = len(combined)

        lag_results.append({
            "indicator": col,
            "lag": lag,
            "r": round(r, 4),
            "abs_r": round(abs(r), 4),
            "p_value": round(p, 6),
            "n_samples": n,
        })

        if abs(r) > abs(best_r):
            best_r = r
            best_lag = lag
            best_p = p
            best_n = n

# 构建 DataFrame
lag_df = pd.DataFrame(lag_results)


# ============================================================
# 3. 找到每个指标的最优滞后期
# ============================================================

print("\n[3/6] 确定每个指标的最优滞后期...")

# 为每个指标找到最佳 lag（按 abs(r) 最大）
best_lags = []
for col in indicator_cols:
    sub = lag_df[lag_df["indicator"] == col]
    if len(sub) == 0:
        continue
    best_row = sub.loc[sub["abs_r"].idxmax()]
    best_lags.append({
        "indicator": col,
        "best_lag": int(best_row["lag"]),
        "best_r": best_row["r"],
        "best_abs_r": best_row["abs_r"],
        "best_p": best_row["p_value"],
        "best_n": int(best_row["n_samples"]),
    })

best_lag_df = pd.DataFrame(best_lags).sort_values("best_abs_r", ascending=False)


# ============================================================
# 4. 方向准确率测试
# ============================================================

print("\n[4/6] 计算方向准确率...")

direction_results = []

for _, row in best_lag_df.iterrows():
    col = row["indicator"]
    lag = int(row["best_lag"])
    best_r = row["best_r"]

    # 滞后序列
    lagged = df[col].shift(lag)

    # 对齐目标变量
    combined = pd.DataFrame({
        "indicator": lagged,
        "target": df["future_3m_return"],
        "date": df["date"],
        "sh_close": df["sh_close"]
    }).dropna()

    if len(combined) < MIN_SAMPLES:
        continue

    # 预测逻辑:
    # - 正相关指标: 当前值 > 中位数 → 看涨
    # - 负相关指标: 当前值 > 中位数 → 看跌
    median = combined["indicator"].median()
    if best_r > 0:
        combined["predicted_up"] = (combined["indicator"] > median).astype(int)
    else:
        combined["predicted_up"] = (combined["indicator"] <= median).astype(int)

    combined["actual_up"] = (combined["target"] > 0).astype(int)
    combined["correct"] = (combined["predicted_up"] == combined["actual_up"]).astype(int)

    accuracy = combined["correct"].mean() * 100
    n = len(combined)
    correct_n = int(combined["correct"].sum())

    # 计算买/卖信号下的平均收益率
    buy_mask = combined["predicted_up"] == 1
    sell_mask = combined["predicted_up"] == 0
    avg_return_buy = combined.loc[buy_mask, "target"].mean() if buy_mask.sum() > 0 else 0
    avg_return_sell = combined.loc[sell_mask, "target"].mean() if sell_mask.sum() > 0 else 0

    # 计算统计显著性 (二项检验)
    # 准确率 > 50% 的 p 值
    if accuracy > 50:
        binom_p = stats.binomtest(correct_n, n, p=0.5, alternative="greater").pvalue
    else:
        binom_p = 1.0

    # 记录失败月份
    fail_months = combined[combined["correct"] == 0]["date"].dt.strftime("%Y-%m").tolist()

    direction_results.append({
        "indicator": col,
        "best_lag": lag,
        "best_r": best_r,
        "abs_r": abs(best_r),
        "direction": "正" if best_r > 0 else "负",
        "n_samples": n,
        "correct": correct_n,
        "accuracy_pct": round(accuracy, 2),
        "binom_p": round(binom_p, 6),
        "avg_return_buy": round(avg_return_buy, 2),
        "avg_return_sell": round(avg_return_sell, 2),
        "spread": round(avg_return_buy - avg_return_sell, 2),
        "fail_months": fail_months,
        "n_fails": len(fail_months),
    })

dir_df = pd.DataFrame(direction_results).sort_values("accuracy_pct", ascending=False)


# ============================================================
# 5. 输出排名表格
# ============================================================

print("\n" + "=" * 80)
print("5. 分析结果")
print("=" * 80)

# ---- 5.1 最优滞后相关性 Top 30 ----
print(f"\n{'='*80}")
print("5.1 最优滞后相关性排名 (Top 30)")
print(f"{'='*80}")
print(f"{'排名':<6}{'指标':<40s}{'最优Lag':<10}{'相关系数r':<12}{'|r|':<10}{'p值':<12}{'样本数'}")
print("-" * 80)

for rank, (_, row) in enumerate(best_lag_df.head(30).iterrows(), 1):
    print(f"{rank:<6}{row['indicator']:<40s}{row['best_lag']:<10}"
          f"{row['best_r']:>+8.4f}  {row['best_abs_r']:>8.4f}  "
          f"{row['best_p']:>10.6f}  {int(row['best_n'])}")


# ---- 5.2 方向准确率 Top 30 ----
print(f"\n{'='*80}")
print("5.2 方向准确率排名 (Top 30)")
print(f"{'='*80}")
print(f"{'排名':<6}{'指标':<40s}{'Lag':<6}{'r':<10}{'方向':<6}"
      f"{'准确率':<10}{'样本':<8}{'买入均收益':<12}{'卖出均收益':<12}{'买卖差':<10}")
print("-" * 80)

for rank, (_, row) in enumerate(dir_df.head(30).iterrows(), 1):
    print(f"{rank:<6}{row['indicator']:<40s}{row['best_lag']:<6}"
          f"{row['best_r']:>+7.4f}  {row['direction']:<6}"
          f"{row['accuracy_pct']:>6.1f}%  {int(row['n_samples']):<8}"
          f"{row['avg_return_buy']:>+8.2f}%  {row['avg_return_sell']:>+8.2f}%  "
          f"{row['spread']:>+8.2f}%")


# ---- 5.3 全量排名表（前50） ----
print(f"\n{'='*80}")
print("5.3 综合排名 (相关性 × 准确率, Top 50)")
print(f"{'='*80}")

dir_df["composite_score"] = dir_df["abs_r"] * dir_df["accuracy_pct"] / 100
composite = dir_df.sort_values("composite_score", ascending=False)

print(f"{'排名':<6}{'指标':<40s}{'最优Lag':<8}{'|r|':<8}"
      f"{'准确率':<8}{'买入均收益':<12}{'卖出均收益':<12}{'综合分':<10}")
print("-" * 80)

for rank, (_, row) in enumerate(composite.head(50).iterrows(), 1):
    print(f"{rank:<6}{row['indicator']:<40s}{row['best_lag']:<8}"
          f"{row['abs_r']:>6.4f}  {row['accuracy_pct']:>5.1f}%  "
          f"{row['avg_return_buy']:>+8.2f}%  {row['avg_return_sell']:>+8.2f}%  "
          f"{row['composite_score']:>8.4f}")


# ============================================================
# 6. 预测失败月份分析
# ============================================================

print(f"\n{'='*80}")
print("6. 预测失败月份分析")
print("=" * 80)

# 取方向准确率 Top 10 指标
top10 = dir_df.head(10)

# 收集所有失败月份（按出现频率）
fail_counter = {}
fail_details = {}

for _, row in top10.iterrows():
    for m in row["fail_months"]:
        fail_counter[m] = fail_counter.get(m, 0) + 1
        if m not in fail_details:
            fail_details[m] = []
        fail_details[m].append(f"{row['indicator']}(lag={row['best_lag']}, acc={row['accuracy_pct']}%)")

# 找出 Top 10 指标都预测失败的月份（高频失败月）
freq_fails = sorted(fail_counter.items(), key=lambda x: x[1], reverse=True)

print(f"\nTop 10 指标中预测失败频率最高的月份:")
print(f"{'月份':<12}{'失败指标数':<14}{'失败的指标'}")
print("-" * 80)

for month, count in freq_fails[:20]:
    indicators = ", ".join(fail_details[month])
    print(f"{month:<12}{count:<14}{indicators}")

# ---- 6.1 在这些失败月份中，哪些指标给出了正确信号 ----
print(f"\n{'='*80}")
print("6.1 高频失败月份中其他指标的正确信号")
print(f"{'='*80}")

# 取前 10 个高频失败月份
high_freq_months = [m for m, _ in freq_fails[:10]]

for month in high_freq_months:
    month_dt = pd.Timestamp(month + "-01")

    # 找到该月份对应的行
    idx = df[df["date"] == month_dt].index
    if len(idx) == 0:
        continue

    idx = idx[0]
    actual_return = df.loc[idx, "future_3m_return"]
    actual_up = actual_return > 0 if pd.notna(actual_return) else None

    if actual_up is None:
        continue

    print(f"\n--- {month}: 3月后实际收益 {actual_return:+.2f}% "
          f"({'看涨' if actual_up else '看跌'}) ---")

    # 找所有非 Top 10 的指标，看哪些在这个月给了正确信号
    correct_signals = []
    all_other_indicators = [c for c in indicator_cols
                            if c not in top10["indicator"].values]

    for col in all_other_indicators:
        # 用该指标的最优滞后期
        sub = lag_df[lag_df["indicator"] == col]
        if len(sub) == 0:
            continue

        best_row = sub.loc[sub["abs_r"].idxmax()]
        best_lag = int(best_row["lag"])
        best_r = best_row["r"]

        # 找到该指标在当前月份的值
        lag_idx = idx - best_lag
        if lag_idx < 0:
            continue

        ind_value = df.loc[lag_idx, col]
        if pd.isna(ind_value):
            continue

        # 用所有历史数据计算中位数
        hist_values = df[col].dropna()
        if len(hist_values) < MIN_SAMPLES:
            continue
        median = hist_values.median()

        # 判断预测方向
        if best_r > 0:
            predicted_up = ind_value > median
        else:
            predicted_up = ind_value <= median

        if predicted_up == actual_up:
            correct_signals.append({
                "indicator": col,
                "value": round(ind_value, 4),
                "median": round(median, 4),
                "lag": best_lag,
                "r": best_r,
            })

    # 按 |r| 排序
    correct_signals.sort(key=lambda x: abs(x["r"]), reverse=True)

    print(f"  正确信号指标 (共 {len(correct_signals)} 个):")
    for s in correct_signals[:15]:
        print(f"    {s['indicator']:<40s} lag={s['lag']:>2d}  r={s['r']:>+7.4f}  "
              f"值={s['value']:>10.4f}  中位数={s['median']:>10.4f}  "
              f"→ {'看涨' if s['value'] > s['median'] else '看跌'}")


# ============================================================
# 7. 与现有预测记录交叉验证
# ============================================================

print(f"\n{'='*80}")
print("7. 预测记录交叉验证")
print(f"{'='*80}")

try:
    pred_df = pd.read_csv("data/predictions.csv", encoding="utf-8-sig")
    pred_df["validated"] = pred_df["validated"].astype(str)

    # 已验证的预测
    validated = pred_df[pred_df["validated"] == "1"].copy()

    # 找预测错误的记录
    if "direction" in validated.columns and "actual_3m_return" in validated.columns:
        validated["actual_up"] = pd.to_numeric(validated["actual_3m_return"], errors="coerce") > 0
        validated["pred_up"] = validated["direction"] == "看涨"
        validated["pred_wrong"] = validated["actual_up"] != validated["pred_up"]

        wrong_preds = validated[validated["pred_wrong"]]
        print(f"  总预测数: {len(validated)}, 方向错误: {len(wrong_preds)}")

        if len(wrong_preds) > 0:
            print(f"\n  预测错误的月份:")
            for _, prow in wrong_preds.iterrows():
                month = prow["date"]
                actual_ret = prow["actual_3m_return"]
                actual_up = prow["actual_up"]
                pred_dir = prow["direction"]
                print(f"\n  {month}: 预测{pred_dir}, 实际{actual_ret:+.2f}% "
                      f"({'涨' if actual_up else '跌'})")

                # 找出 Top 10 指标在这些月份给了什么信号
                month_dt = pd.Timestamp(str(month) + "-01")
                idx = df[df["date"] == month_dt].index
                if len(idx) == 0:
                    continue

                idx = idx[0]
                for _, trow in top10.iterrows():
                    col = trow["indicator"]
                    lag = int(trow["best_lag"])
                    best_r = trow["best_r"]
                    lag_idx = idx - lag
                    if lag_idx < 0:
                        continue
                    ind_value = df.loc[lag_idx, col]
                    if pd.isna(ind_value):
                        continue
                    hist = df[col].dropna()
                    if len(hist) < MIN_SAMPLES:
                        continue
                    median = hist.median()
                    if best_r > 0:
                        pred_up = ind_value > median
                    else:
                        pred_up = ind_value <= median

                    correct = pred_up == actual_up
                    mark = "✓" if correct else "✗"
                    print(f"    {mark} {col:<35s} lag={lag:>2d} "
                          f"值={ind_value:>10.4f} 中位数={median:>10.4f} "
                          f"预测={'看涨' if pred_up else '看跌'}")
except Exception as e:
    print(f"  读取预测记录失败: {e}")


# ============================================================
# 8. 保存结果
# ============================================================

print(f"\n{'='*80}")
print("8. 保存结果文件")
print(f"{'='*80}")

# 保存全量结果到 CSV
output_dir = "output"
import os
os.makedirs(output_dir, exist_ok=True)

# 最优滞后相关性
best_lag_df.to_csv(f"{output_dir}/indicator_best_lag_correlation.csv",
                   index=False, encoding="utf-8-sig")
print(f"  已保存: {output_dir}/indicator_best_lag_correlation.csv")

# 方向准确率
dir_df.to_csv(f"{output_dir}/indicator_direction_accuracy.csv",
              index=False, encoding="utf-8-sig")
print(f"  已保存: {output_dir}/indicator_direction_accuracy.csv")

# 全量滞后相关性
lag_df.to_csv(f"{output_dir}/indicator_all_lag_correlations.csv",
              index=False, encoding="utf-8-sig")
print(f"  已保存: {output_dir}/indicator_all_lag_correlations.csv")

print(f"\n{'='*80}")
print("分析完成!")
print(f"{'='*80}")
