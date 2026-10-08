"""Backtest engine and execution models."""

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

from quant_ko.backtest.calendar import get_rebalance_schedule
from quant_ko.backtest.metrics import (
    BenchmarkComparison,
    PerformanceMetrics,
    calculate_metrics,
    compare_benchmark,
)
from quant_ko.backtest.report import generate_report
from quant_ko.data.krx import normalize_date
from quant_ko.data.store import DataStore
from quant_ko.strategy.scoring import score_and_select
from quant_ko.strategy.universe import filter_universe


@dataclass
class Trade:
    """Represents an executed trade order."""

    date: str
    ticker: str
    side: Literal["BUY", "SELL"]
    shares: int
    price: float
    trade_value: float
    fee: float


@dataclass
class RebalanceResult:
    """Represents the result of a rebalance execution."""

    date: str
    cash: float
    positions: dict[str, int]
    trades: list[Trade] = field(default_factory=list)
    turnover_value: float = 0.0
    turnover_rate: float = 0.0


def execute_rebalance(
    date: str,
    current_cash: float,
    current_positions: dict[str, int],
    target_weights: dict[str, float],
    prices: dict[str, float],
    cost_rate: float = 0.003,
) -> RebalanceResult:
    """Execute differential trading on rebalance date.

    - Retained stocks only trade the delta difference between current target weight
      and held position value.
    - Sells are executed first to free cash.
    - Buys are executed with floor integer share calculation and cost consideration.
    - One-way transaction cost rate is applied to buy/sell turnover.
    """
    norm_date = normalize_date(date)
    cash = float(current_cash)
    positions = {t: q for t, q in current_positions.items() if q > 0}

    # Total portfolio equity before rebalancing
    equity_before = cash + sum(positions.get(t, 0) * prices.get(t, 0.0) for t in positions)

    # Determine desired target shares per target stock
    desired_target_shares: dict[str, int] = {}
    for ticker, weight in target_weights.items():
        if weight <= 0:
            continue
        price = prices.get(ticker, 0.0)
        if price <= 0:
            continue
        target_val = equity_before * weight
        target_shares = math.floor(target_val / price)
        if target_shares > 0:
            desired_target_shares[ticker] = target_shares

    # Identify sells and buys
    sells: list[tuple[str, int, float]] = []
    buys: list[tuple[str, int, float]] = []

    # Check all currently held positions
    for ticker, held_shares in positions.items():
        price = prices.get(ticker, 0.0)
        target_shares = desired_target_shares.get(ticker, 0)
        if target_shares < held_shares:
            sells.append((ticker, held_shares - target_shares, price))
        elif target_shares > held_shares:
            buys.append((ticker, target_shares - held_shares, price))

    # Check target stocks not currently held
    for ticker, target_shares in desired_target_shares.items():
        if ticker not in positions:
            price = prices.get(ticker, 0.0)
            buys.append((ticker, target_shares, price))

    trades: list[Trade] = []

    # 1. Execute Sells first
    for ticker, shares_to_sell, price in sells:
        if shares_to_sell <= 0 or price <= 0:
            continue
        trade_val = shares_to_sell * price
        fee = trade_val * cost_rate
        cash += trade_val - fee
        positions[ticker] = positions.get(ticker, 0) - shares_to_sell
        if positions[ticker] <= 0:
            del positions[ticker]
        trades.append(
            Trade(
                date=norm_date,
                ticker=ticker,
                side="SELL",
                shares=shares_to_sell,
                price=price,
                trade_value=trade_val,
                fee=fee,
            )
        )

    # 2. Execute Buys
    for ticker, delta_shares, price in buys:
        if delta_shares <= 0 or price <= 0:
            continue
        cost_per_share = price * (1.0 + cost_rate)
        max_affordable = math.floor(cash / cost_per_share) if cost_per_share > 0 else 0
        shares_to_buy = min(delta_shares, max_affordable)
        if shares_to_buy > 0:
            trade_val = shares_to_buy * price
            fee = trade_val * cost_rate
            total_outlay = trade_val + fee
            cash -= total_outlay
            positions[ticker] = positions.get(ticker, 0) + shares_to_buy
            trades.append(
                Trade(
                    date=norm_date,
                    ticker=ticker,
                    side="BUY",
                    shares=shares_to_buy,
                    price=price,
                    trade_value=trade_val,
                    fee=fee,
                )
            )

    turnover_value = sum(t.trade_value for t in trades)
    turnover_rate = (turnover_value / (2.0 * equity_before)) if equity_before > 0 else 0.0

    return RebalanceResult(
        date=norm_date,
        cash=cash,
        positions=positions,
        trades=trades,
        turnover_value=turnover_value,
        turnover_rate=turnover_rate,
    )


class EventTracker:
    """Tracks in-period events: 관리종목, 투자주의환기, 거래정지, 상장폐지."""

    LIQUIDATION_DESIGNATION_TYPES = {"관리", "투자주의환기", "거래정지"}

    def __init__(self) -> None:
        # ticker -> date when newly flagged for liquidation
        self.flagged_dates: dict[str, str] = {}

    def process_day(
        self,
        date: str,
        cash: float,
        positions: dict[str, int],
        prices: dict[str, float],
        active_designations: dict[str, set[str]],
        suspended_tickers: set[str],
        delisted_tickers: set[str],
        cost_rate: float = 0.003,
    ) -> tuple[float, dict[str, int], list[Trade]]:
        """Process in-period events for the day.

        Returns updated (cash, positions, trades).
        """
        norm_date = normalize_date(date)
        cash_val = float(cash)
        pos = dict(positions)
        trades: list[Trade] = []

        # 1. Delisting check: any held stock delisted on or before today
        for ticker in list(pos.keys()):
            if ticker in delisted_tickers:
                del pos[ticker]
                self.flagged_dates.pop(ticker, None)

        # 2. Identify new designations for currently held stocks
        for ticker in pos:
            if ticker not in self.flagged_dates:
                desig_types = active_designations.get(ticker, set())
                if desig_types & self.LIQUIDATION_DESIGNATION_TYPES:
                    self.flagged_dates[ticker] = norm_date

        # 3. Attempt liquidation for flagged stocks that were flagged prior to today
        for ticker in list(self.flagged_dates.keys()):
            if ticker not in pos:
                self.flagged_dates.pop(ticker, None)
                continue

            flagged_on = self.flagged_dates[ticker]
            if flagged_on < norm_date:
                # Can we sell today? Must not be suspended and must have positive price
                if ticker not in suspended_tickers:
                    price = prices.get(ticker, 0.0)
                    if price > 0:
                        shares = pos[ticker]
                        trade_val = shares * price
                        fee = trade_val * cost_rate
                        cash_val += trade_val - fee
                        trades.append(
                            Trade(
                                date=norm_date,
                                ticker=ticker,
                                side="SELL",
                                shares=shares,
                                price=price,
                                trade_value=trade_val,
                                fee=fee,
                            )
                        )
                        del pos[ticker]
                        self.flagged_dates.pop(ticker, None)

        return cash_val, pos, trades


@dataclass
class BacktestResult:
    """Complete results from running a backtest simulation."""

    metrics: PerformanceMetrics
    equity_history: pd.DataFrame
    trades: list[Trade] = field(default_factory=list)
    rebalance_records: list[dict[str, Any]] = field(default_factory=list)
    daily_positions: list[dict[str, Any]] = field(default_factory=list)
    benchmarks: list[BenchmarkComparison] = field(default_factory=list)

    def generate_report(self, format_type: Literal["markdown", "text"] = "markdown") -> str:
        """Generate markdown or plain-text performance report."""
        return generate_report(self.metrics, self.benchmarks, format_type=format_type)


class BacktestEngine:
    """Backtesting simulator for the quantitative factor strategy."""

    def __init__(
        self,
        store: DataStore,
        initial_capital: float = 10_000_000.0,
        cost_rate: float = 0.003,
        top_n: int = 20,
        min_trading_value: float = 200_000_000.0,
        market_cap_quantile: float = 0.20,
        risk_free_rate: float = 0.035,
    ) -> None:
        self.store = store
        self.initial_capital = initial_capital
        self.cost_rate = cost_rate
        self.top_n = top_n
        self.min_trading_value = min_trading_value
        self.market_cap_quantile = market_cap_quantile
        self.risk_free_rate = risk_free_rate

    def run(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        benchmark_df: pd.DataFrame | None = None,
        benchmark_name: str = "KOSDAQ",
    ) -> BacktestResult:
        """Execute the backtest over the specified date range."""
        prices_all = self.store.get_daily_prices()
        if prices_all.empty:
            empty_metrics = calculate_metrics(pd.DataFrame(), initial_capital=self.initial_capital)
            return BacktestResult(
                metrics=empty_metrics,
                equity_history=pd.DataFrame(),
            )

        all_trading_days = sorted(prices_all["date"].dropna().unique().tolist())
        norm_start = normalize_date(start_date) if start_date else None
        norm_end = normalize_date(end_date) if end_date else None

        trading_days = [
            d
            for d in all_trading_days
            if (not norm_start or d >= norm_start) and (not norm_end or d <= norm_end)
        ]

        if not trading_days:
            empty_metrics = calculate_metrics(pd.DataFrame(), initial_capital=self.initial_capital)
            return BacktestResult(
                metrics=empty_metrics,
                equity_history=pd.DataFrame(),
            )

        # Get rebalancing schedule within range
        rebalance_events = get_rebalance_schedule(
            all_trading_days,
            start_date=start_date,
            end_date=end_date,
        )
        reb_date_map = {e.rebalance_date: e for e in rebalance_events}

        companies_df = self.store.get_companies()

        current_cash = float(self.initial_capital)
        current_positions: dict[str, int] = {}
        all_trades: list[Trade] = []
        rebalance_records: list[dict[str, Any]] = []
        equity_records: list[dict[str, Any]] = []
        daily_positions_records: list[dict[str, Any]] = []

        event_tracker = EventTracker()

        for current_date in trading_days:
            # Prices for current day
            day_prices = prices_all[prices_all["date"] == current_date]
            price_map = dict(
                zip(day_prices["ticker"], day_prices["close"].astype(float), strict=False)
            )

            # Active designations as of today
            active_desig_df = self.store.get_designations(as_of_date=current_date)
            active_desig_map: dict[str, set[str]] = {}
            if not active_desig_df.empty:
                for _, row in active_desig_df.iterrows():
                    active_desig_map.setdefault(str(row["ticker"]), set()).add(str(row["type"]))

            # Suspended tickers (explicit "거래정지" or zero/missing price)
            suspended_tickers: set[str] = {t for t, p in price_map.items() if p <= 0}
            for t, desigs in active_desig_map.items():
                if "거래정지" in desigs:
                    suspended_tickers.add(t)

            # Delisted tickers as of today
            delisted_tickers: set[str] = set()
            if not companies_df.empty and "delisted_at" in companies_df.columns:
                for _, row in companies_df.iterrows():
                    d_at = row.get("delisted_at")
                    if d_at and normalize_date(str(d_at)) <= current_date:
                        delisted_tickers.add(str(row["ticker"]))

            # 1. In-period events handling
            current_cash, current_positions, event_trades = event_tracker.process_day(
                date=current_date,
                cash=current_cash,
                positions=current_positions,
                prices=price_map,
                active_designations=active_desig_map,
                suspended_tickers=suspended_tickers,
                delisted_tickers=delisted_tickers,
                cost_rate=self.cost_rate,
            )
            all_trades.extend(event_trades)

            # 2. Rebalance check
            if current_date in reb_date_map:
                event = reb_date_map[current_date]
                prior_date = event.prior_date

                # Strategy universe filtering using prior trading day data
                universe_df = filter_universe(
                    store=self.store,
                    as_of_date=prior_date,
                    min_trading_value=self.min_trading_value,
                    market_cap_quantile=self.market_cap_quantile,
                )

                # Factor scoring and portfolio selection
                selected_df = score_and_select(universe_df, top_n=self.top_n)

                target_weights: dict[str, float] = {}
                if not selected_df.empty:
                    target_weights = dict(
                        zip(selected_df["ticker"], selected_df["weight"], strict=False)
                    )

                # Differential trading execution at today's close prices
                reb_res = execute_rebalance(
                    date=current_date,
                    current_cash=current_cash,
                    current_positions=current_positions,
                    target_weights=target_weights,
                    prices=price_map,
                    cost_rate=self.cost_rate,
                )
                current_cash = reb_res.cash
                current_positions = reb_res.positions
                all_trades.extend(reb_res.trades)
                rebalance_records.append(
                    {
                        "rebalance_date": current_date,
                        "date": current_date,
                        "prior_date": prior_date,
                        "period_label": event.period_label,
                        "turnover_value": reb_res.turnover_value,
                        "turnover_rate": reb_res.turnover_rate,
                        "target_count": len(target_weights),
                        "trades_count": len(reb_res.trades),
                        "trades": reb_res.trades,
                        "cash": reb_res.cash,
                        "positions": dict(reb_res.positions),
                    }
                )

            # 3. Daily valuation tracking
            positions_val = sum(qty * price_map.get(t, 0.0) for t, qty in current_positions.items())
            total_equity = current_cash + positions_val
            equity_records.append(
                {
                    "date": current_date,
                    "equity": total_equity,
                    "cash": current_cash,
                    "positions_value": positions_val,
                }
            )
            daily_positions_records.append(
                {
                    "date": current_date,
                    "positions": dict(current_positions),
                }
            )

        equity_df = pd.DataFrame(equity_records)
        metrics = calculate_metrics(
            equity_history=equity_df,
            rebalance_records=rebalance_records,
            initial_capital=self.initial_capital,
            risk_free_rate=self.risk_free_rate,
        )

        benchmarks: list[BenchmarkComparison] = []
        if benchmark_df is not None and not benchmark_df.empty:
            bench_comp = compare_benchmark(
                portfolio_equity=equity_df,
                benchmark_prices=benchmark_df,
                benchmark_name=benchmark_name,
                risk_free_rate=self.risk_free_rate,
            )
            benchmarks.append(bench_comp)

        return BacktestResult(
            metrics=metrics,
            equity_history=equity_df,
            trades=all_trades,
            rebalance_records=rebalance_records,
            daily_positions=daily_positions_records,
            benchmarks=benchmarks,
        )
