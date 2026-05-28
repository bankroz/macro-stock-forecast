# -*- coding: utf-8 -*-
"""
数据爬虫模块
- akshare macro_rmb_deposit 自动抓取居民存款（7天缓存）
- 非银金融机构存款需从央行Excel手动补充
- akshare 获取上证指数（主）
- 手动 CSV 补充为备用
"""

import pandas as pd
import numpy as np
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def fetch_pbc_deposits() -> list[dict] | None:
    """
    从 akshare 自动抓取最新存款数据
    - 居民存款：akshare macro_rmb_deposit（储蓄存款余额，亿元→万亿），自动更新
    - 非银存款：央行报告增量与存量口径不一致，暂不自动更新（需手动从央行Excel提取）

    返回格式: [{"date": "2026-05-01", "household_deposit": 175.0, "non_bank_deposit": NaN}]
    返回 None 表示无新数据
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare，请运行 pip install akshare")
        return None

    # --- 1. 从 macro_rmb_deposit 获取居民存款余额 ---
    logger.info("akshare: 获取人民币存款数据(居民存款余额)...")
    try:
        df = ak.macro_rmb_deposit()
        if df.empty:
            logger.warning("macro_rmb_deposit 返回空数据")
            return None
    except Exception as e:
        logger.error(f"macro_rmb_deposit 获取失败: {e}")
        return None

    # 解析月份格式 "2026-04" → "2026-04-01"
    df["date"] = pd.to_datetime(df["月份"] + "-01")

    # --- 2. 读取现有 deposits.csv ---
    deposits_path = Path(__file__).resolve().parent.parent / "data" / "deposits.csv"
    if not deposits_path.exists():
        logger.warning("deposits.csv 不存在，无法增量更新")
        return None

    existing = pd.read_csv(deposits_path, encoding="utf-8-sig")
    existing["date"] = pd.to_datetime(existing["date"])
    last_date = existing["date"].max()
    last_household = existing.loc[existing["date"] == last_date, "household_deposit"].values[0]
    logger.info(f"现有存款数据截止: {last_date.strftime('%Y-%m')}, 住户={last_household:.2f}万亿")

    # --- 3. 找出新月份 ---
    new_months = df[df["date"] > last_date].copy()
    if new_months.empty:
        logger.info("居民存款数据已是最新，无需更新")
        return None

    logger.info(f"发现 {len(new_months)} 个月的新居民存款数据")

    # --- 4. 生成新行（居民存款自动，非银存款留空需手动补充） ---
    new_rows = []
    for _, row in new_months.iterrows():
        month_date = row["date"]
        household = round(row["新增储蓄存款-数量"] / 10000, 2)  # 亿元→万亿
        logger.info(f"  {month_date.strftime('%Y-%m')}: 居民存款={household:.2f}万亿, 非银存款需手动补充")
        new_rows.append({
            "date": month_date,
            "household_deposit": household,
            "non_bank_deposit": np.nan,
        })

    logger.info(f"成功获取 {len(new_rows)} 条新居民存款数据（非银存款需从央行Excel手动补充）")
    return new_rows


def fetch_akshare_index(start_date: str = "20150101") -> list[dict] | None:
    """
    使用 akshare 获取上证指数月度数据（含成交量）
    返回格式: [{"date": "2026-05-01", "sh_close": 4200.0, "sh_volume": 6.5e10}]
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare，请运行 pip install akshare")
        return None

    try:
        logger.info(f"akshare: 获取上证指数月度数据含成交量 (from {start_date})...")

        # 获取上证指数月K线
        df = ak.stock_zh_index_daily(symbol="sh000001")
        df = df.reset_index()
        df["date"] = pd.to_datetime(df["date"])

        # 筛选起始日期
        start_dt = pd.to_datetime(start_date)
        df = df[df["date"] >= start_dt].copy()

        # 按月聚合：取月末收盘价 + 月度累计成交额
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month").agg(
            date=("date", "last"),
            sh_close=("close", "last"),
            sh_volume=("volume", "sum"),
        ).reset_index()
        monthly["date"] = monthly["date"].dt.to_period("M").dt.to_timestamp()

        result = []
        for _, row in monthly.iterrows():
            result.append({
                "date": row["date"],
                "sh_close": row["sh_close"],
                "sh_volume": row["sh_volume"],
            })

        logger.info(f"akshare: 获取到 {len(result)} 条月度指数数据(含成交量)")
        return result

    except Exception as e:
        logger.error(f"akshare 获取指数数据失败: {e}")
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
# 第四批冷门宏观指标抓取函数
# ============================================================

def fetch_macro_enterprise_boom() -> list[dict] | None:
    """
    抓取企业景气指数及企业家信心指数（季度）
    预测性：企业景气指数领先企业利润和投资决策1-2季度
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取企业景气指数...")
        df = ak.macro_china_enterprise_boom_index()
        df = df.rename(columns={
            "季度": "date",
            "企业景气指数-指数": "enterprise_boom_index",
            "企业家信心指数-指数": "entrepreneur_confidence_index",
        })
        # 日期格式 "2026年第1季度" → 该季度末月份
        def parse_quarter(q):
            m = re.search(r"(\d{4})年第(\d)", q)
            if not m:
                return pd.NaT
            year, qn = int(m.group(1)), int(m.group(2))
            month = qn * 3  # Q1→3月, Q2→6月, Q3→9月, Q4→12月
            return pd.Timestamp(year, month, 1)
        df["date"] = df["date"].apply(parse_quarter)
        cols = ["date", "enterprise_boom_index", "entrepreneur_confidence_index"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        # 数值转 float
        df["enterprise_boom_index"] = pd.to_numeric(df["enterprise_boom_index"], errors="coerce")
        df["entrepreneur_confidence_index"] = pd.to_numeric(df["entrepreneur_confidence_index"], errors="coerce")
        logger.info(f"获取到 {len(df)} 条企业景气指数数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"企业景气指数获取失败: {e}")
        return None


def fetch_macro_consumer_confidence() -> list[dict] | None:
    """
    抓取消费者信心指数（月度）
    预测性：消费者信心领先消费数据3-6个月，是可选消费板块的先行指标
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取消费者信心指数...")
        df = ak.macro_china_xfzxx()
        df = df.rename(columns={
            "月份": "date",
            "消费者信心指数-指数值": "confidence_index",
            "消费者满意指数-指数值": "satisfaction_index",
            "消费者预期指数-指数值": "expectation_index",
        })
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        cols = ["date", "confidence_index", "satisfaction_index", "expectation_index"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        df["confidence_index"] = pd.to_numeric(df["confidence_index"], errors="coerce")
        df["satisfaction_index"] = pd.to_numeric(df["satisfaction_index"], errors="coerce")
        df["expectation_index"] = pd.to_numeric(df["expectation_index"], errors="coerce")
        logger.info(f"获取到 {len(df)} 条消费者信心指数数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"消费者信心指数获取失败: {e}")
        return None


def fetch_macro_lpi() -> list[dict] | None:
    """
    抓取物流景气指数（月度）
    预测性：物流景气反映经济活动和贸易活跃度，与制造业PMI高度相关
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取物流景气指数...")
        df = ak.macro_china_lpi_index()
        df = df.rename(columns={
            "日期": "date",
            "最新值": "lpi_index",
        })
        df["date"] = pd.to_datetime(df["date"])
        df["lpi_index"] = pd.to_numeric(df["lpi_index"], errors="coerce")
        cols = ["date", "lpi_index"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条物流景气指数数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"物流景气指数获取失败: {e}")
        return None


def fetch_macro_real_estate() -> list[dict] | None:
    """
    抓取国房景气指数（月度）
    预测性：房地产是国民经济支柱，国房景气指数领先银行、建材、家电等板块
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取国房景气指数...")
        df = ak.macro_china_real_estate()
        df = df.rename(columns={
            "日期": "date",
            "最新值": "re_prosperity_index",
        })
        df["date"] = pd.to_datetime(df["date"])
        df["re_prosperity_index"] = pd.to_numeric(df["re_prosperity_index"], errors="coerce")
        cols = ["date", "re_prosperity_index"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条国房景气指数数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"国房景气指数获取失败: {e}")
        return None


def fetch_macro_unemployment() -> list[dict] | None:
    """
    抓取城镇调查失业率（月度）
    预测性：失业率是经济周期的滞后指标，但趋势拐点预示消费和政策的边际变化
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取城镇调查失业率...")
        df = ak.macro_china_urban_unemployment()
        # 筛选全国城镇调查失业率（注意尾部空格）
        df["item"] = df["item"].str.strip()
        df = df[df["item"] == "全国城镇调查失业率"].copy()
        df = df.rename(columns={"date": "date_raw", "value": "unemployment_rate"})
        # 日期格式 "201801" → pd.Timestamp
        df["date"] = pd.to_datetime(df["date_raw"].astype(str) + "01", format="%Y%m%d")
        df["unemployment_rate"] = pd.to_numeric(df["unemployment_rate"], errors="coerce")
        cols = ["date", "unemployment_rate"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条失业率数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"失业率数据获取失败: {e}")
        return None


def fetch_macro_trade() -> list[dict] | None:
    """
    抓取海关进出口数据（月度）
    预测性：出口是外需直接反映，进口是内需反映，贸易差额影响GDP和汇率
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取海关进出口数据...")
        df = ak.macro_china_hgjck()
        df = df.rename(columns={
            "月份": "date",
            "当月出口额-同比增长": "export_yoy",
            "当月进口额-同比增长": "import_yoy",
            "当月出口额-金额": "export_amount",
            "当月进口额-金额": "import_amount",
        })
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        cols = ["date", "export_yoy", "import_yoy", "export_amount", "import_amount"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        for c in ["export_yoy", "import_yoy", "export_amount", "import_amount"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        logger.info(f"获取到 {len(df)} 条进出口数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"进出口数据获取失败: {e}")
        return None


def fetch_macro_industry() -> list[dict] | None:
    """
    抓取规模以上工业增加值同比增速（月度）
    预测性：工业增加值是工业板块盈利的直接基本面，领先工业企业利润1-2月
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取工业增加值增速...")
        df = ak.macro_china_industrial_production_yoy()
        # 金十格式：有发布日期和今值，需要提取今值作为该月数据
        df = df[["日期", "今值"]].copy()
        df = df.rename(columns={"日期": "pub_date", "今值": "industrial_production_yoy"})
        df["pub_date"] = pd.to_datetime(df["pub_date"])
        df["industrial_production_yoy"] = pd.to_numeric(df["industrial_production_yoy"], errors="coerce")
        # 用发布日期作为近似月份（金十数据发布日期≈数据月份）
        df["date"] = df["pub_date"].dt.to_period("M").dt.to_timestamp()
        cols = ["date", "industrial_production_yoy"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        # 去重
        df = df.drop_duplicates(subset=["date"], keep="first")
        logger.info(f"获取到 {len(df)} 条工业增加值数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"工业增加值数据获取失败: {e}")
        return None


def fetch_macro_fa_investment() -> list[dict] | None:
    """
    抓取城镇固定资产投资同比增速（月度）
    预测性：固定资产投资是资本开支和基建的领先指标，与建材/钢铁/机械板块高度相关
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取固定资产投资增速...")
        df = ak.macro_china_gdzctz()
        df = df.rename(columns={
            "月份": "date",
            "同比增长": "fa_investment_yoy",
        })
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        df["fa_investment_yoy"] = pd.to_numeric(df["fa_investment_yoy"], errors="coerce")
        cols = ["date", "fa_investment_yoy"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条固定资产投资数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"固定资产投资数据获取失败: {e}")
        return None


def fetch_macro_insurance() -> list[dict] | None:
    """
    抓取保险保费收入（月度）
    预测性：保险保费是居民风险偏好和财富水平的综合反映，金融板块的间接指标
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取保险保费收入...")
        df = ak.macro_china_insurance_income()
        # 东方财富格式：日期 + 最新值 + 涨跌幅系列
        df = df.rename(columns={"日期": "date", "最新值": "insurance_premium"})
        df["date"] = pd.to_datetime(df["date"])
        df["insurance_premium"] = pd.to_numeric(df["insurance_premium"], errors="coerce")
        # 按月聚合
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month").last().reset_index()
        monthly["date"] = monthly["date"].dt.to_period("M").dt.to_timestamp()
        # 计算同比
        monthly["insurance_premium_yoy"] = monthly["insurance_premium"].pct_change(periods=12) * 100
        cols = ["date", "insurance_premium_yoy"]
        monthly = monthly[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(monthly)} 条保险保费数据")
        return monthly.to_dict("records")
    except Exception as e:
        logger.error(f"保险保费数据获取失败: {e}")
        return None


def fetch_macro_enterprise_price() -> list[dict] | None:
    """
    抓取企业商品价格指数（月度）
    预测性：企业商品价格是PPI和CPI的中间环节，通胀传导的领先指标
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取企业商品价格指数...")
        df = ak.macro_china_qyspjg()
        df = df.rename(columns={
            "月份": "date",
            "总指数-同比增长": "enterprise_price_yoy",
            "总指数-指数值": "enterprise_price_index",
        })
        df["date"] = pd.to_datetime(
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df["date"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        df["enterprise_price_yoy"] = pd.to_numeric(df["enterprise_price_yoy"], errors="coerce")
        cols = ["date", "enterprise_price_yoy"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(df)} 条企业商品价格数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"企业商品价格数据获取失败: {e}")
        return None


def fetch_macro_gdp() -> list[dict] | None:
    """
    抓取GDP同比增速（季度）
    预测性：GDP是股市长期走势的基石，GDP增速拐点领先政策转向
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取GDP增速...")
        df = ak.macro_china_gdp_yearly()
        # 金十格式：有发布日期和今值
        df = df[["日期", "今值"]].copy()
        df = df.rename(columns={"日期": "pub_date", "今值": "gdp_yoy"})
        df["pub_date"] = pd.to_datetime(df["pub_date"])
        df["gdp_yoy"] = pd.to_numeric(df["gdp_yoy"], errors="coerce")
        # 发布日期近似季度末
        df["date"] = df["pub_date"].dt.to_period("M").dt.to_timestamp()
        cols = ["date", "gdp_yoy"]
        df = df[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        df = df.drop_duplicates(subset=["date"], keep="first")
        logger.info(f"获取到 {len(df)} 条GDP数据")
        return df.to_dict("records")
    except Exception as e:
        logger.error(f"GDP数据获取失败: {e}")
        return None



# ============================================================
# 周度/日度数据聚合函数（先存起来，后续分析用）
# ============================================================

def fetch_vegetable_basket() -> list[dict] | None:
    """
    抓取菜篮子产品价格指数（日度），聚合为月度均值
    参考意义：食品通胀高频替代，领先 CPI 1-2 月
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None
    try:
        logger.info("akshare: 获取菜篮子价格指数（日度→月度聚合）...")
        df = ak.macro_china_vegetable_basket()
        df = df.rename(columns={"日期": "date", "最新值": "vegetable_basket_index"})
        df["date"] = pd.to_datetime(df["date"])
        df["vegetable_basket_index"] = pd.to_numeric(df["vegetable_basket_index"], errors="coerce")
        df = df.dropna(subset=["date", "vegetable_basket_index"])
        # 月度均值
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month")["vegetable_basket_index"].mean().reset_index()
        monthly["date"] = monthly["year_month"].dt.to_timestamp()
        # 计算同比（vs 去年同期均值）
        monthly = monthly.sort_values("date").reset_index(drop=True)
        monthly["vegetable_basket_yoy"] = monthly["vegetable_basket_index"].pct_change(periods=12) * 100
        cols = ["date", "vegetable_basket_yoy"]
        monthly = monthly[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(monthly)} 条菜篮子同比数据")
        return monthly.to_dict("records")
    except Exception as e:
        logger.error(f"菜篮子数据获取失败: {e}")
        return None


def fetch_commodity_price() -> list[dict] | None:
    """
    抓取大宗商品价格指数（日度），聚合为月度均值
    参考意义：PPI 高频领先指标，工业成本端压力
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None
    try:
        logger.info("akshare: 获取大宗商品价格指数（日度→月度聚合）...")
        df = ak.macro_china_commodity_price_index()
        df = df.rename(columns={"日期": "date", "最新值": "commodity_price_index"})
        df["date"] = pd.to_datetime(df["date"])
        df["commodity_price_index"] = pd.to_numeric(df["commodity_price_index"], errors="coerce")
        df = df.dropna(subset=["date", "commodity_price_index"])
        # 月度均值
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month")["commodity_price_index"].mean().reset_index()
        monthly["date"] = monthly["year_month"].dt.to_timestamp()
        monthly = monthly.sort_values("date").reset_index(drop=True)
        monthly["commodity_price_yoy"] = monthly["commodity_price_index"].pct_change(periods=12) * 100
        cols = ["date", "commodity_price_yoy"]
        monthly = monthly[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(monthly)} 条大宗商品价格同比数据")
        return monthly.to_dict("records")
    except Exception as e:
        logger.error(f"大宗商品价格数据获取失败: {e}")
        return None


# ============================================================
# 第五批：政策情绪指标（信贷脉冲）
# ============================================================

def fetch_macro_credit_impulse() -> list[dict] | None:
    """
    抓取新增金融信贷（社融替代）+ 新增人民币贷款
    预测性：信贷脉冲是政策宽松/收紧的同步指标，信贷扩张领先经济复苏6-12月
    主接口: macro_china_new_financial_credit (220条, 2008-2026)
    辅接口: macro_rmb_loan (约30条, 近年数据)
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取信贷脉冲数据（新增金融信贷+人民币贷款）...")

        # 主接口：新增金融信贷
        df_credit = ak.macro_china_new_financial_credit()
        df_credit = df_credit.rename(columns={
            "月份": "date_raw",
            "当月": "new_credit_amount",
            "当月-同比增长": "new_credit_yoy",
        })
        # 解析中文日期 "2026年04月份"
        df_credit["date"] = pd.to_datetime(
            df_credit["date_raw"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
            df_credit["date_raw"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
        )
        df_credit["new_credit_yoy"] = pd.to_numeric(df_credit["new_credit_yoy"], errors="coerce")
        credit_cols = ["date", "new_credit_yoy"]
        df_credit = df_credit[credit_cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

        # 辅接口：新增人民币贷款
        rmb_loan_data = {}
        try:
            df_loan = ak.macro_rmb_loan()
            df_loan = df_loan.rename(columns={
                "月份": "date_raw",
                "新增人民币贷款-同比": "rmb_loan_yoy",
            })
            df_loan["date"] = pd.to_datetime(
                df_loan["date_raw"].str.extract(r"(\d{4})年(\d{1,2})")[0] + "-" +
                df_loan["date_raw"].str.extract(r"(\d{4})年(\d{1,2})")[1] + "-01"
            )
            df_loan["rmb_loan_yoy"] = pd.to_numeric(df_loan["rmb_loan_yoy"], errors="coerce")
            for _, row in df_loan.iterrows():
                if pd.notna(row.get("rmb_loan_yoy")):
                    rmb_loan_data[row["date"]] = row["rmb_loan_yoy"]
            logger.info(f"获取到 {len(df_loan)} 条人民币贷款数据")
        except Exception as e:
            logger.warning(f"人民币贷款数据获取失败: {e}")

        # 合并 rmb_loan_yoy 到信贷数据
        if rmb_loan_data:
            df_credit["rmb_loan_yoy"] = df_credit["date"].map(rmb_loan_data)
        else:
            df_credit["rmb_loan_yoy"] = np.nan

        result = df_credit.to_dict("records")
        logger.info(f"获取到 {len(result)} 条信贷脉冲数据 ({df_credit['date'].min().strftime('%Y-%m')} ~ {df_credit['date'].max().strftime('%Y-%m')})")
        return result
    except Exception as e:
        logger.error(f"信贷脉冲数据获取失败: {e}")
        return None


# ============================================================
# 第六批：汇率指标（替代北向资金的外资风向标）
# ============================================================

def fetch_macro_usdcny() -> list[dict] | None:
    """
    抓取美元兑人民币汇率（中国银行中间价，日频），聚合为月度

    预测性：
    - USDCNY水平值滞后3月与上证3月收益 r=+0.45***（正相关：人民币贬值→利好出口→A股上涨）
    - 接口: currency_boc_safe() (中国银行, 从1994年起, 非常稳定)
    - 替代已失效的北向资金（2024-08后数据缺失）
    - 接口返回宽格式：日期 + 美元/欧元/日元等列，美元列值为100外币兑人民币

    逻辑：人民币贬值(USDCNY↑) → 出口竞争力↑ → 外资流入 → A股↑
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("缺少 akshare")
        return None

    try:
        logger.info("akshare: 获取美元兑人民币汇率（中国银行中间价，日频→月度聚合）...")
        df = ak.currency_boc_safe()
        # 宽格式: 列名为货币名, 值为100单位外币兑人民币
        # 需要取"美元"列, 值为100美元兑人民币, 除以100得到1美元兑人民币
        if "美元" not in df.columns:
            logger.error("USDCNY: 接口未返回'美元'列")
            return None

        df = df[["日期", "美元"]].copy()
        df = df.rename(columns={"日期": "date", "美元": "usdcny_mid"})
        df["date"] = pd.to_datetime(df["date"])
        df["usdcny_mid"] = pd.to_numeric(df["usdcny_mid"], errors="coerce")
        df = df.dropna(subset=["date", "usdcny_mid"])

        # 100美元兑人民币 → 1美元兑人民币
        df["usdcny_raw"] = df["usdcny_mid"] / 100.0

        # 按月聚合：月度均值
        df["year_month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("year_month").agg(
            date=("date", "last"),
            usdcny=("usdcny_raw", "mean"),
        ).reset_index()
        monthly["date"] = monthly["date"].dt.to_period("M").dt.to_timestamp()

        # 计算环比变化率(%)
        monthly["usdcny_mom"] = monthly["usdcny"].pct_change() * 100

        cols = ["date", "usdcny", "usdcny_mom"]
        monthly = monthly[cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        logger.info(f"获取到 {len(monthly)} 条 USDCNY 月度数据 ({monthly['date'].min().strftime('%Y-%m')} ~ {monthly['date'].max().strftime('%Y-%m')})")
        return monthly.to_dict("records")
    except Exception as e:
        logger.error(f"USDCNY 汇率数据获取失败: {e}")
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
    # 第四批冷门宏观指标
    "enterprise_boom": ("企业景气指数", fetch_macro_enterprise_boom),
    "consumer_confidence": ("消费者信心指数", fetch_macro_consumer_confidence),
    "lpi": ("物流景气指数", fetch_macro_lpi),
    "real_estate": ("国房景气指数", fetch_macro_real_estate),
    "unemployment": ("城镇调查失业率", fetch_macro_unemployment),
    "trade": ("海关进出口", fetch_macro_trade),
    "industry": ("工业增加值", fetch_macro_industry),
    "fa_investment": ("固定资产投资", fetch_macro_fa_investment),
    "insurance": ("保险保费收入", fetch_macro_insurance),
    "enterprise_price": ("企业商品价格指数", fetch_macro_enterprise_price),
    "gdp": ("GDP增速", fetch_macro_gdp),
    # 周度/日度聚合（先存，后续分析）
    "vegetable_basket": ("菜篮子价格指数", fetch_vegetable_basket),
    "commodity_price": ("大宗商品价格指数", fetch_commodity_price),
    # 第五批：政策情绪指标（信贷脉冲）
    "credit": ("信贷脉冲", fetch_macro_credit_impulse),
    # 第六批：汇率指标（替代北向资金）
    "usdcny": ("美元兑人民币汇率", fetch_macro_usdcny),
}
