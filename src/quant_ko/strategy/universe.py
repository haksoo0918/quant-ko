"""Strategy Universe Filtering Engine."""

from typing import Any

import pandas as pd

from quant_ko.data.krx import (
    is_chinese_company,
    is_holding_or_financial,
    is_preferred_stock,
    is_spac,
    normalize_date,
)
from quant_ko.data.store import DataStore
from quant_ko.pit.builder import PITSnapshotBuilder


def filter_universe(
    store: DataStore,
    as_of_date: str,
    pit_df: pd.DataFrame | None = None,
    min_trading_value: float = 0.0,
    market_cap_quantile: float = 0.20,
) -> pd.DataFrame:
    """Filter stocks according to PRD section 3.1 rules.

    1. Base exclusions: preferred, spac, chinese, holding/financial, non-Dec fiscal month,
       delisted, active designations as of date.
    2. Market cap cut: bottom quantile (default 20%) by market cap.
    3. Liquidity filter: 20-day average trading value >= min_trading_value (default 200M KRW).
    4. Financial health filter: debt_ratio <= 200%, impairment_ratio <= 0%.
    5. Profitability filter: latest quarter op_income > 0, net_income_owner > 0,
       TTM op_income > 0, TTM net_income_owner > 0.
    """
    norm_date = normalize_date(as_of_date)  # YYYY-MM-DD
    dt_str = norm_date.replace("-", "")

    # 1. Base company exclusions
    companies_df = store.get_companies()
    if companies_df.empty:
        return pd.DataFrame()

    # Active designations as of date
    designations_df = store.get_designations(as_of_date=norm_date)
    designated_tickers = set()
    if not designations_df.empty:
        designated_tickers = set(designations_df["ticker"].unique())

    valid_tickers: list[dict[str, Any]] = []
    for _, row in companies_df.iterrows():
        ticker = str(row["ticker"]).strip()
        name = str(row.get("name") or "").strip()
        sector = str(row.get("sector") or "").strip()

        # Preferred
        if row.get("is_preferred") == 1 or is_preferred_stock(ticker, name):
            continue

        # SPAC
        if row.get("is_spac") == 1 or is_spac(name, ticker):
            continue

        # Chinese
        if is_chinese_company(name, ticker):
            continue

        # Holding or financial
        if is_holding_or_financial(sector, name):
            continue

        # Fiscal month == 12
        fiscal_month = row.get("fiscal_month")
        if fiscal_month is not None and fiscal_month != 12:
            continue

        # Active designations
        if ticker in designated_tickers:
            continue

        # Delisted or not yet listed
        delisted_at = row.get("delisted_at")
        if delisted_at and normalize_date(delisted_at) <= norm_date:
            continue
        listed_at = row.get("listed_at")
        if listed_at and normalize_date(listed_at) > norm_date:
            continue

        valid_tickers.append(row.to_dict())

    if not valid_tickers:
        return pd.DataFrame()

    universe_candidates = pd.DataFrame(valid_tickers)

    # 2. Daily prices: Market cap & 20-day average trading value
    price_df = store.get_daily_prices(end_date=norm_date)
    if price_df.empty:
        return pd.DataFrame()

    # Calculate latest market cap and 20-day avg trading value per ticker
    price_metrics: list[dict[str, Any]] = []
    for ticker, group in price_df.groupby("ticker"):
        sorted_group = group.sort_values("date", ascending=True)
        latest_row = sorted_group.iloc[-1]
        last_20 = sorted_group.tail(20)
        avg_tv = last_20["trading_value"].mean()

        price_metrics.append(
            {
                "ticker": ticker,
                "price_date": latest_row["date"],
                "close": latest_row["close"],
                "market_cap": latest_row["market_cap"],
                "trading_value_20d_avg": avg_tv,
            }
        )

    price_metrics_df = pd.DataFrame(price_metrics)
    merged = pd.merge(universe_candidates, price_metrics_df, on="ticker", how="inner")
    if merged.empty:
        return pd.DataFrame()

    # 3. Market Cap cut: Bottom 20% (smallest market caps)
    # Bottom 20% means lowest market cap
    # We rank market_cap ascending (lowest rank is smallest)
    if market_cap_quantile < 1.0:
        cap_cutoff = merged["market_cap"].quantile(market_cap_quantile)
        merged = merged[merged["market_cap"] <= cap_cutoff].copy()

    if merged.empty:
        return pd.DataFrame()

    # 4. Liquidity Filter: 20-day average trading value >= min_trading_value
    merged = merged[merged["trading_value_20d_avg"] >= min_trading_value].copy()
    if merged.empty:
        return pd.DataFrame()

    # 5. Financial metrics from PIT snapshot
    if pit_df is None:
        builder = PITSnapshotBuilder(store)
        corp_codes = merged["corp_code"].dropna().unique().tolist()
        pit_df = builder.build_snapshot(as_of_date=dt_str, corp_codes=corp_codes)

    if pit_df is None or pit_df.empty:
        return pd.DataFrame()

    # Merge on corp_code (or ticker)
    if "ticker" in pit_df.columns:
        final_df = pd.merge(
            merged,
            pit_df.drop(columns=["ticker"], errors="ignore"),
            on="corp_code",
            how="inner",
        )
    else:
        final_df = pd.merge(merged, pit_df, on="corp_code", how="inner")

    if final_df.empty:
        return pd.DataFrame()

    # 6. Financial Health Filter
    # debt_ratio <= 200%, impairment_ratio <= 0%
    cond_debt = (final_df["debt_ratio"].notna()) & (final_df["debt_ratio"] <= 200.0)
    cond_impairment = (final_df["impairment_ratio"].notna()) & (final_df["impairment_ratio"] <= 0.0)
    final_df = final_df[cond_debt & cond_impairment].copy()
    if final_df.empty:
        return pd.DataFrame()

    # 7. Profitability Filter
    # Latest quarter op_income > 0 and net_income_owner > 0
    # AND TTM op_income > 0 and net_income_owner > 0
    cond_qtr_op = final_df["op_income_quarter"] > 0
    cond_qtr_net = final_df["net_income_owner_quarter"] > 0
    cond_ttm_op = final_df["op_income_ttm"] > 0
    cond_ttm_net = final_df["net_income_owner_ttm"] > 0

    final_df = final_df[cond_qtr_op & cond_qtr_net & cond_ttm_op & cond_ttm_net].copy()

    return final_df.reset_index(drop=True)
