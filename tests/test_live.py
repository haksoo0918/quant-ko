from unittest.mock import MagicMock

import pytest

from quant_ko.broker.kis import Balance, KisClient, OrderResult, Position
from quant_ko.data.store import DataStore
from quant_ko.live.monitor import DailyMonitor
from quant_ko.live.rebalancer import LiveRebalancer
from quant_ko.notify.discord import DiscordNotifier


@pytest.fixture
def store():
    ds = DataStore(":memory:")
    ds.initialize_schema()

    # Insert test companies
    companies = [
        {
            "ticker": "000010",
            "corp_code": "c1",
            "name": "회사A",
            "market": "KOSDAQ",
            "sector": "IT",
        },
        {
            "ticker": "000020",
            "corp_code": "c2",
            "name": "회사B",
            "market": "KOSDAQ",
            "sector": "제조",
        },
        {
            "ticker": "000030",
            "corp_code": "c3",
            "name": "퇴출대상C",
            "market": "KOSDAQ",
            "sector": "서비스",
        },
    ]
    ds.upsert_companies(companies)

    # Insert prices for 2026-03-31 and 2026-04-01
    prices = [
        {
            "ticker": "000010",
            "date": "2026-03-31",
            "close": 10000,
            "market_cap": 50_000_000_000,
            "trading_value": 500_000_000,
        },
        {
            "ticker": "000020",
            "date": "2026-03-31",
            "close": 20000,
            "market_cap": 60_000_000_000,
            "trading_value": 500_000_000,
        },
        {
            "ticker": "000030",
            "date": "2026-03-31",
            "close": 5000,
            "market_cap": 40_000_000_000,
            "trading_value": 500_000_000,
        },
        {
            "ticker": "000010",
            "date": "2026-04-01",
            "close": 10000,
            "market_cap": 50_000_000_000,
            "trading_value": 500_000_000,
        },
        {
            "ticker": "000020",
            "date": "2026-04-01",
            "close": 20000,
            "market_cap": 60_000_000_000,
            "trading_value": 500_000_000,
        },
        {
            "ticker": "000030",
            "date": "2026-04-01",
            "close": 5000,
            "market_cap": 40_000_000_000,
            "trading_value": 500_000_000,
        },
    ]
    ds.upsert_daily_prices(prices)

    # Insert financials so 000010 and 000020 pass universe and scoring
    for c in ["c1", "c2"]:
        ds.upsert_financials(
            [
                {
                    "corp_code": c,
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

    yield ds
    ds.close()


def test_is_rebalance_date():
    trading_days = [
        "2026-03-31",
        "2026-04-01",
        "2026-04-02",
        "2026-05-28",
        "2026-05-29",
    ]
    rebalancer = LiveRebalancer(
        store=MagicMock(),
        kis_client=MagicMock(),
        notifier=MagicMock(),
    )
    # 2026-04-01 is first trading day of April -> True
    assert rebalancer.is_rebalance_date("2026-04-01", trading_days) is True
    # 2026-04-02 -> False
    assert rebalancer.is_rebalance_date("2026-04-02", trading_days) is False
    # 2026-05-29 is last trading day of May -> True
    assert rebalancer.is_rebalance_date("2026-05-29", trading_days) is True


def test_rebalancer_differential_orders_execution(store):
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Initial balance: 5,000,000 cash, holding 100 shares of 000030 (which is not in target)
    kis_mock.fetch_balance.return_value = Balance(
        cash=5_000_000.0,
        total_eval_amount=5_500_000.0,
        positions=[
            Position(
                ticker="000030",
                name="퇴출대상C",
                qty=100,
                current_price=5000.0,
                eval_amount=500_000.0,
            )
        ],
    )
    # Price mock
    price_map = {"000010": 10000.0, "000020": 20000.0, "000030": 5000.0}
    kis_mock.fetch_current_price.side_effect = lambda t: price_map.get(t, 10000.0)

    # Order place mock
    order_counter = [0]

    def mock_place_order(ticker, side, qty, price, order_type="01"):
        order_counter[0] += 1
        return OrderResult(
            order_no=f"ORD{order_counter[0]:05d}",
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
    )

    result = rebalancer.execute(
        rebalance_date="2026-04-01",
        pit_date="2026-03-31",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert result["success"] is True
    assert len(result["orders"]) > 0

    # Ensure SELL of 000030 occurred FIRST
    first_order = result["orders"][0]
    assert first_order["ticker"] == "000030"
    assert first_order["side"] == "SELL"
    assert first_order["qty"] == 100

    # Orders should be saved in SQLite store
    db_orders = store.get_orders(rebalance_date="2026-04-01", env="mock")
    assert len(db_orders) == len(result["orders"])
    assert "000030" in db_orders["ticker"].values

    # Check discord notification was sent
    assert len(notifier.sent_messages) > 0


def test_rebalancer_retry_unfilled_orders(store):
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Insert an unfulfilled order into store
    order_id = store.insert_order(
        {
            "rebalance_date": "2026-04-01",
            "ticker": "000010",
            "side": "BUY",
            "qty": 50,
            "price": 10000,
            "status": "UNFILLED",
            "filled_qty": 0,
            "env": "mock",
        }
    )

    # Mock KIS fetch_orders returns FILLED for this order
    kis_mock.fetch_orders.return_value = [
        {
            "order_no": "ORD0001",
            "ticker": "000010",
            "side": "BUY",
            "order_qty": 50,
            "filled_qty": 50,
            "order_price": 10000.0,
            "status": "FILLED",
        }
    ]

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
    )

    updated = rebalancer.retry_unfilled_orders(date="2026-04-01")
    assert len(updated) == 1
    assert updated[0]["id"] == order_id
    assert updated[0]["status"] == "FILLED"

    # Check store DB was updated
    saved_orders = store.get_orders(rebalance_date="2026-04-01", env="mock")
    assert saved_orders.iloc[0]["status"] == "FILLED"
    assert saved_orders.iloc[0]["filled_qty"] == 50


def test_daily_monitor_liquidates_designated_stock(store):
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Add designation: 000010 is designated as '관리종목'
    store.upsert_designations(
        [
            {
                "ticker": "000010",
                "type": "관리종목",
                "start_date": "2026-04-05",
                "end_date": None,
            }
        ]
    )

    # Currently holding 000010 and 000020
    kis_mock.fetch_balance.return_value = Balance(
        cash=1_000_000.0,
        total_eval_amount=3_000_000.0,
        positions=[
            Position(
                ticker="000010",
                name="위험종목",
                qty=50,
                current_price=10000.0,
                eval_amount=500_000.0,
            ),
            Position(
                ticker="000020",
                name="정상종목",
                qty=100,
                current_price=20000.0,
                eval_amount=2_000_000.0,
            ),
        ],
    )
    kis_mock.fetch_current_price.return_value = 9500.0
    kis_mock.place_order.return_value = OrderResult(
        order_no="LIQ001",
        ticker="000010",
        side="SELL",
        qty=50,
        price=9500.0,
        success=True,
    )

    monitor = DailyMonitor(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
    )

    liquidated = monitor.check_and_liquidate(as_of_date="2026-04-06")

    assert len(liquidated) == 1
    assert liquidated[0]["ticker"] == "000010"
    assert liquidated[0]["qty"] == 50

    # Ensure SELL order called on kis_client
    kis_mock.place_order.assert_called_once_with(
        ticker="000010",
        side="SELL",
        qty=50,
        price=9500.0,
    )

    # Check alert notification sent to discord
    assert len(notifier.sent_messages) == 1
    alert_payload = notifier.sent_messages[0]
    assert "관리종목" in str(alert_payload) or "긴급 매도" in str(alert_payload)


def test_daily_monitor_no_action_when_healthy(store):
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Holding 000020 (no designation)
    kis_mock.fetch_balance.return_value = Balance(
        cash=1_000_000.0,
        total_eval_amount=2_000_000.0,
        positions=[
            Position(
                ticker="000020",
                name="정상종목",
                qty=50,
                current_price=20000.0,
                eval_amount=1_000_000.0,
            ),
        ],
    )

    monitor = DailyMonitor(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
    )

    liquidated = monitor.check_and_liquidate(as_of_date="2026-04-06")
    assert len(liquidated) == 0
    kis_mock.place_order.assert_not_called()
    assert len(notifier.sent_messages) == 0
