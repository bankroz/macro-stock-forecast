# -*- coding: utf-8 -*-
"""
数据爬虫模块
- 央行官网爬取存款数据（主）
- akshare 获取上证指数（主）
- 手动 CSV 补充为备用
"""

import pandas as pd
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def fetch_pbc_deposits() -> list[dict] | None:
    """
    从央行官网抓取最新存款数据
    目前央行官网数据需要登录或有动态加载，作为预留接口
    返回格式: [{"date": "2026-05-01", "household_deposit": 175.0, "non_bank_deposit": 46.0}]
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("缺少 requests 或 beautifulsoup4，请运行 pip install requests beautifulsoup4 lxml")
        return None

    # 尝试从央行统计页面抓取
    # 注意：央行官网数据通常需要手动下载 Excel，此爬虫作为框架预留
    # 实际使用时可能需要根据页面结构调整选择器
    logger.info("央行数据爬虫：正在尝试获取...")
    logger.info("提示：央行官网数据通常需要手动下载 Excel 后导入 data/ 目录")
    logger.info("请将下载的文件放到 data/manual_deposits.csv，格式为 date,household_deposit,non_bank_deposit")
    return None


def fetch_akshare_index(start_date: str = "20150101") -> list[dict] | None:
    """
    使用 akshare 获取上证指数月度数据
    返回格式: [{"date": "2026-05-01", "sh_close": 4200.0}]
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare，请运行 pip install akshare")
        return None

    try:
        logger.info(f"akshare: 获取上证指数月度数据 (from {start_date})...")

        # 获取上证指数月K线
        df = ak.stock_zh_index_daily(symbol="sh000001")
        df = df.reset_index()
        df["date"] = pd.to_datetime(df["date"])

        # 筛选起始日期
        start_dt = pd.to_datetime(start_date)
        df = df[df["date"] >= start_dt].copy()

        # 按月取最后一个交易日的收盘价
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month").last().reset_index()
        monthly["date"] = monthly["date"].dt.to_period("M").dt.to_timestamp()

        result = []
        for _, row in monthly.iterrows():
            result.append({
                "date": row["date"],
                "sh_close": row["close"],
            })

        logger.info(f"akshare: 获取到 {len(result)} 条月度指数数据")
        return result

    except Exception as e:
        logger.error(f"akshare 获取指数数据失败: {e}")
        return None


def fetch_manual_csv(path: Path) -> list[dict] | None:
    """
    从手动 CSV 文件读取数据
    格式要求: date,household_deposit,non_bank_deposit[,sh_close]
    """
    if not path.exists():
        return None

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        df["date"] = pd.to_datetime(df["date"])
        result = df.to_dict("records")
        logger.info(f"从手动 CSV 读取 {len(result)} 条数据: {path}")
        return result
    except Exception as e:
        logger.error(f"读取手动 CSV 失败: {e}")
        return None


# ============================================================
# 宏观指标抓取函数
# ============================================================

def fetch_macro_m2() -> list[dict] | None:
    """
    抓取 M2/M1/M0 货币供应量月度数据
    预测性：M2增速拐点领先股市6-12月，是信用周期的核心锚定指标
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取货币供应量(M2/M1/M0)...")
        df = ak.macro_china_money_supply()
        # 列名：月份, 货币和准货币(M2)-数量(亿元), 货币和准货币(M2)-同比增长, ...
        df = df.rename(columns={
            "月份": "date",
            "货币和准货币(M2)-数量(亿元)": "m2_amount",
            "货币和准货币(M2)-同比增长": "m2_yoy",
            "货币(M1)-数量(亿元)": "m1_amount",
            "货币(M1)-同比增长": "m1_yoy",
            "流通中的现金(M0)-数量(亿元)": "m0_amount",
            "流通中的现金(M0)-同比增长": "m0_yoy",
        })
        # 解析中文日期 "2008年03月份" → pd.Timestamp
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        cols = ["date", "m2_amount", "m1_amount", "m0_amount", "m2_yoy", "m1_yoy", "m0_yoy"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条 M2 数据 ({df['date'].min().strftime('%Y-%m')} ~ {df['date'].max().strftime('%Y-%m')})")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"M2 数据获取失败: {e}")
        return None


def fetch_macro_pmi() -> list[dict] | None:
    """
    抓取 PMI 采购经理指数月度数据
    预测性：PMI是景气先行指标，连续<50领先企业利润下滑1-2季度
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取 PMI 数据...")
        df = ak.macro_china_pmi()
        df = df.rename(columns={
            "月份": "date",
            "制造业-指数": "pmi_manufacturing",
            "非制造业-指数": "pmi_non_manufacturing",
        })
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        cols = ["date", "pmi_manufacturing", "pmi_non_manufacturing"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条 PMI 数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"PMI 数据获取失败: {e}")
        return None


def fetch_macro_electricity() -> list[dict] | None:
    """
    抓取全社会用电量月度数据
    预测性：二产用电增速是GDP的高频替代，领先工业利润1-2季度
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取全社会用电量数据...")
        df = ak.macro_china_society_electricity()
        df = df.rename(columns={
            "统计时间": "date",
            "全社会用电量同比": "electricity_total_yoy",
            "第二产业用电量同比": "electricity_industrial_yoy",
            "第三产业用电量同比": "electricity_tertiary_yoy",
            "城乡居民生活用电量合计同比": "electricity_residential_yoy",
        })
        # 日期格式 "2026.4" → pd.Timestamp
        df["date"] = pd.to_datetime(df["date"].str.replace(".", "-", regex=False) + "-01")
        cols = ["date", "electricity_total_yoy", "electricity_industrial_yoy",
                "electricity_tertiary_yoy", "electricity_residential_yoy"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        # 去重（可能同月有多条累计记录，取最后一条）
        df = df.drop_duplicates(subset=["date"], keep="last")
        logger.info(f"获取到 {len(df)} 条用电量数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"用电量数据获取失败: {e}")
        return None


def fetch_macro_margin() -> list[dict] | None:
    """
    抓取两融余额日度数据，聚合为月度
    预测性：散户杠杆度量，两融增速见顶前1-2月股市往往见顶
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取两融余额数据（日度→月度聚合）...")
        df = ak.macro_china_market_margin_sh()
        df = df.rename(columns={"日期": "date", "融资融券余额": "margin_balance"})
        df["date"] = pd.to_datetime(df["date"])
        df["margin_balance"] = pd.to_numeric(df["margin_balance"], errors="coerce")

        # 按月聚合：取月末最后一个交易日的余额
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month").last().reset_index()
        monthly["date"] = monthly["date"].dt.to_period("M").dt.to_timestamp()

        # margin_balance 单位从元转为亿元（÷1e8）
        monthly["margin_balance"] = monthly["margin_balance"] / 1e8

        # 计算同比变化率
        monthly["margin_yoy"] = monthly["margin_balance"].pct_change(periods=12) * 100

        cols = ["date", "margin_balance", "margin_yoy"]
        monthly = monthly[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(monthly)} 条两融月度数据")
        return monthly.to_dict("records")
    except Exception as e:
        logger.error(f"两融数据获取失败: {e}")
        return None


def fetch_macro_shibor() -> list[dict] | None:
    """
    抓取 SHIBOR 隔夜/1周利率日度数据，聚合为月度均值
    预测性：资金面紧张时市场承压，SHIBOR飙升是短期风险信号
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取 SHIBOR 数据（日度→月度聚合）...")
        df = ak.macro_china_shibor_all()
        df = df.rename(columns={"日期": "date", "O/N-定价": "shibor_on", "1W-定价": "shibor_1w"})
        df["date"] = pd.to_datetime(df["date"])
        df["shibor_on"] = pd.to_numeric(df["shibor_on"], errors="coerce")
        df["shibor_1w"] = pd.to_numeric(df["shibor_1w"], errors="coerce")

        # 按月聚合均值
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month").agg(
            date=("date", "last"),
            shibor_on_avg=("shibor_on", "mean"),
            shibor_1w_avg=("shibor_1w", "mean"),
        ).reset_index()
        monthly["date"] = monthly["date"].dt.to_period("M").dt.to_timestamp()

        cols = ["date", "shibor_on_avg", "shibor_1w_avg"]
        monthly = monthly[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(monthly)} 条 SHIBOR 月度数据")
        return monthly.to_dict("records")
    except Exception as e:
        logger.error(f"SHIBOR 数据获取失败: {e}")
        return None


def fetch_macro_lpr() -> list[dict] | None:
    """
    抓取 LPR 报价利率日度数据，聚合为月度（取月末值）
    预测性：LPR连续下调对应宽松周期，利好股市估值
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取 LPR 数据（日度→月度）...")
        df = ak.macro_china_lpr()
        df = df.rename(columns={
            "TRADE_DATE": "date",
            "LPR1Y": "lpr_1y",
            "LPR5Y": "lpr_5y",
        })
        df["date"] = pd.to_datetime(df["date"])
        df["lpr_1y"] = pd.to_numeric(df["lpr_1y"], errors="coerce")
        df["lpr_5y"] = pd.to_numeric(df["lpr_5y"], errors="coerce")

        # 按月聚合：取月末最后一个报价
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month").last().reset_index()
        monthly["date"] = monthly["date"].dt.to_period("M").dt.to_timestamp()

        cols = ["date", "lpr_1y", "lpr_5y"]
        monthly = monthly[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        # 去重
        monthly = monthly.drop_duplicates(subset=["date"], keep="last")
        logger.info(f"获取到 {len(monthly)} 条 LPR 月度数据")
        return monthly.to_dict("records")
    except Exception as e:
        logger.error(f"LPR 数据获取失败: {e}")
        return None


def fetch_macro_cpi() -> list[dict] | None:
    """
    抓取 CPI 月度数据
    预测性：通缩(CPI<1%)压制企业盈利，CPI-PPI剪刀差影响利润传导
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取 CPI 数据...")
        df = ak.macro_china_cpi()
        df = df.rename(columns={
            "月份": "date",
            "全国-同比增长": "cpi_yoy",
            "全国-环比增长": "cpi_mom",
        })
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        cols = ["date", "cpi_yoy", "cpi_mom"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条 CPI 数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"CPI 数据获取失败: {e}")
        return None


def fetch_macro_ppi() -> list[dict] | None:
    """
    抓取 PPI 月度数据
    预测性：PPI转正领先上游周期股行情1-2月，CPI-PPI剪刀差影响板块利润分配
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取 PPI 数据...")
        df = ak.macro_china_ppi()
        df = df.rename(columns={
            "月份": "date",
            "当月同比增长": "ppi_yoy",
        })
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        cols = ["date", "ppi_yoy"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条 PPI 数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"PPI 数据获取失败: {e}")
        return None


def fetch_macro_northbound() -> list[dict] | None:
    """
    抓取北向资金日度数据，聚合为月度净买入额
    预测性：外资风向标，持续净流出预示外资撤退，领先或同步于指数下跌
    注意：akshare接口自2024.08后部分数据缺失，尽力获取
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取北向资金数据（日度→月度聚合）...")
        df = ak.stock_hsgt_hist_em(symbol="北向资金")
        df = df.rename(columns={
            "日期": "date",
            "当日成交净买额": "net_buy",
        })
        df["date"] = pd.to_datetime(df["date"])
        df["net_buy"] = pd.to_numeric(df["net_buy"], errors="coerce")

        # 按月聚合：月度净买入 = 当月每日净买入之和
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month").agg(
            date=("date", "last"),
            northbound_net_buy=("net_buy", "sum"),
        ).reset_index()
        monthly["date"] = monthly["date"].dt.to_period("M").dt.to_timestamp()

        cols = ["date", "northbound_net_buy"]
        monthly = monthly[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(monthly)} 条北向资金月度数据（注意：2024.08后数据可能缺失）")
        return monthly.to_dict("records")
    except Exception as e:
        logger.error(f"北向资金数据获取失败: {e}")
        return None


# ============================================================
# 第三批宏观指标抓取函数
# ============================================================

def fetch_macro_bdi() -> list[dict] | None:
    """
    抓取 BDI 波罗的海干散货指数日频数据，聚合为月度均值
    预测性：全球需求同步指标(r=+0.36)，BDI极端值反转对应市场拐点
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取 BDI 干散货指数（日频→月度聚合）...")
        df = ak.macro_china_freight_index()
        df = df.rename(columns={
            "截止日期": "date",
            "波罗的海综合运价指数BDI": "bdi_value",
        })
        df["date"] = pd.to_datetime(df["date"])
        df["bdi_value"] = pd.to_numeric(df["bdi_value"], errors="coerce")

        # 按月聚合均值
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month").agg(
            date=("date", "last"),
            bdi_value=("bdi_value", "mean"),
        ).reset_index()
        monthly["date"] = monthly["date"].dt.to_period("M").dt.to_timestamp()

        # 计算 YoY
        monthly["bdi_yoy"] = monthly["bdi_value"].pct_change(periods=12) * 100

        cols = ["date", "bdi_value", "bdi_yoy"]
        monthly = monthly[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(monthly)} 条 BDI 月度数据")
        return monthly.to_dict("records")
    except Exception as e:
        logger.error(f"BDI 数据获取失败: {e}")
        return None


def fetch_macro_retail() -> list[dict] | None:
    """
    抓取社会消费品零售总额月度数据
    预测性：领先上证10月(r=-0.50)，A股"政策市"反向指标
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取社消零售总额数据...")
        df = ak.macro_china_consumer_goods_retail()
        df = df.rename(columns={
            "月份": "date",
            "同比增长": "retail_yoy",
        })
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        df["retail_yoy"] = pd.to_numeric(df["retail_yoy"], errors="coerce")

        cols = ["date", "retail_yoy"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条社消零售数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"社消零售数据获取失败: {e}")
        return None


def fetch_macro_fiscal() -> list[dict] | None:
    """
    抓取财政收入月度数据
    预测性：领先上证10月(r=-0.37)，财政下行→政策宽松预期
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取财政收入数据...")
        df = ak.macro_china_czsr()
        df = df.rename(columns={
            "月份": "date",
            "当月-同比增长": "fiscal_yoy",
        })
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        df["fiscal_yoy"] = pd.to_numeric(df["fiscal_yoy"], errors="coerce")

        cols = ["date", "fiscal_yoy"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条财政收入数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"财政收入数据获取失败: {e}")
        return None


# ============================================================
# 宏观指标批量抓取入口
# ============================================================

MACRO_FETCHERS = {
    "m2": ("M2货币供应量", fetch_macro_m2),
    "pmi": ("PMI采购经理指数", fetch_macro_pmi),
    "electricity": ("全社会用电量", fetch_macro_electricity),
    "margin": ("两融余额", fetch_macro_margin),
    "shibor": ("SHIBOR利率", fetch_macro_shibor),
    "lpr": ("LPR利率", fetch_macro_lpr),
    "cpi": ("CPI居民消费价格", fetch_macro_cpi),
    "ppi": ("PPI工业生产者价格", fetch_macro_ppi),
    "northbound": ("北向资金", fetch_macro_northbound),
    # 第三批宏观指标
    "bdi": ("BDI干散货指数", fetch_macro_bdi),
    "retail": ("社消零售总额", fetch_macro_retail),
    "fiscal": ("财政收入", fetch_macro_fiscal),
}
