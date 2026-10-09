"""Collect all historical daily prices (2015-01-01 to 2017-12-31) for target universe.

Uses FinanceDataReader with KRX share count mapping to populate:
- close, volume, trading_value, market_cap
Checkpoints per batch and skips already collected tickers.
"""

import logging
import time
import FinanceDataReader as fdr
import pandas as pd
from quant_ko.data.store import DataStore
from quant_ko.data.krx import clean_price_val

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("collect_prices_2015_2017")

START_DATE = "2015-01-01"
END_DATE = "2017-12-31"

def main():
    store = DataStore("data/quant_ko.db")

    # 1. Identify all target tickers
    fin_df = store.get_financials()
    corp_codes = list(set(fin_df["corp_code"].unique()))
    comps = store.get_companies()
    target_comps = comps[comps["corp_code"].isin(corp_codes)]
    tickers = sorted(target_comps["ticker"].unique().tolist())
    total_tickers = len(tickers)
    logger.info("Total target universe tickers: %d", total_tickers)

    # 2. Map shares for market cap
    listing = fdr.StockListing("KRX")
    shares_map = dict(zip(listing["Code"], listing["Stocks"].astype(float), strict=False))

    # 3. Check existing and filter needed tickers
    needed_tickers = []
    for t in tickers:
        existing = store.get_daily_prices(ticker=t, start_date=START_DATE, end_date=END_DATE)
        if existing.empty or len(existing) < 600:
            needed_tickers.append(t)

    logger.info("Tickers needing price collection for 2015-2017: %d / %d", len(needed_tickers), total_tickers)
    if not needed_tickers:
        logger.info("All 2015-2017 prices already collected!")
        return

    # Benchmark protocol: sample 10 tickers
    logger.info("Measuring throughput on 10 sample tickers...")
    t0 = time.time()
    for t in needed_tickers[:10]:
        try:
            fdr.DataReader(t, START_DATE, END_DATE)
        except Exception:
            pass
    dur = time.time() - t0
    rate = 10.0 / max(dur, 0.001)
    eta_sec = len(needed_tickers) / rate
    logger.info("Benchmark complete: 10 tickers in %.2fs (%.2f tickers/sec). ETA: ~%.1f minutes", dur, rate, eta_sec / 60.0)

    # Run collection with batch saving
    saved_total = 0
    batch_records = []
    t_start = time.time()

    for idx, ticker in enumerate(needed_tickers, 1):
        try:
            df = fdr.DataReader(ticker, START_DATE, END_DATE)
            if df is not None and not df.empty:
                sh = shares_map.get(ticker, 0.0)
                for dt, row in df.iterrows():
                    close = clean_price_val(row.get("Close"))
                    volume = clean_price_val(row.get("Volume"))
                    tv = clean_price_val(row.get("Amount", volume * close))
                    mcap = close * sh if sh > 0 else 0.0
                    batch_records.append({
                        "ticker": ticker,
                        "date": pd.to_datetime(dt).strftime("%Y-%m-%d"),
                        "close": close,
                        "market_cap": mcap,
                        "trading_value": tv,
                    })

            if len(batch_records) >= 5000:
                store.upsert_daily_prices(batch_records)
                saved_total += len(batch_records)
                elapsed = time.time() - t_start
                logger.info("[%d/%d] Saved %d price records (Total: %d, Elapsed: %.1fs)...", idx, len(needed_tickers), len(batch_records), saved_total, elapsed)
                batch_records = []

        except Exception as e:
            logger.warning("Error fetching %s: %s", ticker, e)

    if batch_records:
        store.upsert_daily_prices(batch_records)
        saved_total += len(batch_records)
        logger.info("Saved final batch of %d price records.", len(batch_records))

    # Also update KQ11 daily prices for 2015-2026
    try:
        kq_df = fdr.DataReader("KQ11", START_DATE, "2026-10-08")
        kq_df[["Close"]].to_csv("data/kq11_daily.csv")
        logger.info("Updated data/kq11_daily.csv (%d rows)", len(kq_df))
    except Exception as e:
        logger.warning("Error updating KQ11: %s", e)

    logger.info("Price collection complete! Total saved: %d records.", saved_total)

if __name__ == "__main__":
    main()
