"""Quant-KO 심플 모니터링 대시보드 (Streamlit + Plotly).

실행 명령:
    streamlit run src/quant_ko/dashboard/app.py

필수 포함 구성:
    1. 전체 자산 변화 추이 & 보유 포트폴리오 (실제 계좌 시계열 + 10.5개년 백테스트 비교)
    2. 실제 거래기록 (SQLite orders 테이블 실시간 필터링 및 CSV 다운로드)
    3. 전략 소개 (Order B 후절삭 유니버스, 9대 팩터 공식, 계절성 운용 및 리스크 관리 규칙)
    4. 최신 타깃 20종목 & 시스템 상태 (DB 적재 현황 및 9대 팩터 Top 20 산출 조회)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# src 디렉터리를 sys.path에 자동 등록하여 Streamlit 단독 실행 시 quant_ko 모듈 임포트 보장
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from quant_ko.dashboard.data_loader import (  # noqa: E402
    build_account_equity_curve,
    diagnose_held_positions_risk,
    get_db_status_summary,
    get_next_rebalance_countdown,
    load_account_and_positions,
    load_actual_trade_logs,
    load_long_term_backtest_series,
    load_top20_preview,
)

try:
    import streamlit as st
except ImportError:  # pragma: no cover - 오프라인/비설치 환경에서도 모듈 임포트 보장
    st = None  # type: ignore[assignment]


DASHBOARD_CSS = """
<style>
    :root {
        --bg-card: #0f172a;
        --bg-surface: #1e293b;
        --border-subtle: #334155;
        --text-primary: #f8fafc;
        --text-secondary: #cbd5e1;
        --accent-blue: #38bdf8;
        --accent-green: #22c55e;
        --accent-amber: #f59e0b;
        --accent-red: #ef4444;
    }
    .quant-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.25rem;
        color: #f8fafc;
    }
    .quant-badge {
        display: inline-block;
        padding: 0.3rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-right: 0.5rem;
        border: 1px solid rgba(255, 255, 255, 0.18);
    }
    .badge-mock { background-color: #1e3a8a; color: #93c5fd; }
    .badge-real { background-color: #065f46; color: #6ee7b7; }
    .badge-parking { background-color: #78350f; color: #fde68a; }
    .badge-active { background-color: #14532d; color: #86efac; }
    .badge-account { background-color: #334155; color: #f1f5f9; font-family: monospace; }
    .rule-card {
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        border-left: 5px solid #0284c7;
        border-radius: 8px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 1rem;
        color: #0f172a;
        line-height: 1.6;
    }
    .rule-card h3 {
        margin-top: 0;
        color: #0f172a;
        font-size: 1.15rem;
    }
    .formula-box {
        background-color: #0f172a;
        color: #38bdf8;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        padding: 0.9rem 1.2rem;
        border-radius: 8px;
        border: 1px solid #334155;
        font-size: 0.95rem;
        margin: 0.75rem 0;
    }
    .badge-countdown {
        background-color: #4338ca;
        color: #c7d2fe;
        font-weight: 700;
    }
    .risk-card-normal {
        background-color: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-left: 4px solid #16a34a;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        color: #14532d;
    }
    .risk-card-warning {
        background-color: #fffbeb;
        border: 1px solid #fde68a;
        border-left: 4px solid #f59e0b;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        color: #78350f;
    }
    .risk-card-danger {
        background-color: #fef2f2;
        border: 1px solid #fecaca;
        border-left: 4px solid #dc2626;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        color: #7f1d1d;
    }
</style>
"""


def create_equity_curve_figure(equity_df: pd.DataFrame) -> go.Figure:
    """실제 계좌의 전체 자산 변화 추이(총자산 및 예수금 vs 주식평가액) Plotly 차트를 생성합니다."""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        row_heights=[0.6, 0.4],
        subplot_titles=(
            "실제 계좌 총자산 변화 추이 (총자산 = 예수금 + 주식평가액)",
            "자산 구성 비중 추이 (예수금 vs 보유 주식 평가액)",
        ),
    )

    if equity_df.empty:
        fig.update_layout(
            height=520,
            template="plotly_white",
            annotations=[
                {
                    "text": "표시할 계좌 자산 추이 데이터가 없습니다.",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "font": {"size": 15},
                }
            ],
        )
        return fig

    fig.add_trace(
        go.Scatter(
            x=equity_df["date"],
            y=equity_df["total_equity"],
            mode="lines+markers",
            name="총자산 (Total Equity)",
            line={"color": "#0284c7", "width": 3},
            marker={"size": 7, "symbol": "circle"},
            customdata=equity_df["return_pct"],
            hovertemplate=(
                "일자: %{x}<br>총자산: %{y:,.0f}원<br>누적수익률: %{customdata:+.2f}%<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            x=equity_df["date"],
            y=equity_df["stock_value"],
            name="주식 평가액 (Stock Value)",
            marker_color="#16a34a",
            hovertemplate="일자: %{x}<br>주식 평가액: %{y:,.0f}원<extra></extra>",
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            x=equity_df["date"],
            y=equity_df["cash"],
            name="주문가능 예수금 (Cash)",
            marker_color="#64748b",
            hovertemplate="일자: %{x}<br>예수금: %{y:,.0f}원<extra></extra>",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        barmode="stack",
        height=560,
        template="plotly_white",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.04, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 25, "t": 65, "b": 40},
    )
    fig.update_yaxes(title_text="총자산 (원)", tickformat=",.0f", row=1, col=1)
    fig.update_yaxes(title_text="금액 (원)", tickformat=",.0f", row=2, col=1)
    return fig


def create_portfolio_allocation_figure(positions_df: pd.DataFrame, cash: float) -> go.Figure:
    """보유 종목별 평가금액 및 현금 비중을 시각화하는 Plotly 차트를 생성합니다."""
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "domain"}, {"type": "xy"}]],
        subplot_titles=("포트폴리오 자산 배분 비중 (%)", "보유 종목별 평가금액 (원)"),
    )

    labels: list[str] = []
    values: list[float] = []

    if not positions_df.empty:
        for _, row in positions_df.iterrows():
            labels.append(f"{row['name']} ({row['ticker']})")
            values.append(float(row["eval_amount"]))

    if cash > 0:
        labels.append("예수금 (Cash)")
        values.append(float(cash))

    if not values:
        labels = ["예수금 (Cash)"]
        values = [1.0]

    fig.add_trace(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.45,
            textinfo="label+percent",
            hovertemplate="%{label}<br>금액: %{value:,.0f}원 (%{percent})<extra></extra>",
        ),
        row=1,
        col=1,
    )

    if not positions_df.empty:
        fig.add_trace(
            go.Bar(
                x=positions_df["name"] + " (" + positions_df["ticker"] + ")",
                y=positions_df["eval_amount"],
                text=positions_df["weight_pct"].map(lambda v: f"{v:.1f}%"),
                textposition="auto",
                name="종목 평가금액",
                marker_color="#0284c7",
                hovertemplate="%{x}<br>평가금액: %{y:,.0f}원<extra></extra>",
            ),
            row=1,
            col=2,
        )

    fig.update_layout(
        height=400,
        template="plotly_white",
        showlegend=False,
        margin={"l": 30, "r": 30, "t": 55, "b": 40},
    )
    fig.update_yaxes(title_text="평가금액 (원)", tickformat=",.0f", row=1, col=2)
    return fig


def create_backtest_10y_trajectory_figure(series_df: pd.DataFrame) -> go.Figure:
    """10.5개년(2016~2026) 단독 전략의 일별 누적 자산 성장 및 언더워터 낙폭(MDD) 차트를 생성합니다.

    KOSPI 및 KOSDAQ 벤치마크와의 상관관계 및 상대 성과를 한눈에 비교할 수 있습니다.
    """
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "10.5개년 누적 자산 성장 궤적 (초기자본 1,000만 원 기준, 원)",
            "언더워터 고점 대비 낙폭 (Drawdown %)",
        ),
        row_heights=[0.65, 0.35],
    )

    if series_df.empty:
        fig.update_layout(
            height=500,
            template="plotly_white",
            annotations=[
                {
                    "text": "10.5개년 백테스트 시계열 데이터가 없습니다.",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                }
            ],
        )
        return fig

    # 1. 상단: 누적 자산 추이
    # 전략 (계절성)
    fig.add_trace(
        go.Scatter(
            x=series_df["date"],
            y=series_df["strategy_equity"],
            mode="lines",
            name="🔥 소형주 성장·가치 계절성 전략",
            line={"color": "#0284c7", "width": 3.0},
            customdata=series_df["strategy_cum_return"],
            hovertemplate="일자: %{x}<br>총자산: %{y:,.0f}원<br>누적수익률: %{customdata:+.2f}%<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # KOSPI 벤치마크
    if "kospi_equity" in series_df.columns:
        fig.add_trace(
            go.Scatter(
                x=series_df["date"],
                y=series_df["kospi_equity"],
                mode="lines",
                name="🏛️ KOSPI 지수 (상관계수 0.34)",
                line={"color": "#64748b", "width": 1.5, "dash": "dot"},
                customdata=series_df["kospi_cum_return"],
                hovertemplate="일자: %{x}<br>KOSPI 평가액: %{y:,.0f}원<br>수익률: %{customdata:+.2f}%<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # KOSDAQ 벤치마크
    if "kosdaq_equity" in series_df.columns:
        fig.add_trace(
            go.Scatter(
                x=series_df["date"],
                y=series_df["kosdaq_equity"],
                mode="lines",
                name="📈 KOSDAQ 지수 (상관계수 0.42)",
                line={"color": "#d97706", "width": 1.5, "dash": "dot"},
                customdata=series_df["kosdaq_cum_return"],
                hovertemplate="일자: %{x}<br>KOSDAQ 평가액: %{y:,.0f}원<br>수익률: %{customdata:+.2f}%<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # 2. 하단: 언더워터 낙폭 (Drawdown %)
    fig.add_trace(
        go.Scatter(
            x=series_df["date"],
            y=series_df["strategy_dd"],
            mode="lines",
            name="전략 낙폭 (MDD -40.1%)",
            line={"color": "#0284c7", "width": 1.8},
            fill="tozeroy",
            fillcolor="rgba(2, 132, 199, 0.15)",
            hovertemplate="일자: %{x}<br>전략 낙폭: %{y:.2f}%<extra></extra>",
        ),
        row=2,
        col=1,
    )

    if "kospi_dd" in series_df.columns:
        fig.add_trace(
            go.Scatter(
                x=series_df["date"],
                y=series_df["kospi_dd"],
                mode="lines",
                name="KOSPI 낙폭",
                line={"color": "#94a3b8", "width": 1.2},
                hovertemplate="일자: %{x}<br>KOSPI 낙폭: %{y:.2f}%<extra></extra>",
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        height=620,
        template="plotly_white",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.03, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 30, "t": 60, "b": 40},
    )
    fig.update_yaxes(title_text="자산 평가액 (원)", tickformat=",.0f", row=1, col=1)
    fig.update_yaxes(title_text="낙폭 (Drawdown %)", range=[-60, 2], row=2, col=1)
    return fig


def create_backtest_comparison_figure() -> go.Figure:
    """10.5개년 백테스트(2016.04~2026.10) 핵심 전략별 성과 비교 인터랙티브 차트를 생성합니다."""
    strategies = [
        "Order B 계절성 (현행 채택)",
        "Order A 선절삭 계절성",
        "상시보유 (모의투자 검증모드)",
        "KOSPI 벤치마크",
        "KOSDAQ 벤치마크",
    ]
    cum_returns = [275.34, 278.80, 127.23, 30.85, 14.20]
    cagrs = [13.40, 13.50, 8.12, 2.59, 1.27]
    mdds = [-41.23, -40.08, -55.40, -35.71, -44.20]

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            "10.5개년 누적 수익률 비교 (%)",
            "연평균 복리수익률(CAGR) vs 최대낙폭(MDD) (%)",
        ),
    )

    bar_colors = ["#0284c7", "#0ea5e9", "#6366f1", "#64748b", "#94a3b8"]
    fig.add_trace(
        go.Bar(
            x=strategies,
            y=cum_returns,
            text=[f"+{v:.2f}%" for v in cum_returns],
            textposition="outside",
            name="누적 수익률 (%)",
            marker_color=bar_colors,
            hovertemplate="%{x}<br>누적 수익률: +%{y:.2f}%<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            x=strategies,
            y=cagrs,
            text=[f"{v:.2f}%" for v in cagrs],
            textposition="auto",
            name="CAGR (%)",
            marker_color="#16a34a",
            hovertemplate="%{x}<br>CAGR: %{y:.2f}%<extra></extra>",
        ),
        row=1,
        col=2,
    )

    fig.add_trace(
        go.Bar(
            x=strategies,
            y=mdds,
            text=[f"{v:.2f}%" for v in mdds],
            textposition="auto",
            name="MDD (%)",
            marker_color="#dc2626",
            hovertemplate="%{x}<br>MDD: %{y:.2f}%<extra></extra>",
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        height=430,
        template="plotly_white",
        barmode="group",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.04, "xanchor": "right", "x": 1},
        margin={"l": 35, "r": 30, "t": 60, "b": 40},
    )
    fig.update_yaxes(title_text="누적 수익률 (%)", range=[0, 330], row=1, col=1)
    fig.update_yaxes(title_text="CAGR / MDD (%)", range=[-65, 25], row=1, col=2)
    return fig


def _render_top_header_and_kpis(
    acc_info: dict[str, Any], privacy_mode: bool = False
) -> None:
    """상단 운용 모드 배너 및 4대 핵심 KPI 메트릭 카드를 렌더링합니다."""
    is_mock = bool(acc_info.get("is_mock", True))
    is_parking = bool(acc_info.get("is_parking_season", True))
    account_masked = str(acc_info.get("account_masked", "5021****-01"))
    source_label = (
        "🟢 KIS 실시간 연동"
        if acc_info.get("source") == "KIS_LIVE"
        else "💾 SQLite DB 오프라인 복원"
    )

    mode_badge_cls = "badge-mock" if is_mock else "badge-real"
    mode_badge_text = (
        "🧪 모의투자 (상시보유 검증)" if is_mock else "🚀 실전투자 (계절성 운용)"
    )

    season_badge_cls = "badge-parking" if is_parking else "badge-active"
    season_badge_text = (
        "🛡️ 5~10월 CD금리 ETF 파킹기"
        if is_parking
        else "🔥 11~4월 소형주 적극 투자기"
    )

    countdown = get_next_rebalance_countdown()
    rebalance_badge_text = (
        f"⏳ 차기 리밸런싱: {countdown['target_date']} 15:20 ({countdown['formatted_countdown']})"
    )

    privacy_badge = (
        '<span class="quant-badge" style="background-color:#064e3b; color:#a7f3d0;">🔒 프라이버시 보호 모드 ON</span>'
        if privacy_mode
        else ""
    )

    banner_html = (
        '<div class="quant-banner" role="region" aria-label="Quant-KO 운용 상태 요약 배너">'
        '<h1 style="margin:0 0 0.6rem 0; font-size:1.65rem; color:#f8fafc;">'
        "📊 Quant-KO 소형주 성장·가치 자동매매 모니터링 대시보드</h1>"
        "<div>"
        f'<span class="quant-badge {mode_badge_cls}">{mode_badge_text}</span>'
        f'<span class="quant-badge {season_badge_cls}">{season_badge_text}</span>'
        f'<span class="quant-badge badge-countdown">{rebalance_badge_text}</span>'
        f'<span class="quant-badge badge-account">계좌: {account_masked}</span>'
        f'<span class="quant-badge badge-account">데이터 소스: {source_label}</span>'
        f"{privacy_badge}"
        "</div></div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    total_eq = float(acc_info.get("total_equity", 0.0))
    ret_pct = float(acc_info.get("return_pct", 0.0))
    stock_val = float(acc_info.get("stock_value", 0.0))
    cash_val = float(acc_info.get("cash", 0.0))
    pos_cnt = int(acc_info.get("positions_count", 0))
    ord_cnt = int(acc_info.get("total_orders_count", 0))

    stock_ratio = (stock_val / total_eq * 100.0) if total_eq > 0 else 0.0
    cash_ratio = (cash_val / total_eq * 100.0) if total_eq > 0 else 0.0

    total_display = "***원" if privacy_mode else f"{total_eq:,.0f}원"
    stock_display = "***원" if privacy_mode else f"{stock_val:,.0f}원"
    cash_display = "***원" if privacy_mode else f"{cash_val:,.0f}원"

    col1.metric(
        label="💰 총 자산 평가액",
        value=total_display,
        delta=f"{ret_pct:+.2f}% (초기자본 대비)",
    )
    col2.metric(
        label="📈 주식 평가금액",
        value=stock_display,
        delta=f"비중 {stock_ratio:.1f}%",
    )
    col3.metric(
        label="💵 주문가능 예수금",
        value=cash_display,
        delta=f"비중 {cash_ratio:.1f}%",
    )
    col4.metric(
        label="📦 보유 종목 수 / 총 주문 건수",
        value=f"{pos_cnt}종목 / {ord_cnt}건",
        delta="동일비중 목표 20종목",
    )


def _render_tab1_equity_and_portfolio(
    acc_info: dict[str, Any], db_path: str, privacy_mode: bool = False
) -> None:
    """Tab 1: 전체 자산 변화 추이, 보유 포트폴리오, 10.5개년 단독 전략 시계열 및 벤치마크 비교."""
    st.subheader("1️⃣ 실제 계좌 전체 자산 변화 추이 (Total Equity Trajectory)")
    equity_df = build_account_equity_curve(db_path=db_path)
    fig_eq = create_equity_curve_figure(equity_df)
    st.plotly_chart(fig_eq, use_container_width=True)

    st.divider()
    st.subheader("2️⃣ 현재 보유 포트폴리오 비중 및 상세 현황")
    positions_df: pd.DataFrame = acc_info.get("positions_df", pd.DataFrame())
    cash = float(acc_info.get("cash", 0.0))

    fig_alloc = create_portfolio_allocation_figure(positions_df, cash=cash)
    st.plotly_chart(fig_alloc, use_container_width=True)

    if positions_df.empty:
        st.info("현재 보유 중인 주식 포지션이 없습니다 (100% 예수금 상태).")
    else:
        display_pos = pd.DataFrame(
            {
                "종목코드": positions_df["ticker"],
                "종목명": positions_df["name"],
                "보유수량": positions_df["qty"].map(
                    lambda x: "***주" if privacy_mode else f"{int(x):,}주"
                ),
                "평균매입가": positions_df["avg_price"].map(
                    lambda x: "***원" if privacy_mode else f"{int(x):,}원"
                ),
                "현재가": positions_df["current_price"].map(
                    lambda x: f"{int(x):,}원"
                ),
                "평가금액": positions_df["eval_amount"].map(
                    lambda x: "***원" if privacy_mode else f"{int(x):,}원"
                ),
                "수익률(%)": positions_df["return_pct"].map(
                    lambda x: f"{float(x):+.2f}%"
                ),
                "포트폴리오 비중(%)": positions_df["weight_pct"].map(
                    lambda x: f"{float(x):.2f}%"
                ),
            }
        )
        st.dataframe(display_pos, use_container_width=True, hide_index=True)

        # 보유 종목 긴급 리스크 및 재무 건전성 진단 섹션
        diagnoses = diagnose_held_positions_risk(positions_df, db_path=db_path)
        with st.expander("🛡️ 보유 종목 긴급 리스크 & 관리종목 진단 (08:30 일일 감시 연동)", expanded=True):
            danger_cnt = sum(1 for d in diagnoses if d["severity"] == "DANGER")
            warning_cnt = sum(1 for d in diagnoses if d["severity"] == "WARNING")
            if danger_cnt > 0:
                st.error(f"🚨 긴급 청산 대상 종목이 {danger_cnt}건 발견되었습니다! (다음 개장일 08:30 시장가 전량 청산)")
            elif warning_cnt > 0:
                st.warning(f"⚠️ 주의 관찰 종목이 {warning_cnt}건 있습니다. (고부채비율 등)")
            else:
                st.success("✅ 현재 보유 중인 모든 종목이 관리종목/투자주의환기/자본잠식 위험 없이 정상 상태입니다.")

            for diag in diagnoses:
                sev = diag["severity"]
                cls_name = "risk-card-normal" if sev == "NORMAL" else ("risk-card-danger" if sev == "DANGER" else "risk-card-warning")
                st.markdown(
                    f"""
                    <div class="{cls_name}">
                        <strong>{diag['name']} ({diag['ticker']})</strong>: {diag['issues']}
                        <span style="float:right; font-size:0.85rem;">부채비율: {diag['debt_ratio']:.1f}% | 자본잠식률: {diag['impairment_ratio']:.1f}%</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.divider()
    st.subheader("3️⃣ 10.5개년 단독 전략 시계열 및 벤치마크 비교 (2016.04 ~ 2026.10)")
    st.markdown(
        """
        > 💡 **전략 단독 10.5년 실제 궤적**: 압축 요약이 아닌 **2016년 4월부터 2026년 10월까지 2,579영업일 동안 매일매일 어떻게 자산이 움직였는지**를
        > 일별 시계열 차트 및 언더워터 낙폭(MDD) 곡선으로 온전히 보여줍니다.
        > 시장 대표 지표인 **KOSPI 지수** 및 **KOSDAQ 지수**와 상관계수(Correlation) 및 연도별 수익률을 정밀 비교합니다.
        """
    )

    bt_data = load_long_term_backtest_series()
    series_df = bt_data.get("series_df", pd.DataFrame())

    if not series_df.empty:
        # 1. 핵심 성과 지표 & 상관계수 4대 카드
        bcol1, bcol2, bcol3, bcol4 = st.columns(4)
        bcol1.metric("누적 수익률 (전략 10.5년)", f"+{bt_data['total_return_strategy']:.2f}%", "초기 1,000만 ➔ 5,161만 원")
        bcol2.metric("연평균 복리수익률 (CAGR)", f"{bt_data['cagr_strategy']:.2f}%", f"MDD {bt_data['mdd_strategy']:.2f}%")
        bcol3.metric("KOSPI 상관계수", f"{bt_data['corr_kospi']:.4f}", "낮은 상관관계 (시장 독립성)")
        bcol4.metric("KOSDAQ 상관계수", f"{bt_data['corr_kosdaq']:.4f}", "소형주 시장 적정 동조화")

        # 2. 10.5개년 일별 누적 자산 성장 및 언더워터 낙폭 인터랙티브 차트
        fig_10y = create_backtest_10y_trajectory_figure(series_df)
        st.plotly_chart(fig_10y, use_container_width=True)

        # 3. 연도별 수익률 및 KOSPI 대비 초과수익률 비교 테이블
        yearly_df = bt_data.get("yearly_df", pd.DataFrame())
        if not yearly_df.empty:
            st.markdown("#### 📅 10.5개년 연도별 수익률 및 KOSPI 대비 초과 성과")
            styled_yearly = yearly_df.copy()
            styled_yearly["전략(소형주+계절성)"] = styled_yearly["전략(소형주+계절성)"].map(lambda v: f"{v:+.2f}%")
            styled_yearly["KOSPI 지수"] = styled_yearly["KOSPI 지수"].map(lambda v: f"{v:+.2f}%")
            styled_yearly["KOSDAQ 지수"] = styled_yearly["KOSDAQ 지수"].map(lambda v: f"{v:+.2f}%")
            styled_yearly["KOSPI 대비 초과수익"] = styled_yearly["KOSPI 대비 초과수익"].map(lambda v: f"{v:+.2f}%p")
            # 11개 행 전체가 스크롤 없이 한눈에 딱 맞게 표시되도록 높이 지정 (헤더 38px + 11행*35px = 약 430px)
            st.dataframe(styled_yearly, use_container_width=True, hide_index=True, height=435)
    else:
        st.info("10.5개년 백테스트 시계열 데이터가 준비되지 않았습니다.")


def _render_tab2_trade_logs(db_path: str) -> None:
    """Tab 2: 실제 거래기록 조회 및 필터링."""
    st.subheader("🧾 실제 거래기록 (SQLite `orders` 원장)")

    all_logs = load_actual_trade_logs(db_path=db_path)
    total_cnt = len(all_logs)
    buy_filled_cnt = int(
        len(
            all_logs[
                (all_logs["매매구분"] == "BUY")
                & (all_logs["상태"].isin(["FILLED", "ORDERED", "PARTIAL"]))
            ]
        )
    )
    sell_filled_cnt = int(
        len(
            all_logs[
                (all_logs["매매구분"] == "SELL")
                & (all_logs["상태"].isin(["FILLED", "ORDERED", "PARTIAL"]))
            ]
        )
    )
    failed_cnt = int(len(all_logs[all_logs["상태"] == "FAILED"]))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 주문 건수", f"{total_cnt:,}건")
    m2.metric("매수 체결/접수", f"{buy_filled_cnt:,}건")
    m3.metric("매도 체결/접수", f"{sell_filled_cnt:,}건")
    m4.metric("실패/거절 (FAILED)", f"{failed_cnt:,}건")

    fcol1, fcol2, fcol3 = st.columns(3)
    mode_choice = fcol1.selectbox(
        "운용 환경 필터",
        options=["ALL", "MOCK", "REAL"],
        format_func=lambda x: {
            "ALL": "전체 (ALL)",
            "MOCK": "모의투자 (MOCK)",
            "REAL": "실전투자 (REAL)",
        }[x],
    )
    side_choice = fcol2.selectbox(
        "매매 구분 필터",
        options=["ALL", "BUY", "SELL"],
        format_func=lambda x: {
            "ALL": "전체 (ALL)",
            "BUY": "매수 (BUY)",
            "SELL": "매도 (SELL)",
        }[x],
    )
    status_choice = fcol3.selectbox(
        "체결 상태 필터",
        options=["ALL", "ORDERED", "FILLED", "FAILED", "DRY_RUN"],
        format_func=lambda x: {
            "ALL": "전체 (ALL)",
            "ORDERED": "주문접수/체결 (ORDERED)",
            "FILLED": "체결완료 (FILLED)",
            "FAILED": "주문거절/실패 (FAILED)",
            "DRY_RUN": "모의실행 (DRY_RUN)",
        }[x],
    )

    filtered_df = load_actual_trade_logs(
        db_path=db_path,
        mode_filter=mode_choice,
        side_filter=side_choice,
        status_filter=status_choice,
    )

    if filtered_df.empty:
        st.warning("선택한 조건에 해당하는 거래기록이 없습니다.")
    else:
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        csv_bytes = filtered_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 조회된 거래기록 CSV 다운로드",
            data=csv_bytes,
            file_name="quant_ko_trade_logs.csv",
            mime="text/csv",
        )


def _render_tab3_strategy_spec() -> None:
    """Tab 3: 전략 소개 (Order B 후절삭, 9대 팩터 공식, 계절성 운용 및 리스크 관리)."""
    st.subheader("🎯 소형주 성장·가치 9대 팩터 계절성 전략 명세 (Single Source of Truth)")

    st.markdown(
        """
        <div class="rule-card">
            <h3>1. 유니버스 산출 순서 (Order B: 재무 필터 선적용 ➔ 시가총액 하위 20% 후절삭)</h3>
            <ul>
                <li><strong>기본 대상:</strong> 코스피(KOSPI) · 코스닥(KOSDAQ) 12월 결산 보통주 (코넥스 <code>KONEX</code> 제외)</li>
                <li><strong>1차 제외 필터:</strong> 금융업(은행·증권·보험 등), 지주사, 관리종목, 투자주의환기종목, 거래정지·정리매매, 중국계 상장사, 스팩(SPAC), 우선주 제외</li>
                <li><strong>2차 재무 건전성 & 흑자 선필터:</strong>
                    <code>TTM 영업이익 &gt; 0</code> · <code>TTM 지배주주순이익 &gt; 0</code> · <code>자본잠식률 ≤ 0% (자본총계 ≥ 자본금)</code> · <strong>부채비율 상한 제한 없음</strong> (단일 분기 흑자 강제 없음)
                </li>
                <li><strong>3차 시가총액 후절삭 (Order B):</strong> 재무/흑자 필터를 통과한 우량 기업 모수 중에서 <strong>시가총액 하위 20%</strong> 소형주만 최종 유니버스로 절삭 (거래대금 하한 필터 0원)</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="rule-card">
            <h3>2. 9대 팩터 멀티 스코어링 공식 (Total Rank 합산 오름차순)</h3>
            <div class="formula-box">
                Total Rank = Rank(시가총액 ↑) + Σ Rank(밸류 4종: PER, PSR, POR, PGPR ↑) + Σ Rank(성장 4종: 매출·매출총이익·영업이익·순이익 YoY ↓, 흑자전환 최우선)
            </div>
            <ul>
                <li><strong>시총 팩터 (1종):</strong> 시가총액 오름차순 순위 (작을수록 우수, 1위부터 부여)</li>
                <li><strong>밸류 팩터 (4종):</strong> <code>PER</code>(시총/TTM 지배주주순이익), <code>PSR</code>(시총/TTM 매출액), <code>POR</code>(시총/TTM 영업이익), <code>PGPR</code>(시총/TTM 매출총이익) 각각 오름차순 순위</li>
                <li><strong>성장 팩터 (4종):</strong> 최근 분기 YoY 매출액·매출총이익·영업이익·지배주주순이익 성장률 내림차순 순위 (전년 동분기 적자 ➔ 당기 흑자전환 기업은 최상위 순위 부여)</li>
                <li><strong>최종 포트폴리오 선정:</strong> <code>Total Rank</code> 합계가 가장 작은 상위 <strong>20종목 동일비중(각 5.0%)</strong> 편입 (동점 시 시가총액이 작은 종목 우선)</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="rule-card">
            <h3>3. 실전 계절성 운용 vs 모의 상시보유 및 리스크 관리 규칙</h3>
            <ul>
                <li><strong>🚀 실전투자 (<code>REAL</code> — 계절성 운용):</strong>
                    <ul>
                        <li><strong>11월 ~ 4월 (적극 투자기):</strong> 소형주 9대 팩터 상위 20종목 동일비중(각 5%) 보유</li>
                        <li><strong>5월 ~ 10월 (안전 파킹기):</strong> <code>357870</code> <strong>TIGER CD금리투자KIS(합성) ETF 100% 파킹</strong> (소형주 비수기 하락장 회피 + CD금리 이자 수취)</li>
                    </ul>
                </li>
                <li><strong>🧪 모의투자 (<code>MOCK</code> — 상시보유 검증):</strong> 5~10월 파킹 없이 365일 연중 소형주 20종목을 매월 리밸런싱하여 주문·체결·비상청산 파이프라인 상시 검증</li>
                <li><strong>⏰ 정기 리밸런싱 실행:</strong> 매월 마지막 영업일 <strong>15:20 장마감 동시호가 시장가(<code>ORD_DVSN="01"</code>)</strong> 차이분 매매 (매도 선행 후 매수, 수수료 버퍼 0.3% 차감)</li>
                <li><strong>🚨 일일 비상 손절 감시:</strong> 평일 <strong>08:30</strong> 보유 종목의 관리종목·투자주의환기종목 지정 여부를 감시하여 지정 즉시 시장가 전량 청산 후 현금 보유</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_tab4_universe_and_status(db_path: str) -> None:
    """Tab 4: 최신 타깃 20종목 & 시스템 상태 점검."""
    st.subheader("🔍 데이터베이스 적재 현황 & 최신 9대 팩터 타깃 20종목")

    db_summary = get_db_status_summary(db_path=db_path)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📅 최신 거래일 (daily_prices)", db_summary["latest_date"])
    c2.metric("🏢 등록 기업 수 (companies)", f"{db_summary['companies_count']:,}개")
    c3.metric("📊 일별 시세 레코드 수", f"{db_summary['daily_prices_count']:,}건")
    c4.metric("📑 DART 재무제표 건수", f"{db_summary['financials_count']:,}건")

    st.markdown(
        """
        > **안내:** 아래 버튼을 클릭하면 DB의 최신 기준일(`PIT`) 재무 스냅샷과 시가총액을 바탕으로
        > **Order B 유니버스 필터** 및 **9대 팩터 멀티 스코어링**을 즉시 실행하여 상위 20개 타깃 종목을 산출합니다.
        """
    )

    if st.button("🎯 최신 기준일 9대 팩터 Top 20 타깃 종목 산출하기", type="primary"):
        with st.spinner("PIT 재무 스냅샷 및 9대 팩터 스코어링 계산 중..."):
            latest_dt, univ_cnt, top20_df = load_top20_preview(db_path=db_path, top_n=20)
        st.success(
            f"기준일 **{latest_dt}** · Order B 유니버스 통과 **{univ_cnt}종목** 중 상위 **{len(top20_df)}종목** 선정 완료!"
        )
        if not top20_df.empty:
            cols = [
                "순위",
                "종목코드",
                "종목명",
                "시가총액(억)",
                "PER",
                "PSR",
                "POR",
                "PGPR",
                "부채비율(%)",
                "밸류순위평균",
                "성장순위평균",
                "Total Rank",
            ]
            available_cols = [c for c in cols if c in top20_df.columns]
            st.dataframe(top20_df[available_cols], use_container_width=True, hide_index=True)

            # 팩터 밸런스 프로파일 시각화 (밸류 vs 성장 순위 비교)
            if "밸류순위평균" in top20_df.columns and "성장순위평균" in top20_df.columns:
                st.markdown("#### ⚖️ Top 20 종목 밸류(저평가) vs 성장(고성장) 팩터 프로파일")
                st.caption("※ 순위 수치가 낮을수록(왼쪽·아래쪽) 해당 팩터에서 더 우수한 종목입니다.")
                fig_factor = go.Figure()
                fig_factor.add_trace(
                    go.Scatter(
                        x=top20_df["밸류순위평균"],
                        y=top20_df["성장순위평균"],
                        mode="markers+text",
                        text=top20_df["종목명"],
                        textposition="top center",
                        marker={
                            "size": 11,
                            "color": top20_df["Total Rank"],
                            "colorscale": "Viridis",
                            "showscale": True,
                            "colorbar": {"title": "Total Rank"},
                        },
                        hovertemplate=(
                            "<b>%{text} (%{customdata[0]})</b><br>"
                            "시가총액: %{customdata[1]:,.1f}억원<br>"
                            "밸류 4종 평균 순위: %{x:.1f}위<br>"
                            "성장 4종 평균 순위: %{y:.1f}위<br>"
                            "종합 Total Rank: %{marker.color}위<extra></extra>"
                        ),
                        customdata=list(
                            zip(
                                top20_df["종목코드"],
                                top20_df["시가총액(억)"],
                                strict=False,
                            )
                        ),
                    )
                )
                fig_factor.update_layout(
                    height=450,
                    template="plotly_white",
                    xaxis_title="밸류 4종 팩터 평균 순위 (작을수록 저평가 우수)",
                    yaxis_title="성장 4종 팩터 평균 순위 (작을수록 고성장 우수)",
                    margin={"l": 40, "r": 30, "t": 30, "b": 40},
                )
                st.plotly_chart(fig_factor, use_container_width=True)


def main(db_path: str = "data/quant_ko.db") -> None:
    """Streamlit 모니터링 대시보드 메인 엔트리포인트."""
    if st is None:
        raise RuntimeError(
            "streamlit 패키지가 설치되어 있지 않습니다. `uv add streamlit plotly` 실행 후 다시 시도하세요."
        )

    st.set_page_config(
        page_title="Quant-KO 모니터링 대시보드",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

    # 상단 우측 실전 계좌 금액 마스킹 프라이버시 토글 스위치
    pcol1, pcol2 = st.columns([0.78, 0.22])
    with pcol2:
        privacy_mode = st.toggle(
            "🔒 실전 금액 숨기기 (프라이버시 모드)",
            value=False,
            help="실전 투자 시 전체 자산 평가액, 예수금, 보유 종목별 매입/평가금액을 '***원'으로 마스킹합니다.",
        )

    acc_info = load_account_and_positions(db_path=db_path, fetch_live_kis=True)
    _render_top_header_and_kpis(acc_info, privacy_mode=privacy_mode)

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📈 전체 자산 변화 추이 & 보유 포트폴리오",
            "🧾 실제 거래기록 (Orders)",
            "🎯 전략 소개 (Strategy Spec)",
            "🔍 최신 타깃 20종목 & 시스템 상태",
        ]
    )

    with tab1:
        _render_tab1_equity_and_portfolio(acc_info, db_path=db_path, privacy_mode=privacy_mode)
    with tab2:
        _render_tab2_trade_logs(db_path=db_path)
    with tab3:
        _render_tab3_strategy_spec()
    with tab4:
        _render_tab4_universe_and_status(db_path=db_path)


if __name__ == "__main__":
    main()
