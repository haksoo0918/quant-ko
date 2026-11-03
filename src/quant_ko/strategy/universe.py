"""전략 투자 유니버스 필터링 엔진."""

from datetime import datetime
from typing import Any

import pandas as pd

from quant_ko.data.krx import (
    is_chinese_company,
    is_holding_or_financial,
    is_preferred_stock,
    is_spac,
    normalize_date,
)
from quant_ko.data.store import DataStore
from quant_ko.pit.builder import PITSnapshotBuilder

PARKING_MONTHS = {5, 6, 7, 8, 9, 10}
FISCAL_MONTH_DECEMBER = 12
SEASONALITY_OCTOBER_SWITCH_DAY = 25
SEASONALITY_APRIL_SWITCH_DAY = 25
DEFAULT_MARKET_CAP_QUANTILE = 0.20
TRADING_DAYS_ROLLING_WINDOW = 20
FINANCIAL_COVERAGE_THRESHOLD = 0.8


def is_seasonality_parking_period(date_str: str) -> bool:
    """5-10월 안전 자산(CD금리 ETF) 대피 구간 여부 판정.

    월말 리밸런싱 경계 기준:
    - 10월 말 리밸런싱(10월 25일 이상, 예: 2026-10-29 D-1일 및 2026-10-30 리밸런싱일)은
      11-4월 소형주 20종목 활성 투자 구간으로 진입하므로 False를 반환합니다.
    - 4월 말 리밸런싱(4월 25일 이상, 예: 2026-04-30 리밸런싱일)은
      5-10월 CD금리 ETF 안전 파킹 구간으로 진입하므로 True를 반환합니다.
    - 5-9월 및 10월 25일 미만은 파킹 구간(True), 11-3월 및 4월 25일 미만(예: 2026-04-01)은 활성 구간(False)입니다.
    """
    dt = datetime.strptime(normalize_date(date_str), "%Y-%m-%d")
    if dt.month == 10 and dt.day >= SEASONALITY_OCTOBER_SWITCH_DAY:
        return False
    if dt.month == 4 and dt.day >= SEASONALITY_APRIL_SWITCH_DAY:
        return True
    return dt.month in PARKING_MONTHS


def filter_universe(
    store: DataStore,
    as_of_date: str,
    pit_df: pd.DataFrame | None = None,
    min_trading_value: float = 0.0,
    market_cap_quantile: float = DEFAULT_MARKET_CAP_QUANTILE,
    max_debt_ratio: float | None = None,
    require_quarter_profit: bool = False,
) -> pd.DataFrame:
    """전략 요구사항(PRD 3.1)에 따라 투자 적격 유니버스를 필터링합니다.

    1. 기본 제외: 우선주, 스팩(SPAC), 중국계 기업, 지주/금융사, 12월 결산 외, 상장폐지, 당일 기준 활성 특이종목 지정.
    2. 재무 건전성 필터: 자본잠식률 <= 0% (완전자본잠식 및 부분자본잠식 배제), 부채비율(선택).
    3. 수익성 필터: TTM 영업이익 > 0, TTM 지배주주순이익 > 0 (옵션 지정 시 최근 분기 영업이익/순이익 > 0 포함).
    4. 시가총액 필터: 재무 적격 종목군 중 시가총액 하위 분위(기본값: 하위 20%) 소형주 선정.
    5. 유동성 필터: 20영업일 평균 거래대금 >= min_trading_value.

    Args:
        store: SQLite 데이터베이스 저장소.
        as_of_date: 필터링 기준일자 (YYYY-MM-DD 또는 YYYYMMDD).
        pit_df: 기생성된 PIT 재무 스냅샷 DataFrame (미지정 시 자동 생성).
        min_trading_value: 최소 20영업일 평균 거래대금 (원).
        market_cap_quantile: 소형주 시가총액 분위 컷 (기본값: 0.20 = 하위 20%).
        max_debt_ratio: 최대 부채비율 제한 (선택 사항).
        require_quarter_profit: 최근 분기 영업이익/순이익 흑자 필수 여부.

    Returns:
        필터링을 통과한 투자 유니버스 DataFrame.
    """
    norm_date = normalize_date(as_of_date)  # YYYY-MM-DD
    dt_str = norm_date.replace("-", "")

    # 1. 기업 기본 특성 제외 (우선주, 스팩, 중국계, 지주/금융 등)
    companies_df = store.get_companies()
    if companies_df.empty:
        return pd.DataFrame()

    # 기준일 기준 활성 특이종목 지정 내역
    designations_df = store.get_designations(as_of_date=norm_date)
    designated_tickers = set()
    if not designations_df.empty:
        designated_tickers = set(designations_df["ticker"].unique())

    valid_tickers: list[dict[str, Any]] = []
    for _, row in companies_df.iterrows():
        ticker = str(row["ticker"]).strip()
        name = str(row.get("name") or "").strip()
        sector = str(row.get("sector") or "").strip()

        # 우선주 제외
        if row.get("is_preferred") == 1 or is_preferred_stock(ticker, name):
            continue

        # 스팩 제외
        if row.get("is_spac") == 1 or is_spac(name, ticker):
            continue

        # 중국계 기업 제외
        if is_chinese_company(name, ticker):
            continue

        # 지주회사 또는 금융업 제외
        if is_holding_or_financial(sector, name):
            continue

        # 코넥스 시장 제외
        market_val = str(row.get("market") or "").strip().upper()
        if market_val == "KONEX":
            continue

        # 섹터 내 관리/환기/외국기업 키워드 제외
        if any(kw in sector for kw in ("관리종목", "환기종목", "외국기업")):
            continue

        # 12월 결산 법인만 포함
        fiscal_month = row.get("fiscal_month")
        if fiscal_month is not None and fiscal_month != FISCAL_MONTH_DECEMBER:
            continue

        # 활성 관리/환기/거래정지 종목 제외
        if ticker in designated_tickers:
            continue

        # 상장폐지 또는 미상장 종목 제외
        delisted_at = row.get("delisted_at")
        if delisted_at and normalize_date(delisted_at) <= norm_date:
            continue
        listed_at = row.get("listed_at")
        if listed_at and normalize_date(listed_at) > norm_date:
            continue

        valid_tickers.append(row.to_dict())

    if not valid_tickers:
        return pd.DataFrame()

    universe_candidates = pd.DataFrame(valid_tickers)

    # 2. 일별 시세: 시가총액 및 20영업일 평균 거래대금 산출
    trading_days = store.get_trading_days(end_date=norm_date)
    start_date = (
        trading_days[-30]
        if len(trading_days) >= 30
        else (trading_days[0] if trading_days else None)
    )
    price_df = store.get_daily_prices(start_date=start_date, end_date=norm_date)
    if price_df.empty:
        return pd.DataFrame()

    # 종목별 최신 종가, 시가총액, 20영업일 평균 거래대금 집계
    price_metrics: list[dict[str, Any]] = []
    for ticker, group in price_df.groupby("ticker"):
        sorted_group = group.sort_values("date", ascending=True)
        latest_row = sorted_group.iloc[-1]
        last_20 = sorted_group.tail(TRADING_DAYS_ROLLING_WINDOW)
        avg_tv = last_20["trading_value"].mean()

        price_metrics.append(
            {
                "ticker": ticker,
                "price_date": latest_row["date"],
                "close": latest_row["close"],
                "market_cap": latest_row["market_cap"],
                "trading_value_20d_avg": avg_tv,
            }
        )

    price_metrics_df = pd.DataFrame(price_metrics)
    merged = pd.merge(universe_candidates, price_metrics_df, on="ticker", how="inner")
    if merged.empty:
        return pd.DataFrame()

    # 3. 시점 기준(PIT) 재무 지표 결합
    if pit_df is None:
        builder = PITSnapshotBuilder(store)
        corp_codes = merged["corp_code"].dropna().unique().tolist()
        pit_df = builder.build_snapshot(as_of_date=dt_str, corp_codes=corp_codes)

    if pit_df is None or pit_df.empty:
        return pd.DataFrame()

    # 고유번호(corp_code) 기준 결합
    if "ticker" in pit_df.columns:
        final_df = pd.merge(
            merged,
            pit_df.drop(columns=["ticker"], errors="ignore"),
            on="corp_code",
            how="inner",
        )
    else:
        final_df = pd.merge(merged, pit_df, on="corp_code", how="inner")

    if final_df.empty:
        return pd.DataFrame()

    n_with_fin = len(final_df)

    # 4. 재무 건전성 필터 (자본잠식률 <= 0%, 부채비율 조건)
    cond_impairment = (final_df["impairment_ratio"].notna()) & (final_df["impairment_ratio"] <= 0.0)
    if max_debt_ratio is not None:
        cond_debt = (final_df["debt_ratio"].notna()) & (final_df["debt_ratio"] <= max_debt_ratio)
        final_df = final_df[cond_debt & cond_impairment].copy()
    else:
        final_df = final_df[cond_impairment].copy()
    if final_df.empty:
        return pd.DataFrame()

    # 5. 수익성 필터 (TTM 영업이익/지배순이익 > 0)
    cond_ttm_op = final_df["op_income_ttm"] > 0
    cond_ttm_net = final_df["net_income_owner_ttm"] > 0
    if require_quarter_profit:
        cond_qtr_op = final_df["op_income_quarter"] > 0
        cond_qtr_net = final_df["net_income_owner_quarter"] > 0
        final_df = final_df[cond_qtr_op & cond_qtr_net & cond_ttm_op & cond_ttm_net].copy()
    else:
        final_df = final_df[cond_ttm_op & cond_ttm_net].copy()

    if final_df.empty:
        return pd.DataFrame()

    # 6. 시가총액 컷: 재무/수익성 적격 종목군 기준 하위 분위(기본: 20%) 소형주 선정
    if market_cap_quantile < 1.0:
        if n_with_fin < len(universe_candidates) * FINANCIAL_COVERAGE_THRESHOLD:
            target_count = max(1, int(round(len(universe_candidates) * market_cap_quantile)))
            final_df = final_df.sort_values("market_cap", ascending=True).head(target_count).copy()
        else:
            cap_cutoff = final_df["market_cap"].quantile(market_cap_quantile)
            final_df = final_df[final_df["market_cap"] <= cap_cutoff].copy()

    if final_df.empty:
        return pd.DataFrame()

    # 7. 유동성 필터: 20영업일 평균 거래대금 >= min_trading_value
    final_df = final_df[final_df["trading_value_20d_avg"] >= min_trading_value].copy()

    return final_df.reset_index(drop=True)
