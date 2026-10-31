"""Unit and integration tests for catch-up rebalancing and notification refinement."""

from unittest.mock import MagicMock

import pytest

from quant_ko.broker.kis import Balance, KisClient, OrderResult
from quant_ko.data.store import DataStore
from quant_ko.live.rebalancer import LiveRebalancer
from quant_ko.notify.discord import DiscordNotifier


@pytest.fixture
def store():
    ds = DataStore(":memory:")
    ds.initialize_schema()

    # Insert 20 mock companies
    companies = [
        {
            "ticker": f"0000{i:02d}",
            "corp_code": f"c{i:02d}",
            "name": f"종목_{i:02d}",
            "market": "KOSDAQ",
            "sector": "제조",
        }
        for i in range(1, 21)
    ]
    ds.upsert_companies(companies)

    prices = []
    for i in range(1, 21):
        prices.append(
            {
                "ticker": f"0000{i:02d}",
                "date": "2026-10-30",
                "close": 10000.0,
                "market_cap": 50_000_000_000,
                "trading_value": 500_000_000,
            }
        )
        prices.append(
            {
                "ticker": f"0000{i:02d}",
                "date": "2026-11-02",
                "close": 10000.0,
                "market_cap": 50_000_000_000,
                "trading_value": 500_000_000,
            }
        )
    ds.upsert_daily_prices(prices)

    for i in range(1, 21):
        ds.upsert_financials(
            [
                {
                    "corp_code": f"c{i:02d}",
                    "fiscal_year": 2025,
                    "quarter": 4,
                    "fs_type": "CFS",
                    "revenue": 10_000_000_000,
                    "gross_profit": 5_000_000_000,
                    "op_income": 2_000_000_000,
                    "net_income_owner": 1_500_000_000,
                    "total_liabilities": 5_000_000_000,
                    "total_equity": 10_000_000_000,
                    "capital_stock": 2_000_000_000,
                    "rcept_dt": "20260320",
                },
            ]
        )
    return ds


def test_rebalance_message_refinement(store):
    """Test refined Discord message: buy field title and +5% catch-up notice."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    kis_mock.fetch_balance.return_value = Balance(
        cash=1_000_000.0,
        total_eval_amount=1_000_000.0,
        positions=[],
    )
    kis_mock.fetch_current_price.return_value = 10000.0
    kis_mock.place_order.return_value = OrderResult(
        order_no="ORD001",
        ticker="000001",
        side="BUY",
        qty=10,
        price=10500.0,
        success=True,
        message="OK",
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
        strategy_mode="seasonality",
    )

    result = rebalancer.execute(
        rebalance_date="2026-10-30",
        pit_date="2026-10-30",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert result["success"] is True
    assert len(notifier.sent_messages) > 0
    embed = notifier.sent_messages[0]["embeds"][0]

    # Verify field title
    buy_fields = [f for f in embed.get("fields", []) if "매수 주문 접수" in f["name"]]
    assert len(buy_fields) >= 1
    assert "15:30 동시호가 체결 예정" in buy_fields[0]["name"]

    # Verify notice in description or footer
    notice_text = "※ 15:30 동시호가 중 +5% 초과 급등 등으로 미체결이 발생할 경우, 다음 거래일 15:20에 남은 예수금 범위 내에서 자동 보충 매수됩니다."
    desc = embed.get("description", "")
    footer = embed.get("footer", {}).get("text", "")
    assert notice_text in desc or notice_text in footer


def test_catchup_no_pending_orders_exits_immediately(store):
    """Test when no PENDING_CATCHUP queue exists, catchup exits immediately without broker calls."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Orders exist but none with status PENDING_CATCHUP
    store.insert_order(
        {
            "rebalance_date": "2026-10-30",
            "ticker": "000001",
            "side": "BUY",
            "qty": 50,
            "price": 10000.0,
            "status": "ORDERED",
            "env": "mock",
        }
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
        strategy_mode="seasonality",
    )

    result = rebalancer.catchup_unfilled_orders(as_of_date="2026-11-02", dry_run=False)

    assert result["success"] is True
    assert result["count"] == 0
    assert result["orders"] == []
    assert "보충 매수 대상 큐(PENDING_CATCHUP)가 없습니다." in result["message"]
    # Verify no broker balance fetch or order placement occurred
    assert kis_mock.fetch_balance.call_count == 0
    assert kis_mock.place_order.call_count == 0


def test_catchup_executes_pending_order_and_resolves(store):
    """Test when 1 stock has status PENDING_CATCHUP, catchup executes 1 buy and marks RESOLVED."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Insert order with PENDING_CATCHUP status
    order_id = store.insert_order(
        {
            "rebalance_date": "2026-10-30",
            "ticker": "000020",
            "side": "BUY",
            "qty": 50,
            "price": 10000.0,
            "status": "PENDING_CATCHUP",
            "env": "mock",
        }
    )

    kis_mock.fetch_balance.return_value = Balance(
        cash=600_000.0,
        total_eval_amount=10_000_000.0,
        positions=[],
    )
    kis_mock.fetch_current_price.return_value = 10000.0

    placed_orders = []

    def mock_place_order(ticker, side, qty, price, order_type="00"):
        placed_orders.append((ticker, side, qty, price, order_type))
        return OrderResult(
            order_no="ORD_CATCHUP_01",
            ticker=ticker,
            side=side,
            qty=qty,
            price=price,
            success=True,
            message="OK",
        )

    kis_mock.place_order.side_effect = mock_place_order

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
        strategy_mode="seasonality",
        buy_buffer_pct=0.05,
    )

    result = rebalancer.catchup_unfilled_orders(as_of_date="2026-11-02", dry_run=False)

    assert result["success"] is True
    assert result["count"] == 1
    assert len(placed_orders) == 1

    ticker, side, qty, price, order_type = placed_orders[0]
    assert ticker == "000020"
    assert side == "BUY"
    assert qty > 0
    assert price == 10500.0  # +5%
    assert order_type == "00"

    # Verify status changed to RESOLVED in DB
    orders_df = store.get_orders(env="mock")
    target_row = orders_df[orders_df["id"] == order_id]
    assert len(target_row) == 1
    assert target_row["status"].iloc[0] == "RESOLVED"

    # Verify PENDING_CATCHUP queue is now empty
    pending_left = store.get_orders(env="mock", status="PENDING_CATCHUP")
    assert pending_left.empty

    # Verify Discord notification
    assert len(notifier.sent_messages) == 1
    embed = notifier.sent_messages[0]["embeds"][0]
    assert "📢 [미체결 잔여 종목 보충 매수]" in embed["title"]


def test_catchup_fails_marks_expired_and_notifies_discord(store):
    """Test when catchup order fails, status becomes EXPIRED (no rollover) and Discord alert is sent."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    order_id = store.insert_order(
        {
            "rebalance_date": "2026-10-30",
            "ticker": "000020",
            "side": "BUY",
            "qty": 50,
            "price": 10000.0,
            "status": "PENDING_CATCHUP",
            "env": "mock",
        }
    )

    kis_mock.fetch_balance.return_value = Balance(
        cash=600_000.0,
        total_eval_amount=10_000_000.0,
        positions=[],
    )
    kis_mock.fetch_current_price.return_value = 10000.0
    kis_mock.place_order.return_value = OrderResult(
        order_no="",
        ticker="000020",
        side="BUY",
        qty=50,
        price=10500.0,
        success=False,
        message="증거금 부족 / 상한가 초과",
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
        strategy_mode="seasonality",
        buy_buffer_pct=0.05,
    )

    result = rebalancer.catchup_unfilled_orders(as_of_date="2026-11-02", dry_run=False)

    assert result["success"] is True
    assert result["count"] == 0

    # Verify order is marked EXPIRED (queue completely destroyed, no rollover)
    orders_df = store.get_orders(env="mock")
    target_row = orders_df[orders_df["id"] == order_id]
    assert len(target_row) == 1
    assert target_row["status"].iloc[0] == "EXPIRED"

    # Queue is completely cleared
    pending_left = store.get_orders(env="mock", status="PENDING_CATCHUP")
    assert pending_left.empty

    # Verify Discord notification for final failure
    assert len(notifier.sent_messages) == 1
    embed = notifier.sent_messages[0]["embeds"][0]
    assert "⚠️ [보충 매수 최종 실패]" in embed["title"]


def test_catchup_insufficient_cash_marks_expired(store):
    """Test that insufficient cash marks PENDING_CATCHUP orders EXPIRED and notifies final failure."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    order_id = store.insert_order(
        {
            "rebalance_date": "2026-10-30",
            "ticker": "000020",
            "side": "BUY",
            "qty": 50,
            "price": 10000.0,
            "status": "PENDING_CATCHUP",
            "env": "mock",
        }
    )

    kis_mock.fetch_balance.return_value = Balance(
        cash=0.0,
        total_eval_amount=0.0,
        positions=[],
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
        strategy_mode="seasonality",
    )

    result = rebalancer.catchup_unfilled_orders(as_of_date="2026-11-02", dry_run=False)

    assert result["count"] == 0
    orders_df = store.get_orders(env="mock")
    target_row = orders_df[orders_df["id"] == order_id]
    assert target_row["status"].iloc[0] == "EXPIRED"

    # Discord alert sent
    assert len(notifier.sent_messages) == 1
    embed = notifier.sent_messages[0]["embeds"][0]
    assert "⚠️ [보충 매수 최종 실패]" in embed["title"]


def test_execute_records_pending_catchup_on_buy_failure(store):
    """Test that when a BUY order fails during execute(), it is logged as PENDING_CATCHUP."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    kis_mock.fetch_balance.return_value = Balance(
        cash=1_000_000.0,
        total_eval_amount=1_000_000.0,
        positions=[],
    )
    kis_mock.fetch_current_price.return_value = 10000.0
    # Simulate BUY order failure
    kis_mock.place_order.return_value = OrderResult(
        order_no="",
        ticker="000001",
        side="BUY",
        qty=10,
        price=10500.0,
        success=False,
        message="호가 한도 초과 거절",
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
        strategy_mode="seasonality",
    )

    result = rebalancer.execute(
        rebalance_date="2026-10-30",
        pit_date="2026-10-30",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert result["success"] is True
    # Verify in DB that failed BUY orders have status PENDING_CATCHUP
    failed_buys = store.get_orders(rebalance_date="2026-10-30", env="mock", status="PENDING_CATCHUP")
    assert len(failed_buys) > 0


def test_retry_unfilled_orders_marks_unfilled_buy_as_pending_catchup(store):
    """Test that retry_unfilled_orders marks 15:35 unfilled/cancelled BUY orders as PENDING_CATCHUP."""
    order_id = store.insert_order(
        {
            "rebalance_date": "2026-10-30",
            "ticker": "000015",
            "side": "BUY",
            "qty": 50,
            "price": 10000.0,
            "status": "ORDERED",
            "filled_qty": 0,
            "env": "mock",
        }
    )

    kis_mock = MagicMock(spec=KisClient)
    # Broker reports CANCELLED with filled_qty = 0
    kis_mock.fetch_orders.return_value = [
        {
            "ticker": "000015",
            "status": "CANCELLED",
            "filled_qty": 0,
        }
    ]

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        env="mock",
    )

    updated = rebalancer.retry_unfilled_orders(date="2026-10-30")
    assert len(updated) == 1
    assert updated[0]["status"] == "PENDING_CATCHUP"

    # Verify DB
    orders_df = store.get_orders(env="mock")
    row = orders_df[orders_df["id"] == order_id]
    assert row["status"].iloc[0] == "PENDING_CATCHUP"


def test_main_cli_rebalance_catchup_integration(monkeypatch, store):
    """Test CLI main() when mode=rebalance on non-rebalance day during active season."""
    from quant_ko.main import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "main.py",
            "--mode",
            "rebalance",
            "--date",
            "2026-11-02",
            "--env",
            "mock",
            "--strategy",
            "seasonality",
        ],
    )
    monkeypatch.setattr("quant_ko.main.DataStore", lambda *args, **kwargs: store)

    # Mock LiveRebalancer.is_rebalance_date to return False
    monkeypatch.setattr(LiveRebalancer, "is_rebalance_date", lambda self, d, t: False)

    # Mock catchup_unfilled_orders to simulate 1 executed order
    catchup_called = []

    def mock_catchup(self, as_of_date, dry_run=False):
        catchup_called.append((as_of_date, dry_run))
        return {
            "success": True,
            "orders": [{"ticker": "000020", "side": "BUY", "qty": 10, "price": 10000.0}],
        }

    monkeypatch.setattr(LiveRebalancer, "catchup_unfilled_orders", mock_catchup)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert len(catchup_called) == 1
    assert catchup_called[0][0] == "2026-11-02"


def test_main_cli_rebalance_parking_skips_catchup(monkeypatch, store):
    """Test CLI main() when mode=rebalance on non-rebalance day during parking period (5~10월)."""
    from quant_ko.main import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "main.py",
            "--mode",
            "rebalance",
            "--date",
            "2026-06-15",
            "--env",
            "mock",
            "--strategy",
            "seasonality",
        ],
    )
    monkeypatch.setattr("quant_ko.main.DataStore", lambda *args, **kwargs: store)
    monkeypatch.setattr(LiveRebalancer, "is_rebalance_date", lambda self, d, t: False)

    catchup_called = []
    monkeypatch.setattr(
        LiveRebalancer,
        "catchup_unfilled_orders",
        lambda self, as_of_date, dry_run=False: catchup_called.append(as_of_date),
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    # In parking period (06-15), catchup_unfilled_orders is NOT called
    assert len(catchup_called) == 0

