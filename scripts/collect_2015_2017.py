"""Collect historical DART financial statements (2015~2017) and daily prices (2015~2017).

Extends backtest capability from 2019 back to 2016 (over 10.5 years).
Uses checkpointing: skips already collected items in SQLite.
"""

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
logger = logging.getLogger("collect_2015_2017")


def main():
    load_dotenv()
    api_key = os.getenv("OPENDART_API_KEY")
    if not api_key:
        logger.error("OPENDART_API_KEY not found in .env!")
        sys.exit(1)

    store = DataStore("data/quant_ko.db")
    dart = DartClient(api_key=api_key)
    # 0.05s delay to be safe and fast within DART limits
    collector = DataCollector(store=store, dart_client=dart, rate_limit_delay=0.05)

    # 1. Target companies (all current active target pool)
    fin_df = store.get_financials()
    corp_codes = sorted(set(fin_df["corp_code"].unique()))
    logger.info("대상 소형주 기업 수: %d개", len(corp_codes))

    # 2. DART 과거 재무제표 수집 (2015 - 2017년 3개년 분기/연간 실적)
    start_year = 2015
    end_year = 2017
    logger.info("1. DART 과거 재무제표 수집 시작 (%d - %d)...", start_year, end_year)
    saved_fin = collector.collect_financials(
        corp_codes=corp_codes,
        start_year=start_year,
        end_year=end_year,
    )
    logger.info("과거 DART 재무제표 %d건 저장 완료.", saved_fin)

    # 3. 일별 시세 수집 (2015-01-01 - 2017-12-31)
    logger.info("2. 과거 일별 시세 수집 시작 (2015-01-01 - 2017-12-31)...")
    comps = store.get_companies()
    target_comps = comps[comps["corp_code"].isin(corp_codes)]
    tickers = sorted(target_comps["ticker"].unique().tolist())

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
        start_date="2015-01-01",
        end_date="2017-12-31",
        price_source_fn=fetch_fdr_with_shares,
    )
    logger.info("과거 일별 시세 %d건 저장 완료.", saved_prices)

    # 4. 코스닥 벤치마크 지수(KQ11) 2015 - 2017 수집
    logger.info("3. 코스닥 벤치마크 지수(KQ11) 2015-2017 수집 중...")
    try:
        kq_df = fdr.DataReader("KQ11", "2015-01-01", "2026-10-08")
        kq_df[["Close"]].to_csv("data/kq11_daily.csv")
        logger.info("Updated data/kq11_daily.csv from 2015 to 2026 (%d rows)", len(kq_df))
    except Exception as e:
        logger.warning("Error updating KQ11 daily prices: %s", e)

    logger.info("2015-2017 과거 데이터 수집 완료! 백테스트 가능 기간이 2016년으로 확장되었습니다.")


if __name__ == "__main__":
    main()
