"""Unit and integration tests for catch-up rebalancing and notification refinement."""

from unittest.mock import MagicMock

import pytest

from quant_ko.broker.kis import Balance, KisClient, OrderResult, Position
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


def test_catchup_unfilled_orders_buys_unfilled_stock(store):
    """Test when 1 stock was unfilled previously, catchup buys it using remaining cash at 15:20."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # 20 target stocks were scheduled on 2026-10-30
    for i in range(1, 21):
        store.insert_order(
            {
                "rebalance_date": "2026-10-30",
                "ticker": f"0000{i:02d}",
                "side": "BUY",
                "qty": 50,
                "price": 10000.0,
                "status": "ORDERED",
                "env": "mock",
            }
        )

    # Broker has 19 stocks held, 000020 is missing
    held_positions = [
        Position(
            ticker=f"0000{i:02d}",
            name=f"종목_{i:02d}",
            qty=50,
            current_price=10000.0,
            eval_amount=500_000.0,
        )
        for i in range(1, 20)  # 1 to 19 held, 20 is missing
    ]

    kis_mock.fetch_balance.return_value = Balance(
        cash=600_000.0,
        total_eval_amount=10_100_000.0,
        positions=held_positions,
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
    # +5% limit price of 10,000 is 10,500
    assert price == 10500.0
    assert order_type == "00"

    # Verify order logged in DB
    orders_in_db = store.get_orders(rebalance_date="2026-11-02", env="mock")
    assert len(orders_in_db) == 1
    assert orders_in_db["ticker"].iloc[0] == "000020"

    # Verify Discord notification
    assert len(notifier.sent_messages) == 1
    embed = notifier.sent_messages[0]["embeds"][0]
    assert "📢 [미체결 잔여 종목 보충 매수]" in embed["title"]


def test_catchup_skips_dangerous_designated_stocks(store):
    """Test that designated dangerous stocks (관리/투자주의환기종목) are skipped."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    for i in range(1, 21):
        store.insert_order(
            {
                "rebalance_date": "2026-10-30",
                "ticker": f"0000{i:02d}",
                "side": "BUY",
                "qty": 50,
                "price": 10000.0,
                "status": "ORDERED",
                "env": "mock",
            }
        )

    # 000020 is missing from held positions
    held_positions = [
        Position(
            ticker=f"0000{i:02d}",
            name=f"종목_{i:02d}",
            qty=50,
            current_price=10000.0,
            eval_amount=500_000.0,
        )
        for i in range(1, 20)
    ]

    kis_mock.fetch_balance.return_value = Balance(
        cash=600_000.0,
        total_eval_amount=10_100_000.0,
        positions=held_positions,
    )
    kis_mock.fetch_current_price.return_value = 10000.0

    # Mark 000020 as 관리종목 in designations table
    store.upsert_designations(
        [
            {
                "ticker": "000020",
                "type": "관리종목",
                "start_date": "2026-11-01",
                "end_date": None,
            }
        ]
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
    assert len(result["orders"]) == 0
    assert kis_mock.place_order.call_count == 0


def test_catchup_skips_parking_period(store):
    """Test that parking period (5~10월) skips catchup."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
        strategy_mode="seasonality",
    )

    result = rebalancer.catchup_unfilled_orders(as_of_date="2026-06-15", dry_run=False)

    assert result["success"] is True
    assert result["count"] == 0
    assert len(result["orders"]) == 0
    assert kis_mock.fetch_balance.call_count == 0


def test_catchup_no_orders_when_all_20_stocks_held(store):
    """Test when all 20 stocks are held, no orders are sent."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    for i in range(1, 21):
        store.insert_order(
            {
                "rebalance_date": "2026-10-30",
                "ticker": f"0000{i:02d}",
                "side": "BUY",
                "qty": 50,
                "price": 10000.0,
                "status": "ORDERED",
                "env": "mock",
            }
        )

    # All 20 held
    held_positions = [
        Position(
            ticker=f"0000{i:02d}",
            name=f"종목_{i:02d}",
            qty=50,
            current_price=10000.0,
            eval_amount=500_000.0,
        )
        for i in range(1, 21)
    ]

    kis_mock.fetch_balance.return_value = Balance(
        cash=50_000.0,
        total_eval_amount=10_050_000.0,
        positions=held_positions,
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
    assert len(result["orders"]) == 0
    assert kis_mock.place_order.call_count == 0


def test_catchup_insufficient_cash(store):
    """Test that insufficient cash prevents catchup orders and notifies Discord."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Target stock 000020 missing
    store.insert_order(
        {
            "rebalance_date": "2026-10-30",
            "ticker": "000020",
            "side": "BUY",
            "qty": 50,
            "price": 10000.0,
            "status": "ORDERED",
            "env": "mock",
        }
    )

    # Cash is 0
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

    assert result["success"] is False
    assert result["count"] == 0
    assert "예수금 부족" in result["message"]
    assert any("예수금 부족으로 보충 매수 불가" in msg.get("content", "") for msg in notifier.sent_messages)


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

