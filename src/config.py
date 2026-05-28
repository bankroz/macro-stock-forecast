# -*- coding: utf-8 -*-
"""
全局配置文件
所有路径、阈值、参数集中管理
支持 JSON 外部配置文件（优先）+ 代码默认值（回退）
"""

import json
import logging
from copy import deepcopy
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# 路径配置
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent  # 项目根目录

DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_DIR = BASE_DIR / "config"

# 数据文件 — 存款与指数
DEPOSITS_CSV = DATA_DIR / "deposits.csv"
SH_INDEX_CSV = DATA_DIR / "sh_index.csv"

# 数据文件 — 宏观指标
MACRO_M2_CSV = DATA_DIR / "macro_m2.csv"
MACRO_PMI_CSV = DATA_DIR / "macro_pmi.csv"
MACRO_ELECTRICITY_CSV = DATA_DIR / "macro_electricity.csv"
MACRO_MARGIN_CSV = DATA_DIR / "macro_margin.csv"
MACRO_SHIBOR_CSV = DATA_DIR / "macro_shibor.csv"
MACRO_LPR_CSV = DATA_DIR / "macro_lpr.csv"
MACRO_CPI_CSV = DATA_DIR / "macro_cpi.csv"
MACRO_PPI_CSV = DATA_DIR / "macro_ppi.csv"
MACRO_NORTHBOUND_CSV = DATA_DIR / "macro_northbound.csv"

# 数据文件 — 第三批宏观指标
MACRO_BDI_CSV = DATA_DIR / "macro_bdi.csv"
MACRO_RETAIL_CSV = DATA_DIR / "macro_retail.csv"
MACRO_FISCAL_CSV = DATA_DIR / "macro_fiscal.csv"

# 预测记录
PREDICTIONS_CSV = DATA_DIR / "predictions.csv"

# 配置文件（JSON）
SIGNAL_CONFIG_PATH = CONFIG_DIR / "signal_config.json"
PREDICTION_CONFIG_PATH = CONFIG_DIR / "prediction_config.json"

# 偏差日志
DEVIATION_LOG_PATH = DATA_DIR / "prediction_deviations.jsonl"

# 宏观指标 CSV 列名定义（标准化）
MACRO_COLUMNS = {
    "m2": ["date", "m2_amount", "m1_amount", "m0_amount", "m2_yoy", "m1_yoy", "m0_yoy"],
    "pmi": ["date", "pmi_manufacturing", "pmi_non_manufacturing"],
    "electricity": ["date", "electricity_total_yoy", "electricity_industrial_yoy",
                    "electricity_tertiary_yoy", "electricity_residential_yoy"],
    "margin": ["date", "margin_balance", "margin_yoy"],
    "shibor": ["date", "shibor_on_avg", "shibor_1w_avg"],
    "lpr": ["date", "lpr_1y", "lpr_5y"],
    "cpi": ["date", "cpi_yoy", "cpi_mom"],
    "ppi": ["date", "ppi_yoy"],
    "northbound": ["date", "northbound_net_buy"],
    # 第三批宏观指标
    "bdi": ["date", "bdi_value", "bdi_yoy"],
    "retail": ["date", "retail_yoy"],
    "fiscal": ["date", "fiscal_yoy"],
}

# ============================================================
# 图表配置
# ============================================================
CHART_DPI = 150
CHART_FIGSIZE = (24, 14)
FONT_FAMILY = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']

# ============================================================
# 央行数据爬虫配置
# ============================================================
PBC_DATA_URL = "https://www.pbc.gov.cn"

# ============================================================
# JSON 配置加载器
# ============================================================

# ---- 默认信号配置（代码内兜底） ----
DEFAULT_SIGNAL_CONFIG = {
    "meta": {"version": "1.0", "description": "信号检测阈值配置 - 手动编辑或自动学习调整"},
    "yoy_decline": {"lookback_months": 12, "decline_threshold": 0.30, "peak_high_watermark": 15},
    "mom_decline": {"lookback_months": 12, "decline_threshold": 0.50,
                    "peak_high_watermark": 3, "current_ratio_to_peak": 0.3},
    "divergence_a": {"consecutive_months": 3},
    "divergence_b": {"consecutive_months": 2},
    "m2_inflection": {"ma_window": 3},
    "pmi_contraction": {"consecutive_months": 3},
    "margin_peak": {"high_watermark": 20, "decline_threshold": 0.30},
    "shibor_spike": {"spike_threshold": 1.50},
    "cpi_ppi_divergence": {"consecutive_months": 3},
    "northbound_outflow": {"consecutive_months": 3},
    "bdi_extreme": {"extreme_high": 80, "extreme_low": -40,
                    "reversal_window": 3, "reversal_ratio": 0.5},
    "retail_decline": {"consecutive_months": 3},
    "fiscal_turning": {"window_months": 6},
    "risk_level_rules": {"critical_primary_threshold": 2, "high_require_secondary_or_warning": True},
    "known_tops": [
        {"date": "2015-06", "label": "2015年牛市高点", "index": 5178},
        {"date": "2018-01", "label": "2018年初高点", "index": 3587},
        {"date": "2021-02", "label": "2021年结构性牛市高点", "index": 3731},
        {"date": "2021-09", "label": "2021年9月高点", "index": 3715},
        {"date": "2022-07", "label": "2022年7月反弹高点", "index": 3424},
    ],
    "known_bottoms": [
        {"date": "2016-01", "label": "2016年熔断低点", "index": 2638},
        {"date": "2019-01", "label": "2019年初低点", "index": 2440},
        {"date": "2020-03", "label": "2020年疫情低点", "index": 2750},
        {"date": "2022-10", "label": "2022年10月低点", "index": 2885},
        {"date": "2024-02", "label": "2024年初低点", "index": 2789},
    ],
}

# ---- 默认预测配置（代码内兜底） ----
DEFAULT_PREDICTION_CONFIG = {
    "meta": {"version": "1.0", "description": "预测引擎配置 - 手动编辑或自动学习调整"},
    "parameters": {
        "horizon_months": 3, "percentile_window": 60,
        "bull_threshold": 0.20, "bear_threshold": -0.20,
        "min_history_months": 12, "return_direction_threshold": 2.0,
        "single_direction_threshold": 0.1,
    },
    "predictive_indicators": {
        "retail_yoy": {"weight": 0.37, "lag_months": 10, "r": -0.5007,
                       "direction": "negative", "label": "社消零售",
                       "min_weight": 0.05, "max_weight": 0.50},
        "fiscal_yoy": {"weight": 0.27, "lag_months": 10, "r": -0.3681,
                       "direction": "negative", "label": "财政收入",
                       "min_weight": 0.05, "max_weight": 0.50},
        "non_bank_yoy": {"weight": 0.22, "lag_months": 6, "r": 0.30,
                         "direction": "positive", "label": "非银存款增速",
                         "min_weight": 0.05, "max_weight": 0.50},
        "m2_yoy": {"weight": 0.14, "lag_months": 6, "r": 0.20,
                   "direction": "positive", "label": "M2增速",
                   "min_weight": 0.05, "max_weight": 0.50},
    },
    "confirming_indicators": {
        "bdi_yoy": {"label": "BDI干散货指数", "r": 0.3629, "description": "全球需求同步",
                    "threshold": 0, "inverse": False},
        "pmi_manufacturing": {"label": "PMI制造业", "r": 0.20, "description": "景气度确认",
                              "threshold": 50, "inverse": False},
        "margin_yoy": {"label": "两融余额增速", "r": 0, "description": "杠杆水位",
                       "threshold": 0, "inverse": False},
        "shibor_on_avg": {"label": "SHIBOR隔夜", "r": 0, "description": "资金面即时",
                          "threshold": 2.0, "inverse": True, "neutral_upper": 3.0},
        "non_bank_mom": {"label": "非银存款MoM", "r": 0, "description": "资金流入即时",
                         "threshold": 0, "inverse": False},
    },
    "confirming_labels": {"high": 0.70, "partial": 0.40},
    "self_learning": {
        "enabled": True,
        "min_samples_for_adjust": 5,
        "weight_adjust_step": 0.05,
        "direction_accuracy_boost_threshold": 65,
        "direction_accuracy_penalty_threshold": 45,
        "adjust_interval_runs": 3,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 中的值优先"""
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


def _load_json_config(path: Path, defaults: dict) -> dict:
    """
    加载 JSON 配置文件

    - 文件存在 → 读取并与默认值深合并（JSON 覆盖默认值）
    - 文件不存在或损坏 → 使用默认值并自动生成文件
    """
    path = Path(path)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            merged = _deep_merge(defaults, loaded)
            logger.debug(f"已加载配置: {path}")
            return merged
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"配置文件损坏，使用默认值: {path} ({e})")
            return deepcopy(defaults)
    else:
        # 首次运行：生成默认配置文件
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(defaults, f, ensure_ascii=False, indent=2)
        logger.info(f"已生成默认配置文件: {path}")
        return deepcopy(defaults)


def _save_json_config(path: Path, config: dict) -> None:
    """保存配置到 JSON 文件"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    logger.debug(f"已保存配置: {path}")


# ---- 模块级加载配置 ----
SIGNAL_CONFIG = _load_json_config(SIGNAL_CONFIG_PATH, DEFAULT_SIGNAL_CONFIG)
PREDICTION_CONFIG = _load_json_config(PREDICTION_CONFIG_PATH, DEFAULT_PREDICTION_CONFIG)


# ---- 便捷访问函数 ----

def get_signal(key_path: str, default=None):
    """
    按点分路径获取信号配置值

    示例:
        get_signal('yoy_decline.decline_threshold') → 0.30
        get_signal('bdi_extreme.extreme_high') → 80
        get_signal('risk_level_rules.critical_primary_threshold') → 2
    """
    keys = key_path.split(".")
    val = SIGNAL_CONFIG
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val


def get_prediction(key_path: str, default=None):
    """
    按点分路径获取预测配置值

    示例:
        get_prediction('parameters.horizon_months') → 3
        get_prediction('predictive_indicators.retail_yoy.weight') → 0.37
        get_prediction('self_learning.enabled') → True
    """
    keys = key_path.split(".")
    val = PREDICTION_CONFIG
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val


def save_signal_config() -> None:
    """保存当前信号配置到 JSON"""
    _save_json_config(SIGNAL_CONFIG_PATH, SIGNAL_CONFIG)


def save_prediction_config() -> None:
    """保存当前预测配置到 JSON"""
    _save_json_config(PREDICTION_CONFIG_PATH, PREDICTION_CONFIG)


# ============================================================
# 向后兼容：模块级变量（从 JSON 配置同步）
# ============================================================

# 信号检测阈值
YOY_LOOKBACK_MONTHS = get_signal("yoy_decline.lookback_months", 12)
YOY_DECLINE_THRESHOLD = get_signal("yoy_decline.decline_threshold", 0.30)
YOY_HIGH_WATERMARK = get_signal("yoy_decline.peak_high_watermark", 15)
MOM_LOOKBACK_MONTHS = get_signal("mom_decline.lookback_months", 12)
MOM_DECLINE_THRESHOLD = get_signal("mom_decline.decline_threshold", 0.50)
MOM_HIGH_WATERMARK = get_signal("mom_decline.peak_high_watermark", 3)
MOM_RATIO_TO_PEAK = get_signal("mom_decline.current_ratio_to_peak", 0.3)
DIVERGENCE_A_CONSECUTIVE = get_signal("divergence_a.consecutive_months", 3)
DIVERGENCE_B_CONSECUTIVE = get_signal("divergence_b.consecutive_months", 2)

# 宏观信号阈值
M2_MA_WINDOW = get_signal("m2_inflection.ma_window", 3)
PMI_CONTRACTION_MONTHS = get_signal("pmi_contraction.consecutive_months", 3)
MARGIN_HIGH_WATERMARK = get_signal("margin_peak.high_watermark", 20)
MARGIN_DECLINE_THRESHOLD = get_signal("margin_peak.decline_threshold", 0.30)
SHIBOR_SPIKE_THRESHOLD = get_signal("shibor_spike.spike_threshold", 1.50)
CPI_PPI_DIVERGENCE_MONTHS = get_signal("cpi_ppi_divergence.consecutive_months", 3)
NORTHBOUND_OUTFLOW_MONTHS = get_signal("northbound_outflow.consecutive_months", 3)

# 第三批宏观信号阈值
BDI_EXTREME_HIGH = get_signal("bdi_extreme.extreme_high", 80)
BDI_EXTREME_LOW = get_signal("bdi_extreme.extreme_low", -40)
BDI_REVERSAL_WINDOW = get_signal("bdi_extreme.reversal_window", 3)
BDI_REVERSAL_RATIO = get_signal("bdi_extreme.reversal_ratio", 0.5)
RETAIL_DECLINE_MONTHS = get_signal("retail_decline.consecutive_months", 3)
FISCAL_TURNING_WINDOW = get_signal("fiscal_turning.window_months", 6)

# 历史已知顶部/底部
KNOWN_MARKET_TOPS = get_signal("known_tops", [])
KNOWN_MARKET_BOTTOMS = get_signal("known_bottoms", [])

# 风险等级规则
RISK_CRITICAL_THRESHOLD = get_signal("risk_level_rules.critical_primary_threshold", 2)
RISK_HIGH_REQUIRE_OTHER = get_signal("risk_level_rules.high_require_secondary_or_warning", True)

# 预测系统配置
PREDICTION_HORIZON = get_prediction("parameters.horizon_months", 3)
PREDICTION_PERCENTILE_WINDOW = get_prediction("parameters.percentile_window", 60)
PREDICTION_BULL_THRESHOLD = get_prediction("parameters.bull_threshold", 0.20)
PREDICTION_BEAR_THRESHOLD = get_prediction("parameters.bear_threshold", -0.20)
PREDICTION_MIN_HISTORY = get_prediction("parameters.min_history_months", 12)
RETURN_DIRECTION_THRESHOLD = get_prediction("parameters.return_direction_threshold", 2.0)
SINGLE_DIRECTION_THRESHOLD = get_prediction("parameters.single_direction_threshold", 0.1)

# 预测指标和确认指标（直接引用配置字典）
PREDICTIVE_INDICATORS = PREDICTION_CONFIG["predictive_indicators"]
CONFIRMING_INDICATORS = PREDICTION_CONFIG["confirming_indicators"]
CONFIRMING_LABELS = PREDICTION_CONFIG["confirming_labels"]


def _refresh_aliases():
    """
    刷新模块级变量（JSON 配置修改后调用）

    将 JSON 配置中的最新值同步到模块级常量，
    确保后续代码引用到更新后的值。
    """
    global YOY_LOOKBACK_MONTHS, YOY_DECLINE_THRESHOLD, YOY_HIGH_WATERMARK
    global MOM_LOOKBACK_MONTHS, MOM_DECLINE_THRESHOLD, MOM_HIGH_WATERMARK, MOM_RATIO_TO_PEAK
    global DIVERGENCE_A_CONSECUTIVE, DIVERGENCE_B_CONSECUTIVE
    global M2_MA_WINDOW, PMI_CONTRACTION_MONTHS
    global MARGIN_HIGH_WATERMARK, MARGIN_DECLINE_THRESHOLD
    global SHIBOR_SPIKE_THRESHOLD, CPI_PPI_DIVERGENCE_MONTHS, NORTHBOUND_OUTFLOW_MONTHS
    global BDI_EXTREME_HIGH, BDI_EXTREME_LOW, BDI_REVERSAL_WINDOW, BDI_REVERSAL_RATIO
    global RETAIL_DECLINE_MONTHS, FISCAL_TURNING_WINDOW
    global KNOWN_MARKET_TOPS, KNOWN_MARKET_BOTTOMS
    global RISK_CRITICAL_THRESHOLD, RISK_HIGH_REQUIRE_OTHER
    global PREDICTION_HORIZON, PREDICTION_PERCENTILE_WINDOW
    global PREDICTION_BULL_THRESHOLD, PREDICTION_BEAR_THRESHOLD
    global PREDICTION_MIN_HISTORY, RETURN_DIRECTION_THRESHOLD, SINGLE_DIRECTION_THRESHOLD
    global PREDICTIVE_INDICATORS, CONFIRMING_INDICATORS, CONFIRMING_LABELS

    YOY_LOOKBACK_MONTHS = get_signal("yoy_decline.lookback_months", 12)
    YOY_DECLINE_THRESHOLD = get_signal("yoy_decline.decline_threshold", 0.30)
    YOY_HIGH_WATERMARK = get_signal("yoy_decline.peak_high_watermark", 15)
    MOM_LOOKBACK_MONTHS = get_signal("mom_decline.lookback_months", 12)
    MOM_DECLINE_THRESHOLD = get_signal("mom_decline.decline_threshold", 0.50)
    MOM_HIGH_WATERMARK = get_signal("mom_decline.peak_high_watermark", 3)
    MOM_RATIO_TO_PEAK = get_signal("mom_decline.current_ratio_to_peak", 0.3)
    DIVERGENCE_A_CONSECUTIVE = get_signal("divergence_a.consecutive_months", 3)
    DIVERGENCE_B_CONSECUTIVE = get_signal("divergence_b.consecutive_months", 2)

    M2_MA_WINDOW = get_signal("m2_inflection.ma_window", 3)
    PMI_CONTRACTION_MONTHS = get_signal("pmi_contraction.consecutive_months", 3)
    MARGIN_HIGH_WATERMARK = get_signal("margin_peak.high_watermark", 20)
    MARGIN_DECLINE_THRESHOLD = get_signal("margin_peak.decline_threshold", 0.30)
    SHIBOR_SPIKE_THRESHOLD = get_signal("shibor_spike.spike_threshold", 1.50)
    CPI_PPI_DIVERGENCE_MONTHS = get_signal("cpi_ppi_divergence.consecutive_months", 3)
    NORTHBOUND_OUTFLOW_MONTHS = get_signal("northbound_outflow.consecutive_months", 3)

    BDI_EXTREME_HIGH = get_signal("bdi_extreme.extreme_high", 80)
    BDI_EXTREME_LOW = get_signal("bdi_extreme.extreme_low", -40)
    BDI_REVERSAL_WINDOW = get_signal("bdi_extreme.reversal_window", 3)
    BDI_REVERSAL_RATIO = get_signal("bdi_extreme.reversal_ratio", 0.5)
    RETAIL_DECLINE_MONTHS = get_signal("retail_decline.consecutive_months", 3)
    FISCAL_TURNING_WINDOW = get_signal("fiscal_turning.window_months", 6)

    KNOWN_MARKET_TOPS = get_signal("known_tops", [])
    KNOWN_MARKET_BOTTOMS = get_signal("known_bottoms", [])

    RISK_CRITICAL_THRESHOLD = get_signal("risk_level_rules.critical_primary_threshold", 2)
    RISK_HIGH_REQUIRE_OTHER = get_signal("risk_level_rules.high_require_secondary_or_warning", True)

    PREDICTION_HORIZON = get_prediction("parameters.horizon_months", 3)
    PREDICTION_PERCENTILE_WINDOW = get_prediction("parameters.percentile_window", 60)
    PREDICTION_BULL_THRESHOLD = get_prediction("parameters.bull_threshold", 0.20)
    PREDICTION_BEAR_THRESHOLD = get_prediction("parameters.bear_threshold", -0.20)
    PREDICTION_MIN_HISTORY = get_prediction("parameters.min_history_months", 12)
    RETURN_DIRECTION_THRESHOLD = get_prediction("parameters.return_direction_threshold", 2.0)
    SINGLE_DIRECTION_THRESHOLD = get_prediction("parameters.single_direction_threshold", 0.1)

    PREDICTIVE_INDICATORS = PREDICTION_CONFIG["predictive_indicators"]
    CONFIRMING_INDICATORS = PREDICTION_CONFIG["confirming_indicators"]
    CONFIRMING_LABELS = PREDICTION_CONFIG["confirming_labels"]

    logger.debug("配置别名已刷新")


# ============================================================
# 确保目录存在
# ============================================================
for d in [DATA_DIR, REPORTS_DIR, LOGS_DIR, OUTPUT_DIR, CONFIG_DIR]:
    d.mkdir(parents=True, exist_ok=True)
