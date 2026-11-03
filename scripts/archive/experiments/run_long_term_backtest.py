"""Run comprehensive 8-year backtest (2019-01-01 ~ 2026-10-07)."""

import logging

from quant_ko.backtest.engine import BacktestEngine
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_8year_backtest")


def main():
    store = DataStore("data/quant_ko.db")

    # We will test both the Original baseline (20% cap cut) and the Optimized Option B (30% cap cut)
    experiments = [
        {
            "title": "기준 원안 (시총 하위 20% + 거래대금 2억)",
            "quantile": 0.20,
            "min_tv": 200_000_000.0,
        },
        {
            "title": "옵션 B (시총 하위 30% + 거래대금 2억)",
            "quantile": 0.30,
            "min_tv": 200_000_000.0,
        },
    ]

    md_output = ["# 소형주 성장 가치 퀀트 전략 8개년 장기 백테스트 결과 (2019 - 2026.10)\n"]

    for exp in experiments:
        logger.info("Starting 8-year backtest: %s...", exp["title"])
        engine = BacktestEngine(
            store=store,
            initial_capital=10_000_000.0,
            cost_rate=0.003,  # 편도 0.3%
            top_n=20,
            min_trading_value=exp["min_tv"],
            market_cap_quantile=exp["quantile"],
        )

        # 2018 is warm-up for YoY/TTM; trading begins in 2019
        result = engine.run(
            start_date="2019-01-01",
            end_date="2026-10-07",
            benchmark_name="KOSDAQ",
        )

        md_report = result.generate_report(format_type="markdown")
        logger.info("Completed: %s", exp["title"])

        md_output.append(f"\n## [{exp['title']}] 성과 리포트\n")
        md_output.append(md_report)
        md_output.append("\n### 연도별 상세 수익률")
        md_output.append("| 연도 | 연간 수익률 |")
        md_output.append("|:---:|:---:|")
        for yr, yret in sorted(result.metrics.yearly_returns.items()):
            md_output.append(f"| {yr}년 | {yret * 100:.2f}% |")

    with open("docs/long_term_backtest_result.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_output) + "\n")

    logger.info("8-year long-term backtest saved to docs/long_term_backtest_result.md")


if __name__ == "__main__":
    main()
