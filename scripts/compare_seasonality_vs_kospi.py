"""Comparative backtest runner: Strategy 1 (Seasonality + CD ETF) vs KOSPI vs KOSDAQ (2016.04 - 2026.10).

Compares:
1. Strategy 1 (Seasonality + CD Rate ETF):
   - 11-4월 (6개월): 소형주 9대 팩터 20종목 동일비중 (월별 리밸런싱)
   - 5-10월 (6개월): CD금리 ETF (또는 단기금리) 100% 안전 파킹
2. KOSPI Buy & Hold (코스피 지수 단순 보유)
3. KOSDAQ Buy & Hold (코스닥 지수 단순 보유)
"""

import logging
import pickle
from datetime import datetime

import pandas as pd

from quant_ko.backtest.calendar import get_cd_daily_return_series, get_rebalance_schedule
from quant_ko.backtest.engine import EventTracker, Trade, execute_rebalance
from quant_ko.backtest.metrics import calculate_metrics
from quant_ko.data.krx import normalize_date
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("compare_seasonality_vs_kospi")

CACHE_FILE = "data/monthly_targets_cache.pkl"


def run_seasonality_strategy(
    store: DataStore,
    cache: dict,
    trading_days: list[str],
    prices_all: pd.DataFrame,
    companies_df: pd.DataFrame,
    cd_returns: pd.Series,
    initial_capital: float = 10_000_000.0,
    cost_rate: float = 0.003,
) -> dict:
    events = get_rebalance_schedule(
        trading_days,
        start_date=trading_days[0],
        end_date=trading_days[-1],
        rebalance_freq="monthly",
    )
    reb_date_map = {e.rebalance_date: e for e in events}

    current_cash = float(initial_capital)
    current_positions: dict[str, int] = {}
    all_trades: list[Trade] = []
    equity_records: list[dict] = []
    rebalance_records: list[dict] = []
    event_tracker = EventTracker()

    price_by_date: dict[str, dict[str, float]] = {}
    for row in prices_all[["date", "ticker", "close"]].itertuples(index=False):
        d = str(row[0])
        t = str(row[1])
        c = float(row[2]) if row[2] is not None else 0.0
        if d not in price_by_date:
            price_by_date[d] = {}
        price_by_date[d][t] = c

    all_desigs_df = store.get_designations()
    desigs_by_date: dict[str, dict[str, set[str]]] = {}
    if not all_desigs_df.empty:
        for row in all_desigs_df[["date", "ticker", "type"]].itertuples(index=False):
            d, t, typ = str(row[0]), str(row[1]), str(row[2])
            desigs_by_date.setdefault(d, {}).setdefault(t, set()).add(typ)

    delisted_by_date: dict[str, set[str]] = {}
    if not companies_df.empty and "delisted_at" in companies_df.columns:
        for row in companies_df[["ticker", "delisted_at"]].itertuples(index=False):
            t, d_at = str(row[0]), row[1]
            if d_at:
                delisted_by_date.setdefault(normalize_date(str(d_at)), set()).add(t)

    active_delisted_set: set[str] = set()
    is_parked_cd = False

    for current_date in trading_days:
        price_map = price_by_date.get(current_date, {})
        active_desig_map = desigs_by_date.get(current_date, {})

        if current_date in delisted_by_date:
            active_delisted_set.update(delisted_by_date[current_date])
        delisted_tickers = active_delisted_set

        suspended_tickers = {t for t, p in price_map.items() if p <= 0}
        for t, desigs in active_desig_map.items():
            if "거래정지" in desigs:
                suspended_tickers.add(t)

        current_cash, current_positions, event_trades = event_tracker.process_day(
            date=current_date,
            cash=current_cash,
            positions=current_positions,
            prices=price_map,
            active_designations=active_desig_map,
            suspended_tickers=suspended_tickers,
            delisted_tickers=delisted_tickers,
            cost_rate=cost_rate,
        )
        all_trades.extend(event_trades)

        if is_parked_cd and current_cash > 0:
            daily_cd_yield = cd_returns.get(current_date, 0.0)
            current_cash += current_cash * daily_cd_yield

        if current_date in reb_date_map:
            cached_item = cache.get(current_date)
            selected_df = cached_item["selected_df"] if cached_item else pd.DataFrame()
            dt = datetime.strptime(current_date, "%Y-%m-%d")

            # Seasonality: 5, 6, 7, 8, 9, 10월 진입 리밸런싱은 CD 파킹
            if dt.month in [5, 6, 7, 8, 9, 10]:
                allow_equity = False
            else:
                allow_equity = True

            target_weights = {}
            if allow_equity and not selected_df.empty:
                target_weights = dict(
                    zip(selected_df["ticker"], selected_df["weight"], strict=False)
                )
                is_parked_cd = False
            else:
                target_weights = {}
                is_parked_cd = True

            reb_res = execute_rebalance(
                date=current_date,
                current_cash=current_cash,
                current_positions=current_positions,
                target_weights=target_weights,
                prices=price_map,
                cost_rate=cost_rate,
            )
            current_cash = reb_res.cash
            current_positions = reb_res.positions
            all_trades.extend(reb_res.trades)
            rebalance_records.append(
                {
                    "rebalance_date": current_date,
                    "date": current_date,
                    "allow_equity": allow_equity,
                    "trades_count": len(reb_res.trades),
                    "turnover_rate": reb_res.turnover_rate,
                }
            )

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

    equity_df = pd.DataFrame(equity_records)
    metrics = calculate_metrics(
        equity_history=equity_df,
        rebalance_records=rebalance_records,
        initial_capital=initial_capital,
        risk_free_rate=0.035,
    )
    return {
        "label": "1. 계절성 필터 (11-4월 주식, 5-10월 CD금리 ETF)",
        "metrics": metrics,
        "trades": all_trades,
        "equity_df": equity_df,
    }


def run_benchmark_index(
    csv_path: str,
    label: str,
    trading_days: list[str],
    initial_capital: float = 10_000_000.0,
) -> dict:
    """Simulate Buy & Hold benchmark from CSV."""
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df.index = [d.strftime("%Y-%m-%d") for d in df.index]

    # Reindex to trading days and forward fill
    close_series = df["Close"].reindex(trading_days).ffill().bfill()
    base_val = close_series.iloc[0]

    equity_records = []
    for d in trading_days:
        val = close_series.loc[d]
        eq = initial_capital * (val / base_val)
        equity_records.append({"date": d, "equity": eq, "cash": 0.0, "positions_value": eq})

    equity_df = pd.DataFrame(equity_records)
    metrics = calculate_metrics(
        equity_history=equity_df,
        rebalance_records=[],
        initial_capital=initial_capital,
        risk_free_rate=0.035,
    )
    return {
        "label": label,
        "metrics": metrics,
        "trades": [],
        "equity_df": equity_df,
    }


def main():
    store = DataStore("data/quant_ko.db")
    with open(CACHE_FILE, "rb") as f:
        cache = pickle.load(f)

    prices_all = store.get_daily_prices()
    all_trading_days = sorted(prices_all["date"].dropna().unique().tolist())
    trading_days = [d for d in all_trading_days if "2016-04-01" <= d <= "2026-10-08"]

    companies_df = store.get_companies()
    cd_returns = get_cd_daily_return_series(trading_days)

    logger.info("1. Running Strategy 1 (Seasonality + CD ETF)...")
    strat1_res = run_seasonality_strategy(
        store=store,
        cache=cache,
        trading_days=trading_days,
        prices_all=prices_all,
        companies_df=companies_df,
        cd_returns=cd_returns,
    )

    logger.info("2. Running KOSPI Benchmark...")
    kospi_res = run_benchmark_index("data/ks11_daily.csv", "KOSPI 지수 (Buy & Hold)", trading_days)

    logger.info("3. Running KOSDAQ Benchmark...")
    kosdaq_res = run_benchmark_index(
        "data/kq11_daily.csv", "KOSDAQ 지수 (Buy & Hold)", trading_days
    )

    results = [strat1_res, kospi_res, kosdaq_res]

    # Generate Markdown Report
    md_lines = [
        "# 전략 1 (계절성 필터) vs 코스피 / 코스닥 10.5개년 종합 비교 리포트\n",
        "## 1. 비교 개요 (2016.04 - 2026.10)\n",
        "- **분석 기간**: 2016년 4월 1일 ~ 2026년 10월 8일 (만 10년 6개월, 127개월)",
        "- **초기 원금**: 10,000,000 KRW (1,000만 원)",
        "- **거래 비용**: 편도 0.3% (왕복 0.6%) 실전 슬리피지/수수료 완벽 반영\n",
        "### 비교 대상:",
        "1. **전략 1 (계절성 + CD금리 ETF)**: 11-4월 소형주 9대 팩터 20종목 동일비중, 5-10월 CD금리 ETF 100% 안전 파킹",
        "2. **KOSPI 지수 (코스피 단순 보유)**: 국내 대표 대형주 시장 벤치마크",
        "3. **KOSDAQ 지수 (코스닥 단순 보유)**: 국내 대표 중소형/기술주 시장 벤치마크\n",
        "## 2. 종합 성과 비교 요약표\n",
        "| 구분 | 누적 수익률 | CAGR (연복리) | MDD (최대낙폭) | 연율화 변동성 | 샤프지수 | 연간 승률 | 최종 자산 (1천만 원 시작) |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for res in results:
        m = res["metrics"]
        final_eq = res["equity_df"]["equity"].iloc[-1]
        md_lines.append(
            f"| **{res['label']}** | **{m.total_return * 100:+.2f}%** | {m.cagr * 100:.2f}% | **{m.mdd * 100:.2f}%** | {m.annualized_volatility * 100:.2f}% | {m.sharpe_ratio:.2f} | {m.win_rate_yearly * 100:.1f}% | **{int(final_eq):,}원** |"
        )

    md_lines.append("\n## 3. 연도별 수익률 비교\n")
    header = "| 연도 | 전략 1 (계절성) | KOSPI (코스피) | KOSDAQ (코스닥) | 전략 1 vs 코스피 초과수익 (알파) |"
    sep = "|:---:|:---:|:---:|:---:|:---:|"
    md_lines.append(header)
    md_lines.append(sep)

    years = sorted(strat1_res["metrics"].yearly_returns.keys())
    for yr in years:
        s1_ret = strat1_res["metrics"].yearly_returns.get(yr, 0.0)
        kp_ret = kospi_res["metrics"].yearly_returns.get(yr, 0.0)
        kq_ret = kosdaq_res["metrics"].yearly_returns.get(yr, 0.0)
        alpha = s1_ret - kp_ret
        alpha_str = f"**{alpha * 100:+.2f}%p**" if alpha >= 0 else f"{alpha * 100:+.2f}%p"
        md_lines.append(
            f"| **{yr}년** | **{s1_ret * 100:+.2f}%** | {kp_ret * 100:+.2f}% | {kq_ret * 100:+.2f}% | {alpha_str} |"
        )

    out_file = "docs/seasonality_vs_kospi_backtest_result.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    logger.info("Report successfully written to %s!", out_file)

    # Print summary to console
    print("\n" + "=" * 65)
    print(" [전략 1 vs 코스피/코스닥 10.5개년 비교 백테스트 결과] ")
    print("=" * 65)
    for res in results:
        m = res["metrics"]
        final_eq = res["equity_df"]["equity"].iloc[-1]
        print(f"[{res['label']}]")
        print(
            f"  누적 수익률: {m.total_return * 100:+.2f}% | CAGR: {m.cagr * 100:.2f}% | MDD: {m.mdd * 100:.2f}% | Sharpe: {m.sharpe_ratio:.2f} | 최종 자산: {int(final_eq):,}원"
        )
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
