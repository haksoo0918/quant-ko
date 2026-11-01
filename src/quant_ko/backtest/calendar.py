"""연 4회 분기 및 월별 리밸런싱 일정을 산출하는 캘린더 모듈."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from quant_ko.data.krx import normalize_date


@dataclass(frozen=True)
class RebalanceEvent:
    """예약된 리밸런싱 이벤트 정보(리밸런싱일, D-1일, 대상 기간 라벨)."""

    rebalance_date: str
    prior_date: str
    period_label: str


def get_rebalance_schedule(
    trading_days: Sequence[str],
    start_date: str | None = None,
    end_date: str | None = None,
    rebalance_freq: str = "quarterly",
) -> list[RebalanceEvent]:
    """주어진 거래일 목록을 바탕으로 리밸런싱 일정을 산출합니다.

    Args:
        trading_days: 전체 영업일 목록.
        start_date: 일정 산출 시작일 (선택 사항).
        end_date: 일정 산출 종료일 (선택 사항).
        rebalance_freq: 리밸런싱 주기 ("quarterly": 연 4회 - 4월 첫 영업일, 5/8/11월 마지막 영업일,
            "monthly": 매월 마지막 영업일).

    Returns:
        리밸런싱 이벤트(RebalanceEvent) 목록.
    """
    if not trading_days:
        return []

    # 고유 거래일 정규화 및 오름차순 정렬
    sorted_days = sorted({normalize_date(d) for d in trading_days})
    day_to_idx = {d: i for i, d in enumerate(sorted_days)}

    # (연도, 월) 단위로 거래일 그룹화
    by_year_month: dict[tuple[int, int], list[str]] = {}
    for d in sorted_days:
        dt = datetime.strptime(d, "%Y-%m-%d")
        key = (dt.year, dt.month)
        by_year_month.setdefault(key, []).append(d)

    norm_start = normalize_date(start_date) if start_date else None
    norm_end = normalize_date(end_date) if end_date else None

    all_years = sorted({dt_key[0] for dt_key in by_year_month})
    events: list[RebalanceEvent] = []

    if rebalance_freq == "monthly":
        for (year, month), days in sorted(by_year_month.items()):
            if not days:
                continue
            reb_date = days[-1]  # 매월 마지막 거래일
            if norm_start and reb_date < norm_start:
                continue
            if norm_end and reb_date > norm_end:
                continue
            idx = day_to_idx[reb_date]
            prior_date = sorted_days[idx - 1] if idx > 0 else reb_date
            events.append(
                RebalanceEvent(
                    rebalance_date=reb_date,
                    prior_date=prior_date,
                    period_label=f"{year:04d}-{month:02d}",
                )
            )
        return events

    # 분기별: 대상 월 4월(첫 영업일), 5/8/11월(마지막 영업일)
    target_months = [
        (4, "first"),
        (5, "last"),
        (8, "last"),
        (11, "last"),
    ]

    events: list[RebalanceEvent] = []
    for year in all_years:
        for month, position in target_months:
            days_in_month = by_year_month.get((year, month))
            if not days_in_month:
                continue

            reb_date = days_in_month[0] if position == "first" else days_in_month[-1]

            if norm_start and reb_date < norm_start:
                continue
            if norm_end and reb_date > norm_end:
                continue

            idx = day_to_idx[reb_date]
            if idx == 0:
                # 이전 거래일(D-1)을 특정할 수 없는 경우 제외
                continue

            prior_date = sorted_days[idx - 1]
            events.append(
                RebalanceEvent(
                    rebalance_date=reb_date,
                    prior_date=prior_date,
                    period_label=f"{year:04d}-{month:02d}",
                )
            )

    return events


def get_cd_daily_return_series(
    trading_days: Sequence[str],
    csv_path: str = "data/cd_daily.csv",
    fallback_annual_rate: float = 0.035,
) -> pd.Series:
    """CD금리 ETF(안전 대피 자산) 대용을 위한 일별 수익률 시리즈를 반환합니다."""
    try:
        cd_df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        cd_df.index = [d.strftime("%Y-%m-%d") for d in cd_df.index]
        cd_close = cd_df["Close"].to_dict()
    except Exception:
        cd_close = {}

    daily_ret = {}
    prev_close = None
    default_daily = fallback_annual_rate / 250.0

    for d in trading_days:
        if d in cd_close:
            curr = cd_close[d]
            if prev_close and prev_close > 0:
                ret = (curr - prev_close) / prev_close
            else:
                ret = default_daily
            prev_close = curr
        else:
            ret = default_daily
        daily_ret[d] = ret

    return pd.Series(daily_ret)
