"""Run live backtest up to 2026-10-07 and generate latest portfolio report."""

import logging
from quant_ko.data.store import DataStore
from quant_ko.backtest.engine import BacktestEngine
from quant_ko.strategy.universe import filter_universe
from quant_ko.strategy.scoring import score_and_select

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_backtest_2026")

def main():
    store = DataStore("data/quant_ko.db")
    engine = BacktestEngine(
        store=store,
        initial_capital=10_000_000.0,
        cost_rate=0.003, # 편도 0.3%
        top_n=20,
        min_trading_value=200_000_000.0,
        market_cap_quantile=0.20,
    )

    logger.info("Starting backtest (2023-01-01 ~ 2026-10-07)...")
    result = engine.run(
        start_date="2023-01-01",
        end_date="2026-10-07",
    )

    md_report = result.generate_report(format_type="markdown")
    print("\n" + "="*80)
    print("소형주 성장 가치 퀀트 전략 백테스트 성과 리포트 (2023 ~ 2026 현재)")
    print("="*80 + "\n")
    print(md_report)

    # Company name mapping
    comps_df = store.get_companies()
    name_map = dict(zip(comps_df["ticker"], comps_df["name"], strict=False))
    market_map = dict(zip(comps_df["ticker"], comps_df["market"], strict=False))

    # Extract current latest selected portfolio as of 2026-10-07
    logger.info("Extracting latest active portfolio as of 2026-10-07...")
    u_df = filter_universe(
        store=store,
        as_of_date="2026-10-06", # prior trading day
        min_trading_value=200_000_000.0,
        market_cap_quantile=0.20,
    )
    latest_selected = score_and_select(u_df, top_n=20)

    # Save to report file
    with open("docs/backtest_result.md", "w", encoding="utf-8") as f:
        f.write("# 소형주 성장 가치 퀀트 전략 백테스트 결과 (2023 ~ 2026.10 현재)\n\n")
        f.write(md_report)

        f.write("\n\n---\n\n## 3. [최신] 2026년 10월 현재 기준 추천 포트폴리오 (20종목)\n\n")
        if not latest_selected.empty:
            f.write("| 순위 | 종목코드 | 종목명 | 시장 | 시가총액 | 종합순위점수 | 권장비중 |\n")
            f.write("|:---:|:---:|:---|:---:|:---:|:---:|:---:|\n")
            for idx, row in latest_selected.reset_index(drop=True).iterrows():
                t = row["ticker"]
                c_name = name_map.get(t, "알수없음")
                c_mkt = market_map.get(t, "")
                mcap = row.get("market_cap", 0.0) / 1e8
                trank = row.get("total_rank", 0)
                wt = row.get("weight", 0.0) * 100
                f.write(f"| {idx+1} | `{t}` | **{c_name}** | {c_mkt} | {mcap:,.1f}억 원 | {trank}점 | {wt:.1f}% |\n")
        else:
            f.write("현재 필터를 통과한 추천 종목이 없습니다 (현금 100% 보유 권장).\n")

        f.write("\n\n---\n\n## 4. 리밸런싱 회차별 실행 내역\n")
        for rec in result.rebalance_records:
            date = rec.get("date")
            turnover = rec.get("turnover_rate", 0.0) * 100
            f.write(f"\n#### [{date}] 리밸런싱\n")
            f.write(f"- 포트폴리오 회전율: {turnover:.1f}%\n")
            f.write(f"- 잔여 현금: {rec.get('cash', 0):,.0f}원\n")
            trades = rec.get("trades", [])
            if trades:
                f.write("- 체결 거래 목록:\n")
                for t in trades:
                    side_kr = "매수" if t.side == "BUY" else "매도"
                    c_name = name_map.get(t.ticker, "알수없음")
                    c_mkt = market_map.get(t.ticker, "")
                    f.write(f"  - [{side_kr}] **{c_name}** (`{t.ticker}` / {c_mkt}) | {t.shares:,}주 @ {t.price:,.0f}원 (수수료: {t.fee:,.0f}원)\n")
            else:
                f.write("- 매매 내역 없음\n")

    logger.info("Complete! Updated report saved to docs/backtest_result.md")

if __name__ == "__main__":
    main()
