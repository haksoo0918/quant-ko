"""Collect historical DART financial statements (2018~2021) and daily prices (2018~2021)."""

import logging
import os
import sys

import FinanceDataReader as fdr
import pandas as pd
from dotenv import load_dotenv

from quant_ko.data.collector import DataCollector
from quant_ko.data.dart import DartClient
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("collect_historical")


def main():
    load_dotenv()
    api_key = os.getenv("OPENDART_API_KEY")
    if not api_key:
        logger.error("OPENDART_API_KEY not found in .env!")
        sys.exit(1)

    store = DataStore("data/quant_ko.db")
    dart = DartClient(api_key=api_key)
    # Using 0.05s delay to safely stay within API throughput limits
    collector = DataCollector(store=store, dart_client=dart, rate_limit_delay=0.05)

    fin_df = store.get_financials()
    corp_codes = list(set(fin_df["corp_code"].unique()))
    logger.info("대상 소형주 기업 수: %d개", len(corp_codes))

    # 1. DART 재무제표 수집 (2018 - 2021년 4개년 분기/연간 실적)
    start_year = 2018
    end_year = 2021
    logger.info("1. DART 과거 재무제표 수집 시작 (%d - %d)...", start_year, end_year)
    saved_fin = collector.collect_financials(
        corp_codes=corp_codes,
        start_year=start_year,
        end_year=end_year,
    )
    logger.info("과거 DART 재무제표 %d건 저장 완료.", saved_fin)

    # 2. 일별 시세 수집 (2018-01-01 - 2021-12-31)
    logger.info("2. 과거 일별 시세 수집 시작 (2018-01-01 - 2021-12-31)...")
    comps = store.get_companies()
    target_comps = comps[comps["corp_code"].isin(corp_codes)]
    tickers = target_comps["ticker"].tolist()

    listing = fdr.StockListing("KRX")
    shares_map = {}
    for _, row in listing.iterrows():
        code = str(row["Code"]).strip()
        stocks = float(row.get("Stocks") or 0)
        if stocks > 0:
            shares_map[code] = stocks

    def fetch_fdr_with_shares(ticker: str, s_date: str, e_date: str) -> pd.DataFrame:
        df = fdr.DataReader(ticker, s_date, e_date)
        if df is not None and not df.empty:
            sh = shares_map.get(ticker, 0.0)
            if "Close" in df.columns:
                df["MarketCap"] = df["Close"] * sh
                df["Amount"] = df["Close"] * df["Volume"]
        return df

    saved_prices = collector.collect_daily_prices(
        tickers=tickers,
        start_date="2018-01-01",
        end_date="2021-12-31",
        price_source_fn=fetch_fdr_with_shares,
    )
    logger.info("과거 일별 시세 %d건 저장 완료.", saved_prices)

    # 3. 코스닥 벤치마크 지수(KQ11) 2018 - 2021 수집
    logger.info("3. 코스닥 벤치마크 지수(KQ11) 과거 데이터 수집 중...")
    collector.collect_benchmark_prices(
        benchmark_ticker="KQ11",
        start_date="2018-01-01",
        end_date="2021-12-31",
    )
    logger.info("과거 데이터 수집 완료! DB 업데이트 완료.")


if __name__ == "__main__":
    main()
