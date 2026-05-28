# -*- coding: utf-8 -*-
"""
报告生成模块
生成 HTML 格式的分析报告（图表以 Base64 内嵌）
"""

import pandas as pd
import logging
from datetime import datetime
from pathlib import Path

from src.config import REPORTS_DIR, PREDICTION_HORIZON
from src.indicators import get_latest_metrics
from src.signal_detector import DetectionResult, RiskLevel

logger = logging.getLogger(__name__)


def _fmt(val, fmt_str=".2f", default="-"):
    """安全格式化数值"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return f"{float(val):{fmt_str}}"
    except (ValueError, TypeError):
        return default


def generate_report(
    df: pd.DataFrame,
    indicators_df: pd.DataFrame,
    result: DetectionResult,
    backtest_df: pd.DataFrame,
    prediction_result=None,
    prediction_report_text="",
    deviation_report_text="",
    chart_paths: dict | None = None,
) -> Path:
    """
    生成 HTML 分析报告（图表以 Base64 内嵌）

    Args:
        chart_paths: 图表路径字典，键名: main_trend, rate_comparison, signal_backtest,
                     macro_credit, macro_liquidity, prediction_dashboard
                     如果不传，报告不嵌入图表（向后兼容）。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = REPORTS_DIR / f"{today}_report.html"

    from src.html_builder import build_html

    html_content = build_html(
        df=df,
        indicators_df=indicators_df,
        result=result,
        backtest_df=backtest_df,
        chart_paths=chart_paths or {},
        prediction_result=prediction_result,
        prediction_report_text=prediction_report_text,
        deviation_report_text=deviation_report_text,
    )

    report_path.write_text(html_content, encoding="utf-8")
    logger.info(f"HTML报告已生成: {report_path}")
    return report_path
