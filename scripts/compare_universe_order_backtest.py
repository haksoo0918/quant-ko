"""Fast in-memory 10.5-year backtest & 2026-10-23 portfolio extraction comparison:
Comparing Market Cap Bottom 20% Cut Order (Before vs After Financial Filters)
and Profitability Filter (TTM only vs TTM + Single Quarter).

Runs 100% offline against local data/quant_ko.db inside the sandbox.
"""

import sys
import time
from datetime import datetime
from typing import Any

import pandas as pd

from quant_ko.backtest.calendar import get_cd_daily_return_series, get_rebalance_schedule
from quant_ko.backtest.engine import EventTracker, execute_rebalance
from quant_ko.backtest.metrics import calculate_metrics
from quant_ko.data.krx import (
    is_chinese_company,
    is_holding_or_financial,
    is_preferred_stock,
    is_spac,
    normalize_date,
)
from quant_ko.data.store import DataStore
from quant_ko.pit.builder import BS_METRICS, INCOME_METRICS
from quant_ko.strategy.scoring import score_and_select

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

QUANTUS_CSV_TICKERS = {
    "002880": "디와이에이",
    "021050": "서원",
    "378850": "화승알앤에이",
    "017650": "대림제지",
    "017000": "신원종합개발",
    "318020": "포인트모바일",
    "050860": "아세아텍",
    "115480": "씨유메디칼",
    "053270": "구영테크",
    "090080": "평화산업",
    "060380": "동양에스텍",
    "227950": "엔투텍",
    "128540": "에코캡",
    "310870": "디와이씨",
    "045060": "오공",
    "105760": "포스뱅크",
    "052790": "액토즈소프트",
    "115570": "스타플렉스",
    "090150": "아이윈",
    "263020": "디케이앤디",
}


class FastInMemoryPIT:
    """In-memory equivalent of PITSnapshotBuilder to avoid 60,000+ SQLite queries."""

    def __init__(self, fin_df: pd.DataFrame, code_to_ticker: dict[str, str]) -> None:
        self.code_to_ticker = code_to_ticker
        df = fin_df.copy()
        df["rcept_dt_clean"] = df["rcept_dt"].astype(str).str.replace("-", "").str.strip()
        df = df.sort_values("rcept_dt_clean", ascending=True)
        self.by_corp: dict[str, list[dict[str, Any]]] = {}
        for rec in df.to_dict("records"):
            c = str(rec["corp_code"])
            self.by_corp.setdefault(c, []).append(rec)

    def _get_discrete(
        self, filings: dict[tuple[int, int], dict[str, Any]], fy: int, qtr: int
    ) -> dict[str, float | None] | None:
        if (fy, qtr) not in filings:
            return None
        f = filings[(fy, qtr)]
        disc: dict[str, float | None] = {}
        if qtr in (1, 2, 3):
            for m in INCOME_METRICS:
                v = f.get(m)
                disc[m] = float(v) if v is not None and pd.notna(v) else None
            return disc
        for m in INCOME_METRICS:
            ann = f.get(m)
            if ann is None or pd.isna(ann):
                disc[m] = None
                continue
            psum = 0.0
            found = False
            for q in (1, 2, 3):
                if (fy, q) in filings:
                    qv = filings[(fy, q)].get(m)
                    if qv is not None and pd.notna(qv):
                        psum += float(qv)
                        found = True
            disc[m] = (float(ann) - psum) if found else float(ann)
        return disc

    def build_snapshot(self, cutoff_dt: str, corp_codes: list[str]) -> pd.DataFrame:
        cutoff = cutoff_dt.replace("-", "").strip()
        rows = []
        for c in corp_codes:
            recs = self.by_corp.get(c)
            if not recs:
                continue
            valid = [r for r in recs if r["rcept_dt_clean"] <= cutoff]
            if not valid:
                continue
            # Group by (fiscal_year, quarter), prefer CFS over OFS, latest rcept_dt
            filings: dict[tuple[int, int], dict[str, Any]] = {}
            by_yq: dict[tuple[int, int], list[dict[str, Any]]] = {}
            for r in valid:
                key = (int(r["fiscal_year"]), int(r["quarter"]))
                by_yq.setdefault(key, []).append(r)
            for key, grp in by_yq.items():
                cfs = [x for x in grp if x.get("fs_type") == "CFS"]
                filings[key] = cfs[-1] if cfs else grp[-1]

            skeys = sorted(filings.keys())
            ly, lq = skeys[-1]
            lf = filings[(ly, lq)]
            ldisc = self._get_discrete(filings, ly, lq)
            if not ldisc:
                continue

            res: dict[str, Any] = {
                "corp_code": c,
                "fiscal_year": ly,
                "quarter": lq,
                "rcept_dt": str(lf.get("rcept_dt", "")),
                "fs_type": lf.get("fs_type", ""),
            }
            for m in INCOME_METRICS:
                res[f"{m}_quarter"] = ldisc.get(m)
                res[m] = ldisc.get(m)

            q_seq = []
            cy, cq = ly, lq
            for _ in range(4):
                q_seq.append((cy, cq))
                if cq > 1:
                    cq -= 1
                else:
                    cy -= 1
                    cq = 4

            for m in INCOME_METRICS:
                tvals = []
                for y, q in q_seq:
                    d = self._get_discrete(filings, y, q)
                    if d and d.get(m) is not None:
                        tvals.append(d[m])
                res[f"{m}_ttm"] = sum(tvals) if tvals else None

            pdisc = self._get_discrete(filings, ly - 1, lq)
            for m in INCOME_METRICS:
                lval = ldisc.get(m)
                pval = pdisc.get(m) if pdisc else None
                if lval is not None and pval is not None:
                    is_ta = bool(pval <= 0 and lval > 0)
                    if abs(pval) > 0:
                        yoy = (lval - pval) / abs(pval)
                    elif lval > 0:
                        yoy = float("inf")
                    elif lval == 0:
                        yoy = 0.0
                    else:
                        yoy = -1.0
                    res[f"{m}_yoy"] = yoy
                    res[f"{m}_turnaround"] = is_ta
                else:
                    res[f"{m}_yoy"] = None
                    res[f"{m}_turnaround"] = False

            for bs in BS_METRICS:
                v = lf.get(bs)
                res[bs] = float(v) if v is not None and pd.notna(v) else None

            te = res.get("total_equity")
            tl = res.get("total_liabilities")
            cs = res.get("capital_stock")
            if te is not None and te > 0:
                res["debt_ratio"] = (tl / te) * 100.0 if tl is not None else 0.0
            elif te is not None and te <= 0:
                res["debt_ratio"] = float("inf")
            else:
                res["debt_ratio"] = None

            if cs is not None and cs > 0 and te is not None:
                res["impairment_ratio"] = ((cs - te) / cs) * 100.0
            else:
                res["impairment_ratio"] = 0.0

            rows.append(res)
        return pd.DataFrame(rows)


def run_backtest_sim(
    trading_days: list[str],
    reb_date_map: dict,
    selections_by_date: dict[str, pd.DataFrame],
    price_by_date: dict[str, dict[str, float]],
    desigs_by_date: dict[str, dict[str, set[str]]],
    delisted_by_date: dict[str, set[str]],
    cd_returns: pd.Series,
    seasonality: bool = True,
    initial_capital: float = 10_000_000.0,
    cost_rate: float = 0.003,
):
    current_cash = float(initial_capital)
    current_positions: dict[str, int] = {}
    equity_records: list[dict] = []
    rebalance_records: list[dict] = []
    event_tracker = EventTracker()
    active_delisted_set: set[str] = set()
    is_parked_cd = False

    for current_date in trading_days:
        price_map = price_by_date.get(current_date, {})
        active_desig_map = desigs_by_date.get(current_date, {})
        if current_date in delisted_by_date:
            active_delisted_set.update(delisted_by_date[current_date])
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
            delisted_tickers=active_delisted_set,
            cost_rate=cost_rate,
        )

        if is_parked_cd and current_cash > 0:
            current_cash += current_cash * cd_returns.get(current_date, 0.0)

        if current_date in reb_date_map:
            selected_df = selections_by_date.get(current_date, pd.DataFrame())
            dt = datetime.strptime(current_date, "%Y-%m-%d")
            allow_equity = (dt.month not in [5, 6, 7, 8, 9, 10]) if seasonality else True

            target_weights = {}
            if allow_equity and not selected_df.empty:
                target_weights = dict(
                    zip(selected_df["ticker"], selected_df["weight"], strict=False)
                )
                is_parked_cd = False
            else:
                target_weights = {}
                is_parked_cd = seasonality

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
                    "trades_count": len(reb_res.trades),
                    "turnover_rate": reb_res.turnover_rate,
                }
            )

        pos_val = sum(qty * price_map.get(t, 0.0) for t, qty in current_positions.items())
        equity_records.append({"date": current_date, "equity": current_cash + pos_val})

    eq_df = pd.DataFrame(equity_records)
    return calculate_metrics(
        equity_history=eq_df, rebalance_records=rebalance_records, initial_capital=initial_capital
    )


def main() -> None:
    t_start = time.time()
    store = DataStore("data/quant_ko.db")
    companies_df = store.get_companies()
    fin_df = store.get_financials()
    prices_all = store.get_daily_prices(start_date="2016-01-01", end_date="2026-10-23")
    desigs_all = store.get_designations()

    print(
        f"Loaded DB in {time.time() - t_start:.2f}s: "
        f"companies={len(companies_df)}, financials={len(fin_df)}, prices={len(prices_all)}"
    )

    # Filter base valid companies
    valid_rows = []
    for _, row in companies_df.iterrows():
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
        valid_rows.append(row.to_dict())
    base_cand_df = pd.DataFrame(valid_rows)
    code_to_ticker = (
        base_cand_df.dropna(subset=["corp_code"])
        .drop_duplicates(subset=["corp_code"])
        .set_index("corp_code")["ticker"]
        .to_dict()
    )
    fast_pit = FastInMemoryPIT(fin_df, code_to_ticker)

    # Index prices by ticker for fast as-of lookup
    prices_sorted = prices_all.sort_values(["ticker", "date"], ascending=[True, True])
    ticker_price_groups: dict[str, pd.DataFrame] = {
        str(t): grp for t, grp in prices_sorted.groupby("ticker", sort=False)
    }

    trading_days = sorted(prices_all["date"].dropna().unique().tolist())
    bt_days = [d for d in trading_days if "2016-04-01" <= d <= "2026-10-08"]
    events = get_rebalance_schedule(
        bt_days, start_date=bt_days[0], end_date=bt_days[-1], rebalance_freq="monthly"
    )
    reb_date_map = {e.rebalance_date: e for e in events}

    # Check how many companies have historical prices on a typical rebalance date (e.g., 2023-10-31)
    # vs 2026-10-23
    def get_merged_with_pit(as_of_date: str) -> pd.DataFrame:
        norm_date = normalize_date(as_of_date)
        # Filter listed_at / delisted_at
        cands = base_cand_df.copy()
        if "delisted_at" in cands.columns:
            cands = cands[
                cands["delisted_at"].isna()
                | (cands["delisted_at"].astype(str).str.slice(0, 10) > norm_date)
            ]
        if "listed_at" in cands.columns:
            cands = cands[
                cands["listed_at"].isna()
                | (cands["listed_at"].astype(str).str.slice(0, 10) <= norm_date)
            ]

        p_rows = []
        for t in cands["ticker"]:
            grp = ticker_price_groups.get(str(t))
            if grp is None:
                continue
            sub = grp[grp["date"] <= norm_date]
            if sub.empty:
                continue
            last = sub.iloc[-1]
            p_rows.append(
                {
                    "ticker": str(t),
                    "price_date": last["date"],
                    "close": float(last["close"]),
                    "market_cap": float(last["market_cap"]),
                }
            )
        if not p_rows:
            return pd.DataFrame()
        p_df = pd.DataFrame(p_rows)
        merged = pd.merge(cands, p_df, on="ticker", how="inner")
        corp_codes = merged["corp_code"].dropna().unique().tolist()
        pit_df = fast_pit.build_snapshot(norm_date, corp_codes)
        if pit_df.empty:
            return pd.DataFrame()
        return pd.merge(merged, pit_df, on="corp_code", how="inner")

    # 1. Inspect 2026-10-23 (latest date) under:
    #    - Order A: Cut bottom 20% of ALL valid KRX stocks FIRST (<= 386.8억), then apply TTM profit
    #    - Order B: Apply TTM profit FIRST, then cut bottom 20% of profitable stocks (or compare cutoff)
    df_1023 = get_merged_with_pit("2026-10-23")
    # Also get all 2,274 valid KRX stocks' market cap on 2026-10-23 for exact quantile reference
    p_1023 = prices_all[prices_all["date"] == "2026-10-23"]
    all_valid_1023 = pd.merge(base_cand_df, p_1023, on="ticker", how="inner")
    raw_20_cutoff = all_valid_1023["market_cap"].quantile(0.20)

    # Apply impairment <= 0 & TTM profit > 0
    prof_1023 = df_1023[
        (df_1023["impairment_ratio"].notna())
        & (df_1023["impairment_ratio"] <= 0.0)
        & (df_1023["op_income_ttm"] > 0)
        & (df_1023["net_income_owner_ttm"] > 0)
    ].copy()

    u_order_a = prof_1023[prof_1023["market_cap"] <= raw_20_cutoff].copy()
    # What if we cut at ~520억 (which is bottom 20% of profitable stocks in KRX: ~1,400 profitable stocks * 0.20 = ~280 stocks -> ~520억)?
    # Let's check how many profitable stocks exist up to 520억 vs raw_20_cutoff:
    u_order_b_520 = prof_1023[prof_1023["market_cap"] <= 520e8].copy()

    s_order_a = score_and_select(u_order_a, top_n=20)
    s_order_b = score_and_select(u_order_b_520, top_n=20)
    q_set = set(QUANTUS_CSV_TICKERS.keys())

    print("\n" + "=" * 85)
    print(" [1] 2026-10-23 기준 시총 하위 20% 절삭 순서 비교 (Order A vs Order B)")
    print("=" * 85)
    print(
        f" - Order A (전체 상장사 하위 20% 선절삭 <= {raw_20_cutoff/1e8:.1f}억 ➔ TTM 흑자): "
        f"통과 {len(u_order_a)}종목 | 퀀터스 Top 20 일치: {len(set(s_order_a['ticker']) & q_set)}/20"
    )
    print(
        f" - Order B (재무/흑자 필터 선적용 ➔ 흑자기업 하위 20% <= 520.0억): "
        f"통과 {len(u_order_b_520)}종목 | 퀀터스 Top 20 일치: {len(set(s_order_b['ticker']) & q_set)}/20"
    )

    # 2. Check historical backtest (2016-04 ~ 2026-10)
    # Note: In historical DB (2016-2026), how many stocks have prices on each rebalance date?
    sample_counts = []
    for ev in events[::12]:
         norm_d = normalize_date(ev.prior_date)
         cnt = prices_all[prices_all["date"] == norm_d]["ticker"].nunique()
         sample_counts.append((ev.prior_date, cnt))
    print("\n[Historical DB Daily Price Ticker Counts by Year]:", sample_counts)

    # Build monthly selections across 127 events for:
    # 1) TTM + Quarter Profit (require_quarter_profit=True)
    # 2) TTM Profit Only (require_quarter_profit=False)
    sel_ttm_and_qtr: dict[str, pd.DataFrame] = {}
    sel_ttm_only: dict[str, pd.DataFrame] = {}

    t_bt = time.time()
    for ev in events:
        df_m = get_merged_with_pit(ev.prior_date)
        if df_m.empty:
            sel_ttm_and_qtr[ev.rebalance_date] = pd.DataFrame()
            sel_ttm_only[ev.rebalance_date] = pd.DataFrame()
            continue

        # Base impairment & TTM profit
        cond_base = (
            (df_m["impairment_ratio"].notna())
            & (df_m["impairment_ratio"] <= 0.0)
            & (df_m["op_income_ttm"] > 0)
            & (df_m["net_income_owner_ttm"] > 0)
        )
        u_ttm = df_m[cond_base].copy()
        sel_ttm_only[ev.rebalance_date] = (
            score_and_select(u_ttm, top_n=20) if not u_ttm.empty else pd.DataFrame()
        )

        cond_qtr = (u_ttm["op_income_quarter"] > 0) & (u_ttm["net_income_owner_quarter"] > 0)
        u_qtr = u_ttm[cond_qtr].copy()
        sel_ttm_and_qtr[ev.rebalance_date] = (
            score_and_select(u_qtr, top_n=20) if not u_qtr.empty else pd.DataFrame()
        )

    print(f"Built 127 monthly PIT snapshots & factor rankings in {time.time() - t_bt:.2f}s!")

    price_by_date: dict[str, dict[str, float]] = {}
    for row in prices_all[["date", "ticker", "close"]].itertuples(index=False):
        d, t, c = str(row[0]), str(row[1]), float(row[2]) if row[2] is not None else 0.0
        price_by_date.setdefault(d, {})[t] = c

    desigs_by_date: dict[str, dict[str, set[str]]] = {}
    if not desigs_all.empty:
        for row in desigs_all[["date", "ticker", "type"]].itertuples(index=False):
            desigs_by_date.setdefault(str(row[0]), {}).setdefault(str(row[1]), set()).add(
                str(row[2])
            )

    delisted_by_date: dict[str, set[str]] = {}
    if not companies_df.empty and "delisted_at" in companies_df.columns:
        for row in companies_df[["ticker", "delisted_at"]].itertuples(index=False):
            if row[1]:
                delisted_by_date.setdefault(normalize_date(str(row[1])), set()).add(str(row[0]))

    cd_returns = get_cd_daily_return_series(bt_days)

    m_seas_qtr = run_backtest_sim(
        bt_days, reb_date_map, sel_ttm_and_qtr, price_by_date, desigs_by_date, delisted_by_date, cd_returns, seasonality=True
    )
    m_seas_ttm = run_backtest_sim(
        bt_days, reb_date_map, sel_ttm_only, price_by_date, desigs_by_date, delisted_by_date, cd_returns, seasonality=True
    )
    m_std_qtr = run_backtest_sim(
        bt_days, reb_date_map, sel_ttm_and_qtr, price_by_date, desigs_by_date, delisted_by_date, cd_returns, seasonality=False
    )
    m_std_ttm = run_backtest_sim(
        bt_days, reb_date_map, sel_ttm_only, price_by_date, desigs_by_date, delisted_by_date, cd_returns, seasonality=False
    )

    print("\n" + "=" * 85)
    print(f" [2] 10.5개년 백테스트 결과 ({bt_days[0]} ~ {bt_days[-1]}, 부채비율 제한 없음)")
    print("=" * 85)
    print(
        f"1. 계절성(11~4월) + [TTM + 단일분기 흑자]: "
        f"누적 {m_seas_qtr.total_return*100:+6.2f}% | CAGR {m_seas_qtr.cagr*100:5.2f}% | "
        f"MDD {m_seas_qtr.mdd*100:6.2f}% | Sharpe {m_seas_qtr.sharpe_ratio:4.2f} | 연승률 {m_seas_qtr.win_rate_yearly*100:4.1f}%"
    )
    print(
        f"2. 계절성(11~4월) + [TTM 흑자만 (퀀터스)] : "
        f"누적 {m_seas_ttm.total_return*100:+6.2f}% | CAGR {m_seas_ttm.cagr*100:5.2f}% | "
        f"MDD {m_seas_ttm.mdd*100:6.2f}% | Sharpe {m_seas_ttm.sharpe_ratio:4.2f} | 연승률 {m_seas_ttm.win_rate_yearly*100:4.1f}%"
    )
    print(
        f"3. 상시보유(1~12월) + [TTM + 단일분기 흑자]: "
        f"누적 {m_std_qtr.total_return*100:+6.2f}% | CAGR {m_std_qtr.cagr*100:5.2f}% | "
        f"MDD {m_std_qtr.mdd*100:6.2f}% | Sharpe {m_std_qtr.sharpe_ratio:4.2f} | 연승률 {m_std_qtr.win_rate_yearly*100:4.1f}%"
    )
    print(
        f"4. 상시보유(1~12월) + [TTM 흑자만 (퀀터스)] : "
        f"누적 {m_std_ttm.total_return*100:+6.2f}% | CAGR {m_std_ttm.cagr*100:5.2f}% | "
        f"MDD {m_std_ttm.mdd*100:6.2f}% | Sharpe {m_std_ttm.sharpe_ratio:4.2f} | 연승률 {m_std_ttm.win_rate_yearly*100:4.1f}%"
    )
    print("=" * 85)


if __name__ == "__main__":
    main()
