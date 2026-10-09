"""Run live backtest on collected database and print report."""

import logging

from quant_ko.backtest.engine import BacktestEngine
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_backtest")


def main():
    store = DataStore("data/quant_ko.db")
    engine = BacktestEngine(
        store=store,
        initial_capital=10_000_000.0,
        cost_rate=0.003,  # 편도 0.3%
        top_n=20,
        min_trading_value=200_000_000.0,  # 2억 원
        market_cap_quantile=0.20,
    )

    logger.info("Starting backtest (2023-01-01 ~ 2024-12-31)...")
    result = engine.run(
        start_date="2023-01-01",
        end_date="2024-12-31",
    )

    md_report = result.generate_report(format_type="markdown")
    print("\n" + "=" * 80)
    print("소형주 성장 가치 퀀트 전략 백테스트 성과 리포트")
    print("=" * 80 + "\n")
    print(md_report)

    # Company name mapping
    comps_df = store.get_companies()
    name_map = dict(zip(comps_df["ticker"], comps_df["name"], strict=False))
    market_map = dict(zip(comps_df["ticker"], comps_df["market"], strict=False))

    # Save to report file
    with open("docs/backtest_result.md", "w", encoding="utf-8") as f:
        f.write("# 소형주 성장 가치 퀀트 전략 백테스트 결과 (2023~2024)\n\n")
        f.write(md_report)
        f.write("\n\n### 리밸런싱 회차별 실행 내역\n")
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
                    f.write(
                        f"  - [{side_kr}] **{c_name}** (`{t.ticker}` / {c_mkt}) | {t.shares:,}주 @ {t.price:,.0f}원 (수수료: {t.fee:,.0f}원)\n"
                    )
            else:
                f.write("- 매매 내역 없음\n")

    logger.info("Backtest complete! Report saved to docs/backtest_result.md")


if __name__ == "__main__":
    main()
