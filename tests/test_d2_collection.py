"""Tests for Rebalance D-2 Data Collection and Pre-flight Freshness Check."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quant_ko.data.store import DataStore
from quant_ko.live.rebalancer import LiveRebalancer


@pytest.fixture
def test_db_with_calendar(tmp_path: Path) -> Path:
    """임시 SQLite DB 생성 및 기본 캘린더/기업 데이터 주입."""
    db_file = tmp_path / "test_d2.db"
    store = DataStore(db_file)
    store.initialize_schema()

    store.upsert_companies(
        [
            {
                "ticker": "000010",
                "corp_code": "00000001",
                "name": "알파테크",
                "market": "KOSDAQ",
                "sector": "IT",
                "listed_at": "2015-01-01",
                "delisted_at": None,
                "fiscal_month": 12,
                "is_preferred": 0,
                "is_spac": 0,
            }
        ]
    )

    # 2026-10-27(D-3), 2026-10-28(D-2), 2026-10-29(D-1), 2026-10-30(D-Day 월말 리밸런싱일)
    prices = [
        {
            "ticker": "000010",
            "date": d,
            "close": 1000.0,
            "market_cap": 30_000_000_000.0,
            "trading_value": 500_000_000.0,
        }
        for d in ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]
    ]
    store.upsert_daily_prices(prices)
    return db_file


def test_is_d_minus_two_detection(test_db_with_calendar: Path) -> None:
    """D-2 일자 정확 판정 단위 테스트."""
    store = DataStore(test_db_with_calendar)
    mock_kis = MagicMock()
    mock_notifier = MagicMock()

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=mock_kis,
        notifier=mock_notifier,
        env="mock",
    )

    trading_days = ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]
    # 2026-10-30이 월말 마지막 영업일(리밸런싱일)
    # D-1: 2026-10-29
    # D-2: 2026-10-28

    assert rebalancer.is_rebalance_date("2026-10-30", trading_days) is True
    assert rebalancer.is_d_minus_one("2026-10-29", trading_days) is True
    assert rebalancer.is_d_minus_two("2026-10-28", trading_days) is True
    assert rebalancer.is_d_minus_two("2026-10-27", trading_days) is False
    assert rebalancer.is_d_minus_two("2026-10-29", trading_days) is False
    assert rebalancer.is_d_minus_two("2026-10-30", trading_days) is False


def test_collect_d_minus_two_data(test_db_with_calendar: Path) -> None:
    """D-2 시점 최신 데이터 수집 및 디스코드 알림 전송 검증."""
    store = DataStore(test_db_with_calendar)
    mock_kis = MagicMock()
    mock_notifier = MagicMock()

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=mock_kis,
        notifier=mock_notifier,
        env="mock",
    )

    with patch("quant_ko.live.rebalancer.collect_latest_market_data") as mock_collect:
        mock_collect.return_value = {
            "success": True,
            "prices_count": 50,
            "financials_count": 0,
            "latest_date": "2026-10-28",
        }

        res = rebalancer.collect_d_minus_two_data(as_of_date="2026-10-28")

        assert res["success"] is True
        assert res["prices_count"] == 50
        assert mock_notifier.send_text.called or mock_notifier.send_embed.called


def test_ensure_data_freshness_triggers_collection_if_stale(tmp_path: Path) -> None:
    """DB 시세가 오래되었을 경우 Pre-flight Check에서 자동 수집 트리거 검증."""
    db_file = tmp_path / "stale.db"
    store = DataStore(db_file)
    store.initialize_schema()

    # 10월 20일 시세만 있는 과거 DB
    store.upsert_daily_prices(
        [
            {
                "ticker": "000010",
                "date": "2026-10-20",
                "close": 1000.0,
                "market_cap": 30_000_000_000.0,
                "trading_value": 500_000_000.0,
            }
        ]
    )

    mock_kis = MagicMock()
    mock_notifier = MagicMock()
    rebalancer = LiveRebalancer(
        store=store,
        kis_client=mock_kis,
        notifier=mock_notifier,
        env="mock",
    )

    with patch.object(rebalancer, "collect_d_minus_two_data") as mock_collect_d2:
        mock_collect_d2.return_value = {"success": True, "prices_count": 10}

        # D-Day(2026-10-30) 시점에 Pre-flight Check 실행 시 과거 데이터 감지하여 자동 수집 호출
        rebalancer.ensure_data_freshness(as_of_date="2026-10-30")
        assert mock_collect_d2.called is True
