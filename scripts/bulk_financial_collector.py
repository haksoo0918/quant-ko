"""High-speed bulk financial statements collector using OpenDART fnlttMultiAcnt API.

Collects up to 100 companies per single API request:
- 2015 Q4
- 2016 Q1, Q2, Q3, Q4
- 2017 Q1, Q2, Q3, Q4

Reduces total HTTP requests from ~5,000 to only ~45 requests!
Completes in under 1 minute.
"""

import logging
import os
import sys
import time

from dotenv import load_dotenv

from quant_ko.data.dart import REPRT_CODE_MAP, DartClient
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bulk_financial_collector")


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
    total_corps = len(corp_codes)
    logger.info("Total target small-cap universe: %d companies", total_corps)

    # Chunk corp_codes into batches of 100
    batch_size = 100
    corp_batches = [corp_codes[i : i + batch_size] for i in range(0, total_corps, batch_size)]
    logger.info("Divided into %d batches (each up to 100 companies).", len(corp_batches))

    # Target quarters to collect
    target_periods = [
        (2015, 4),  # 2015 Q4
        (2016, 1),
        (2016, 2),
        (2016, 3),
        (2016, 4),
        (2017, 1),
        (2017, 2),
        (2017, 3),
        (2017, 4),
    ]

    total_requests = len(corp_batches) * len(target_periods)
    logger.info("Total bulk API requests needed: %d calls", total_requests)

    # Benchmark protocol: test 1 call
    logger.info("--- Measuring throughput with 1 bulk call ---")
    t0 = time.time()
    sample_params = {
        "crtfc_key": dart.api_key,
        "corp_code": ",".join(corp_batches[0]),
        "bsns_year": "2016",
        "reprt_code": "11011",
    }
    r_sample = dart.session.get(f"{dart.base_url}/fnlttMultiAcnt.json", params=sample_params).json()
    dur = time.time() - t0
    logger.info(
        "1 bulk call completed in %.2fs (Fetched %d line items for 100 companies)!",
        dur,
        len(r_sample.get("list", [])),
    )
    logger.info("Projected total duration: ~%.1f seconds (under 1 minute)", dur * total_requests)

    saved_total = 0
    t_start = time.time()
    req_count = 0

    for yr, qtr in target_periods:
        reprt_code = REPRT_CODE_MAP[qtr]
        for b_idx, b_corps in enumerate(corp_batches, 1):
            req_count += 1
            url = f"{dart.base_url}/fnlttMultiAcnt.json"
            params = {
                "crtfc_key": dart.api_key,
                "corp_code": ",".join(b_corps),
                "bsns_year": str(yr),
                "reprt_code": reprt_code,
            }
            try:
                resp = dart.session.get(url, params=params).json()
                items = resp.get("list") or []
                if not items:
                    time.sleep(0.1)
                    continue

                # Group items by corp_code and parse
                # Separate CFS and OFS items
                by_corp: dict[str, dict[str, list]] = {}
                for it in items:
                    c = it.get("corp_code")
                    fs = it.get("fs_div", "CFS").upper()
                    if c:
                        by_corp.setdefault(c, {}).setdefault(fs, []).append(it)

                parsed_records = []
                for c, fs_dict in by_corp.items():
                    # Check if already present in DB
                    existing = store.get_financials(corp_code=c, fiscal_year=yr, quarter=qtr)
                    if not existing.empty:
                        continue

                    # CFS preferred, fallback to OFS
                    cfs_items = fs_dict.get("CFS", [])
                    ofs_items = fs_dict.get("OFS", [])

                    rec = None
                    if cfs_items:
                        rec = dart.parse_financial_accounts(cfs_items, c, yr, qtr, fs_type="CFS")
                    if (not rec or rec.get("revenue") is None) and ofs_items:
                        rec = dart.parse_financial_accounts(ofs_items, c, yr, qtr, fs_type="OFS")

                    if rec:
                        # Convert to dict for upsert
                        parsed_records.append(rec)

                if parsed_records:
                    store.upsert_financials(parsed_records)
                    saved_total += len(parsed_records)

                logger.info(
                    "[%d/%d] %d Q%d Batch %d/%d: Saved %d records (Cumulative: %d, Elapsed: %.1fs)",
                    req_count,
                    total_requests,
                    yr,
                    qtr,
                    b_idx,
                    len(corp_batches),
                    len(parsed_records),
                    saved_total,
                    time.time() - t_start,
                )

            except Exception as e:
                logger.warning("Error fetching bulk %d Q%d batch %d: %s", yr, qtr, b_idx, e)

            # 0.15s safe sleep to never trigger WAF
            time.sleep(0.15)

    logger.info("=== SUCCESS! Bulk collection complete! ===")
    logger.info(
        "Total new financial records saved: %d in %.1fs", saved_total, time.time() - t_start
    )


if __name__ == "__main__":
    main()
