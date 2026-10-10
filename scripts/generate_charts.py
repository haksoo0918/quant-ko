"""Generate comprehensive visualization charts (PNG & interactive HTML) for backtest comparison.

1. Cumulative Equity Curve (10.5 Years)
2. Underwater / Drawdown Chart
3. Annual Returns Comparison Bar Chart
"""

import logging
import os
import pickle
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quant_ko.backtest.calendar import get_cd_daily_return_series, get_rebalance_schedule
from quant_ko.backtest.engine import EventTracker, execute_rebalance
from quant_ko.backtest.metrics import calculate_metrics
from quant_ko.data.krx import normalize_date
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_charts")

CACHE_FILE = "data/monthly_targets_cache.pkl"
ARTIFACT_DIR = "C:/Users/hakso/.gemini/antigravity/brain/9b73f42b-8f55-4286-bdc5-cca7e6213392"
DOCS_CHARTS_DIR = "docs/charts"

# Configure Korean font for matplotlib
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def run_strategy(
    store: DataStore,
    cache: dict,
    trading_days: list[str],
    prices_all: pd.DataFrame,
    companies_df: pd.DataFrame,
    cd_returns: pd.Series,
    mode: str,  # 'seasonality' or 'no_filter'
    initial_capital: float = 10_000_000.0,
    cost_rate: float = 0.003,
) -> tuple[pd.DataFrame, dict]:
    events = get_rebalance_schedule(
        trading_days,
        start_date=trading_days[0],
        end_date=trading_days[-1],
        rebalance_freq="monthly",
    )
    reb_date_map = {e.rebalance_date: e for e in events}

    current_cash = float(initial_capital)
    current_positions: dict[str, int] = {}
    equity_records: list[dict] = []
    rebalance_records: list[dict] = []
    event_tracker = EventTracker()

    price_by_date: dict[str, dict[str, float]] = {}
    for row in prices_all[["date", "ticker", "close"]].itertuples(index=False):
        d, t, c = str(row[0]), str(row[1]), float(row[2]) if row[2] is not None else 0.0
        price_by_date.setdefault(d, {})[t] = c

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

        current_cash, current_positions, _ = event_tracker.process_day(
            date=current_date,
            cash=current_cash,
            positions=current_positions,
            prices=price_map,
            active_designations=active_desig_map,
            suspended_tickers=suspended_tickers,
            delisted_tickers=delisted_tickers,
            cost_rate=cost_rate,
        )

        if is_parked_cd and current_cash > 0:
            daily_cd_yield = cd_returns.get(current_date, 0.0)
            current_cash += current_cash * daily_cd_yield

        if current_date in reb_date_map:
            cached_item = cache.get(current_date)
            selected_df = cached_item["selected_df"] if cached_item else pd.DataFrame()
            dt = datetime.strptime(current_date, "%Y-%m-%d")

            if mode == "seasonality":
                allow_equity = dt.month not in [5, 6, 7, 8, 9, 10]
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
            rebalance_records.append(
                {
                    "rebalance_date": current_date,
                    "date": current_date,
                    "allow_equity": allow_equity,
                    "turnover_rate": reb_res.turnover_rate,
                }
            )

        positions_val = sum(qty * price_map.get(t, 0.0) for t, qty in current_positions.items())
        total_equity = current_cash + positions_val
        equity_records.append(
            {
                "date": current_date,
                "equity": total_equity,
            }
        )

    equity_df = pd.DataFrame(equity_records)
    metrics = calculate_metrics(
        equity_history=equity_df,
        rebalance_records=rebalance_records,
        initial_capital=initial_capital,
        risk_free_rate=0.035,
    )
    return equity_df, metrics


def run_benchmark(
    csv_path: str, trading_days: list[str], initial_capital: float = 10_000_000.0
) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df.index = [d.strftime("%Y-%m-%d") for d in df.index]
    close_series = df["Close"].reindex(trading_days).ffill().bfill()
    base_val = close_series.iloc[0]

    equity_records = [
        {"date": d, "equity": initial_capital * (close_series.loc[d] / base_val)}
        for d in trading_days
    ]
    equity_df = pd.DataFrame(equity_records)
    metrics = calculate_metrics(
        equity_history=equity_df,
        rebalance_records=[],
        initial_capital=initial_capital,
        risk_free_rate=0.035,
    )
    return equity_df, metrics


def main():
    os.makedirs(DOCS_CHARTS_DIR, exist_ok=True)
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    store = DataStore("data/quant_ko.db")
    with open(CACHE_FILE, "rb") as f:
        cache = pickle.load(f)

    prices_all = store.get_daily_prices()
    all_trading_days = sorted(prices_all["date"].dropna().unique().tolist())
    trading_days = [d for d in all_trading_days if "2016-04-01" <= d <= "2026-10-08"]
    companies_df = store.get_companies()
    cd_returns = get_cd_daily_return_series(trading_days)

    logger.info("Computing strategy simulations for charting...")
    eq_strat1, m_strat1 = run_strategy(
        store, cache, trading_days, prices_all, companies_df, cd_returns, mode="seasonality"
    )
    eq_base, m_base = run_strategy(
        store, cache, trading_days, prices_all, companies_df, cd_returns, mode="no_filter"
    )
    eq_kospi, m_kospi = run_benchmark("data/ks11_daily.csv", trading_days)
    eq_kosdaq, m_kosdaq = run_benchmark("data/kq11_daily.csv", trading_days)

    # Prepare DataFrame
    dates = pd.to_datetime(trading_days)
    chart_df = pd.DataFrame(
        {
            "Date": dates,
            "전략 1 (계절성+CD)": eq_strat1["equity"].values,
            "기준 전략 (No Filter)": eq_base["equity"].values,
            "KOSPI 지수": eq_kospi["equity"].values,
            "KOSDAQ 지수": eq_kosdaq["equity"].values,
        }
    ).set_index("Date")

    # Compute Drawdown
    dd_df = pd.DataFrame(index=chart_df.index)
    for col in chart_df.columns:
        cummax = chart_df[col].cummax()
        dd_df[col] = (chart_df[col] - cummax) / cummax * 100.0

    # -------------------------------------------------------------
    # 1. MATPLOTLIB MULTI-PANEL CHART
    # -------------------------------------------------------------
    logger.info("Creating Matplotlib comparison figure...")
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(14, 15), gridspec_kw={"height_ratios": [3, 1.8, 2.2]}
    )

    colors = {
        "전략 1 (계절성+CD)": "#D32F2F",  # 진한 빨강
        "기준 전략 (No Filter)": "#1976D2",  # 진한 파랑
        "KOSPI 지수": "#7B1FA2",  # 보라
        "KOSDAQ 지수": "#388E3C",  # 초록
    }

    # Panel 1: Cumulative Equity Curve
    for col in chart_df.columns:
        lw = 2.5 if "전략 1" in col else 1.8
        ls = "-" if "전략 1" in col else "--" if "KOS" in col else "-"
        ax1.plot(
            chart_df.index,
            chart_df[col] / 10_000.0,
            label=f"{col} (+{((chart_df[col].iloc[-1] / 10_000_000) - 1) * 100:.1f}%)",
            color=colors[col],
            linewidth=lw,
            linestyle=ls,
        )

    ax1.set_title(
        "소형주 퀀트 전략 vs 코스피 / 코스닥 10.5개년 자산 성장 곡선 (2016 - 2026)",
        fontsize=16,
        fontweight="bold",
        pad=12,
    )
    ax1.set_ylabel("평가 금액 (만 원)", fontsize=12)
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x):,}만"))
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left", fontsize=11, framealpha=0.9)
    ax1.axhline(1000, color="gray", linestyle=":", alpha=0.7)  # 원금선

    # Panel 2: Drawdown (Underwater Chart)
    for col in dd_df.columns:
        lw = 2.0 if "전략 1" in col else 1.2
        ax2.plot(
            dd_df.index,
            dd_df[col],
            label=f"{col} (MDD: {dd_df[col].min():.1f}%)",
            color=colors[col],
            linewidth=lw,
        )

    ax2.set_title(
        "고점 대비 최대 낙폭 (Underwater / Drawdown)", fontsize=13, fontweight="bold", pad=8
    )
    ax2.set_ylabel("낙폭 (%)", fontsize=11)
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x)}%"))
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="lower left", fontsize=10, framealpha=0.9)
    ax2.set_ylim(-65, 5)

    # Panel 3: Annual Return Bar Chart
    years = sorted(m_strat1.yearly_returns.keys())
    bar_data = {
        "전략 1 (계절성)": [m_strat1.yearly_returns.get(y, 0) * 100 for y in years],
        "기준 전략": [m_base.yearly_returns.get(y, 0) * 100 for y in years],
        "KOSPI": [m_kospi.yearly_returns.get(y, 0) * 100 for y in years],
        "KOSDAQ": [m_kosdaq.yearly_returns.get(y, 0) * 100 for y in years],
    }

    x = np.arange(len(years))
    width = 0.2
    ax3.bar(
        x - 1.5 * width,
        bar_data["전략 1 (계절성)"],
        width,
        label="전략 1 (계절성)",
        color=colors["전략 1 (계절성+CD)"],
    )
    ax3.bar(
        x - 0.5 * width,
        bar_data["기준 전략"],
        width,
        label="기준 전략",
        color=colors["기준 전략 (No Filter)"],
    )
    ax3.bar(x + 0.5 * width, bar_data["KOSPI"], width, label="KOSPI", color=colors["KOSPI 지수"])
    ax3.bar(x + 1.5 * width, bar_data["KOSDAQ"], width, label="KOSDAQ", color=colors["KOSDAQ 지수"])

    ax3.set_title("연도별 수익률 비교 (2016 - 2026)", fontsize=13, fontweight="bold", pad=8)
    ax3.set_xticks(x)
    ax3.set_xticklabels([f"{y}년" for y in years], fontsize=10)
    ax3.set_ylabel("연간 수익률 (%)", fontsize=11)
    ax3.yaxis.set_major_formatter(ticker.FuncFormatter(lambda val, p: f"{int(val)}%"))
    ax3.axhline(0, color="black", linewidth=0.8)
    ax3.grid(True, axis="y", linestyle=":", alpha=0.6)
    ax3.legend(loc="upper left", fontsize=10, ncol=4, framealpha=0.9)

    plt.tight_layout()

    # Save to docs and artifacts
    png_docs_path = os.path.join(DOCS_CHARTS_DIR, "backtest_comparison_chart.png")
    png_artifact_path = os.path.join(ARTIFACT_DIR, "backtest_comparison_chart.png")

    fig.savefig(png_docs_path, dpi=180, bbox_inches="tight")
    fig.savefig(png_artifact_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved PNG chart to %s and %s", png_docs_path, png_artifact_path)

    # -------------------------------------------------------------
    # 2. INTERACTIVE PLOTLY HTML DASHBOARD
    # -------------------------------------------------------------
    logger.info("Creating Interactive Plotly Dashboard...")
    fig_plotly = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "10.5개년 누적 자산 성장 곡선 (1,000만 원 시작)",
            "고점 대비 낙폭 (Drawdown %)",
        ),
        row_heights=[0.65, 0.35],
    )

    for col in chart_df.columns:
        fig_plotly.add_trace(
            go.Scatter(
                x=chart_df.index,
                y=chart_df[col],
                mode="lines",
                name=col,
                line={"color": colors[col], "width": 2.5 if "전략 1" in col else 1.5},
                hovertemplate="%{x|%Y-%m-%d}<br>자산: %{y:,.0f}원<extra></extra>",
            ),
            row=1,
            col=1,
        )

        fig_plotly.add_trace(
            go.Scatter(
                x=dd_df.index,
                y=dd_df[col],
                mode="lines",
                name=f"{col} DD",
                showlegend=False,
                line={"color": colors[col], "width": 1.5},
                hovertemplate="%{x|%Y-%m-%d}<br>낙폭: %{y:.2f}%<extra></extra>",
            ),
            row=2,
            col=1,
        )

    fig_plotly.update_layout(
        title="소형주 성장 가치 퀀트 전략 vs 코스피 / 코스닥 10.5개년 인터랙티브 분석 대시보드",
        template="plotly_white",
        height=750,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    fig_plotly.update_yaxes(title_text="평가 자산 (원)", row=1, col=1, tickformat=",.0f")
    fig_plotly.update_yaxes(title_text="낙폭 (%)", row=2, col=1, tickformat=".1f")

    html_docs_path = os.path.join(DOCS_CHARTS_DIR, "backtest_dashboard.html")
    html_artifact_path = os.path.join(ARTIFACT_DIR, "backtest_dashboard.html")
    fig_plotly.write_html(html_docs_path)
    fig_plotly.write_html(html_artifact_path)
    logger.info("Saved Interactive HTML to %s and %s", html_docs_path, html_artifact_path)

    print("\n" + "=" * 60)
    print(" 차트 및 인터랙티브 대시보드 생성 완료! ")
    print(f" - PNG 이미지: {png_docs_path}")
    print(f" - HTML 대시보드: {html_docs_path}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
