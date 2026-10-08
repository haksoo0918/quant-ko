"""Factor scoring and portfolio selection engine."""

import numpy as np
import pandas as pd

VALUE_FACTORS = [
    ("per", "net_income_owner_ttm"),
    ("psr", "revenue_ttm"),
    ("por", "op_income_ttm"),
    ("pgpr", "gross_profit_ttm"),
]

GROWTH_FACTORS = [
    ("net_income_owner_yoy", "net_income_owner_turnaround"),
    ("op_income_yoy", "op_income_turnaround"),
    ("gross_profit_yoy", "gross_profit_turnaround"),
    ("revenue_yoy", "revenue_turnaround"),
]


def _rank_growth_with_turnaround(
    df: pd.DataFrame,
    growth_col: str,
    turnaround_col: str,
) -> pd.Series:
    """Rank growth factor descending, with turnaround stocks strictly ranked at the top.

    Turnaround stocks receive top ranks (1, 2, ...).
    Within turnaround and within non-turnaround, stocks are ranked by growth rate descending.
    """
    is_turnaround = df[turnaround_col].fillna(False).astype(bool)
    growth = pd.to_numeric(df[growth_col], errors="coerce").fillna(-np.inf)

    # Base large bonus for turnaround so they always exceed non-turnaround
    # Use 1e9 as base bonus
    effective_growth = np.where(is_turnaround, 1e9 + growth, growth)

    # If growth is inf, handle gracefully
    effective_series = pd.Series(effective_growth, index=df.index)
    return effective_series.rank(ascending=False, method="min").astype(int)


def score_and_select(
    universe_df: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    """Compute 9-factor model scores, rank stocks, and select top N portfolio.

    9-factor model:
    - Market cap: Ascending rank (lower is better)
    - Value (4 factors): PER, PSR, POR, PGPR (Ascending rank)
    - Growth (4 factors): net_income YoY, op_income YoY, gross_profit YoY, revenue YoY
      (Descending rank, turnaround ranked highest)

    Total Rank = Rank(시총) + sum(Rank(Value 4)) + sum(Rank(Growth 4)).
    Sort: Total Rank ascending, tie-breaker: market_cap ascending.
    Selection: Top N stocks (or all if < N), equal weighting (1 / N).
    """
    if universe_df.empty:
        return pd.DataFrame()

    df = universe_df.copy()

    # 1. Market Cap factor rank (Ascending)
    df["rank_market_cap"] = df["market_cap"].rank(ascending=True, method="min").astype(int)

    # 2. Value factors (Ascending rank: lower ratio is cheaper)
    for ratio_name, denom_col in VALUE_FACTORS:
        denom = df[denom_col].replace(0, np.nan)
        df[ratio_name] = df["market_cap"] / denom
        # Higher rank for NaN / non-positive
        df[f"rank_{ratio_name}"] = (
            df[ratio_name].rank(ascending=True, method="min", na_option="bottom").astype(int)
        )

    # 3. Growth factors (Descending rank, turnaround at top)
    for growth_col, turnaround_col in GROWTH_FACTORS:
        df[f"rank_{growth_col}"] = _rank_growth_with_turnaround(df, growth_col, turnaround_col)

    # 4. Total Rank
    value_rank_cols = [f"rank_{ratio_name}" for ratio_name, _ in VALUE_FACTORS]
    growth_rank_cols = [f"rank_{growth_col}" for growth_col, _ in GROWTH_FACTORS]

    df["total_rank"] = (
        df["rank_market_cap"] + df[value_rank_cols].sum(axis=1) + df[growth_rank_cols].sum(axis=1)
    )

    # 5. Sort by total_rank ascending, market_cap ascending
    sorted_df = df.sort_values(
        by=["total_rank", "market_cap"],
        ascending=[True, True],
    ).reset_index(drop=True)

    # 6. Select Top N
    n_select = min(len(sorted_df), top_n)
    selected = sorted_df.iloc[:n_select].copy()

    if n_select > 0:
        selected["weight"] = 1.0 / n_select
    else:
        selected["weight"] = 0.0

    return selected.reset_index(drop=True)
