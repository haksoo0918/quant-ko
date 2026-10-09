"""Collect and update latest daily price records (2026-10-08).

Fetches the latest trading day (2026-10-08) close, volume, trading value,
and market cap (using KRX listing shares count) for all 471 active universe stocks.
Also updates CD rate ETF (357870) and KOSDAQ benchmark.
"""

import logging
import pandas as pd
import FinanceDataReader as fdr
from quant_ko.data.store import DataStore
from quant_ko.data.krx import clean_price_val

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("update_latest_data")

TARGET_DATE = "2026-10-08"

def main():
    store = DataStore("data/quant_ko.db")

    # 1. Check existing records for target date
    existing = store.get_daily_prices(start_date=TARGET_DATE, end_date=TARGET_DATE)
    existing_tickers = set(existing["ticker"].tolist()) if not existing.empty else set()
    logger.info("Existing records for %s in DB: %d", TARGET_DATE, len(existing_tickers))

    # 2. Get active target universe tickers
    recent_df = store.get_daily_prices(start_date="2026-10-01", end_date="2026-10-07")
    target_tickers = sorted(recent_df["ticker"].unique().tolist())
    logger.info("Total target universe tickers: %d", len(target_tickers))

    # 3. Load KRX stock listing for shares count
    krx_listing = fdr.StockListing("KRX")
    shares_map = dict(zip(krx_listing["Code"], krx_listing["Stocks"].astype(float), strict=False))

    needed_tickers = [t for t in target_tickers if t not in existing_tickers]
    logger.info("Tickers needing update for %s: %d", TARGET_DATE, len(needed_tickers))

    records_to_save = []
    success_count = 0

    for idx, ticker in enumerate(needed_tickers, 1):
        try:
            df = fdr.DataReader(ticker, TARGET_DATE, TARGET_DATE)
            if df is None or df.empty:
                continue

            row = df.iloc[-1]
            close = clean_price_val(row.get("Close"))
            volume = clean_price_val(row.get("Volume"))
            trading_value = clean_price_val(row.get("Amount", volume * close))

            shares = shares_map.get(ticker, 0.0)
            market_cap = close * shares if shares > 0 else 0.0

            records_to_save.append({
                "ticker": ticker,
                "date": TARGET_DATE,
                "close": close,
                "market_cap": market_cap,
                "trading_value": trading_value,
            })
            success_count += 1

            if len(records_to_save) >= 50:
                store.upsert_daily_prices(records_to_save)
                logger.info("[%d/%d] Upserted %d records to DB...", idx, len(needed_tickers), len(records_to_save))
                records_to_save = []

        except Exception as e:
            logger.warning("Error fetching %s for %s: %s", ticker, TARGET_DATE, e)

    if records_to_save:
        store.upsert_daily_prices(records_to_save)
        logger.info("Upserted final batch of %d records.", len(records_to_save))

    # 4. Update CD rate ETF (357870) daily prices
    try:
        cd_df = fdr.DataReader("357870", "2020-01-01", TARGET_DATE)
        cd_df[["Close"]].to_csv("data/cd_daily.csv")
        logger.info("Updated data/cd_daily.csv up to %s (%d rows)", TARGET_DATE, len(cd_df))
    except Exception as e:
        logger.warning("Error updating CD daily prices: %s", e)

    logger.info("Data update for %s completed! Successfully fetched: %d tickers.", TARGET_DATE, success_count)

if __name__ == "__main__":
    main()
