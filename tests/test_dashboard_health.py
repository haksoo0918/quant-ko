"""Quant-KO 대시보드 데이터 건강성 및 핵심 수치 무결성 회귀 방지 테스트."""

from __future__ import annotations

from scripts.verify_dashboard_health import (
    verify_account_and_equity_integrity,
    verify_top20_targets_integrity,
    verify_trade_logs_integrity,
)


def test_trade_logs_integrity() -> None:
    """Tab 2 실제 거래기록 4대 지표(21건, 20건, 0건, 1건) 및 종목명 100% 매핑을 검증합니다."""
    metrics = verify_trade_logs_integrity()
    assert metrics["total"] == 21
    assert metrics["buy"] == 20
    assert metrics["sell"] == 0
    assert metrics["unfilled"] == 1


def test_account_and_equity_integrity() -> None:
    """Tab 1 계좌 총평가액과 자산 곡선 종가 일치성을 검증합니다."""
    verify_account_and_equity_integrity()


def test_top20_targets_integrity() -> None:
    """Tab 4 최신 타깃 20종목의 9대 팩터 스코어 및 메타데이터 정합성을 검증합니다."""
    verify_top20_targets_integrity()
