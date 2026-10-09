"""Run comparative backtest between Monthly rebalancing and Quarterly rebalancing.

Comparing:
1. 사용자 원안 팩트: 월별(Monthly) 리밸런싱 + 시총 하위 20%
2. 사용자 원안 팩트 (거래대금 0원 vs 거래대금 2억): 유동성 필터 유무 차이 비교
3. 기존 분기(Quarterly) 리밸런싱 (시총 하위 20%)
4. 옵션 B 분기(Quarterly) 리밸런싱 (시총 하위 30%)
"""

import logging

from quant_ko.backtest.engine import BacktestEngine
from quant_ko.data.store import DataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_monthly_backtest")


def main():
    store = DataStore("data/quant_ko.db")

    experiments = [
        {
            "title": "원안 팩트: 월별 리밸런싱 (시총 20%, 거래대금 제한없음)",
            "quantile": 0.20,
            "min_tv": 0.0,
            "freq": "monthly",
        },
        {
            "title": "원안 팩트: 월별 리밸런싱 (시총 20%, 거래대금 2억)",
            "quantile": 0.20,
            "min_tv": 200_000_000.0,
            "freq": "monthly",
        },
        {
            "title": "기존 원안: 분기 리밸런싱 (시총 20%, 거래대금 2억)",
            "quantile": 0.20,
            "min_tv": 200_000_000.0,
            "freq": "quarterly",
        },
        {
            "title": "옵션 B: 분기 리밸런싱 (시총 30%, 거래대금 2억)",
            "quantile": 0.30,
            "min_tv": 200_000_000.0,
            "freq": "quarterly",
        },
    ]

    md_output = [
        "# 소형주 성장 가치 퀀트: 월별 vs 분기 리밸런싱 백테스트 비교 리포트 (2019 - 2026.10)\n",
        "## 전략 설정 및 조건 비교 요약\n",
        "- 공통 유니버스: 금융주, 지주사, 관리종목, 중국기업, 스팩, 우선주 제외, 흑자기업(분기 & TTM 2중 필터)\n",
        "- 공통 팩터: 9대 팩터 (낮은 시가총액 + 가치 4개 PER/PSR/POR/PGPR + 성장 4개 순이익/영업익/매출총익/매출액 YoY)\n",
        "- 공통 파라미터: 초기 자본 1,000만 원, 편도 수수료 0.3% (왕복 0.6%), 종목 수 20개 동일비중\n\n",
    ]

    summary_table = [
        "### 종합 성과 비교 요약표\n",
        "| 전략 구분 | 리밸런싱 주기 | 시총 컷 | 거래대금 조건 | 누적 수익률 | CAGR (연복리) | MDD (최대낙폭) | 샤프지수 | 총 거래비용 |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    detail_sections = []

    for exp in experiments:
        logger.info("Starting backtest: %s...", exp["title"])
        engine = BacktestEngine(
            store=store,
            initial_capital=10_000_000.0,
            cost_rate=0.003,
            top_n=20,
            min_trading_value=exp["min_tv"],
            market_cap_quantile=exp["quantile"],
            rebalance_freq=exp["freq"],
        )

        result = engine.run(
            start_date="2019-01-01",
            end_date="2026-10-07",
            benchmark_name="KOSDAQ",
        )

        m = result.metrics
        total_fees = sum(t.fee for t in result.trades)
        logger.info(
            "[%s] Cumulative: %.2f%%, CAGR: %.2f%%, MDD: %.2f%%, Total Fees: %s KRW",
            exp["title"],
            m.total_return * 100,
            m.cagr * 100,
            m.mdd * 100,
            f"{int(total_fees):,}",
        )

        tv_str = "제한없음" if exp["min_tv"] == 0 else f"{int(exp['min_tv'] / 100_000_000)}억 이상"
        freq_str = "매월 말일" if exp["freq"] == "monthly" else "분기 (연 4회)"
        summary_table.append(
            f"| {exp['title']} | {freq_str} | 하위 {int(exp['quantile'] * 100)}% | {tv_str} | **{m.total_return * 100:.2f}%** | {m.cagr * 100:.2f}% | {m.mdd * 100:.2f}% | {m.sharpe_ratio:.2f} | {int(total_fees):,}원 |"
        )

        report_md = result.generate_report(format_type="markdown")
        detail_sections.append(f"\n## [{exp['title']}] 상세 리포트\n")
        detail_sections.append(report_md)
        detail_sections.append("\n### 연도별 상세 수익률")
        detail_sections.append("| 연도 | 연간 수익률 |")
        detail_sections.append("|:---:|:---:|")
        for yr, yret in sorted(m.yearly_returns.items()):
            detail_sections.append(f"| {yr}년 | {yret * 100:.2f}% |")

    md_output.extend(summary_table)
    md_output.extend(detail_sections)

    output_path = "docs/monthly_vs_quarterly_backtest_result.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_output))

    logger.info("All backtests completed! Saved to %s", output_path)


if __name__ == "__main__":
    main()
