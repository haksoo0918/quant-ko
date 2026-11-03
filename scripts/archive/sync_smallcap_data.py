"""Sync 2015-2023 bulk DART financials and 2016-2026 daily prices for the expanded small-cap pool
(up to 525B KRW, covering Order B: Profitable-First Bottom 20%).

Follows GEMINI.md Anti-Hang Discipline:
- Benchmarks sample requests first to measure throughput and log ETA.
- Uses explicit request timeouts and progress logging.
- Stores all data into project database: data/quant_ko.db
"""

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import FinanceDataReader as fdr
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

from quant_ko.data.dart import REPRT_CODE_MAP, DartClient
from quant_ko.data.krx import (
    clean_price_val,
    is_chinese_company,
    is_holding_or_financial,
    is_preferred_stock,
    is_spac,
)
from quant_ko.data.store import DataStore

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
    dart.session.mount("https://", HTTPAdapter(pool_connections=15, pool_maxsize=15))

    # 1. Identify valid KOSPI/KOSDAQ common stocks with market_cap <= 525B KRW on 2026-10-23
    companies_df = store.get_companies()
    p_1023 = store.get_daily_prices(start_date="2026-10-23", end_date="2026-10-23")
    merged = companies_df.merge(p_1023, on="ticker", how="inner")

    valid_smallcaps = []
    for _, row in merged.iterrows():
        ticker = str(row["ticker"]).strip()
        name = str(row.get("name") or "").strip()
        sector = str(row.get("sector") or "").strip()
        market_val = str(row.get("market") or "").strip().upper()
        if row.get("is_preferred") == 1 or is_preferred_stock(ticker, name):
            continue
        if row.get("is_spac") == 1 or is_spac(name, ticker):
            continue
        if is_chinese_company(name, ticker):
            continue
        if is_holding_or_financial(sector, name):
            continue
        if market_val == "KONEX":
            continue
        if any(kw in sector for kw in ("관리종목", "환기종목", "외국기업")):
            continue
        fm = row.get("fiscal_month")
        if fm is not None and fm != 12:
            continue
        if float(row["market_cap"]) <= 525e8:
            valid_smallcaps.append(row.to_dict())

    # Check which of these tickers lack historical daily prices (e.g. < 50 rows in daily_prices)
    with store.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT ticker, COUNT(*) FROM daily_prices GROUP BY ticker")
        price_cnt_map = dict(cur.fetchall())

        cur.execute("SELECT DISTINCT corp_code FROM financials WHERE fiscal_year <= 2023")
        corps_with_hist_fin = {r[0] for r in cur.fetchall() if r[0]}

    missing_hist_corps = sorted(
        {
            str(r["corp_code"])
            for r in valid_smallcaps
            if r.get("corp_code") and str(r["corp_code"]) not in corps_with_hist_fin
        }
    )
    missing_hist_tickers = sorted(
        {
            str(r["ticker"])
            for r in valid_smallcaps
            if price_cnt_map.get(str(r["ticker"]), 0) < 50
        }
    )

    logger.info(
        "Target <=525B pool: %d stocks | Need 2015-2023 financials: %d corps | Need 2016-2026 prices: %d tickers",
        len(valid_smallcaps),
        len(missing_hist_corps),
        len(missing_hist_tickers),
    )

    # 2. Fetch 2015 Q4 ~ 2023 Q4 bulk financials via fnlttMultiAcnt.json
    if missing_hist_corps:
        batches = [missing_hist_corps[i : i + 100] for i in range(0, len(missing_hist_corps), 100)]
        periods = [(2015, 4)] + [(yr, q) for yr in range(2016, 2024) for q in (1, 2, 3, 4)]
        tasks = [(b, yr, q) for yr, q in periods for b in batches]

        # Probe 1 call first: if OpenDART WAF blocks or resets connection, exit immediately in 1s!
        probe_url = f"{dart.base_url}/fnlttMultiAcnt.json"
        probe_params = {
            "crtfc_key": dart.api_key,
            "corp_code": ",".join(batches[0][:50]),
            "bsns_year": "2023",
            "reprt_code": "11011",
        }
        try:
            probe_resp = dart.session.get(probe_url, params=probe_params, timeout=5).json()
            logger.info("OpenDART probe succeeded (status=%s)!", probe_resp.get("status"))
        except Exception as exc:
            logger.warning("OpenDART WAF rate-limit active (%s). Skipping 2015-2023 sync immediately.", exc)
            return

        logger.info("Fetching %d OpenDART bulk tasks (2015-2023) sequentially with 0.12s WAF-safe pacing...", len(tasks))

        t0 = time.time()
        all_fin_recs = []
        for idx, (b_corps, yr, q) in enumerate(tasks, 1):
            url = f"{dart.base_url}/fnlttMultiAcnt.json"
            params = {
                "crtfc_key": dart.api_key,
                "corp_code": ",".join(b_corps),
                "bsns_year": str(yr),
                "reprt_code": REPRT_CODE_MAP[q],
            }
            for attempt in range(3):
                try:
                    resp = dart.session.get(url, params=params, timeout=15).json()
                    items = resp.get("list") or []
                    if items:
                        all_fin_recs.extend(parse_bulk_items(dart, items, yr, q))
                    break
                except Exception as exc:
                    if attempt == 2:
                        logger.warning("Bulk error %d Q%d: %s", yr, q, exc)
                    time.sleep(0.5 * (attempt + 1))
            time.sleep(0.12)
            if idx % 25 == 0 or idx == len(tasks):
                logger.info(
                    "OpenDART bulk progress: %d/%d tasks (%d records in %.1fs)",
                    idx,
                    len(tasks),
                    len(all_fin_recs),
                    time.time() - t0,
                )

        if all_fin_recs:
            store.upsert_financials(all_fin_recs)
        logger.info(
            "Saved %d historical financial records (2015-2023) in %.2fs!",
            len(all_fin_recs),
            time.time() - t0,
        )

    # 3. Fetch 2016-01-01 ~ 2026-10-23 daily prices for missing_hist_tickers
    if missing_hist_tickers:
        shares_map = {}
        for _, row in p_1023.iterrows():
            code = str(row["ticker"]).strip().zfill(6)
            c_val = float(row.get("close") or 0.0)
            m_val = float(row.get("market_cap") or 0.0)
            if c_val > 0 and m_val > 0:
                shares_map[code] = m_val / c_val

        # Benchmark 5 tickers first
        t_bench = time.time()
        for t_sample in missing_hist_tickers[:5]:
            _ = fdr.DataReader(t_sample, "2016-01-01", "2026-10-23")
        bench_sec = time.time() - t_bench
        rate = 5.0 / max(bench_sec, 0.01)
        eta_sec = len(missing_hist_tickers) / (rate * 15)
        logger.info(
            "Benchmark: 5 tickers in %.2fs (%.1f tickers/s) -> Projected ETA with 15 workers: %.1fs",
            bench_sec,
            rate,
            eta_sec,
        )

        def fetch_ticker_prices(ticker_str: str) -> list[dict]:
            try:
                df = fdr.DataReader(ticker_str, "2016-01-01", "2026-10-23")
                if df is None or df.empty:
                    return []
                sh = shares_map.get(ticker_str, 0.0)
                recs = []
                for dt, r in df.iterrows():
                    c = clean_price_val(r.get("Close", 0.0))
                    v = clean_price_val(r.get("Volume", 0.0))
                    if c <= 0:
                        continue
                    recs.append(
                        {
                            "ticker": ticker_str,
                            "date": dt.strftime("%Y-%m-%d"),
                            "close": c,
                            "market_cap": c * sh,
                            "trading_value": c * v,
                        }
                    )
                return recs
            except Exception:
                return []

        t_p = time.time()
        all_price_recs = []
        done_p = 0
        with ThreadPoolExecutor(max_workers=15) as ex:
            futs = {ex.submit(fetch_ticker_prices, t): t for t in missing_hist_tickers}
            for fut in as_completed(futs):
                done_p += 1
                res = fut.result()
                if res:
                    all_price_recs.extend(res)
                if done_p % 50 == 0 or done_p == len(missing_hist_tickers):
                    logger.info(
                        "Price sync progress: %d/%d tickers (%d rows in %.1fs)",
                        done_p,
                        len(missing_hist_tickers),
                        len(all_price_recs),
                        time.time() - t_p,
                    )

        if all_price_recs:
            store.upsert_daily_prices(all_price_recs)
            logger.info("Upserted %d daily price rows into data/quant_ko.db!", len(all_price_recs))


if __name__ == "__main__":
    main()
