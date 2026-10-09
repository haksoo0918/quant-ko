"""Compare baseline vs Option A (Liquidity 50M) vs Option B (Quantile 30%) vs Option A+B."""

import logging

from quant_ko.backtest.engine import BacktestEngine
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_experiment():
    store = DataStore("data/quant_ko.db")
    start_date = "2023-01-01"
    end_date = "2026-10-07"

    configs = [
        {
            "name": "기준 원안 (하위 20% + 거래대금 2억)",
            "quantile": 0.20,
            "min_tv": 200_000_000.0,
        },
        {
            "name": "옵션 A (거래대금 5천만 원 완화)",
            "quantile": 0.20,
            "min_tv": 50_000_000.0,
        },
        {
            "name": "옵션 B (시총 하위 30% 확대)",
            "quantile": 0.30,
            "min_tv": 200_000_000.0,
        },
        {
            "name": "옵션 A+B (하위 30% + 거래대금 5천만 원)",
            "quantile": 0.30,
            "min_tv": 50_000_000.0,
        },
    ]

    results = []
    for cfg in configs:
        print(f"\n실행 중: {cfg['name']}...")
        engine = BacktestEngine(
            store=store,
            initial_capital=10_000_000.0,
            cost_rate=0.003,
            top_n=20,
            min_trading_value=cfg["min_tv"],
            market_cap_quantile=cfg["quantile"],
        )
        res = engine.run(start_date=start_date, end_date=end_date)
        m = res.metrics
        results.append(
            {
                "name": cfg["name"],
                "cum_ret": m.total_return * 100,
                "cagr": m.cagr * 100,
                "mdd": m.mdd * 100,
                "vol": m.annualized_volatility * 100,
                "sharpe": m.sharpe_ratio,
                "turnover": m.avg_turnover_rate * 100,
                "final_equity": m.final_equity,
                "records": res.rebalance_records,
            }
        )

    # Summary Table
    print("\n" + "=" * 95)
    print("4개 설정 비교 백테스트 결과 (2023-01-01 - 2026-10-07)")
    print("=" * 95)
    header = f"| {'전략 설정':<32} | {'누적수익률':<10} | {'CAGR':<8} | {'MDD':<8} | {'샤프':<6} | {'평균종목수':<8} |"
    print(header)
    print(
        "|"
        + "-" * 34
        + "|"
        + "-" * 12
        + "|"
        + "-" * 10
        + "|"
        + "-" * 10
        + "|"
        + "-" * 8
        + "|"
        + "-" * 12
        + "|"
    )

    md_lines = [
        "# 소형주 퀀트 필터 완화 실험 비교 리포트 (2023 - 2026.10)\n",
        "| 전략 설정 | 누적수익률 | CAGR | MDD | 샤프 지수 | 평균 보유 종목수 | 최종 평가액 |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for r in results:
        # Calculate average stock count across rebalances
        counts = [rec.get("target_count", 0) for rec in r["records"]]
        avg_count = sum(counts) / len(counts) if counts else 0
        latest_count = counts[-1] if counts else 0
        line = f"| {r['name']:<32} | {r['cum_ret']:>9.2f}% | {r['cagr']:>7.2f}% | {r['mdd']:>7.2f}% | {r['sharpe']:>6.2f} | {avg_count:>4.1f}개 (최근{latest_count}개) |"
        print(line)
        md_lines.append(
            f"| **{r['name']}** | **{r['cum_ret']:.2f}%** | {r['cagr']:.2f}% | {r['mdd']:.2f}% | {r['sharpe']:.2f} | {avg_count:.1f}개 (최근 {latest_count}개) | {r['final_equity']:,.0f}원 |"
        )

    # Save to markdown report
    with open("docs/filter_comparison_result.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    print("\n결과 보고서 저장 완료: docs/filter_comparison_result.md")


if __name__ == "__main__":
    run_experiment()
