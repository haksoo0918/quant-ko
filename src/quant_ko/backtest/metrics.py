"""Performance metrics calculation and benchmark comparison."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """Summary of backtest portfolio performance metrics."""

    initial_capital: float
    final_equity: float
    total_return: float
    cagr: float
    mdd: float
    mdd_peak_date: str
    mdd_trough_date: str
    annualized_volatility: float
    sharpe_ratio: float
    win_rate_rebalance: float
    win_rate_yearly: float
    avg_turnover_rate: float
    period_returns: dict[str, float] = field(default_factory=dict)
    yearly_returns: dict[int, float] = field(default_factory=dict)


@dataclass
class BenchmarkComparison:
    """Comparison results between portfolio and benchmark."""

    benchmark_name: str
    benchmark_return: float
    benchmark_cagr: float
    benchmark_mdd: float
    benchmark_sharpe: float
    correlation: float
    alpha: float
    beta: float


def calculate_metrics(
    equity_history: pd.DataFrame,
    rebalance_records: list[dict[str, Any]] | None = None,
    initial_capital: float = 10_000_000.0,
    risk_free_rate: float = 0.035,
) -> PerformanceMetrics:
    """Calculate standard quantitative portfolio metrics."""
    if equity_history.empty:
        return PerformanceMetrics(
            initial_capital=initial_capital,
            final_equity=initial_capital,
            total_return=0.0,
            cagr=0.0,
            mdd=0.0,
            mdd_peak_date="",
            mdd_trough_date="",
            annualized_volatility=0.0,
            sharpe_ratio=0.0,
            win_rate_rebalance=0.0,
            win_rate_yearly=0.0,
            avg_turnover_rate=0.0,
        )

    df = equity_history.sort_values("date").reset_index(drop=True).copy()
    equity = df["equity"].astype(float)
    final_equity = float(equity.iloc[-1])
    total_return = (final_equity - initial_capital) / initial_capital

    start_date_str = str(df["date"].iloc[0])[:10]
    end_date_str = str(df["date"].iloc[-1])[:10]
    dt_start = datetime.strptime(start_date_str, "%Y-%m-%d")
    dt_end = datetime.strptime(end_date_str, "%Y-%m-%d")
    total_days = max((dt_end - dt_start).days, 1)

    cagr = ((final_equity / initial_capital) ** (365.25 / total_days)) - 1.0

    # MDD calculation
    running_max = equity.cummax()
    drawdowns = (equity - running_max) / running_max
    mdd = float(drawdowns.min())

    trough_idx = drawdowns.idxmin()
    peak_idx = equity.iloc[: trough_idx + 1].idxmax()
    mdd_peak_date = str(df.loc[peak_idx, "date"])[:10]
    mdd_trough_date = str(df.loc[trough_idx, "date"])[:10]

    # Volatility & Sharpe
    daily_returns = equity.pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        annualized_vol = float(daily_returns.std() * np.sqrt(252))
        sharpe = (cagr - risk_free_rate) / annualized_vol if annualized_vol > 0 else 0.0
    else:
        annualized_vol = 0.0
        sharpe = 0.0

    # Turnover
    if rebalance_records:
        turnovers = [r.get("turnover_rate", 0.0) for r in rebalance_records if "turnover_rate" in r]
        avg_turnover = float(np.mean(turnovers)) if turnovers else 0.0
    else:
        avg_turnover = 0.0

    # Yearly returns
    df["year"] = pd.to_datetime(df["date"]).dt.year
    yearly_returns: dict[int, float] = {}
    grouped = df.groupby("year")
    prev_year_end = initial_capital
    for year, group in grouped:
        first_val = float(group["equity"].iloc[0])
        last_val = float(group["equity"].iloc[-1])
        base_val = prev_year_end if prev_year_end > 0 else first_val
        ret = (last_val - base_val) / base_val
        yearly_returns[int(year)] = ret
        prev_year_end = last_val

    win_rate_yearly = (
        sum(1 for ret in yearly_returns.values() if ret > 0) / len(yearly_returns)
        if yearly_returns
        else 0.0
    )

    # Rebalance period returns
    period_returns: dict[str, float] = {}
    if rebalance_records and len(rebalance_records) > 0:
        date_to_equity = dict(zip(df["date"].astype(str).str[:10], df["equity"], strict=False))
        reb_dates = [str(r["rebalance_date"])[:10] for r in rebalance_records]
        labels = [str(r.get("period_label", r["rebalance_date"])) for r in rebalance_records]

        for i, reb_d in enumerate(reb_dates):
            lbl = labels[i]
            eq_start = date_to_equity.get(reb_d)
            if eq_start is None:
                # Find closest on or after reb_d
                sub = df[df["date"] >= reb_d]
                eq_start = float(sub["equity"].iloc[0]) if not sub.empty else None

            next_reb_d = reb_dates[i + 1] if i + 1 < len(reb_dates) else end_date_str
            eq_end = date_to_equity.get(next_reb_d)
            if eq_end is None:
                sub = df[df["date"] >= next_reb_d]
                eq_end = (
                    float(sub["equity"].iloc[0]) if not sub.empty else float(df["equity"].iloc[-1])
                )

            if eq_start and eq_end:
                period_returns[lbl] = (eq_end - eq_start) / eq_start

    win_rate_rebalance = (
        sum(1 for ret in period_returns.values() if ret > 0) / len(period_returns)
        if period_returns
        else 0.0
    )

    return PerformanceMetrics(
        initial_capital=initial_capital,
        final_equity=final_equity,
        total_return=total_return,
        cagr=cagr,
        mdd=mdd,
        mdd_peak_date=mdd_peak_date,
        mdd_trough_date=mdd_trough_date,
        annualized_volatility=annualized_vol,
        sharpe_ratio=sharpe,
        win_rate_rebalance=win_rate_rebalance,
        win_rate_yearly=win_rate_yearly,
        avg_turnover_rate=avg_turnover,
        period_returns=period_returns,
        yearly_returns=yearly_returns,
    )


def compare_benchmark(
    portfolio_equity: pd.DataFrame,
    benchmark_prices: pd.DataFrame,
    benchmark_name: str = "KOSDAQ",
    risk_free_rate: float = 0.035,
) -> BenchmarkComparison:
    """Compare portfolio daily returns against a benchmark index."""
    # Align dates
    port = portfolio_equity[["date", "equity"]].copy()
    port["date"] = port["date"].astype(str).str[:10]
    bench = benchmark_prices[["date", "close"]].rename(columns={"close": "bench_close"}).copy()
    bench["date"] = bench["date"].astype(str).str[:10]

    merged = (
        pd.merge(port, bench, on="date", how="inner").sort_values("date").reset_index(drop=True)
    )
    if merged.empty or len(merged) < 2:
        return BenchmarkComparison(
            benchmark_name=benchmark_name,
            benchmark_return=0.0,
            benchmark_cagr=0.0,
            benchmark_mdd=0.0,
            benchmark_sharpe=0.0,
            correlation=0.0,
            alpha=0.0,
            beta=0.0,
        )

    b_start = merged["bench_close"].iloc[0]
    b_end = merged["bench_close"].iloc[-1]
    b_ret = (b_end - b_start) / b_start

    dt_start = datetime.strptime(merged["date"].iloc[0], "%Y-%m-%d")
    dt_end = datetime.strptime(merged["date"].iloc[-1], "%Y-%m-%d")
    days = max((dt_end - dt_start).days, 1)
    b_cagr = ((b_end / b_start) ** (365.25 / days)) - 1.0

    b_running_max = merged["bench_close"].cummax()
    b_drawdowns = (merged["bench_close"] - b_running_max) / b_running_max
    b_mdd = float(b_drawdowns.min())

    b_daily = merged["bench_close"].pct_change().dropna()
    p_daily = merged["equity"].pct_change().dropna()

    b_vol = float(b_daily.std() * np.sqrt(252)) if len(b_daily) > 1 else 0.0
    b_sharpe = (b_cagr - risk_free_rate) / b_vol if b_vol > 0 else 0.0

    corr = float(p_daily.corr(b_daily)) if len(p_daily) > 1 else 0.0
    var_b = b_daily.var()
    if var_b > 0 and len(p_daily) > 1:
        cov = float(p_daily.cov(b_daily))
        beta = cov / var_b
        # Annualized alpha: Portfolio Ann Return - (rf + beta * (Benchmark Ann Return - rf))
        p_cagr = ((merged["equity"].iloc[-1] / merged["equity"].iloc[0]) ** (365.25 / days)) - 1.0
        alpha = p_cagr - (risk_free_rate + beta * (b_cagr - risk_free_rate))
    else:
        beta = 0.0
        alpha = 0.0

    return BenchmarkComparison(
        benchmark_name=benchmark_name,
        benchmark_return=b_ret,
        benchmark_cagr=b_cagr,
        benchmark_mdd=b_mdd,
        benchmark_sharpe=b_sharpe,
        correlation=corr,
        alpha=alpha,
        beta=beta,
    )
