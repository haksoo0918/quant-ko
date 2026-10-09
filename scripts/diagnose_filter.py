import pandas as pd

from quant_ko.data.store import DataStore
from quant_ko.pit.builder import PITSnapshotBuilder

store = DataStore("data/quant_ko.db")
as_of = "2026-10-06"
dt_str = "20261006"

comps = store.get_companies()
prices = store.get_daily_prices(end_date=as_of)

latest_prices = []
for ticker, grp in prices.groupby("ticker"):
    s = grp.sort_values("date")
    last_row = s.iloc[-1]
    last_20 = s.tail(20)
    avg_val = last_20["trading_value"].mean()
    latest_prices.append(
        {
            "ticker": ticker,
            "market_cap": last_row["market_cap"],
            "trading_value_20d_avg": avg_val,
            "close": last_row["close"],
        }
    )
p_df = pd.DataFrame(latest_prices)

merged = comps.merge(p_df, on="ticker", how="inner")
cap_cut = merged["market_cap"].quantile(0.20)
bottom_20 = merged[merged["market_cap"] <= cap_cut].copy()
print(f"1. 전체 시총 하위 20% 후보: {len(bottom_20)}개")

builder = PITSnapshotBuilder(store)
corp_codes = bottom_20["corp_code"].dropna().unique().tolist()
pit_df = builder.build_snapshot(as_of_date=dt_str, corp_codes=corp_codes)
f_df = bottom_20.merge(pit_df, on="corp_code", how="inner")
print(f"2. PIT 재무제표가 존재하는 종목: {len(f_df)}개")

# Profitability condition
prof = f_df[
    (f_df["op_income_quarter"] > 0)
    & (f_df["net_income_owner_quarter"] > 0)
    & (f_df["op_income_ttm"] > 0)
    & (f_df["net_income_owner_ttm"] > 0)
]
print(f"3. [분기 AND TTM 모두 흑자]인 종목: {len(prof)}개")

print("\n--- 3번 흑자 통과 종목 5개의 세부 지표 ---")
for _, r in prof.iterrows():
    val_e8 = r["trading_value_20d_avg"] / 1e8
    t_code = r.get("ticker_x") or r.get("ticker")
    print(
        f"- {r['name']} ({t_code}): 거래대금={val_e8:.2f}억, 부채비율={r['debt_ratio']:.1f}%, 자본잠식률={r['impairment_ratio']:.1f}%"
    )
