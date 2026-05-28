# -*- coding: utf-8 -*-
"""
指标修正能力分析脚本 (v4.0 Step 1a)

核心目标:
  当某个指标预测方向错误时，哪些其他指标能给出正确方向的信号？
  → 找出最具"修正价值"的指标，为重构预测指标池提供依据。

分析流程:
  1. 对每个指标，用最优滞后+中位数切分确定各月份的预测方向
  2. 构建指标×月份的预测方向矩阵 (1=看涨, -1=看跌, 0=数据缺失)
  3. 对每个"被错误预测"的月份，检查其他指标是否给出正确信号
  4. 统计: 修正次数、修正率、修正时的|相关系数|加权分
  5. 输出修正能力排名 + 修正详情

用法:
    python analyze_correction_power.py
"""

import sys
sys.path.insert(0, ".")

import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime
import warnings
import os
import json

warnings.filterwarnings("ignore")

from src.data_manager import load_merged
from src.indicators import compute_indicators


# ============================================================
# 配置
# ============================================================

TARGET_HORIZON = 3   # 预测 3 个月后
MAX_LAG = 12         # 最大滞后
MIN_SAMPLES = 30     # 最少样本

EXCLUDE_COLS = {
    "date", "sh_close", "sh_volume", "sh_mom", "sh_mom_ma3", "sh_mom_ma6",
    "sh_ma3", "sh_ma20_approx", "sh_ma_slope", "sh_yoy",
    "sh_volume_mom", "sh_volume_ma3_ratio",
}


# ============================================================
# 1. 加载数据
# ============================================================

print("=" * 80)
print("指标修正能力分析")
print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)

print("\n[1/5] 加载数据...")
df = load_merged()
df = compute_indicators(df)
df = df.sort_values("date").reset_index(drop=True)

# 3个月后收益率
df["future_3m_return"] = df["sh_close"].pct_change(periods=TARGET_HORIZON) * 100

print(f"  数据行数: {len(df)}")
print(f"  日期范围: {df['date'].min().strftime('%Y-%m')} ~ {df['date'].max().strftime('%Y-%m')}")

# 可用指标
all_cols = df.columns.tolist()
indicator_cols = [c for c in all_cols if c not in EXCLUDE_COLS
                  and df[c].dropna().shape[0] >= MIN_SAMPLES
                  and c != "future_3m_return"]

# 排除衍生列
for c in list(indicator_cols):
    if c.startswith("confirm_") or c.endswith("_direction") or c == "northbound_outflow":
        indicator_cols.remove(c)

print(f"  有效指标数: {len(indicator_cols)}")


# ============================================================
# 2. 对每个指标找最优滞后 + 构建方向矩阵
# ============================================================

print(f"\n[2/5] 计算各指标最优滞后 + 构建预测方向矩阵...")

# 存储每个指标的最优滞后信息
indicator_meta = {}  # {col: {"best_lag": int, "best_r": float, "direction": "正"/"负"}}

# 方向矩阵: 行=月份索引, 列=指标名, 值=+1(看涨)/-1(看跌)/0(缺失)
direction_matrix = pd.DataFrame(0, index=df.index, columns=indicator_cols, dtype=int)

for col in indicator_cols:
    target = df["future_3m_return"].dropna()
    series = df[col]

    best_r = 0
    best_lag = 0

    for lag in range(0, MAX_LAG + 1):
        lagged = series.shift(lag)
        combined = pd.DataFrame({"indicator": lagged, "target": target}).dropna()
        if len(combined) < MIN_SAMPLES:
            continue
        r, p = stats.pearsonr(combined["indicator"], combined["target"])
        if abs(r) > abs(best_r):
            best_r = r
            best_lag = lag

    indicator_meta[col] = {
        "best_lag": best_lag,
        "best_r": round(best_r, 4),
        "abs_r": round(abs(best_r), 4),
        "direction": "正" if best_r > 0 else "负",
    }

    # 计算方向矩阵: 用全历史中位数
    hist_median = series.dropna().median()
    if pd.isna(hist_median):
        continue

    for idx in df.index:
        # 需要的滞后位置
        lag_idx = idx - best_lag
        if lag_idx < 0 or lag_idx >= len(df):
            continue
        val = df.loc[lag_idx, col]
        if pd.isna(val):
            continue
        # 该位置对应的实际收益率
        actual_ret = df.loc[idx, "future_3m_return"]
        if pd.isna(actual_ret):
            continue

        # 预测方向
        if best_r > 0:
            direction_matrix.loc[idx, col] = 1 if val > hist_median else -1
        else:
            direction_matrix.loc[idx, col] = -1 if val > hist_median else 1

# 实际方向向量
actual_direction = pd.Series(0, index=df.index, dtype=int)
for idx in df.index:
    ret = df.loc[idx, "future_3m_return"]
    if pd.notna(ret):
        actual_direction[idx] = 1 if ret > 0 else -1

print(f"  已为 {len(indicator_cols)} 个指标构建方向矩阵")

# 显示几个指标的方向准确性
print(f"\n  各指标方向准确率 (Top 15):")
accuracies = []
for col in indicator_cols:
    valid = (direction_matrix[col] != 0) & (actual_direction != 0)
    if valid.sum() < MIN_SAMPLES:
        continue
    correct = (direction_matrix[col][valid] == actual_direction[valid]).sum()
    total = valid.sum()
    acc = correct / total * 100
    meta = indicator_meta[col]
    accuracies.append({
        "indicator": col,
        "best_lag": meta["best_lag"],
        "best_r": meta["best_r"],
        "abs_r": meta["abs_r"],
        "accuracy_pct": round(acc, 1),
        "correct": int(correct),
        "total": int(total),
        "n_wrong": int(total - correct),
    })

acc_df = pd.DataFrame(accuracies).sort_values("accuracy_pct", ascending=False)
print(f"  {'排名':<4}{'指标':<40s}{'Lag':<5}{'r':<9}{'准确率':<8}{'正确/总数':<10}{'错误数'}")
print(f"  {'-'*90}")
for rank, (_, row) in enumerate(acc_df.head(15).iterrows(), 1):
    print(f"  {rank:<4}{row['indicator']:<40s}{row['best_lag']:<5}"
          f"{row['best_r']:>+7.4f} {row['accuracy_pct']:>5.1f}%  "
          f"{row['correct']}/{row['total']:<6}{row['n_wrong']}")


# ============================================================
# 3. 修正能力分析
# ============================================================

print(f"\n[3/5] 分析修正能力...")

# 修正逻辑:
# 对每个指标A，找出它预测错误的月份。
# 在这些月份中，检查其他指标B是否预测正确（即与实际方向一致）。
# 如果B预测正确且A预测错误 → B修正了A的错误。

# 修正矩阵: correction_count[A][B] = B修正A错误的次数
correction_results = []

for col_a in indicator_cols:
    # 指标A预测错误的月份
    valid_a = (direction_matrix[col_a] != 0) & (actual_direction != 0)
    wrong_mask = valid_a & (direction_matrix[col_a] != actual_direction)
    wrong_indices = wrong_mask[wrong_mask].index.tolist()

    if len(wrong_indices) < 10:
        continue  # 错误样本太少，跳过

    meta_a = indicator_meta[col_a]
    acc_a = acc_df[acc_df["indicator"] == col_a]

    for col_b in indicator_cols:
        if col_b == col_a:
            continue

        # 在A错误的月份中，B的修正情况
        corrections = 0
        total_wrong = 0
        correction_details = []

        for idx in wrong_indices:
            if direction_matrix.loc[idx, col_b] == 0:
                continue
            total_wrong += 1
            # B预测正确（与实际方向一致）
            if direction_matrix.loc[idx, col_b] == actual_direction[idx]:
                corrections += 1
                month = df.loc[idx, "date"].strftime("%Y-%m")
                actual_ret = df.loc[idx, "future_3m_return"]
                correction_details.append({
                    "month": month,
                    "actual_return": round(actual_ret, 2),
                    "actual_dir": "涨" if actual_direction[idx] == 1 else "跌",
                    "a_signal": "涨" if direction_matrix.loc[idx, col_a] == 1 else "跌",
                    "b_signal": "涨" if direction_matrix.loc[idx, col_b] == 1 else "跌",
                })

        if total_wrong == 0:
            continue

        correction_rate = corrections / total_wrong * 100
        meta_b = indicator_meta[col_b]

        correction_results.append({
            "wrong_indicator": col_a,
            "corrector_indicator": col_b,
            "a_acc": float(acc_a["accuracy_pct"].values[0]) if len(acc_a) > 0 else 0,
            "a_best_r": meta_a["best_r"],
            "a_abs_r": meta_a["abs_r"],
            "b_best_r": meta_b["best_r"],
            "b_abs_r": meta_b["abs_r"],
            "b_acc": float(acc_df[acc_df["indicator"] == col_b]["accuracy_pct"].values[0])
                        if len(acc_df[acc_df["indicator"] == col_b]) > 0 else 0,
            "total_wrong_a": len(wrong_indices),
            "total_evaluable": total_wrong,
            "corrections": corrections,
            "correction_rate": round(correction_rate, 1),
            # 综合修正分 = 修正率 × B的|r| × sqrt(可评估样本数)
            "correction_score": round(
                correction_rate / 100 * meta_b["abs_r"] * np.sqrt(total_wrong), 4
            ),
        })

corr_df = pd.DataFrame(correction_results)
print(f"  分析了 {len(indicator_cols)} 个指标的两两修正关系")


# ============================================================
# 4. 输出结果
# ============================================================

print(f"\n[4/5] 输出分析结果...")

# ---- 4.1 修正能力总排名 ----
print(f"\n{'='*80}")
print("4.1 指标修正能力排名 (综合修正分 Top 30)")
print(f"{'='*80}")
print(f"说明: 修正分 = 修正率 × |r| × √(可评估样本数)")
print(f"      即一个指标在其他指标预测错误时给出正确信号的综合能力")
print(f"{'排名':<4}{'修正指标B':<40s}{'B的|r|':<8}{'B准确率':<8}"
      f"{'总修正次数':<10}{'修正率':<8}{'修正分':<8}")
print(f"{'-'*90}")

# 按修正分排名（每个修正指标只取最高分）
best_correctors = corr_df.groupby("corrector_indicator").agg({
    "correction_score": "max",
    "corrections": "sum",
    "correction_rate": "mean",
    "b_abs_r": "first",
    "b_acc": "first",
}).reset_index().sort_values("correction_score", ascending=False)

for rank, (_, row) in enumerate(best_correctors.head(30).iterrows(), 1):
    print(f"{rank:<4}{row['corrector_indicator']:<40s}{row['b_abs_r']:>6.4f}  "
          f"{row['b_acc']:>5.1f}%  {int(row['corrections']):<10}"
          f"{row['correction_rate']:>5.1f}%  {row['correction_score']:>8.4f}")


# ---- 4.2 每个指标的"最佳修正伙伴" ----
print(f"\n{'='*80}")
print("4.2 每个指标预测错误时的最佳修正伙伴 (Top 20 高准确率指标)")
print(f"{'='*80}")

top20_acc = acc_df.head(20)["indicator"].tolist()

for col_a in top20_acc[:10]:  # 取前10个准确率最高的指标
    meta_a = indicator_meta[col_a]
    acc_a = float(acc_df[acc_df["indicator"] == col_a]["accuracy_pct"].values[0])

    # 该指标的最佳修正者
    sub = corr_df[corr_df["wrong_indicator"] == col_a].sort_values(
        "correction_score", ascending=False
    )

    print(f"\n  【{col_a}】准确率={acc_a:.1f}%, |r|={meta_a['abs_r']}")
    if len(sub) == 0:
        print(f"    (无足够修正数据)")
        continue

    print(f"    {'修正指标':<38s}{'修正次数':<8}{'修正率':<8}{'修正分':<8}{'B的|r|':<8}{'B准确率'}")
    print(f"    {'-'*80}")
    for _, row in sub.head(8).iterrows():
        print(f"    {row['corrector_indicator']:<38s}{row['corrections']:<8}"
              f"{row['correction_rate']:>5.1f}%  {row['correction_score']:>8.4f}  "
              f"{row['b_abs_r']:>6.4f}  {row['b_acc']:>5.1f}%")


# ---- 4.3 高频失败月份的多指标修正矩阵 ----
print(f"\n{'='*80}")
print("4.3 高频失败月份的修正矩阵")
print(f"{'='*80}")

# 找出最多指标预测错误的月份
month_error_count = {}
for col in indicator_cols[:30]:  # 取前30个指标
    valid = (direction_matrix[col] != 0) & (actual_direction != 0)
    wrong = valid & (direction_matrix[col] != actual_direction)
    for idx in wrong[wrong].index:
        month = df.loc[idx, "date"].strftime("%Y-%m")
        month_error_count[month] = month_error_count.get(month, 0) + 1

# 排序，取高频失败月
top_fail_months = sorted(month_error_count.items(), key=lambda x: x[1], reverse=True)[:15]

print(f"\n  {'月份':<12}{'错误指标数':<10}{'实际收益':<10}{'实际方向':<8}{'修正指标数':<10}{'最佳修正指标'}")
print(f"  {'-'*90}")

for month, err_count in top_fail_months:
    month_dt = pd.Timestamp(month + "-01")
    idx_list = df[df["date"] == month_dt].index.tolist()
    if not idx_list:
        continue
    idx = idx_list[0]

    actual_ret = df.loc[idx, "future_3m_return"]
    actual_dir = "涨" if actual_direction[idx] == 1 else "跌"

    # 哪些指标预测正确（给出了修正信号）
    correct_indicators = []
    for col in indicator_cols:
        if direction_matrix.loc[idx, col] != 0 and direction_matrix.loc[idx, col] == actual_direction[idx]:
            meta = indicator_meta[col]
            correct_indicators.append((col, meta["abs_r"]))

    correct_indicators.sort(key=lambda x: x[1], reverse=True)
    top_correctors = ", ".join([f"{c[0]}(r={c[1]:.3f})" for c in correct_indicators[:5]])

    print(f"  {month:<12}{err_count:<10}{actual_ret:>+8.2f}%  {actual_dir:<8}"
          f"{len(correct_indicators):<10}{top_correctors}")


# ---- 4.4 修正阈值分析 ----
print(f"\n{'='*80}")
print("4.4 修正阈值分析 (反常信号比例 vs 降级效果)")
print(f"{'='*80}")

# 模拟修正机制:
# 当N个指标中≥X%给出反向信号时，预测应该降级
# 我们分析不同的X阈值会"捕获"多少错误预测

print(f"\n  模拟: 当k个指标中有n个以上给出反向信号时降级")
print(f"  {'反向信号阈值':<16}{'捕获的错误':<12}{'误杀的正确':<12}{'精确率':<10}{'召回率':<10}{'F1'}")
print(f"  {'-'*80}")

# 逐月份模拟
# 获取所有有效月份
valid_months = df[(actual_direction != 0)].index.tolist()

# 对每个月份，计算"异常指标比例" = 给出与多数指标相反方向的指标占比
for threshold_pct in [10, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70]:
    tp = 0  # 正确降级的错误预测
    fp = 0  # 错误降级的正确预测
    fn = 0  # 未降级的错误预测
    tn = 0  # 正确保留的正确预测

    for idx in valid_months:
        # 模拟: 用所有指标的方向，统计多数方向
        signals = []
        for col in indicator_cols:
            if direction_matrix.loc[idx, col] != 0:
                signals.append(direction_matrix.loc[idx, col])

        if len(signals) < 5:
            continue

        majority = 1 if np.mean(signals) > 0 else -1
        majority_prediction = "看涨" if majority == 1 else "看跌"
        actual = actual_direction[idx]
        actual_label = "看涨" if actual == 1 else "看跌"

        # 多数预测是否正确
        majority_correct = (majority_prediction == actual_label)

        # 反向信号比例
        if majority == 1:
            reverse_count = sum(1 for s in signals if s == -1)
        else:
            reverse_count = sum(1 for s in signals if s == 1)

        reverse_pct = reverse_count / len(signals) * 100

        should_downgrade = reverse_pct >= threshold_pct

        if majority_correct:
            if should_downgrade:
                fp += 1  # 误杀: 正确预测被降级
            else:
                tn += 1  # 正确保留
        else:
            if should_downgrade:
                tp += 1  # 正确降级
            else:
                fn += 1  # 漏掉

    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) * 100 if (precision + recall) > 0 else 0

    print(f"  {threshold_pct:>10}%     {tp:<12}{fp:<12}{precision:>8.1f}%  {recall:>8.1f}%  {f1:>6.1f}%")


# ============================================================
# 5. 保存结果
# ============================================================

print(f"\n[5/5] 保存结果文件...")

output_dir = "output"
os.makedirs(output_dir, exist_ok=True)

# 1) 方向准确率排名（含修正数据）
acc_df.to_csv(f"{output_dir}/correction_direction_accuracy.csv",
              index=False, encoding="utf-8-sig")
print(f"  已保存: {output_dir}/correction_direction_accuracy.csv")

# 2) 两两修正矩阵
corr_df.to_csv(f"{output_dir}/correction_pairwise_matrix.csv",
               index=False, encoding="utf-8-sig")
print(f"  已保存: {output_dir}/correction_pairwise_matrix.csv")

# 3) 最佳修正者排名
best_correctors.to_csv(f"{output_dir}/correction_best_correctors.csv",
                        index=False, encoding="utf-8-sig")
print(f"  已保存: {output_dir}/correction_best_correctors.csv")

# 4) 高频失败月份
fail_months_df = pd.DataFrame(top_fail_months, columns=["month", "error_count"])
fail_months_df.to_csv(f"{output_dir}/correction_fail_months.csv",
                       index=False, encoding="utf-8-sig")
print(f"  已保存: {output_dir}/correction_fail_months.csv")

# 5) 修正摘要 JSON
correction_summary = {
    "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "total_indicators": len(indicator_cols),
    "date_range": f"{df['date'].min().strftime('%Y-%m')} ~ {df['date'].max().strftime('%Y-%m')}",
    "top_correctors": best_correctors.head(15)[
        ["corrector_indicator", "b_abs_r", "b_acc", "corrections", "correction_rate", "correction_score"]
    ].to_dict("records"),
    "top_direction_accuracy": acc_df.head(15)[
        ["indicator", "best_lag", "best_r", "abs_r", "accuracy_pct", "correct", "total"]
    ].to_dict("records"),
}

with open(f"{output_dir}/correction_summary.json", "w", encoding="utf-8") as f:
    json.dump(correction_summary, f, ensure_ascii=False, indent=2)
print(f"  已保存: {output_dir}/correction_summary.json")


# ---- 最终总结 ----
print(f"\n{'='*80}")
print("5. 总结与建议")
print(f"{'='*80}")

print(f"""
  分析维度:
    - {len(indicator_cols)} 个指标两两修正关系 ({len(corr_df)} 组有效配对)
    - 方向准确率最高: {acc_df.iloc[0]['indicator']} ({acc_df.iloc[0]['accuracy_pct']}%)
    - 修正能力最强: {best_correctors.iloc[0]['corrector_indicator']} (修正分={best_correctors.iloc[0]['correction_score']:.4f})

  下一步 (Task #85):
    - 根据方向准确率 + 修正能力排名，重构预测指标池
    - 重点考虑纳入: margin_yoy (r=0.40, 修正力强)
    - 评估 non_bank_deposit 是否应降权或替换
    - 修正阈值: 参考 4.4 的精确率/召回率平衡点
""")

print(f"{'='*80}")
print("分析完成!")
print(f"{'='*80}")
