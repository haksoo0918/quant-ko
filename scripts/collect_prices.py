"""Collect historical daily prices for target small-cap stocks."""

import logging
import pandas as pd
import FinanceDataReader as fdr
from quant_ko.data.store import DataStore
from quant_ko.data.collector import DataCollector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("collect_prices")

def main():
    store = DataStore("data/quant_ko.db")
    collector = DataCollector(store=store, rate_limit_delay=0.01)

    # Get tickers of companies with financials
    comps = store.get_companies()
    fin_df = store.get_financials()
    corp_codes = set(fin_df["corp_code"].unique())
    target_comps = comps[comps["corp_code"].isin(corp_codes)]
    tickers = target_comps["ticker"].tolist()
    logger.info("Found %d companies with financial statements to fetch prices.", len(tickers))

    start_date = "2022-01-01"
    end_date = "2024-12-31"

    # Pre-fetch listed shares to compute market cap
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

    logger.info("Starting historical price collection (%s ~ %s)...", start_date, end_date)
    saved = collector.collect_daily_prices(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        price_source_fn=fetch_fdr_with_shares,
    )
    logger.info("Finished collecting historical prices. Total rows saved: %d", saved)

if __name__ == "__main__":
    main()
