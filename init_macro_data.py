# -*- coding: utf-8 -*-
"""
宏观指标数据初始化脚本（一次性运行）
批量拉取所有宏观指标的历史数据并写入 CSV
"""

import sys
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.scraper import MACRO_FETCHERS
from src.data_manager import update_macro, load_macro

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("宏观指标数据初始化 — 批量拉取历史数据")
    logger.info("=" * 60)

    results = {}

    for name, (label, fetcher) in MACRO_FETCHERS.items():
        logger.info(f"\n--- 拉取: {label} ({name}) ---")
        try:
            data = fetcher()
            if data and len(data) > 0:
                update_macro(name, data)
                # 验证
                df = load_macro(name)
                results[name] = {"label": label, "rows": len(df), "status": "OK"}
                logger.info(f"  ✅ {label}: {len(df)} 条数据已写入")
            else:
                results[name] = {"label": label, "rows": 0, "status": "无数据"}
                logger.warning(f"  ⚠️ {label}: 未获取到数据")
        except Exception as e:
            results[name] = {"label": label, "rows": 0, "status": f"失败: {e}"}
            logger.error(f"  ❌ {label}: {e}")

    # 汇总
    logger.info("\n" + "=" * 60)
    logger.info("初始化汇总")
    logger.info("=" * 60)
    for name, r in results.items():
        status_icon = "✅" if r["status"] == "OK" else "⚠️"
        logger.info(f"  {status_icon} {r['label']}: {r['rows']} 条 ({r['status']})")

    logger.info("\n初始化完成！请运行 python run.py --no-fetch 验证全流程")


if __name__ == "__main__":
    main()
