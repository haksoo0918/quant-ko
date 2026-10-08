"""Quick data collection script for small-cap backtest."""

import os
import sys
import logging
import pandas as pd
import FinanceDataReader as fdr
from dotenv import load_dotenv

from quant_ko.data.store import DataStore
from quant_ko.data.collector import DataCollector
from quant_ko.data.dart import DartClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_quick_collection")

def main():
    load_dotenv()
    api_key = os.getenv("OPENDART_API_KEY")
    if not api_key:
        logger.error("OPENDART_API_KEY not found in .env!")
        sys.exit(1)

    os.makedirs("data", exist_ok=True)
    db_path = "data/quant_ko.db"
    store = DataStore(db_path)
    store.initialize_schema()

    dart = DartClient(api_key=api_key)
    collector = DataCollector(store=store, dart_client=dart, rate_limit_delay=0.1)

    logger.info("1. KRX 상장사 및 종목 메타데이터 수집 중...")
    comp_count = collector.collect_companies()
    logger.info("총 %d개 종목 메타데이터 적재 완료.", comp_count)

    logger.info("2. 최신 시총 기준 2021~2024 가격 및 시총 정보 업데이트...")
    listing = fdr.StockListing("KRX")
    today_str = pd.Timestamp.now().strftime("%Y-%m-%d")
    price_records = []
    for _, row in listing.iterrows():
        code = str(row["Code"]).strip()
        close = float(row.get("Close") or 0)
        marcap = float(row.get("Marcap") or 0)
        amt = float(row.get("Amount") or 0)
        if close > 0 and marcap > 0:
            price_records.append({
                "ticker": code,
                "date": today_str,
                "close": close,
                "market_cap": marcap,
                "trading_value": amt,
            })
    store.upsert_daily_prices(price_records)

    logger.info("3. 코스피/코스닥 시가총액 하위 20%% 소형주 풀 추출 중...")
    pool = collector.identify_small_cap_pool(quantile=0.20)
    logger.info("추출된 순수 소형주 후보: %d개 종목", len(pool))

    # Get corp_codes for pool
    comps_df = store.get_companies()
    pool_comps = comps_df[comps_df["ticker"].isin(pool)]
    corp_codes = [c for c in pool_comps["corp_code"].dropna().tolist() if c]
    logger.info("DART 고유번호 매핑 완료된 소형주: %d개", len(corp_codes))

    # Collect sample for backtesting: take top 100 small caps by liquidity/size
    logger.info("4. 소형주 2022~2024 DART 재무제표 수집 시작...")
    # Target years: 2022, 2023, 2024
    saved_fin = collector.collect_financials(
        corp_codes=corp_codes,
        start_year=2022,
        end_year=2024,
    )
    logger.info("DART 재무제표 수집 완료: 총 %d건 저장.", saved_fin)

    logger.info("5. 코스닥 벤치마크 지수(KQ11) 과거 일별 시세 수집 중...")
    collector.collect_benchmark_prices(
        benchmark_ticker="KQ11",
        start_date="2022-01-01",
        end_date="2024-12-31",
    )
    logger.info("데이터 수집 완료! DB 위치: %s", db_path)

if __name__ == "__main__":
    main()
