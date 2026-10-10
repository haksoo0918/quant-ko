"""Precompute and cache monthly target stock selections for fast testing.

Since 1안 팩터(시총 하위 20%, 거래대금 0원)의 매월 종목 선정 결과는
어떤 모멘텀/필터를 붙이든 매월 동일하므로(월 94회),
이를 1회만 계산해 cache에 저장하면 모멘텀 필터별 시뮬레이션을 몇 초 만에 고속으로 실행할 수 있습니다.
"""

import logging
import os
import pickle

from quant_ko.backtest.calendar import get_rebalance_schedule
from quant_ko.data.store import DataStore
from quant_ko.strategy.scoring import score_and_select
from quant_ko.strategy.universe import filter_universe

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cache_monthly_targets")

CACHE_FILE = "data/monthly_targets_cache.pkl"


def main():
    store = DataStore("data/quant_ko.db")
    prices_all = store.get_daily_prices()
    all_trading_days = sorted(prices_all["date"].dropna().unique().tolist())
    events = get_rebalance_schedule(
        all_trading_days,
        start_date="2016-04-01",
        end_date="2026-10-08",
        rebalance_freq="monthly",
    )

    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "rb") as f:
            cache = pickle.load(f)
        logger.info("Loaded existing cache with %d entries.", len(cache))

    total = len(events)
    for idx, ev in enumerate(events, 1):
        if ev.rebalance_date in cache:
            continue
        logger.info(
            "[%d/%d] Scoring for %s (prior: %s)...", idx, total, ev.rebalance_date, ev.prior_date
        )
        universe_df = filter_universe(
            store=store,
            as_of_date=ev.prior_date,
            min_trading_value=0.0,
            market_cap_quantile=0.20,
        )
        selected_df = score_and_select(universe_df, top_n=20)
        cache[ev.rebalance_date] = {
            "period_label": ev.period_label,
            "prior_date": ev.prior_date,
            "selected_df": selected_df,
        }

        # checkpoint every 10
        if idx % 10 == 0:
            with open(CACHE_FILE, "wb") as f:
                pickle.dump(cache, f)

    with open(CACHE_FILE, "wb") as f:
        pickle.dump(cache, f)
    logger.info("Successfully cached %d monthly target sets to %s!", len(cache), CACHE_FILE)


if __name__ == "__main__":
    main()
