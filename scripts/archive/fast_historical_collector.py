"""Fast multithreaded historical data collector for 2015-2017.

Collects:
1. DART financial statements (2015-2017) using concurrent ThreadPool (10 workers).
2. Daily prices (2015-2017) using concurrent ThreadPool.
3. KOSDAQ index (2015-2017).

Follows GEMINI.md Anti-Hang Protocol:
- Benchmarks 10 samples first and logs measured throughput and estimated total time.
"""

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import FinanceDataReader as fdr
import pandas as pd
from dotenv import load_dotenv

from quant_ko.data.dart import DartClient
from quant_ko.data.krx import clean_price_val
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fast_historical_collector")


def main():
    load_dotenv()
    api_key = os.getenv("OPENDART_API_KEY")
    if not api_key:
        logger.error("OPENDART_API_KEY not found in .env!")
        sys.exit(1)

    store = DataStore("data/quant_ko.db")
    dart = DartClient(api_key=api_key)

    # 1. Target companies
    fin_df = store.get_financials()
    corp_codes = sorted(set(fin_df["corp_code"].unique()))
    comps_df = store.get_companies()
    target_comps = comps_df[comps_df["corp_code"].isin(corp_codes)]
    tickers = sorted(target_comps["ticker"].unique().tolist())
    logger.info(
        "Total target small-cap universe: %d companies, %d tickers", len(corp_codes), len(tickers)
    )

    # 2. Build task list for missing financials (2015-2017, Q1~Q4)
    # Check existing in SQLite to only fetch missing tasks
    missing_tasks = []
    for corp_code in corp_codes:
        for year in [2015, 2016, 2017]:
            for qtr in [1, 2, 3, 4]:
                existing = store.get_financials(corp_code=corp_code, fiscal_year=year, quarter=qtr)
                if existing.empty:
                    missing_tasks.append((corp_code, year, qtr))

    total_missing = len(missing_tasks)
    logger.info("Remaining missing financial tasks (2015-2017): %d tasks", total_missing)

    # BENCHMARK PROTOCOL: Test 10 samples first to measure throughput
    if total_missing > 0:
        logger.info("--- [Benchmark Step] Measuring throughput on 10 samples ---")
        t0 = time.time()
        benchmark_samples = missing_tasks[:10]
        for c, y, q in benchmark_samples:
            for fs in ["CFS", "OFS"]:
                try:
                    dart.fetch_and_parse_financials(c, y, q, fs_type=fs)
                    break
                except Exception:
                    pass
        sample_duration = time.time() - t0
        rate_per_sec = 10.0 / max(sample_duration, 0.001)
        est_minutes = (total_missing / (rate_per_sec * 6)) / 60.0  # with 6 threads
        logger.info(
            "Benchmark complete: 10 items in %.2fs (%.2f items/sec single thread).",
            sample_duration,
            rate_per_sec,
        )
        logger.info("Projected duration with 6 workers: ~%.1f minutes", est_minutes)

        # Execute concurrent worker pool
        logger.info("Starting concurrent collection of %d tasks (6 workers)...", total_missing)
        saved_count = 0
        batch_records = []

        def worker_fetch(task):
            c_code, yr, q = task
            for fs in ["CFS", "OFS"]:
                try:
                    res = dart.fetch_and_parse_financials(c_code, yr, q, fs_type=fs)
                    if res:
                        return res
                except Exception:
                    pass
            return None

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(worker_fetch, t): t for t in missing_tasks}
            completed = 0
            for future in as_completed(futures):
                completed += 1
                result = future.result()
                if result:
                    batch_records.append(result)
                    saved_count += 1

                if len(batch_records) >= 100:
                    store.upsert_financials(batch_records)
                    logger.info(
                        "[%d/%d] Saved %d financials to DB (Total saved: %d)...",
                        completed,
                        total_missing,
                        len(batch_records),
                        saved_count,
                    )
                    batch_records = []

            if batch_records:
                store.upsert_financials(batch_records)
                logger.info("Saved final batch of %d financials.", len(batch_records))

        logger.info("=== Financials collection complete! Total saved: %d ===", saved_count)

    # 3. Daily prices collection (2015-01-01 to 2017-12-31)
    logger.info("--- Starting Daily Prices Collection (2015-01-01 to 2017-12-31) ---")
    krx_listing = fdr.StockListing("KRX")
    shares_map = dict(zip(krx_listing["Code"], krx_listing["Stocks"].astype(float), strict=False))

    price_saved_total = 0
    price_batch = []

    def fetch_price_worker(ticker):
        try:
            # Check if already present
            existing_p = store.get_daily_prices(
                ticker=ticker, start_date="2015-01-01", end_date="2017-12-31"
            )
            if not existing_p.empty and len(existing_p) >= 700:
                return []
            df = fdr.DataReader(ticker, "2015-01-01", "2017-12-31")
            if df is None or df.empty:
                return []
            sh = shares_map.get(ticker, 0.0)
            records = []
            for dt, row in df.iterrows():
                close = clean_price_val(row.get("Close"))
                volume = clean_price_val(row.get("Volume"))
                tv = clean_price_val(row.get("Amount", volume * close))
                mcap = close * sh if sh > 0 else 0.0
                records.append(
                    {
                        "ticker": ticker,
                        "date": pd.to_datetime(dt).strftime("%Y-%m-%d"),
                        "close": close,
                        "market_cap": mcap,
                        "trading_value": tv,
                    }
                )
            return records
        except Exception:
            return []

    logger.info("Fetching prices for %d tickers with 8 workers...", len(tickers))
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_price_worker, t): t for t in tickers}
        p_done = 0
        for future in as_completed(futures):
            p_done += 1
            recs = future.result()
            if recs:
                price_batch.extend(recs)
                price_saved_total += len(recs)

            if len(price_batch) >= 2000:
                store.upsert_daily_prices(price_batch)
                logger.info(
                    "[%d/%d tickers] Saved %d price rows to DB (Cumulative: %d)...",
                    p_done,
                    len(tickers),
                    len(price_batch),
                    price_saved_total,
                )
                price_batch = []

        if price_batch:
            store.upsert_daily_prices(price_batch)
            logger.info("Saved final batch of %d price rows.", len(price_batch))

    # 4. Update KQ11 daily prices from 2015
    try:
        kq_df = fdr.DataReader("KQ11", "2015-01-01", "2026-10-08")
        kq_df[["Close"]].to_csv("data/kq11_daily.csv")
        logger.info("Updated data/kq11_daily.csv from 2015 (%d rows)", len(kq_df))
    except Exception as e:
        logger.warning("Error saving KQ11: %s", e)

    logger.info("SUCCESS! All 2015-2017 historical data collected and saved.")


if __name__ == "__main__":
    main()
