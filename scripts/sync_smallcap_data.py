"""Sync full KRX latest market cap/price snapshot, missing small-cap DART financials,
and enrich missing gross_profit (매출총이익) via fnlttSinglAcntAll API for profitable small caps.

Stores all data into project database: data/quant_ko.db
"""

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

from quant_ko.data.dart import DartClient
from quant_ko.data.store import DataStore
from quant_ko.pit.builder import PITSnapshotBuilder

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_smallcap_data")


def parse_bulk_items(dart: DartClient, items: list[dict], year: int, quarter: int) -> list[dict]:
    """Group fnlttMultiAcnt items by (corp_code, fs_div) and parse into store records."""
    by_corp: dict[str, dict[str, list]] = {}
    for it in items:
        c = it.get("corp_code")
        fs = it.get("fs_div", "CFS").upper()
        if c:
            by_corp.setdefault(c, {}).setdefault(fs, []).append(it)

    parsed_records = []
    for c, fs_dict in by_corp.items():
        cfs_items = fs_dict.get("CFS", [])
        ofs_items = fs_dict.get("OFS", [])
        rec = None
        if cfs_items:
            rec = dart.parse_financial_accounts(cfs_items, c, year, quarter, fs_type="CFS")
        if (not rec or rec.get("revenue") is None) and ofs_items:
            rec = dart.parse_financial_accounts(ofs_items, c, year, quarter, fs_type="OFS")
        if rec:
            parsed_records.append(rec)
    return parsed_records


def main() -> None:
    load_dotenv()
    api_key = os.getenv("OPENDART_API_KEY") or os.getenv("DART_API_KEY")
    if not api_key:
        logger.error("OPENDART_API_KEY missing in .env")
        sys.exit(1)

    store = DataStore("data/quant_ko.db")
    dart = DartClient(api_key=api_key)
    from requests.adapters import HTTPAdapter
    dart.session.mount("https://", HTTPAdapter(pool_connections=15, pool_maxsize=15))

    # 1. Enrich missing gross_profit (매출총이익) for profitable small-cap companies (2025 Q1~Q4, 2026 Q1~Q2)
    builder = PITSnapshotBuilder(store)
    pit_df = builder.build_snapshot("20261023")
    prof_missing_gp = pit_df[
        (pit_df["op_income_ttm"] > 0)
        & (pit_df["net_income_owner_ttm"] > 0)
        & (pit_df["gross_profit_ttm"].isna())
    ]
    missing_gp_corps = sorted(set(prof_missing_gp["corp_code"].tolist()) | {"00109781"})  # + 대림제지
    logger.info(
        "Profitable small-cap corps missing gross_profit (매출총이익): %d corps",
        len(missing_gp_corps),
    )

    if missing_gp_corps:
        periods = [(2025, 1), (2025, 2), (2025, 3), (2025, 4), (2026, 1), (2026, 2)]
        single_tasks = [(c, yr, q) for c in missing_gp_corps for yr, q in periods]
        logger.info("Fetching %d detailed statements (fnlttSinglAcntAll) with 10 workers...", len(single_tasks))

        def fetch_single_gp(task: tuple[str, int, int]) -> dict | None:
            c_code, yr, q = task
            for fs in ("CFS", "OFS"):
                try:
                    rec = dart.fetch_and_parse_financials(c_code, yr, q, fs_type=fs)
                    if rec and rec.get("revenue") is not None:
                        return rec
                except Exception:
                    pass
            return None

        t0 = time.time()
        enriched_recs = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(fetch_single_gp, t): t for t in single_tasks}
            done_cnt = 0
            for fut in as_completed(futs):
                done_cnt += 1
                res = fut.result()
                if res:
                    enriched_recs.append(res)
                if done_cnt % 200 == 0 or done_cnt == len(single_tasks):
                    logger.info(
                        "Progress: %d/%d (%d records fetched in %.1fs)",
                        done_cnt,
                        len(single_tasks),
                        len(enriched_recs),
                        time.time() - t0,
                    )

        if enriched_recs:
            store.upsert_financials(enriched_recs)
            logger.info("Upserted %d detailed financial records with gross_profit into data/quant_ko.db!", len(enriched_recs))


if __name__ == "__main__":
    main()
