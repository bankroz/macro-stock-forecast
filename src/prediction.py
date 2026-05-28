# -*- coding: utf-8 -*-
"""
预测引擎 + 自学习系统
基于预测指标（领先型）生成未来 3 月走势预测，
用趋势确认指标验证，记录预测结果以便后续验证和权重微调。
自学习：偏差记录、per-indicator 准确率追踪、智能权重调整。
"""

import json
import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from src.config import (
    PREDICTIONS_CSV,
    DEVIATION_LOG_PATH,
    PREDICTIVE_INDICATORS,
    CONFIRMING_INDICATORS,
    CONFIRMING_LABELS,
    PREDICTION_CONFIG,
    PREDICTION_HORIZON,
    PREDICTION_PERCENTILE_WINDOW,
    PREDICTION_BULL_THRESHOLD,
    PREDICTION_BEAR_THRESHOLD,
    PREDICTION_MIN_HISTORY,
    RETURN_DIRECTION_THRESHOLD,
    SINGLE_DIRECTION_THRESHOLD,
    save_prediction_config,
    get_prediction,
)

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    """预测结果"""
    date: str                              # 预测日期 YYYY-MM
    score: float                           # 加权预测分数 [-1, +1]
    direction: str                         # "看涨" / "看跌" / "中性"
    confidence: float                      # 置信度 [0, 1]
    indicator_details: dict                # 各预测指标贡献明细
    confirming_score: float                # 趋势确认分数 [-1, +1]
    confirming_pct: float                  # 确认度百分比 [0, 1]
    confirming_details: dict               # 各确认指标状态
    adaptive_info: dict = field(default_factory=dict)      # 自适应阈值状态 (v3.0)
    bear_confirm_info: dict = field(default_factory=dict)  # 看跌确认状态 (v3.0)


def _get_latest_valid(df: pd.DataFrame, col: str) -> float | None:
    """获取指定列的最后一个有效值"""
    if col not in df.columns:
        return None
    series = df[col].dropna()
    if len(series) == 0:
        return None
    return series.iloc[-1]


def _normalize_to_score(value: float, history: pd.Series, direction: str) -> float:
    """
    将指标当前值标准化为 [-1, +1] 的分数

    方法：用过去 PREDICTION_PERCENTILE_WINDOW 个月的分位数位置
    """
    window = history.tail(PREDICTION_PERCENTILE_WINDOW).dropna()
    if len(window) < PREDICTION_MIN_HISTORY:
        return 0.0

    # 计算分位数位置
    percentile = (window < value).sum() / len(window) * 100
    # 映射到 [-1, +1]
    score = (percentile / 50) - 1.0
    score = max(-1.0, min(1.0, score))

    # 负相关指标取反
    if direction == "negative":
        score = -score

    return score


def _judge_confirming_status(col: str, value: float) -> str:
    """基于配置判断确认指标状态"""
    config = CONFIRMING_INDICATORS.get(col, {})
    threshold = config.get("threshold", 0)
    inverse = config.get("inverse", False)

    if col == "shibor_on_avg":
        # SHIBOR 特殊处理：三段式
        neutral_upper = config.get("neutral_upper", 3.0)
        if value < threshold:
            status = "看涨"
        elif value < neutral_upper:
            status = "中性"
        else:
            status = "看跌"
    elif inverse:
        status = "看跌" if value > threshold else ("看涨" if value < threshold else "中性")
    else:
        status = "看涨" if value > threshold else ("看跌" if value < threshold else "中性")

    return status


def generate_prediction(df: pd.DataFrame) -> PredictionResult:
    """
    基于预测指标生成走势预测
    """
    # ---- 预测指标分数 ----
    details = {}
    total_score = 0.0
    total_weight = 0.0

    for col, config in PREDICTIVE_INDICATORS.items():
        value = _get_latest_valid(df, col)
        if value is None:
            details[col] = {
                "label": config["label"],
                "value": None,
                "weight": config["weight"],
                "score": 0.0,
                "status": "数据缺失",
            }
            continue

        # 获取历史数据用于标准化
        if col in df.columns:
            history = df[col]
        else:
            history = pd.Series([value])

        score = _normalize_to_score(value, history, config["direction"])

        details[col] = {
            "label": config["label"],
            "value": round(value, 2),
            "weight": config["weight"],
            "score": round(score, 4),
            "direction": config["direction"],
            "status": "看涨" if score > SINGLE_DIRECTION_THRESHOLD else (
                "看跌" if score < -SINGLE_DIRECTION_THRESHOLD else "中性"),
        }

        total_score += score * config["weight"]
        total_weight += config["weight"]

    # 归一化
    if total_weight > 0:
        final_score = total_score / total_weight
    else:
        final_score = 0.0

    final_score = max(-1.0, min(1.0, final_score))
    confidence = abs(final_score)

    # ---- 自适应阈值 (v3.0) ----
    adaptive_info = {}
    effective_bull = PREDICTION_BULL_THRESHOLD
    effective_bear = PREDICTION_BEAR_THRESHOLD

    adaptive_cfg = PREDICTION_CONFIG.get("adaptive_threshold", {})
    if adaptive_cfg.get("enabled", False) and "sh_close" in df.columns:
        vol_window = adaptive_cfg.get("volatility_window", 6)
        high_vol_ratio = adaptive_cfg.get("high_vol_ratio", 0.04)
        high_vol_adj = adaptive_cfg.get("high_vol_adjust", -0.05)
        low_vol_adj = adaptive_cfg.get("low_vol_adjust", 0.05)

        close_series = df["sh_close"].dropna().tail(vol_window)
        if len(close_series) >= vol_window:
            mom_series = close_series.pct_change().dropna()
            vol_ratio = mom_series.std() if len(mom_series) > 0 else 0
            if vol_ratio > high_vol_ratio:
                # 高波动（趋势市）: 降低阈值 → 更容易输出方向性预测
                effective_bull = max(0.0, PREDICTION_BULL_THRESHOLD + high_vol_adj)
                effective_bear = min(-0.0, PREDICTION_BEAR_THRESHOLD - high_vol_adj)
                adaptive_info = {"market_state": "趋势市", "volatility": round(vol_ratio, 4),
                                  "bull_adj": effective_bull, "bear_adj": effective_bear}
            else:
                # 低波动（震荡市）: 提高阈值 → 更倾向中性预测
                effective_bull = PREDICTION_BULL_THRESHOLD + low_vol_adj
                effective_bear = PREDICTION_BEAR_THRESHOLD - low_vol_adj
                adaptive_info = {"market_state": "震荡市", "volatility": round(vol_ratio, 4),
                                  "bull_adj": effective_bull, "bear_adj": effective_bear}

    # 预测方向
    if final_score > effective_bull:
        direction = "看涨"
    elif final_score < effective_bear:
        direction = "看跌"
    else:
        direction = "中性"

    # ---- 趋势确认 ----
    confirming_details = {}
    confirming_scores = []
    confirming_match = 0
    confirming_count = 0

    for col, config in CONFIRMING_INDICATORS.items():
        value = _get_latest_valid(df, col)
        if value is None:
            confirming_details[col] = {
                "label": config["label"],
                "value": None,
                "status": "数据缺失",
                "signal": "无数据",
            }
            continue

        status = _judge_confirming_status(col, value)

        # 将状态转为分数
        if status == "看涨":
            confirming_score = 1.0
        elif status == "看跌":
            confirming_score = -1.0
        else:
            confirming_score = 0.0

        confirming_details[col] = {
            "label": config["label"],
            "value": round(value, 2) if value is not None else None,
            "status": status,
            "signal": confirming_score,
        }

        confirming_scores.append(confirming_score)
        confirming_count += 1
        if (direction == "看涨" and confirming_score >= 0) or \
           (direction == "看跌" and confirming_score <= 0):
            confirming_match += 1

    avg_confirming = np.mean(confirming_scores) if confirming_scores else 0.0
    confirming_pct = confirming_match / confirming_count if confirming_count > 0 else 0.0

    # 确认度判断（从配置读取阈值）
    high_label = CONFIRMING_LABELS.get("high", 0.70)
    partial_label = CONFIRMING_LABELS.get("partial", 0.40)
    if confirming_pct >= high_label:
        confirming_label = "高度确认"
    elif confirming_pct >= partial_label:
        confirming_label = "部分确认"
    else:
        confirming_label = "矛盾信号"

    # ---- 看跌增强确认 (v3.0) ----
    bear_confirm_cfg = PREDICTION_CONFIG.get("bear_confirm", {})
    bear_confirm_info = {}
    if bear_confirm_cfg.get("enabled", False) and direction == "看跌":
        min_confirm = bear_confirm_cfg.get("min_confirming_pct", 0.40)
        if confirming_pct < min_confirm:
            # 看跌确认不足，降级为中性
            old_direction = direction
            direction = "中性"
            bear_confirm_info = {"downgraded": True, "reason": "看跌确认不足",
                                  "confirming_pct": round(confirming_pct, 2),
                                  "required_pct": min_confirm}
            logger.info(f"看跌预测降级为中性: 确认度{confirming_pct:.0%} < {min_confirm:.0%}")

    # 获取日期
    latest_date = df["date"].dropna().iloc[-1]
    date_str = pd.Timestamp(latest_date).strftime("%Y-%m")

    result = PredictionResult(
        date=date_str,
        score=round(final_score, 4),
        direction=direction,
        confidence=round(confidence, 4),
        indicator_details=details,
        confirming_score=round(avg_confirming, 4),
        confirming_pct=round(confirming_pct, 4),
        confirming_details=confirming_details,
        adaptive_info=adaptive_info,
        bear_confirm_info=bear_confirm_info,
    )

    logger.info(
        f"预测: {date_str} → {direction} (score={final_score:.3f}, "
        f"confidence={confidence:.2f}, 确认度={confirming_pct:.0%} [{confirming_label}])"
    )
    return result


def record_prediction(result: PredictionResult, path: Path = PREDICTIONS_CSV):
    """将预测结果追加到 CSV 文件"""
    path = Path(path)
    row = {
        "date": result.date,
        "score": result.score,
        "direction": result.direction,
        "confidence": result.confidence,
        "confirming_score": result.confirming_score,
        "confirming_pct": result.confirming_pct,
        "actual_3m_return": np.nan,
        "validated": "0",
    }

    # 附加各指标数值
    for col, detail in result.indicator_details.items():
        row[f"{col}_value"] = detail.get("value") if detail.get("value") is not None else np.nan
        row[f"{col}_score"] = detail.get("score") if detail.get("score") is not None else np.nan

    # 确认指标状态
    for col, detail in result.confirming_details.items():
        row[f"confirm_{col}"] = detail.get("status", "")

    # 检查是否已有同日期记录（避免重复）
    if path.exists():
        existing = pd.read_csv(path, encoding="utf-8-sig", dtype={"validated": str})
        if "date" in existing.columns and result.date in existing["date"].values:
            # 更新而非追加（逐列赋值避免 dtype 冲突）
            for k, v in row.items():
                existing.loc[existing["date"] == result.date, k] = v
            existing.to_csv(path, index=False, encoding="utf-8-sig")
            logger.info(f"更新预测记录: {result.date}")
            return

    # 追加新记录
    new_df = pd.DataFrame([row])
    if path.exists():
        new_df.to_csv(path, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        new_df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info(f"新增预测记录: {result.date}")


def validate_predictions(df: pd.DataFrame, path: Path = PREDICTIONS_CSV):
    """
    验证历史预测：用实际 3 个月后上证收益率回填
    """
    path = Path(path)
    if not path.exists():
        return

    predictions = pd.read_csv(path, encoding="utf-8-sig", na_values=["", " "],
                               keep_default_na=True, dtype={"validated": str})
    if "date" not in predictions.columns or "validated" not in predictions.columns:
        return

    if "sh_close" not in df.columns:
        return

    df_sorted = df.sort_values("date").reset_index(drop=True)

    unvalidated = predictions[predictions["validated"] != "1"]
    if len(unvalidated) == 0:
        return

    updated = False
    for idx, row in unvalidated.iterrows():
        pred_date = pd.Timestamp(row["date"])
        target_date = pred_date + pd.DateOffset(months=PREDICTION_HORIZON)

        target_row = df_sorted[df_sorted["date"].dt.to_period("M") == target_date.to_period("M")]
        pred_row = df_sorted[df_sorted["date"].dt.to_period("M") == pred_date.to_period("M")]

        if len(pred_row) > 0 and len(target_row) > 0:
            pred_close = pred_row["sh_close"].iloc[-1]
            actual_close = target_row["sh_close"].iloc[-1]
            actual_return = (actual_close / pred_close - 1) * 100

            predictions.at[idx, "actual_3m_return"] = round(actual_return, 2)
            predictions.at[idx, "validated"] = "1"
            updated = True
            logger.info(f"验证预测: {row['date']} → {row['direction']}, "
                       f"实际 3 月收益 {actual_return:+.2f}%")
        elif len(pred_row) > 0:
            continue

    if updated:
        predictions.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info(f"已验证 {len(unvalidated)} 条历史预测")


def calculate_accuracy(path: Path = PREDICTIONS_CSV) -> dict:
    """
    计算预测准确率

    返回:
        {
            "total": 总预测数,
            "validated": 已验证数,
            "direction_accuracy": 方向准确率(%),
            "avg_mae": 平均绝对误差,
            "avg_score": 平均预测分数,
            "avg_return": 平均实际收益,
            "by_direction": {方向: {accuracy, count}},
        }
    """
    path = Path(path)
    if not path.exists():
        return {"total": 0, "validated": 0, "direction_accuracy": 0}

    df = pd.read_csv(path, encoding="utf-8-sig", na_values=["", " "],
                     keep_default_na=True, dtype={"validated": str})
    validated = df[df["validated"] == "1"].copy()

    result = {
        "total": len(df),
        "validated": len(validated),
        "direction_accuracy": 0,
        "avg_mae": 0,
        "avg_score": 0,
        "avg_return": 0,
        "by_direction": {},
    }

    if len(validated) == 0:
        return result

    # 方向准确率
    validated["actual_direction"] = validated["actual_3m_return"].apply(
        lambda x: "看涨" if pd.notna(x) and float(x) > RETURN_DIRECTION_THRESHOLD
        else ("看跌" if pd.notna(x) and float(x) < -RETURN_DIRECTION_THRESHOLD else "中性")
    )
    correct = (validated["direction"] == validated["actual_direction"]).sum()
    result["direction_accuracy"] = round(correct / len(validated) * 100, 1)

    # 平均 MAE
    if "score" in validated.columns and "actual_3m_return" in validated.columns:
        validated["actual_score"] = pd.to_numeric(
            validated["actual_3m_return"], errors="coerce"
        ).clip(-30, 30) / 30
        validated["score_num"] = pd.to_numeric(validated["score"], errors="coerce")
        result["avg_mae"] = round(abs(validated["score_num"] - validated["actual_score"]).mean(), 4)
        result["avg_score"] = round(validated["score_num"].mean(), 4)
        result["avg_return"] = round(
            pd.to_numeric(validated["actual_3m_return"], errors="coerce").mean(), 2
        )

    # 按方向统计
    for direction in ["看涨", "看跌", "中性"]:
        subset = validated[validated["direction"] == direction]
        if len(subset) > 0:
            sub_correct = (subset["direction"] == subset["actual_direction"]).sum()
            result["by_direction"][direction] = {
                "count": len(subset),
                "accuracy": round(sub_correct / len(subset) * 100, 1),
                "avg_return": round(subset["actual_3m_return"].mean(), 2),
            }

    return result


def calculate_per_indicator_accuracy(path: Path = PREDICTIONS_CSV) -> dict:
    """
    计算每个预测指标的独立方向准确率

    判断逻辑: 每个指标单独预测的方向(基于score正负) vs 实际方向
    """
    path = Path(path)
    if not path.exists():
        return {}

    df = pd.read_csv(path, encoding="utf-8-sig", na_values=["", " "],
                     keep_default_na=True, dtype={"validated": str})
    validated = df[df["validated"] == "1"].copy()
    if len(validated) == 0:
        return {}

    # 实际方向
    validated["actual_direction"] = validated["actual_3m_return"].apply(
        lambda x: "看涨" if pd.notna(x) and float(x) > RETURN_DIRECTION_THRESHOLD
        else ("看跌" if pd.notna(x) and float(x) < -RETURN_DIRECTION_THRESHOLD else "中性")
    )

    result = {}
    for col in PREDICTIVE_INDICATORS:
        score_col = f"{col}_score"
        if score_col not in validated.columns:
            continue

        correct = 0
        total = 0
        contributions = []

        for _, row in validated.iterrows():
            raw = row.get(score_col)
            if pd.isna(raw):
                continue

            indicator_score = float(raw)
            actual_dir = row["actual_direction"]

            # 该指标单独预测的方向
            threshold = SINGLE_DIRECTION_THRESHOLD
            if indicator_score > threshold:
                ind_dir = "看涨"
            elif indicator_score < -threshold:
                ind_dir = "看跌"
            else:
                ind_dir = "中性"

            if ind_dir == actual_dir:
                correct += 1
            total += 1
            weight = PREDICTIVE_INDICATORS[col]["weight"]
            contributions.append(indicator_score * weight)

        if total > 0:
            result[col] = {
                "correct": correct,
                "total": total,
                "accuracy": round(correct / total * 100, 1),
                "avg_contribution": round(
                    sum(contributions) / len(contributions), 4
                ) if contributions else 0,
            }
        else:
            result[col] = {"correct": 0, "total": 0, "accuracy": 0, "avg_contribution": 0}

    return result


def log_prediction_deviation(predictions_path: Path = PREDICTIONS_CSV,
                              deviation_log_path: Path = None) -> list:
    """
    分析已验证预测与实际结果的偏差，记录到 JSONL 文件

    分析维度:
    1. 方向误判记录
    2. 各指标贡献分析
    3. 定位误导指标
    4. 确认指标矛盾检查
    5. 偏差原因推测
    """
    if deviation_log_path is None:
        deviation_log_path = DEVIATION_LOG_PATH
    deviation_log_path = Path(deviation_log_path)
    predictions_path = Path(predictions_path)

    if not predictions_path.exists():
        return []

    df = pd.read_csv(predictions_path, encoding="utf-8-sig", na_values=["", " "],
                     keep_default_na=True, dtype={"validated": str})
    validated = df[df["validated"] == "1"].copy()

    if len(validated) == 0:
        return []

    # 实际方向
    validated["actual_direction"] = validated["actual_3m_return"].apply(
        lambda x: "看涨" if pd.notna(x) and float(x) > RETURN_DIRECTION_THRESHOLD
        else ("看跌" if pd.notna(x) and float(x) < -RETURN_DIRECTION_THRESHOLD else "中性")
    )

    # 找出方向预测错误的记录
    errors = validated[validated["direction"] != validated["actual_direction"]]

    # 读取已有的偏差日志，避免重复记录
    logged_dates = set()
    if deviation_log_path.exists():
        with open(deviation_log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        logged_dates.add(json.loads(line).get("date"))
                    except json.JSONDecodeError:
                        pass

    deviations = []
    for _, row in errors.iterrows():
        # 跳过已记录的偏差
        if row["date"] in logged_dates:
            continue

        # 逐指标分析偏差贡献
        indicator_analysis = {}
        for col in PREDICTIVE_INDICATORS:
            score_col = f"{col}_score"
            value_col = f"{col}_value"
            if score_col not in row.index or pd.isna(row.get(score_col)):
                indicator_analysis[col] = {
                    "value": None, "score": None,
                    "weight": PREDICTIVE_INDICATORS[col]["weight"],
                    "contribution": 0,
                }
                continue

            score = float(row[score_col])
            weight = PREDICTIVE_INDICATORS[col]["weight"]
            indicator_analysis[col] = {
                "value": float(row[value_col]) if pd.notna(row.get(value_col)) else None,
                "score": score,
                "weight": weight,
                "contribution": round(score * weight, 4),
            }

        # 找出"误导指标"：预测方向与最终方向一致，但实际方向相反
        final_dir = row["direction"]
        actual_dir = row["actual_direction"]
        misleading = []
        for col, analysis in indicator_analysis.items():
            score = analysis.get("score")
            if score is None:
                continue
            if score > SINGLE_DIRECTION_THRESHOLD:
                ind_dir = "看涨"
            elif score < -SINGLE_DIRECTION_THRESHOLD:
                ind_dir = "看跌"
            else:
                ind_dir = "中性"
            # 该指标方向与最终预测一致，但实际相反 → 误导
            if ind_dir == final_dir and ind_dir != "中性":
                misleading.append({
                    "indicator": col,
                    "label": PREDICTIVE_INDICATORS[col].get("label", col),
                    "score": score,
                    "contribution": analysis["contribution"],
                })

        # 按贡献度排序
        misleading.sort(key=lambda x: abs(x["contribution"]), reverse=True)

        # 确认指标矛盾检查
        confirming_conflicts = []
        for col in CONFIRMING_INDICATORS:
            confirm_col = f"confirm_{col}"
            if confirm_col in row.index and pd.notna(row[confirm_col]):
                status = str(row[confirm_col])
                if (final_dir == "看涨" and status == "看跌") or \
                   (final_dir == "看跌" and status == "看涨"):
                    confirming_conflicts.append({
                        "indicator": col,
                        "label": CONFIRMING_INDICATORS[col].get("label", col),
                    })

        # 偏差原因推测
        hypothesis = _generate_hypothesis(
            final_dir, actual_dir, misleading, confirming_conflicts
        )

        deviation = {
            "date": row["date"],
            "predicted_direction": final_dir,
            "actual_direction": actual_dir,
            "predicted_score": float(row["score"]),
            "actual_3m_return": float(row["actual_3m_return"]),
            "score_error": round(abs(float(row["score"]) -
                               max(-1, min(1, float(row["actual_3m_return"]) / 30))), 4),
            "indicator_analysis": indicator_analysis,
            "misleading_indicators": misleading[:3],  # 最多记录前3个
            "confirming_conflicts": confirming_conflicts,
            "deviation_cause_hypothesis": hypothesis,
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        deviations.append(deviation)

    # 追加到 JSONL 文件
    if deviations:
        deviation_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(deviation_log_path, "a", encoding="utf-8") as f:
            for d in deviations:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        logger.info(f"记录 {len(deviations)} 条预测偏差到 {deviation_log_path}")

    return deviations


def _generate_hypothesis(pred_dir, actual_dir, misleading, conflicts):
    """自动生成偏差原因推测"""
    reasons = []

    if misleading:
        names = [m["label"] for m in misleading[:3]]
        reasons.append(f"主要误导指标: {', '.join(names)}")

    if conflicts:
        names = [c["label"] for c in conflicts]
        reasons.append(f"确认指标矛盾: {', '.join(names)}")

    if pred_dir == "看涨" and actual_dir == "看跌":
        reasons.append("可能的系统性看涨偏误")
    elif pred_dir == "看跌" and actual_dir == "看涨":
        reasons.append("可能的系统性看跌偏误")

    return "; ".join(reasons) if reasons else "原因不明，需人工分析"


def smart_adjust_weights(path: Path = PREDICTIONS_CSV) -> dict | None:
    """
    智能权重调整 — 基于 per-indicator 准确率差异化调整

    规则:
    1. 小样本保护: validated < min_samples → 不调整
    2. 指标准确率 > boost_threshold → 权重 +step
    3. 指标准确率 < penalty_threshold → 权重 -step
    4. 其他 → 权重不变
    5. 归一化确保总和=1
    6. 调整后保存到 prediction_config.json
    """
    cfg = PREDICTION_CONFIG.get("self_learning", {})
    if not cfg.get("enabled", True):
        logger.info("自学习权重调整已禁用")
        return None

    accuracy = calculate_accuracy(path)
    min_samples = cfg.get("min_samples_for_adjust", 5)

    if accuracy["validated"] < min_samples:
        logger.info(f"样本不足({accuracy['validated']}<{min_samples})，跳过权重调整")
        return None

    per_indicator = calculate_per_indicator_accuracy(path)
    if not per_indicator:
        return None

    boost_threshold = cfg.get("direction_accuracy_boost_threshold", 65)
    penalty_threshold = cfg.get("direction_accuracy_penalty_threshold", 45)
    step = cfg.get("weight_adjust_step", 0.05)

    new_weights = {}
    changed = False
    changes = {}

    for col, config in PREDICTIVE_INDICATORS.items():
        w = config["weight"]
        ind_acc = per_indicator.get(col, {}).get("accuracy", 50)
        min_w = config.get("min_weight", 0.05)
        max_w = config.get("max_weight", 0.50)

        old_w = w
        if ind_acc > boost_threshold:
            w = min(w + step, max_w)
        elif ind_acc < penalty_threshold:
            w = max(w - step, min_w)

        new_weights[col] = round(w, 4)

        if abs(w - old_w) > 0.001:
            changed = True
            changes[col] = {
                "old_weight": round(old_w, 4),
                "new_weight": round(w, 4),
                "accuracy": ind_acc,
                "reason": "提升" if w > old_w else "降低",
            }

    if not changed:
        logger.info("所有指标准确率在中间区间，无需调整权重")
        return None

    # 归一化
    total = sum(new_weights.values())
    if total > 0:
        for k in new_weights:
            new_weights[k] = round(new_weights[k] / total, 4)

    # 写回配置
    for col, w in new_weights.items():
        PREDICTION_CONFIG["predictive_indicators"][col]["weight"] = w
    PREDICTION_CONFIG["meta"]["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_prediction_config()

    logger.info(f"权重已自动调整: {changes}")
    return new_weights


def generate_deviation_report(deviation_log_path: Path = None) -> str:
    """
    生成偏差汇总报告（Markdown 格式）
    """
    if deviation_log_path is None:
        deviation_log_path = DEVIATION_LOG_PATH
    deviation_log_path = Path(deviation_log_path)

    if not deviation_log_path.exists():
        return ""

    deviations = []
    with open(deviation_log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    deviations.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not deviations:
        return ""

    lines = []
    lines.append("### 预测偏差分析")
    lines.append("")
    lines.append(f"共记录 {len(deviations)} 次方向误判")
    lines.append("")
    lines.append("| 日期 | 预测 | 实际 | 分数 | 实际收益 | 主要误导指标 | 原因推测 |")
    lines.append("|------|------|------|------|---------|------------|---------|")

    for d in deviations[-10:]:  # 最近10条
        misleading_names = ", ".join(
            [m.get("label", m["indicator"]) for m in d.get("misleading_indicators", [])[:2]]
        ) or "-"
        hypothesis = d.get("deviation_cause_hypothesis", "")
        # 截断过长的原因推测
        if len(hypothesis) > 40:
            hypothesis = hypothesis[:40] + "..."
        lines.append(
            f"| {d['date']} | {d['predicted_direction']} | {d['actual_direction']} "
            f"| {d['predicted_score']:+.3f} | {d['actual_3m_return']:+.2f}% "
            f"| {misleading_names} | {hypothesis} |"
        )

    lines.append("")

    # 误导指标频率统计
    indicator_count = {}
    for d in deviations:
        for m in d.get("misleading_indicators", []):
            col = m["indicator"]
            indicator_count[col] = indicator_count.get(col, 0) + 1

    if indicator_count:
        lines.append("**误导指标频率排名:**")
        lines.append("")
        sorted_indicators = sorted(indicator_count.items(), key=lambda x: x[1], reverse=True)
        for col, count in sorted_indicators:
            label = PREDICTIVE_INDICATORS.get(col, {}).get("label", col)
            lines.append(f"- {label}({col}): {count} 次")
        lines.append("")

    return "\n".join(lines)


def generate_prediction_report(path: Path = PREDICTIONS_CSV) -> str:
    """生成预测汇总 Markdown 文本"""
    accuracy = calculate_accuracy(path)
    per_indicator = calculate_per_indicator_accuracy(path)

    lines = []
    lines.append("### 预测准确率与验证历史")
    lines.append("")
    lines.append(f"共 {accuracy['total']} 次预测，{accuracy['validated']} 次已验证")
    lines.append("")
    if accuracy["validated"] > 0:
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 方向准确率 | {accuracy['direction_accuracy']}% |")
        lines.append(f"| 平均绝对误差 | {accuracy['avg_mae']} |")
        lines.append(f"| 平均预测分数 | {accuracy['avg_score']} |")
        lines.append(f"| 平均实际收益 | {accuracy['avg_return']:+.2f}% |")
        lines.append("")

        # 按方向统计
        if accuracy.get("by_direction"):
            lines.append("| 预测方向 | 次数 | 准确率 | 平均收益 |")
            lines.append("|---------|------|--------|---------|")
            for direction, stats in accuracy["by_direction"].items():
                lines.append(
                    f"| {direction} | {stats['count']} | {stats['accuracy']}% "
                    f"| {stats['avg_return']:+.2f}% |"
                )
            lines.append("")

        # 各指标独立准确率
        if per_indicator:
            lines.append("### 各指标独立准确率")
            lines.append("")
            lines.append("| 指标 | 正确/总数 | 准确率 | 平均贡献 | 当前权重 |")
            lines.append("|------|----------|--------|---------|---------|")
            for col, stats in per_indicator.items():
                label = PREDICTIVE_INDICATORS[col].get("label", col)
                weight = PREDICTIVE_INDICATORS[col].get("weight", 0)
                lines.append(
                    f"| {label} | {stats['correct']}/{stats['total']} "
                    f"| {stats['accuracy']}% | {stats['avg_contribution']:.4f} "
                    f"| {weight:.2%} |"
                )
            lines.append("")
    else:
        lines.append("> 尚无已验证的预测记录，首次预测将在 3 个月后验证")
        lines.append("")

    # 最近预测记录
    path = Path(path)
    if path.exists():
        df = pd.read_csv(path, encoding="utf-8-sig")
        if len(df) > 0:
            recent = df.tail(6).iloc[::-1]
            lines.append("### 最近预测记录")
            lines.append("")
            lines.append("| 日期 | 预测方向 | 预测分数 | 置信度 | 确认度 | 实际3月收益 | 验证 |")
            lines.append("|------|---------|---------|--------|--------|-----------|------|")
            for _, row in recent.iterrows():
                ret = row.get("actual_3m_return", "")
                if pd.notna(ret) and str(ret).strip() != "":
                    try:
                        ret_str = f"{float(ret):+.2f}%"
                    except (ValueError, TypeError):
                        ret_str = "待验证"
                else:
                    ret_str = "待验证"
                validated = "✅" if str(row.get("validated", "0")) == "1" else "⏳"
                conf_pct = f"{row.get('confirming_pct', 0):.0%}"
                lines.append(
                    f"| {row['date']} | {row['direction']} | {row.get('score', 0):+.3f} "
                    f"| {row.get('confidence', 0):.2f} | {conf_pct} "
                    f"| {ret_str} | {validated} |"
                )
            lines.append("")

    return "\n".join(lines)
