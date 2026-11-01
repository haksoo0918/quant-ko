"""백테스트 성과 분석 보고서 생성 모듈 (마크다운 및 터미널 텍스트 형식)."""

from typing import Literal

from quant_ko.backtest.metrics import BenchmarkComparison, PerformanceMetrics


def _format_pct(val: float | None) -> str:
    """비율 수치를 백분율 문자열(%)로 포맷팅합니다."""
    if val is None:
        return "N/A"
    return f"{val * 100:.2f}%"


def _format_krw(val: float | None) -> str:
    """금액 수치를 원화(KRW) 문자열로 포맷팅합니다."""
    if val is None:
        return "N/A"
    return f"{val:,.0f} KRW"


def generate_report(
    metrics: PerformanceMetrics,
    benchmarks: list[BenchmarkComparison] | None = None,
    title: str = "Backtest Performance Report",
    format_type: Literal["markdown", "text"] = "markdown",
) -> str:
    """백테스트 성과 요약 보고서를 마크다운 또는 텍스트 형식으로 생성합니다.

    Args:
        metrics: 산출된 포트폴리오 성과 지표 객체.
        benchmarks: 비교 대상 벤치마크 지수 결과 목록 (선택 사항).
        title: 보고서 제목 (기본값: "Backtest Performance Report").
        format_type: 출력 포맷 ("markdown" 또는 "text", 기본값: "markdown").

    Returns:
        포맷팅된 성과 보고서 문자열.
    """
    benchmarks = benchmarks or []

    if format_type == "markdown":
        lines: list[str] = [
            f"# {title}",
            "",
            "## 1. Portfolio Overview",
            "| Metric | Portfolio |",
            "|---|---|",
            f"| Initial Capital | {_format_krw(metrics.initial_capital)} |",
            f"| Final Equity | {_format_krw(metrics.final_equity)} |",
            f"| Total Cumulative Return | {_format_pct(metrics.total_return)} |",
            f"| CAGR | {_format_pct(metrics.cagr)} |",
            f"| Maximum Drawdown (MDD) | {_format_pct(metrics.mdd)} |",
            f"| MDD Peak Date | {metrics.mdd_peak_date or 'N/A'} |",
            f"| MDD Trough Date | {metrics.mdd_trough_date or 'N/A'} |",
            f"| Annualized Volatility | {_format_pct(metrics.annualized_volatility)} |",
            f"| Sharpe Ratio (Rf=3.5%) | {metrics.sharpe_ratio:.2f} |",
            f"| Win Rate (Rebalance) | {_format_pct(metrics.win_rate_rebalance)} |",
            f"| Win Rate (Yearly) | {_format_pct(metrics.win_rate_yearly)} |",
            f"| Average Turnover Rate | {_format_pct(metrics.avg_turnover_rate)} |",
            "",
        ]

        if metrics.yearly_returns:
            lines.extend(
                [
                    "## 2. Calendar Year Returns",
                    "| Year | Return |",
                    "|---|---|",
                ]
            )
            for yr, ret in sorted(metrics.yearly_returns.items()):
                lines.append(f"| {yr} | {_format_pct(ret)} |")
            lines.append("")

        if benchmarks:
            lines.extend(
                [
                    "## 3. Benchmark Comparison",
                    "| Metric | Portfolio | "
                    + " | ".join(b.benchmark_name for b in benchmarks)
                    + " |",
                    "|---" + "|---" * (len(benchmarks) + 1) + "|",
                    f"| Cumulative Return | {_format_pct(metrics.total_return)} | "
                    + " | ".join(_format_pct(b.benchmark_return) for b in benchmarks)
                    + " |",
                    f"| CAGR | {_format_pct(metrics.cagr)} | "
                    + " | ".join(_format_pct(b.benchmark_cagr) for b in benchmarks)
                    + " |",
                    f"| MDD | {_format_pct(metrics.mdd)} | "
                    + " | ".join(_format_pct(b.benchmark_mdd) for b in benchmarks)
                    + " |",
                    f"| Sharpe Ratio | {metrics.sharpe_ratio:.2f} | "
                    + " | ".join(f"{b.benchmark_sharpe:.2f}" for b in benchmarks)
                    + " |",
                    "| Correlation | 1.00 | "
                    + " | ".join(f"{b.correlation:.2f}" for b in benchmarks)
                    + " |",
                    "| Beta | 1.00 | " + " | ".join(f"{b.beta:.2f}" for b in benchmarks) + " |",
                    "| Alpha (Ann.) | - | "
                    + " | ".join(_format_pct(b.alpha) for b in benchmarks)
                    + " |",
                    "",
                ]
            )

        return "\n".join(lines)

    # Text format
    lines = [
        "=" * 60,
        f" {title}",
        "=" * 60,
        f" Initial Capital      : {_format_krw(metrics.initial_capital)}",
        f" Final Equity         : {_format_krw(metrics.final_equity)}",
        f" Cumulative Return    : {_format_pct(metrics.total_return)}",
        f" CAGR                 : {_format_pct(metrics.cagr)}",
        f" Maximum Drawdown     : {_format_pct(metrics.mdd)} ({metrics.mdd_peak_date} ~ {metrics.mdd_trough_date})",
        f" Annualized Volatility: {_format_pct(metrics.annualized_volatility)}",
        f" Sharpe Ratio         : {metrics.sharpe_ratio:.2f}",
        f" Win Rate (Rebalance) : {_format_pct(metrics.win_rate_rebalance)}",
        f" Win Rate (Yearly)    : {_format_pct(metrics.win_rate_yearly)}",
        f" Avg Turnover Rate    : {_format_pct(metrics.avg_turnover_rate)}",
        "-" * 60,
    ]

    if metrics.yearly_returns:
        lines.append(" Yearly Returns:")
        for yr, ret in sorted(metrics.yearly_returns.items()):
            lines.append(f"   {yr} : {_format_pct(ret)}")
        lines.append("-" * 60)

    if benchmarks:
        lines.append(" Benchmark Comparison:")
        for b in benchmarks:
            lines.append(
                f"   [{b.benchmark_name}] Return: {_format_pct(b.benchmark_return)} | CAGR: {_format_pct(b.benchmark_cagr)} | MDD: {_format_pct(b.benchmark_mdd)} | Beta: {b.beta:.2f} | Corr: {b.correlation:.2f}"
            )
        lines.append("=" * 60)

    return "\n".join(lines)
