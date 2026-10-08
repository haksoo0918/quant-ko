"""Collect 2025~2026 financials and prices up to current date."""

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
logger = logging.getLogger("collect_latest")

def main():
    load_dotenv()
    api_key = os.getenv("OPENDART_API_KEY")
    if not api_key:
        logger.error("OPENDART_API_KEY not found in .env!")
        sys.exit(1)

    store = DataStore("data/quant_ko.db")
    dart = DartClient(api_key=api_key)
    collector = DataCollector(store=store, dart_client=dart, rate_limit_delay=0.05)

    # Identify corp_codes in existing target pool
    fin_df = store.get_financials()
    corp_codes = list(set(fin_df["corp_code"].unique()))
    logger.info("Target pool company count: %d", len(corp_codes))

    # 1. Collect 2025 (Q1~Q4) and 2026 (Q1~Q2)
    logger.info("1. Collecting 2025~2026 DART financial statements...")
    saved_fin = collector.collect_financials(
        corp_codes=corp_codes,
        start_year=2025,
        end_year=2026,
    )
    logger.info("Saved %d new financial statement records.", saved_fin)

    # 2. Collect prices for target companies up to current date (2025-01-01 ~ 2026-10-07)
    logger.info("2. Collecting daily prices up to 2026-10-07...")
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
        start_date="2025-01-01",
        end_date="2026-10-07",
        price_source_fn=fetch_fdr_with_shares,
    )
    logger.info("Saved %d new price records up to 2026-10-07.", saved_prices)

    # 3. Collect benchmark (KQ11) up to 2026-10-07
    collector.collect_benchmark_prices(
        benchmark_ticker="KQ11",
        start_date="2025-01-01",
        end_date="2026-10-07",
    )
    logger.info("Data collection up to 2026 complete!")

if __name__ == "__main__":
    main()
