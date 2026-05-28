# -*- coding: utf-8 -*-
"""
历史回测预测脚本
用当前 v2.0 预测模型在历史上每个月做预测，回填实际 3 月收益率，评估准确率。

用法: python backtest_prediction.py
"""
import sys
import numpy as np
import pandas as pd
import logging

sys.path.insert(0, ".")
from src.config import (
    PREDICTIONS_CSV,
    PREDICTIVE_INDICATORS,
    CONFIRMING_INDICATORS,
    CONFIRMING_LABELS,
    PREDICTION_PERCENTILE_WINDOW,
    PREDICTION_MIN_HISTORY,
    PREDICTION_BULL_THRESHOLD,
    PREDICTION_BEAR_THRESHOLD,
    RETURN_DIRECTION_THRESHOLD,
    SINGLE_DIRECTION_THRESHOLD,
)
from src.data_manager import load_merged
from src.indicators import compute_indicators

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def normalize_to_score(value: float, history: pd.Series, direction: str) -> float:
    """分位数标准化到 [-1, +1]"""
    window = history[history.index < history.index[-1]].tail(PREDICTION_PERCENTILE_WINDOW).dropna()
    if len(window) < PREDICTION_MIN_HISTORY:
        return 0.0
    percentile = (window < value).sum() / len(window) * 100
    score = (percentile / 50) - 1.0
    score = max(-1.0, min(1.0, score))
    if direction == "negative":
        score = -score
    return score


def judge_confirming_status(col: str, value: float) -> str:
    """基于配置判断确认指标状态"""
    config = CONFIRMING_INDICATORS.get(col, {})
    threshold = config.get("threshold", 0)
    inverse = config.get("inverse", False)

    if col == "shibor_on_avg":
        neutral_upper = config.get("neutral_upper", 3.0)
        if value < threshold:
            return "看涨"
        elif value < neutral_upper:
            return "中性"
        else:
            return "看跌"
    elif inverse:
        return "看跌" if value > threshold else ("看涨" if value < threshold else "中性")
    else:
        return "看涨" if value > threshold else ("看跌" if value < threshold else "中性")


def backtest_predict(df: pd.DataFrame) -> pd.DataFrame:
    """
    在历史每个月做预测（look-ahead free），返回预测记录 DataFrame
    """
    records = []
    df_sorted = df.sort_values("date").reset_index(drop=True)
    df_sorted["date"] = pd.to_datetime(df_sorted["date"])

    total = len(df_sorted)
    start_idx = PREDICTION_PERCENTILE_WINDOW + PREDICTION_MIN_HISTORY  # 需要足够的历史数据

    for i in range(start_idx, total):
        date = df_sorted.loc[i, "date"]
        if pd.isna(date):
            continue

        # 截止到当前月的数据（不包含未来）
        current_df = df_sorted.iloc[:i + 1].copy()

        # 检查4个预测指标是否都有值
        pred_cols = list(PREDICTIVE_INDICATORS.keys())
        values = {}
        valid = True
        for col in pred_cols:
            if col not in current_df.columns:
                valid = False
                break
            v = current_df[col].dropna()
            if len(v) == 0:
                valid = False
                break
            values[col] = v.iloc[-1]

        if not valid:
            continue

        # 计算预测分数
        total_score = 0.0
        total_weight = 0.0
        details = {}

        for col, config in PREDICTIVE_INDICATORS.items():
            value = values[col]
            if col in current_df.columns:
                history = current_df[col]
            else:
                history = pd.Series([value])

            score = normalize_to_score(value, history, config["direction"])

            details[col] = {
                "value": round(value, 2),
                "weight": config["weight"],
                "score": round(score, 4),
                "direction": config["direction"],
            }
            total_score += score * config["weight"]
            total_weight += config["weight"]

        if total_weight > 0:
            final_score = total_score / total_weight
        else:
            continue

        final_score = max(-1.0, min(1.0, final_score))
        confidence = abs(final_score)

        if final_score > PREDICTION_BULL_THRESHOLD:
            direction = "看涨"
        elif final_score < PREDICTION_BEAR_THRESHOLD:
            direction = "看跌"
        else:
            direction = "中性"

        # 趋势确认
        confirming_details = {}

        for col, config in CONFIRMING_INDICATORS.items():
            if col not in current_df.columns:
                continue
            v = current_df[col].dropna()
            if len(v) == 0:
                continue
            value = v.iloc[-1]
            status = judge_confirming_status(col, value)
            confirming_details[col] = status

        # 计算确认度
        confirming_count_correct = 0
        confirming_count = 0
        for col, status in confirming_details.items():
            sc = 1 if status == "看涨" else (-1 if status == "看跌" else 0)
            confirming_count += 1
            if (direction == "看涨" and sc >= 0) or (direction == "看跌" and sc <= 0):
                confirming_count_correct += 1
        confirming_pct = confirming_count_correct / confirming_count if confirming_count > 0 else 0

        # 实际3月收益率
        target_idx = i + 3  # 3个月后
        actual_return = np.nan
        validated = "0"
        if target_idx < total:
            pred_close = df_sorted.loc[i, "sh_close"]
            actual_close = df_sorted.loc[target_idx, "sh_close"]
            if pd.notna(pred_close) and pd.notna(actual_close) and pred_close > 0:
                actual_return = round((actual_close / pred_close - 1) * 100, 2)
                validated = "1"

        record = {
            "date": date.strftime("%Y-%m"),
            "score": round(final_score, 4),
            "direction": direction,
            "confidence": round(confidence, 4),
            "confirming_pct": round(confirming_pct, 4),
            "actual_3m_return": actual_return,
            "validated": validated,
        }
        # 各指标值和分数
        for col, detail in details.items():
            record[f"{col}_value"] = detail["value"]
            record[f"{col}_score"] = detail["score"]
        # 确认指标状态
        for col, status in confirming_details.items():
            record[f"confirm_{col}"] = status

        records.append(record)

        if (len(records)) % 12 == 0:
            logger.info(f"  已处理到 {date.strftime('%Y-%m')}，累计 {len(records)} 条预测")

    return pd.DataFrame(records)


def print_accuracy_report(predictions: pd.DataFrame):
    """打印准确率报告"""
    validated = predictions[predictions["validated"] == "1"].copy()

    print("\n" + "=" * 70)
    print("  历史回测预测准确率报告")
    print("=" * 70)

    print(f"\n总预测数: {len(predictions)}")
    print(f"已验证数: {len(validated)}（有完整3月后收益数据）")

    if len(validated) == 0:
        print("\n没有已验证的预测记录")
        return

    # 方向准确率
    validated = validated.copy()
    validated["actual_direction"] = validated["actual_3m_return"].apply(
        lambda x: "看涨" if x > RETURN_DIRECTION_THRESHOLD
        else ("看跌" if x < -RETURN_DIRECTION_THRESHOLD else "中性")
    )
    correct = (validated["direction"] == validated["actual_direction"]).sum()
    accuracy = correct / len(validated) * 100
    print(f"\n方向准确率: {accuracy:.1f}% ({correct}/{len(validated)})")

    # 按方向统计
    print(f"\n{'方向':<8} {'次数':>6} {'准确':>6} {'准确率':>8} {'平均收益':>10}")
    print("-" * 45)
    for d in ["看涨", "看跌", "中性"]:
        sub = validated[validated["direction"] == d]
        if len(sub) == 0:
            continue
        sub_correct = (sub["direction"] == sub["actual_direction"]).sum()
        sub_acc = sub_correct / len(sub) * 100
        avg_ret = sub["actual_3m_return"].mean()
        print(f"{d:<8} {len(sub):>6} {sub_correct:>6} {sub_acc:>7.1f}% {avg_ret:>+9.2f}%")

    # 分位数统计
    print(f"\n预测分数分布:")
    for q in [0.1, 0.25, 0.5, 0.75, 0.9]:
        v = validated["score"].quantile(q)
        print(f"  {q*100:>5.0f}%ile: {v:+.4f}")

    # 各指标独立准确率
    print(f"\n各指标独立方向准确率:")
    print(f"{'指标':<20} {'正确/总数':>12} {'准确率':>8}")
    print("-" * 45)
    for col in PREDICTIVE_INDICATORS:
        score_col = f"{col}_score"
        if score_col not in validated.columns:
            continue
        col_correct = 0
        col_total = 0
        for _, row in validated.iterrows():
            s = row.get(score_col)
            if pd.isna(s):
                continue
            s = float(s)
            if s > SINGLE_DIRECTION_THRESHOLD:
                ind_dir = "看涨"
            elif s < -SINGLE_DIRECTION_THRESHOLD:
                ind_dir = "看跌"
            else:
                ind_dir = "中性"
            if ind_dir == row["actual_direction"]:
                col_correct += 1
            col_total += 1

        if col_total > 0:
            label = PREDICTIVE_INDICATORS[col].get("label", col)
            acc = col_correct / col_total * 100
            print(f"{label:<20} {col_correct:>5}/{col_total:<5} {acc:>7.1f}%")

    # 大盘关键事件标注
    print(f"\n重大行情预测表现:")
    # 找出实际大涨大跌的月份
    extreme = validated[validated["actual_3m_return"].abs() > 10]
    if len(extreme) > 0:
        extreme_sorted = extreme.sort_values("actual_3m_return", key=abs, ascending=False)
        print(f"{'日期':<10} {'预测':<6} {'分数':>8} {'实际收益':>10} {'结果':>6}")
        print("-" * 45)
        for _, row in extreme_sorted.head(10).iterrows():
            hit = "✓" if row["direction"] == row["actual_direction"] else "✗"
            print(f"{row['date']:<10} {row['direction']:<6} {row['score']:>+8.3f} "
                  f"{row['actual_3m_return']:>+9.2f}% {hit:>6}")

    # 年度准确率
    print(f"\n年度方向准确率:")
    validated["year"] = validated["date"].str[:4]
    print(f"{'年份':<8} {'次数':>6} {'准确':>6} {'准确率':>8}")
    print("-" * 35)
    for year in sorted(validated["year"].unique()):
        sub = validated[validated["year"] == year]
        sub_correct = (sub["direction"] == sub["actual_direction"]).sum()
        sub_acc = sub_correct / len(sub) * 100
        print(f"{year:<8} {len(sub):>6} {sub_correct:>6} {sub_acc:>7.1f}%")

    print()


def main():
    logger.info("加载历史数据...")
    df = load_merged()
    logger.info(f"合并后数据: {len(df)} 行")

    # 计算衍生指标
    df = compute_indicators(df)

    logger.info("开始历史回测预测...")
    predictions = backtest_predict(df)
    logger.info(f"回测完成: {len(predictions)} 条预测")

    if len(predictions) == 0:
        logger.error("没有生成任何预测记录")
        return

    # 统计验证数
    validated = predictions[predictions["validated"] == "1"]
    logger.info(f"已验证: {len(validated)} 条，待验证: {len(predictions) - len(validated)} 条")

    # 保存到 predictions.csv（备份旧文件）
    if PREDICTIONS_CSV.exists():
        backup = PREDICTIONS_CSV.with_suffix(".csv.bak")
        PREDICTIONS_CSV.rename(backup)
        logger.info(f"已备份旧文件: {backup}")

    predictions.to_csv(PREDICTIONS_CSV, index=False, encoding="utf-8-sig")
    logger.info(f"预测记录已保存: {PREDICTIONS_CSV}")

    # 打印报告
    print_accuracy_report(predictions)


if __name__ == "__main__":
    main()
