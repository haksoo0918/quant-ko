from unittest.mock import MagicMock

import pytest

from quant_ko.broker.kis import Balance, KisClient, OrderResult, Position
from quant_ko.data.store import DataStore
from quant_ko.live.monitor import DailyMonitor
from quant_ko.live.rebalancer import LiveRebalancer, _chunk_field_lines
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
        "2026-04-30",
        "2026-05-28",
        "2026-05-29",
    ]
    rebalancer = LiveRebalancer(
        store=MagicMock(),
        kis_client=MagicMock(),
        notifier=MagicMock(),
        rebalance_freq="monthly",
    )
    # 2026-03-31 is last trading day of March -> True
    assert rebalancer.is_rebalance_date("2026-03-31", trading_days) is True
    # 2026-04-01 -> False (not month end)
    assert rebalancer.is_rebalance_date("2026-04-01", trading_days) is False
    # 2026-04-30 is last trading day of April -> True
    assert rebalancer.is_rebalance_date("2026-04-30", trading_days) is True
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


def test_rebalancer_seasonality_parking_period(store):
    """5~10월 파킹 구간 리밸런싱 시 TIGER CD금리(357870) 100% 매수 주문 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Balance: 2,000,000 KRW cash, no holdings
    kis_mock.fetch_balance.return_value = Balance(
        cash=2_000_000.0,
        total_eval_amount=2_000_000.0,
        positions=[],
    )
    # TIGER CD ETF price: 53,000 KRW
    kis_mock.fetch_current_price.return_value = 53000.0

    order_counter = [0]

    def mock_place_order(ticker, side, qty, price, order_type="01"):
        order_counter[0] += 1
        return OrderResult(
            order_no=f"ORD_PARK_{order_counter[0]:05d}",
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
    )

    result = rebalancer.execute(
        rebalance_date="2026-05-29",  # May -> Parking period
    )

    assert result["success"] is True
    assert len(result["orders"]) == 1
    order = result["orders"][0]
    assert order["ticker"] == "357870"
    assert order["side"] == "BUY"
    # 2,000,000 / (53000 * 1.003) = ~37 shares
    assert order["qty"] >= 35


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


def test_daily_monitor_liquidates_short_designation_types(store):
    """한국거래소 DB 단축 표기('관리', '투자주의환기')도 정상 감시하여 매도하는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Add designations with short forms: '관리', '투자주의환기'
    store.upsert_designations(
        [
            {
                "ticker": "000010",
                "type": "관리",
                "start_date": "2026-04-05",
                "end_date": None,
            },
            {
                "ticker": "000020",
                "type": "투자주의환기",
                "start_date": "2026-04-05",
                "end_date": None,
            },
        ]
    )

    kis_mock.fetch_balance.return_value = Balance(
        cash=1_000_000.0,
        total_eval_amount=3_000_000.0,
        positions=[
            Position(
                ticker="000010",
                name="관리주",
                qty=50,
                current_price=10000.0,
                eval_amount=500_000.0,
            ),
            Position(
                ticker="000020",
                name="환기주",
                qty=100,
                current_price=20000.0,
                eval_amount=2_000_000.0,
            ),
        ],
    )
    kis_mock.fetch_current_price.return_value = 10000.0
    kis_mock.place_order.return_value = OrderResult(
        order_no="LIQ_SHORT",
        ticker="000010",
        side="SELL",
        qty=50,
        price=10000.0,
        success=True,
    )

    monitor = DailyMonitor(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
    )

    liquidated = monitor.check_and_liquidate(as_of_date="2026-04-06")
    # Both '관리' and '투자주의환기' must be detected and liquidated!
    assert len(liquidated) == 2
    liquidated_tickers = {item["ticker"] for item in liquidated}
    assert liquidated_tickers == {"000010", "000020"}

    # Check alert notifications sent to discord (1 per liquidated stock)
    assert len(notifier.sent_messages) == 2
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
    # 하트비트 생존 알림은 1건 정상 발송되어야 함 (긴급 매도는 없음)
    assert len(notifier.sent_messages) == 1
    assert "08:30 일일 감시 봇 생존 확인" in notifier.sent_messages[0]["embeds"][0]["title"]


def test_rebalancer_comprehensive_discord_notification(store):
    """Test detailed Discord notification embed with stock names and proper sections."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

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
    price_map = {"000010": 10000.0, "000020": 20000.0, "000030": 5000.0}
    kis_mock.fetch_current_price.side_effect = lambda t: price_map.get(t, 10000.0)

    kis_mock.place_order.side_effect = lambda ticker, side, qty, price, order_type="01": (
        OrderResult(
            order_no="ORD123",
            ticker=ticker,
            side=side,
            qty=qty,
            price=price,
            success=True,
            message="정상 체결",
        )
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
    )

    rebalancer.execute(
        rebalance_date="2026-04-01",
        pit_date="2026-03-31",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert len(notifier.sent_messages) == 1
    embed = notifier.sent_messages[0]["embeds"][0]

    assert embed["title"] == "📈 [리밸런싱 완료] 2026-04-01"
    assert embed["color"] == 0x2ECC71

    field_map = {f["name"]: f["value"] for f in embed["fields"]}

    # 1. Target portfolio contains company names and weights
    target_field = [v for k, v in field_map.items() if "타깃 포트폴리오" in k]
    assert len(target_field) >= 1
    assert "회사A(000010)" in target_field[0]
    assert "회사B(000020)" in target_field[0]
    assert "50.0%" in target_field[0]

    # 2. Sell execution details
    sell_field = [v for k, v in field_map.items() if "매도 체결 상세" in k]
    assert len(sell_field) >= 1
    assert "퇴출대상C(000030) 100주 @ 5,000원 (500,000원)" in sell_field[0]

    # 3. Buy execution details
    buy_field = [v for k, v in field_map.items() if "매수 체결 상세" in k]
    assert len(buy_field) >= 1
    assert "회사A(000010)" in buy_field[0]
    assert "회사B(000020)" in buy_field[0]

    # 4. Account summary
    assert "💰 계좌 요약" in field_map
    assert "총 평가액:" in field_map["💰 계좌 요약"]
    assert "예상 잔여 예수금:" in field_map["💰 계좌 요약"]

    # 5. Operating env
    assert "⚙️ 운용 환경" in field_map
    assert "MOCK" in field_map["⚙️ 운용 환경"]


def test_rebalancer_discord_notification_with_failed_order(store):
    """Test notification handles failed orders and displays error messages."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    kis_mock.fetch_balance.return_value = Balance(
        cash=5_000_000.0,
        total_eval_amount=5_000_000.0,
        positions=[],
    )
    price_map = {"000010": 10000.0, "000020": 20000.0}
    kis_mock.fetch_current_price.side_effect = lambda t: price_map.get(t, 10000.0)

    # Make 000020 buy fail
    def mock_place_order(ticker, side, qty, price, order_type="01"):
        if ticker == "000020":
            return OrderResult(
                order_no="",
                ticker=ticker,
                side=side,
                qty=qty,
                price=price,
                success=False,
                message="호가 한도 초과",
            )
        return OrderResult(
            order_no="ORD001",
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
        env="real",
    )

    rebalancer.execute(
        rebalance_date="2026-04-01",
        pit_date="2026-03-31",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert len(notifier.sent_messages) == 1
    embed = notifier.sent_messages[0]["embeds"][0]

    # Failure color
    assert embed["color"] == 0xE74C3C

    field_map = {f["name"]: f["value"] for f in embed["fields"]}
    failed_field = [v for k, v in field_map.items() if "주문 실패/거절" in k]
    assert len(failed_field) >= 1
    assert "[매수] 회사B(000020)" in failed_field[0]
    assert "거절(호가 한도 초과)" in failed_field[0]


def test_rebalancer_insufficient_cash_records_skipped_order(store):
    """When buy_qty is 0 due to insufficient cash while target qty > 0, record failed order."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Initial cash: 12,000 KRW, holding 000030 (10 shares @ 5,000 = 50,000 KRW)
    # Total equity = 62,000 KRW
    # Target weights: 000010 (50% = 31,000 -> 3 shares @ 10,000), 000020 (50% = 31,000 -> 1 share @ 20,000)
    kis_mock.fetch_balance.return_value = Balance(
        cash=12000.0,
        total_eval_amount=62000.0,
        positions=[
            Position(
                ticker="000030", name="퇴출대상C", qty=10, current_price=5000.0, eval_amount=50000.0
            )
        ],
    )
    price_map = {"000010": 10000.0, "000020": 20000.0, "000030": 5000.0}
    kis_mock.fetch_current_price.side_effect = lambda t: price_map.get(t, 10000.0)

    # Make SELL of 000030 fail, so cash is not replenished!
    def mock_place_order(ticker, side, qty, price, order_type="01"):
        if ticker == "000030":
            return OrderResult(
                order_no="",
                ticker=ticker,
                side=side,
                qty=qty,
                price=price,
                success=False,
                message="매도 불가",
            )
        return OrderResult(
            order_no="ORD001",
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

    # 000010 takes 1 share @ 10,000 (available cash was 12,000). Remaining cash is ~1,970 KRW.
    # 000020 needs 1 share @ 20,000, but only 1,970 is left -> buy_qty = 0!
    # 000020 should NOT be silently dropped!
    skipped = [o for o in result["orders"] if o.get("message") == "예수금 부족으로 주문 스킵"]
    assert len(skipped) == 1
    assert skipped[0]["ticker"] == "000020"
    assert skipped[0]["side"] == "BUY"
    assert skipped[0]["id"] == 0

    # Ensure Discord failure field reflects this
    assert len(notifier.sent_messages) == 1
    embed = notifier.sent_messages[0]["embeds"][0]
    field_map = {f["name"]: f["value"] for f in embed["fields"]}
    failed_field = [v for k, v in field_map.items() if "주문 실패/거절" in k]
    assert len(failed_field) >= 1
    assert "예수금 부족으로 주문 스킵" in failed_field[0]


def test_rebalancer_order_exception_sanitizes_system_error(store):
    """When an exception occurs during order submission, message is sanitized without exposing raw trace."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    kis_mock.fetch_balance.return_value = Balance(
        cash=5_000_000.0,
        total_eval_amount=5_000_000.0,
        positions=[],
    )
    price_map = {"000010": 10000.0, "000020": 20000.0}
    kis_mock.fetch_current_price.side_effect = lambda t: price_map.get(t, 10000.0)

    # Throw a low level connection error
    import requests

    kis_mock.place_order.side_effect = requests.ConnectionError(
        "HTTPSConnectionPool(host='openapi.koreainvestment.com', port=9443): Max retries exceeded with url"
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="real",
    )

    result = rebalancer.execute(
        rebalance_date="2026-04-01",
        pit_date="2026-03-31",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    failed = [o for o in result["orders"] if not o["success"]]
    assert len(failed) > 0
    assert failed[0]["message"] == "시스템 오류 (ConnectionError)"

    embed = notifier.sent_messages[0]["embeds"][0]
    field_map = {f["name"]: f["value"] for f in embed["fields"]}
    failed_field = [v for k, v in field_map.items() if "주문 실패/거절" in k]
    assert "시스템 오류 (ConnectionError)" in failed_field[0]
    assert "HTTPSConnectionPool" not in failed_field[0]


def test_chunk_field_lines_splits_large_content():
    """Verify that field lines exceeding 1000 characters chunk into (1), (2), etc."""
    lines = [
        f"• 종목이름이매우긴회사_{i}({i:06d}) 100주 @ 10,000원 (1,000,000원)" for i in range(40)
    ]
    chunks = _chunk_field_lines("🔴 매도 체결 상세 (40건)", lines, "내역 없음", max_len=500)

    assert len(chunks) > 1
    assert chunks[0]["name"] == "🔴 매도 체결 상세 (40건) (1)"
    assert chunks[1]["name"] == "🔴 매도 체결 상세 (40건) (2)"
    for c in chunks:
        assert len(c["value"]) <= 500


def test_daily_monitor_sends_heartbeat_when_all_healthy(store):
    """위험 지정 종목이 없을 때 매일 아침 정상 가동 생존 확인(Heartbeat) 알림이 전송되는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Balance: 2 positions, healthy
    kis_mock.fetch_balance.return_value = Balance(
        cash=1_500_000.0,
        total_eval_amount=4_500_000.0,
        positions=[
            Position(
                ticker="000010",
                name="회사A",
                qty=100,
                current_price=10000.0,
                eval_amount=1_000_000.0,
            ),
            Position(
                ticker="000020",
                name="회사B",
                qty=100,
                current_price=20000.0,
                eval_amount=2_000_000.0,
            ),
        ],
    )

    monitor = DailyMonitor(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
    )

    # No designations exist in store
    res = monitor.check_and_liquidate(as_of_date="2026-04-06", send_heartbeat=True)

    assert len(res) == 0
    assert len(notifier.sent_messages) == 1

    embed = notifier.sent_messages[0]["embeds"][0]
    assert "08:30 일일 감시 봇 생존 확인" in embed["title"]
    assert embed["color"] == 0x2ECC71  # Green

    field_map = {f["name"]: f["value"] for f in embed["fields"]}
    assert "2026-04-06" in field_map["기준 일자"]
    assert "MOCK" in field_map["운용 환경"]
    assert "2개" in field_map["보유 종목 수"]
    assert "이상 없음" in field_map["감시 결과"]


def test_daily_monitor_heartbeat_disabled(store):
    """send_heartbeat=False 시 정상 상태에서 알림이 전송되지 않는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    kis_mock.fetch_balance.return_value = Balance(
        cash=1_500_000.0,
        total_eval_amount=1_500_000.0,
        positions=[],
    )

    monitor = DailyMonitor(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
    )

    res = monitor.check_and_liquidate(as_of_date="2026-04-06", send_heartbeat=False)

    assert len(res) == 0
    assert len(notifier.sent_messages) == 0

