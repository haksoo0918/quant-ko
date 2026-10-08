"""Rebalancing calendar module for 4 quarterly rebalancing dates per year."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from quant_ko.data.krx import normalize_date


@dataclass(frozen=True)
class RebalanceEvent:
    """Represents a scheduled rebalancing event."""

    rebalance_date: str
    prior_date: str
    period_label: str


def get_rebalance_schedule(
    trading_days: Sequence[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[RebalanceEvent]:
    """Calculate the quarterly rebalancing schedule based on PRD section 3.4.

    Rules:
    - 4 rebalancing dates per year:
      - 1st trading day of April (04)
      - Last trading day of May (05)
      - Last trading day of August (08)
      - Last trading day of November (11)
    - Prior date is the trading day immediately preceding rebalance_date.
    - If start_date and/or end_date are provided, filters rebalance_date in [start_date, end_date].
    """
    if not trading_days:
        return []

    # Normalize and sort unique trading days
    sorted_days = sorted({normalize_date(d) for d in trading_days})
    day_to_idx = {d: i for i, d in enumerate(sorted_days)}

    # Group days by (year, month)
    by_year_month: dict[tuple[int, int], list[str]] = {}
    for d in sorted_days:
        dt = datetime.strptime(d, "%Y-%m-%d")
        key = (dt.year, dt.month)
        by_year_month.setdefault(key, []).append(d)

    norm_start = normalize_date(start_date) if start_date else None
    norm_end = normalize_date(end_date) if end_date else None

    # Target months: 4 (first day), 5 (last day), 8 (last day), 11 (last day)
    target_months = [
        (4, "first"),
        (5, "last"),
        (8, "last"),
        (11, "last"),
    ]

    all_years = sorted({dt_key[0] for dt_key in by_year_month.keys()})

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
                # Cannot determine prior trading day
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
