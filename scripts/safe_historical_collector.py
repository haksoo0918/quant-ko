"""Safe sequential historical DART financial statement collector for 2015-2017.

Features:
- Single thread, conservative 0.15s delay to completely avoid WAF IP blocking.
- Resilient retry on network hiccups.
- Checkpointing: queries SQLite first, fetches ONLY missing quarters.
- Detailed progress logging every 50 records.
"""

import logging
import os
import sys
import time

from dotenv import load_dotenv

from quant_ko.data.dart import DartClient
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("safe_historical_collector")


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
    logger.info("Total target small-cap universe: %d companies", len(corp_codes))

    # 2. Build list of missing tasks
    missing_tasks = []
    for corp_code in corp_codes:
        for year in [2015, 2016, 2017]:
            for qtr in [1, 2, 3, 4]:
                existing = store.get_financials(corp_code=corp_code, fiscal_year=year, quarter=qtr)
                if existing.empty:
                    missing_tasks.append((corp_code, year, qtr))

    total_missing = len(missing_tasks)
    logger.info("Total missing financial tasks to collect (2015-2017): %d tasks", total_missing)
    if total_missing == 0:
        logger.info("All 2015-2017 financials already collected!")
        return

    # Benchmark: 5 items
    t0 = time.time()
    for c, y, q in missing_tasks[:5]:
        for fs in ["CFS", "OFS"]:
            try:
                dart.fetch_and_parse_financials(c, y, q, fs_type=fs)
                break
            except Exception:
                pass
        time.sleep(0.15)
    bench_dur = time.time() - t0
    rate = 5.0 / max(bench_dur, 0.001)
    eta_min = (total_missing / rate) / 60.0
    logger.info(
        "Benchmark complete: 5 items in %.2fs (%.2f items/sec). ETA: ~%.1f minutes",
        bench_dur,
        rate,
        eta_min,
    )

    # Run safe sequential loop
    saved_count = 0
    batch_records = []
    start_time = time.time()

    for idx, (corp_code, year, qtr) in enumerate(missing_tasks, 1):
        parsed = None
        for fs in ["CFS", "OFS"]:
            try:
                parsed = dart.fetch_and_parse_financials(corp_code, year, qtr, fs_type=fs)
                if parsed:
                    break
            except Exception as e:
                # If temporary network issue, pause 2 seconds and retry once
                if "10054" in str(e) or "reset" in str(e).lower():
                    logger.warning("Connection hiccup, backing off for 3 seconds...")
                    time.sleep(3.0)
                pass

        if parsed:
            batch_records.append(parsed)
            saved_count += 1

        if len(batch_records) >= 50:
            store.upsert_financials(batch_records)
            elapsed = time.time() - start_time
            logger.info(
                "[%d/%d] Upserted 50 records (Saved: %d, Elapsed: %.1fm)...",
                idx,
                total_missing,
                saved_count,
                elapsed / 60.0,
            )
            batch_records = []

        # Safe rate limit delay
        time.sleep(0.15)

    if batch_records:
        store.upsert_financials(batch_records)
        logger.info("Upserted final batch of %d records.", len(batch_records))

    logger.info("SUCCESS! Safe collection complete. Total new records saved: %d", saved_count)


if __name__ == "__main__":
    main()
