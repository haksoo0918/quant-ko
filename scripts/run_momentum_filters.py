"""Comprehensive comparative backtest runner for 4 momentum filter strategies.

전략 구성:
0. 기준 전략 (No Filter):
   - 1안 팩터 (시총 하위 20%, 거래대금 제한없음) + 월별 리밸런싱 (20종목 동일비중)

1. 전략 1 (계절성 + CD금리 ETF):
   - 11월 ~ 4월 (6개월): 주식 100% (20종목 동일비중)
   - 5월 ~ 10월 (6개월): CD금리 ETF (또는 단기금리) 100% 투자 (안전 수익 확보)

2. 전략 2 (코스닥 지수 모멘텀 필터링):
   - 매월 말일 리밸런싱 시점, 코스닥 종가 > 코스닥 60일(또는 200일) 이동평균선인 경우: 주식 100%
   - 하회하는 경우: CD금리 ETF (또는 현금) 100% 대피

3. 전략 3 (자체 자산곡선 60일 이평선 필터링):
   - 자체 전략 가상 지표(Shadow Index, 100% 주식 투자 시의 자산곡선)의 60일 단순이동평균(SMA) 추적
   - 매일(또는 매월) Shadow Index > 60일 SMA: 주식 포트폴리오 유지
   - Shadow Index <= 60일 SMA: 전량 현금화 / CD금리 ETF 대피
"""

import logging
import pickle
from datetime import datetime

import numpy as np
import pandas as pd

from quant_ko.backtest.calendar import get_rebalance_schedule
from quant_ko.backtest.engine import EventTracker, Trade, execute_rebalance
from quant_ko.backtest.metrics import calculate_metrics
from quant_ko.data.krx import normalize_date
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_momentum_filters")

CACHE_FILE = "data/monthly_targets_cache.pkl"


def get_cd_daily_return_series(trading_days: list[str]) -> pd.Series:
    """Return daily return multiplier for CD rate proxy."""
    # 2020-07-07부터 실제 KODEX/TIGER CD금리 ETF (357870) 데이터 사용
    # 이전 기간은 연 1.75% 기준 일복리(1.75% / 250) 수익률 적용
    try:
        cd_df = pd.read_csv("data/cd_daily.csv", index_col=0, parse_dates=True)
        cd_df.index = [d.strftime("%Y-%m-%d") for d in cd_df.index]
        cd_close = cd_df["Close"].to_dict()
    except Exception:
        cd_close = {}

    daily_ret = {}
    prev_close = None
    for d in trading_days:
        if d in cd_close:
            curr = cd_close[d]
            if prev_close and prev_close > 0:
                ret = (curr - prev_close) / prev_close
            else:
                ret = 0.035 / 250.0  # 약 연 3.5%
            prev_close = curr
            daily_ret[d] = max(0.0, ret)
        else:
            daily_ret[d] = 0.0175 / 250.0  # 2019-2020 저금리 기조 연 1.75%

    return pd.Series(daily_ret)


def run_simulation(
    store: DataStore,
    mode: str,  # 'no_filter', 'seasonality', 'kosdaq_ma60', 'kosdaq_ma200', 'asset_curve_ma60'
    cache: dict,
    trading_days: list[str],
    prices_all: pd.DataFrame,
    companies_df: pd.DataFrame,
    kosdaq_df: pd.DataFrame,
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

    # Precompute kosdaq moving averages
    kosdaq_close = kosdaq_df["Close"].reindex(trading_days).ffill()
    kosdaq_ma60 = kosdaq_close.rolling(60, min_periods=1).mean()
    kosdaq_ma200 = kosdaq_close.rolling(200, min_periods=1).mean()

    # If mode == 'asset_curve_ma60', we need shadow equity tracking
    # Shadow index starts at initial capital and runs standard strategy
    shadow_cash = float(initial_capital)
    shadow_positions: dict[str, int] = {}
    shadow_equity_history: list[float] = []

    # State: are we invested in equities or parked in CD rate?
    # Pre-index daily prices and designations for instant lookup
    # Group prices by date: date -> {ticker: close}
    price_by_date: dict[str, dict[str, float]] = {}
    for row in prices_all[["date", "ticker", "close"]].itertuples(index=False):
        d = str(row[0])
        t = str(row[1])
        c = float(row[2]) if row[2] is not None else 0.0
        if d not in price_by_date:
            price_by_date[d] = {}
        price_by_date[d][t] = c

    # Pre-index designations by date
    all_desigs_df = store.get_designations()
    desigs_by_date: dict[str, dict[str, set[str]]] = {}
    if not all_desigs_df.empty:
        for row in all_desigs_df[["date", "ticker", "type"]].itertuples(index=False):
            d = str(row[0])
            t = str(row[1])
            typ = str(row[2])
            desigs_by_date.setdefault(d, {}).setdefault(t, set()).add(typ)

    delisted_by_date: dict[str, set[str]] = {}
    if not companies_df.empty and "delisted_at" in companies_df.columns:
        for row in companies_df[["ticker", "delisted_at"]].itertuples(index=False):
            t = str(row[0])
            d_at = row[1]
            if d_at:
                norm_d = normalize_date(str(d_at))
                delisted_by_date.setdefault(norm_d, set()).add(t)

    active_delisted_set: set[str] = set()
    is_parked_cd = False

    for _idx, current_date in enumerate(trading_days):
        price_map = price_by_date.get(current_date, {})
        active_desig_map = desigs_by_date.get(current_date, {})

        if current_date in delisted_by_date:
            active_delisted_set.update(delisted_by_date[current_date])
        delisted_tickers = active_delisted_set

        suspended_tickers = {t for t, p in price_map.items() if p <= 0}
        for t, desigs in active_desig_map.items():
            if "거래정지" in desigs:
                suspended_tickers.add(t)

        # 1. In-period liquidation handling for actual positions
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

        # Update shadow portfolio for asset curve filter
        if mode == "asset_curve_ma60":
            # Process shadow liquidation
            shadow_pos_val = sum(qty * price_map.get(t, 0.0) for t, qty in shadow_positions.items())
            shadow_equity = shadow_cash + shadow_pos_val
            shadow_equity_history.append(shadow_equity)

        # 2. Daily CD rate yield if parked in CD ETF
        if is_parked_cd and current_cash > 0:
            daily_cd_yield = cd_returns.get(current_date, 0.0)
            current_cash += current_cash * daily_cd_yield

        # 3. Rebalance check
        if current_date in reb_date_map:
            cached_item = cache.get(current_date)
            selected_df = cached_item["selected_df"] if cached_item else pd.DataFrame()

            # Determine allocation signal
            allow_equity = True
            dt = datetime.strptime(current_date, "%Y-%m-%d")

            if mode == "no_filter":
                allow_equity = True
            elif mode == "seasonality":
                # 11, 12, 1, 2, 3, 4월 -> 주식 투자 (allow_equity = True)
                # 5, 6, 7, 8, 9, 10월 -> CD금리 ETF 파킹 (allow_equity = False)
                # Note: 4월 말일 리밸런싱 때 5월 보유분이 되므로, 5~10월 보유는 4월 말일 매도 후 10월 말일 매수
                # 즉 4월 말일(5월 진입) ~ 9월 말일(10월 진입) 리밸런싱 때는 CD 파킹
                # 10월 말일(11월 진입) ~ 3월 말일(4월 진입) 리밸런싱 때는 주식 투자
                month = dt.month
                if month in [5, 6, 7, 8, 9, 10]:
                    allow_equity = False
                else:
                    allow_equity = True
            elif mode == "kosdaq_ma60":
                # 코스닥 종가 > 60일 이동평균
                close_val = kosdaq_close.get(current_date, 0.0)
                ma60_val = kosdaq_ma60.get(current_date, 0.0)
                allow_equity = close_val >= ma60_val
            elif mode == "kosdaq_ma200":
                # 코스닥 종가 > 200일 이동평균
                close_val = kosdaq_close.get(current_date, 0.0)
                ma200_val = kosdaq_ma200.get(current_date, 0.0)
                allow_equity = close_val >= ma200_val
            elif mode == "asset_curve_ma60":
                # 자체 자산곡선 60일 SMA 추적
                if len(shadow_equity_history) >= 60:
                    sma60 = np.mean(shadow_equity_history[-60:])
                    curr_shadow = shadow_equity_history[-1]
                    allow_equity = curr_shadow >= sma60
                else:
                    allow_equity = True

            # If mode == asset_curve, also update shadow portfolio rebalance
            if mode == "asset_curve_ma60":
                shadow_targets = {}
                if not selected_df.empty:
                    shadow_targets = dict(
                        zip(selected_df["ticker"], selected_df["weight"], strict=False)
                    )
                shadow_res = execute_rebalance(
                    date=current_date,
                    current_cash=shadow_cash,
                    current_positions=shadow_positions,
                    target_weights=shadow_targets,
                    prices=price_map,
                    cost_rate=cost_rate,
                )
                shadow_cash = shadow_res.cash
                shadow_positions = shadow_res.positions

            # Actual portfolio rebalance
            target_weights = {}
            if allow_equity and not selected_df.empty:
                target_weights = dict(
                    zip(selected_df["ticker"], selected_df["weight"], strict=False)
                )
                is_parked_cd = False
            else:
                # Sell all equities and park 100% into CD
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

        # 4. Daily valuation
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
        "mode": mode,
        "metrics": metrics,
        "trades": all_trades,
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
    kosdaq_df = pd.read_csv("data/kq11_daily.csv", index_col=0, parse_dates=True)
    kosdaq_df.index = [d.strftime("%Y-%m-%d") for d in kosdaq_df.index]

    cd_returns = get_cd_daily_return_series(trading_days)

    modes = [
        ("0. 기준 전략 (No Filter, 월별 리밸런싱)", "no_filter"),
        ("1. 계절성 필터 (11-4월 주식, 5-10월 CD금리 ETF)", "seasonality"),
        ("2-A. 코스닥 60일 이평선 모멘텀 필터", "kosdaq_ma60"),
        ("2-B. 코스닥 200일 이평선 모멘텀 필터", "kosdaq_ma200"),
        ("3. 자체 자산곡선 60일 이평선 필터", "asset_curve_ma60"),
    ]

    results = []
    for label, mode in modes:
        logger.info("Executing simulation for: %s...", label)
        res = run_simulation(
            store=store,
            mode=mode,
            cache=cache,
            trading_days=trading_days,
            prices_all=prices_all,
            companies_df=companies_df,
            kosdaq_df=kosdaq_df,
            cd_returns=cd_returns,
        )
        res["label"] = label
        results.append(res)

    md_lines = [
        "# 소형주 성장 가치 퀀트: 모멘텀/계절성 필터링 전략 10.5개년 종합 비교 리포트 (2016.04 - 2026.10)\n",
        "## 전략 개요 및 가설\n",
        "- **0. 기준 전략**: 1안 팩터(시총 하위 20%, 거래대금 제한 없음) 매월 말일 100% 주식 투자",
        "- **1. 계절성 필터**: 11-4월(6개월) 100% 주식, 5-10월(6개월) 100% CD금리 ETF 안전자산 대피",
        "- **2-A. 코스닥 60일 이평**: 매월 말일 코스닥 종가 >= 60일선이면 주식, 미만이면 CD금리 ETF",
        "- **2-B. 코스닥 200일 이평**: 매월 말일 코스닥 종가 >= 200일선이면 주식, 미만이면 CD금리 ETF",
        "- **3. 자체 자산곡선 60일 이평**: 전략 자체 가상 지수 >= 60일 SMA면 주식, 하회 시 CD금리 ETF 대피\n",
        "### 종합 성과 비교 요약표 (10.5개년: 2016.04 - 2026.10)\n",
        "| 전략 구분 | 누적 수익률 | CAGR (연복리) | MDD (최대낙폭) | 샤프지수 | 연간 승률 | 리밸런싱 승률 | 총 거래비용 |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for res in results:
        m = res["metrics"]
        total_fees = sum(t.fee for t in res["trades"])
        md_lines.append(
            f"| **{res['label']}** | **{m.total_return * 100:+.2f}%** | {m.cagr * 100:.2f}% | **{m.mdd * 100:.2f}%** | {m.sharpe_ratio:.2f} | {m.win_rate_yearly * 100:.1f}% | {m.win_rate_rebalance * 100:.1f}% | {int(total_fees):,}원 |"
        )

    md_lines.append("\n### 연도별 수익률 비교\n")
    header = "| 연도 | " + " | ".join(r["label"].split(".")[0] + "번" for r in results) + " |"
    sep = "|:---:| " + " | ".join(":---:" for _ in results) + " |"
    md_lines.append(header)
    md_lines.append(sep)

    years = sorted(results[0]["metrics"].yearly_returns.keys())
    for yr in years:
        row = [f"**{yr}년**"]
        for r in results:
            yret = r["metrics"].yearly_returns.get(yr, 0.0)
            row.append(f"{yret * 100:+.2f}%")
        md_lines.append("| " + " | ".join(row) + " |")

    content_str = "\n".join(md_lines)
    for p in [
        "docs/momentum_filters_backtest_result.md",
        "docs/momentum_filters_10year_backtest_result.md",
    ]:
        with open(p, "w", encoding="utf-8") as f:
            f.write(content_str)

    print("\n" + "=" * 60)
    print(" 모멘텀 필터링 종합 비교 리포트 생성 완료! ")
    print("=" * 60)
    for res in results:
        m = res["metrics"]
        total_fees = sum(t.fee for t in res["trades"])
        print(f"[{res['label']}]")
        print(
            f"  누적: {m.total_return * 100:+.2f}%, CAGR: {m.cagr * 100:.2f}%, MDD: {m.mdd * 100:.2f}%, Sharpe: {m.sharpe_ratio:.2f}"
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
