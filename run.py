# -*- coding: utf-8 -*-
"""
一键运行入口
数据采集 → 指标计算 → 信号检测 → 预测生成 → 图表生成 → 报告输出
"""

# 过滤 jsonshema/strict mode 警告（来自 pydantic/jsonshema 依赖）
# 这些警告输出到 stderr 会干扰 .bat 脚本的 errorlevel 判断
import warnings
warnings.filterwarnings(
    "ignore",
    message=".*missing type.*keyword.*pattern.*",
)
warnings.filterwarnings(
    "ignore",
    message=".*strict mode.*",
)

import sys
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime

# 确保项目根目录在 Python 路径中
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.config import LOGS_DIR, OUTPUT_DIR, get_prediction, _refresh_aliases
from src.data_manager import load_merged, update_sh_index, update_macro
from src.indicators import compute_indicators
from src.signal_detector import detect_signals, backtest_signals
from src.chart_generator import (
    generate_main_chart, generate_rate_chart, generate_signal_chart,
    generate_macro_credit_chart, generate_macro_liquidity_chart,
    generate_prediction_dashboard, generate_all_charts,
)
from src.report_generator import generate_report
from src.prediction import (
    generate_prediction, record_prediction, validate_predictions,
    generate_prediction_report, calculate_accuracy,
    log_prediction_deviation, generate_deviation_report,
    smart_adjust_weights,
)
from src.scraper import (
    fetch_akshare_index, MACRO_FETCHERS,
)

# ============================================================
# 日志配置
# ============================================================
LOGS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

log_file = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def run(fetch_new_data: bool = True):
    """
    主运行流程

    Args:
        fetch_new_data: 是否尝试获取最新数据（设为 False 可跳过网络请求，仅用本地 CSV）
    """
    logger.info("=" * 60)
    logger.info("股市宏观分析系统 - 开始运行")
    logger.info("=" * 60)

    # Step 1: 数据采集（可选）
    if fetch_new_data:
        logger.info("[Step 1/6] 尝试获取最新数据...")

        # 上证指数
        try:
            new_index_data = fetch_akshare_index()
            if new_index_data:
                update_sh_index(new_index_data)
        except Exception as e:
            logger.warning(f"上证指数采集跳过: {e}")

        # 宏观指标（含第三批）
        for name, (label, fetcher) in MACRO_FETCHERS.items():
            try:
                new_data = fetcher()
                if new_data:
                    update_macro(name, new_data)
            except Exception as e:
                logger.warning(f"{label}采集跳过: {e}")
    else:
        logger.info("[Step 1/6] 跳过数据采集（使用本地CSV）")

    # Step 2: 加载并计算指标
    logger.info("[Step 2/6] 加载数据并计算指标...")
    df = load_merged()
    if df.empty:
        logger.error("无数据可用，请先运行 init_data.py 和 init_macro_data.py 初始化数据")
        return

    indicators_df = compute_indicators(df)
    logger.info(f"数据范围: {df['date'].min().strftime('%Y-%m')} 至 {df['date'].max().strftime('%Y-%m')}, 共 {len(df)} 条")

    # Step 3: 信号检测
    logger.info("[Step 3/6] 执行信号检测（13个信号）...")
    result = detect_signals(indicators_df)
    logger.info(f"风险等级: {result.risk_level.value} - {result.summary}")

    # Step 4: 预测生成 + 自学习闭环
    logger.info("[Step 4/6] 生成走势预测...")
    prediction_result = None
    prediction_report_text = ""
    deviation_report_text = ""
    try:
        # 4.1 验证旧预测（回填实际收益）
        validate_predictions(indicators_df)

        # 4.2 自学习：偏差分析与记录
        logger.info("[Step 4.5/6] 自学习：偏差追踪与权重优化...")
        try:
            # 偏差记录（每次运行都执行）
            deviations = log_prediction_deviation()
            deviation_report_text = generate_deviation_report()

            # 准确率概览
            accuracy = calculate_accuracy()
            if accuracy["validated"] > 0:
                logger.info(f"预测准确率: 方向={accuracy.get('direction_accuracy', 'N/A')}%, "
                           f"MAE={accuracy.get('avg_mae', 'N/A')}")

            # 权重调整（每N次运行执行一次，避免频繁调整）
            adjust_interval = get_prediction("self_learning.adjust_interval_runs", 3)
            run_count_file = LOGS_DIR / ".run_count"
            run_count = 0
            if run_count_file.exists():
                try:
                    run_count = int(run_count_file.read_text().strip())
                except (ValueError, OSError):
                    run_count = 0
            run_count += 1
            run_count_file.write_text(str(run_count))

            if run_count % adjust_interval == 0:
                new_weights = smart_adjust_weights()
                if new_weights:
                    logger.info(f"第{run_count}次运行触发权重调整")
                    _refresh_aliases()
        except Exception as e:
            logger.warning(f"自学习环节跳过: {e}")

        # 4.3 生成新预测
        prediction_result = generate_prediction(indicators_df)
        record_prediction(prediction_result)
        # 4.4 生成预测报告
        prediction_report_text = generate_prediction_report()
        logger.info(f"预测: {prediction_result.direction} (score={prediction_result.score:+.3f}, "
                    f"确认度={prediction_result.confirming_pct:.0%})")
    except Exception as e:
        logger.error(f"预测生成失败: {e}")

    # Step 5: 生成图表
    logger.info("[Step 5/6] 生成图表...")
    chart_paths = generate_all_charts(indicators_df, result, pd.DataFrame(), prediction_result)

    # 回测（需在图表之后，因为回测图依赖 backtest_df）
    logger.info("执行历史回测...")
    try:
        backtest_df = backtest_signals(indicators_df)
        if not backtest_df.empty:
            try:
                c = generate_signal_chart(indicators_df, backtest_df)
                chart_paths["signal_backtest"] = c if c else None
            except Exception as e:
                logger.error(f"信号回测图生成失败: {e}")
        else:
            backtest_df = pd.DataFrame()
    except Exception as e:
        logger.error(f"回测失败: {e}")
        backtest_df = pd.DataFrame()

    # Step 6: 生成 HTML 报告（图表 Base64 内嵌）
    logger.info("[Step 6/6] 生成 HTML 分析报告...")
    try:
        report_path = generate_report(
            df, indicators_df, result, backtest_df,
            prediction_result=prediction_result,
            prediction_report_text=prediction_report_text,
            deviation_report_text=deviation_report_text,
            chart_paths=chart_paths,
        )
        logger.info(f"报告已生成: {report_path}")
    except Exception as e:
        logger.error(f"报告生成失败: {e}")

    # 汇总
    logger.info("=" * 60)
    logger.info(f"运行完成！风险等级: {result.risk_level.value}")
    if prediction_result:
        logger.info(f"走势预测: {prediction_result.direction} (score={prediction_result.score:+.3f}, "
                    f"置信度={prediction_result.confidence:.1%}, 确认度={prediction_result.confirming_pct:.0%})")
    if result.signals:
        for s in result.signals:
            logger.info(f"  - [{s.level.value}] {s.name}: {s.detail}")
    logger.info("=" * 60)

    return result


if __name__ == "__main__":
    fetch = "--no-fetch" not in sys.argv
    run(fetch_new_data=fetch)
