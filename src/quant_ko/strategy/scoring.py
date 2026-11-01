"""9팩터 점수 산출 및 포트폴리오 상위 종목 선정 엔진."""

import numpy as np
import pandas as pd

VALUE_FACTORS = [
    ("per", "net_income_owner_ttm"),
    ("psr", "revenue_ttm"),
    ("por", "op_income_ttm"),
    ("pgpr", "gross_profit_ttm"),
]

GROWTH_FACTORS = [
    ("net_income_owner_yoy", "net_income_owner_turnaround"),
    ("op_income_yoy", "op_income_turnaround"),
    ("gross_profit_yoy", "gross_profit_turnaround"),
    ("revenue_yoy", "revenue_turnaround"),
]


def _rank_growth_with_turnaround(
    df: pd.DataFrame,
    growth_col: str,
    turnaround_col: str,
) -> pd.Series:
    """흑자전환 기업을 최상위로 우선 배정한 후 성장률 내림차순으로 순위를 부여합니다.

    흑자전환(Turnaround) 종목은 1, 2, ... 최상위 순위를 부여받으며,
    흑자전환 종목군 및 비흑자전환 종목군 각각의 내부에서는 성장률 내림차순으로 정렬됩니다.
    """
    is_turnaround = df[turnaround_col].fillna(False).astype(bool)
    growth = pd.to_numeric(df[growth_col], errors="coerce").fillna(-np.inf)

    # 흑자전환 기업이 비흑자전환 기업보다 항상 높은 순위를 갖도록 큰 가산점(1e9) 부여
    effective_growth = np.where(is_turnaround, 1e9 + growth, growth)

    # 성장률 inf/nan 값 안전 처리
    effective_series = pd.Series(effective_growth, index=df.index)
    return effective_series.rank(ascending=False, method="min").astype(int)


def score_and_select(
    universe_df: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    """9팩터 모델 종합 점수를 산출하고 순위를 매겨 상위 N개 포트폴리오를 선정합니다.

    9팩터 모델 구성:
    - 소형주 팩터(1개): 시가총액 오름차순 (낮을수록 우수)
    - 밸류 팩터(4개): PER, PSR, POR, PGPR 오름차순 (저평가일수록 우수)
    - 성장 팩터(4개): 지배주주순이익 YoY, 영업이익 YoY, 매출총이익 YoY, 매출액 YoY 내림차순
      (흑자전환 기업 최우선 순위 배정)

    종합 순위(Total Rank) = Rank(시총) + 합산(Rank(밸류 4종)) + 합산(Rank(성장 4종))
    정렬 기준: 종합 순위 오름차순, 동점자 처리: 시가총액 오름차순 (더 작은 기업 우선)
    선정 및 비중: 상위 N개 종목 동일 가중(1 / N).

    Args:
        universe_df: 유니버스 필터링을 통과한 후보 종목 DataFrame.
        top_n: 최종 포트폴리오 편입 종목 수 (기본값: 20).

    Returns:
        상위 top_n개 선정 종목 및 목표 비중(weight)이 포함된 DataFrame.
    """
    if universe_df.empty:
        return pd.DataFrame()

    df = universe_df.copy()

    # 1. 시가총액 팩터 순위 (오름차순: 소형주일수록 1위에 가까움)
    df["rank_market_cap"] = df["market_cap"].rank(ascending=True, method="min").astype(int)

    # 2. 밸류 팩터 순위 (오름차순: 배수가 낮을수록 저평가 우수)
    for ratio_name, denom_col in VALUE_FACTORS:
        denom = df[denom_col].replace(0, np.nan)
        df[ratio_name] = df["market_cap"] / denom
        # 결측치 및 비정상치는 최하위 순위 부여
        df[f"rank_{ratio_name}"] = (
            df[ratio_name].rank(ascending=True, method="min", na_option="bottom").astype(int)
        )

    # 3. 성장성 팩터 순위 (내림차순, 흑자전환 기업 최우선 순위)
    for growth_col, turnaround_col in GROWTH_FACTORS:
        df[f"rank_{growth_col}"] = _rank_growth_with_turnaround(df, growth_col, turnaround_col)

    # 4. 종합 순위 합산 (Total Rank)
    value_rank_cols = [f"rank_{ratio_name}" for ratio_name, _ in VALUE_FACTORS]
    growth_rank_cols = [f"rank_{growth_col}" for growth_col, _ in GROWTH_FACTORS]

    df["total_rank"] = (
        df["rank_market_cap"] + df[value_rank_cols].sum(axis=1) + df[growth_rank_cols].sum(axis=1)
    )

    # 5. 종합 순위 오름차순 정렬 (동점 시 시가총액 작은 순)
    sorted_df = df.sort_values(
        by=["total_rank", "market_cap"],
        ascending=[True, True],
    ).reset_index(drop=True)

    # 6. 상위 N개 종목 선정 및 동일 비중(1/N) 부여
    n_select = min(len(sorted_df), top_n)
    selected = sorted_df.iloc[:n_select].copy()

    if n_select > 0:
        selected["weight"] = 1.0 / n_select
    else:
        selected["weight"] = 0.0

    return selected.reset_index(drop=True)
