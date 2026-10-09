"""Run single backtest: 1안 팩터 (시총 하위 20%, 거래대금 제한없음) + 리밸런싱 분기(Quarterly).

비교 목적:
- 1안 월별 (시총 20%, 거래대금 제한없음) vs 1안 분기 (시총 20%, 거래대금 제한없음)
"""

import logging

from quant_ko.backtest.engine import BacktestEngine
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_plan1_quarterly")


def main():
    store = DataStore("data/quant_ko.db")

    logger.info("Starting backtest: 1안 분기 리밸런싱 (시총 20%, 거래대금 제한없음)...")
    engine = BacktestEngine(
        store=store,
        initial_capital=10_000_000.0,
        cost_rate=0.003,
        top_n=20,
        min_trading_value=0.0,  # 거래대금 제한 없음
        market_cap_quantile=0.20,  # 시총 하위 20%
        rebalance_freq="quarterly",  # 분기 리밸런싱
    )

    result = engine.run(
        start_date="2019-01-01",
        end_date="2026-10-07",
        benchmark_name="KOSDAQ",
    )

    m = result.metrics
    total_fees = sum(t.fee for t in result.trades)

    logger.info(
        "Cumulative: %.2f%%, CAGR: %.2f%%, MDD: %.2f%%, Sharpe: %.2f, Total Fees: %s KRW",
        m.total_return * 100,
        m.cagr * 100,
        m.mdd * 100,
        m.sharpe_ratio,
        f"{int(total_fees):,}",
    )

    print("\n" + "=" * 50)
    print(" [1안 분기 리밸런싱 (시총 20%, 거래대금 제한없음)] 결과 ")
    print("=" * 50)
    print(f"누적 수익률   : {m.total_return * 100:.2f}%")
    print(f"CAGR (연복리) : {m.cagr * 100:.2f}%")
    print(f"MDD (최대낙폭): {m.mdd * 100:.2f}%")
    print(f"샤프지수      : {m.sharpe_ratio:.2f}")
    print(f"총 거래비용   : {int(total_fees):,} 원")
    print("\n연도별 수익률:")
    for yr, yret in sorted(m.yearly_returns.items()):
        print(f"  {yr}년: {yret * 100:+.2f}%")
    print("=" * 50)


if __name__ == "__main__":
    main()
