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


def test_dirty_db_duplicate_orders_purge_and_resilience(tmp_path) -> None:
    """DB에 41건 이상의 중복 체결 레코드가 오염 유입되더라도 21건으로 자동 정제됨을 검증합니다."""
    from quant_ko.dashboard.data_loader import (
        _ensure_seed_orders_loaded,
        load_account_and_positions,
        load_actual_trade_logs,
    )
    from quant_ko.data.store import DataStore

    db_p = tmp_path / "quant_ko.db"
    store = DataStore(db_p)
    store.initialize_schema()
    _ensure_seed_orders_loaded(store)

    # 1. store.insert_order 레벨에서 실전 FILLED 중복 삽입 원천 차단 검증
    real_orders = store.get_orders(env="real")
    for _, r in real_orders.iterrows():
        if r["status"] == "FILLED":
            ret_id = store.insert_order(
                {
                    "rebalance_date": "2026-11-03",
                    "ticker": r["ticker"],
                    "side": r["side"],
                    "qty": r["qty"],
                    "price": r["price"],
                    "status": "FILLED",
                    "filled_qty": r["filled_qty"],
                    "env": "real",
                }
            )
            assert ret_id == r["id"]  # 기존 주문 ID 재사용 및 중복 row 미생성

    assert len(store.get_orders(env="real")) == 21, "insert_order 레벨 중복 차단 실패"

    # 2. 로우 레벨 SQL로 강제 중복(20건)을 억지로 밀어 넣었을 때 (총 41건 오염 시뮬레이션)
    for _, r in real_orders.iterrows():
        if r["status"] == "FILLED":
            with store.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO orders (rebalance_date, ticker, side, qty, price, status, filled_qty, env)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("2026-11-04", r["ticker"], r["side"], r["qty"], r["price"], "FILLED", r["filled_qty"], "real"),
                )
                conn.commit()

    assert len(store.get_orders(env="real")) == 41

    # 3. DB 물리 정제 검증 (initialize_schema 호출 시 21건으로 즉시 복원)
    store.initialize_schema()
    purged_orders = store.get_orders(env="real")
    assert len(purged_orders) == 21, f"DB 퍼지 실패: {len(purged_orders)}건"

    # 4. 강제 중복 상태에서도 load_actual_trade_logs 및 KPI 카드는 무조건 21건 반환
    clean_logs = load_actual_trade_logs(db_path=str(db_p), mode_filter="REAL")
    assert len(clean_logs) == 21, f"load_actual_trade_logs 21건 보장 실패: {len(clean_logs)}건"
    assert len(clean_logs[clean_logs["체결상태"] == "FILLED"]) == 20
    assert len(clean_logs[clean_logs["체결상태"] == "RESOLVED"]) == 1

    acc_info = load_account_and_positions(db_path=str(db_p), fetch_live_kis=False)
    assert acc_info["total_orders_count"] == 21
