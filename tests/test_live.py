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
        order_type="01",
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
    buy_field = [v for k, v in field_map.items() if "매수 주문 접수" in k]
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


def test_rebalancer_is_d_minus_one_detection():
    """리밸런싱 D-1일(월말 리밸런싱일 바로 전 거래일) 정상 판별 검증."""
    rebalancer = LiveRebalancer(
        store=MagicMock(),
        kis_client=MagicMock(),
        rebalance_freq="monthly",
    )

    # 2026년 3월 말 리밸런싱일은 2026-03-31 (화)
    # 따라서 2026-03-30 (월)은 D-1일이어야 함
    trading_days = [
        "2026-03-27",
        "2026-03-30",
        "2026-03-31",
        "2026-04-01",
        "2026-04-02",
    ]

    assert rebalancer.is_rebalance_date("2026-03-31", trading_days) is True
    assert rebalancer.is_d_minus_one("2026-03-30", trading_days) is True
    assert rebalancer.is_d_minus_one("2026-03-27", trading_days) is False
    assert rebalancer.is_d_minus_one("2026-03-31", trading_days) is False


def test_rebalancer_send_d_minus_one_briefing(store):
    """리밸런싱 전일(D-1) 18:00 사전 브리핑 디스코드 임베드 전송 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # Balance: holds 000030, cash 2,000,000
    kis_mock.fetch_balance.return_value = Balance(
        cash=2_000_000.0,
        total_eval_amount=2_500_000.0,
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

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
        strategy_mode="seasonality",
    )

    trading_days = [
        "2026-03-27",
        "2026-03-30",
        "2026-03-31",
        "2026-04-01",
    ]

    res = rebalancer.send_d_minus_one_briefing(
        as_of_date="2026-03-30",
        trading_days=trading_days,
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert res["success"] is True
    assert res["target_date"] == "2026-03-31"
    assert len(notifier.sent_messages) == 1

    embed = notifier.sent_messages[0]["embeds"][0]
    assert "D-1 사전 안내" in embed["title"]
    assert "2026-03-31" in embed["title"]

    field_map = {f["name"]: f["value"] for f in embed["fields"]}
    assert "2026-03-31" in field_map["리밸런싱 예정일"]
    assert "SEASONALITY" in field_map["운용 전략 / 환경"]
    assert "예수금" in field_map["계좌 잔고 요약"]


def test_rebalancer_automatically_resolves_prior_trading_day_as_pit_date(store):
    """실전 리밸런싱 시 pit_date를 생략해도 직전 거래일을 자동으로 산출하여 미래참조를 차단하는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    kis_mock.fetch_balance.return_value = Balance(
        cash=2_000_000.0,
        total_eval_amount=2_000_000.0,
        positions=[],
    )
    kis_mock.fetch_current_price.return_value = 10000.0
    kis_mock.place_order.return_value = OrderResult(
        order_no="ORD001",
        ticker="000010",
        side="BUY",
        qty=10,
        price=10000.0,
        success=True,
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
    )

    # store has prices for 2026-03-31 and 2026-04-01
    prior_day = rebalancer.get_prior_trading_day("2026-04-01")
    assert prior_day == "2026-03-31"

    # Execute without pit_date
    result = rebalancer.execute(
        rebalance_date="2026-04-01",
        pit_date=None,
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert result["success"] is True
    assert result["pit_date"] == "2026-03-31"


def test_daily_monitor_syncs_realtime_designations_from_krx(store):
    """08:30 감시 실행 시 KRX 실시간 관리종목 API를 선제 호출하여 DB를 갱신하고 청산하는지 검증."""
    from quant_ko.data.krx import KrxClient

    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)
    krx_mock = MagicMock(spec=KrxClient)

    # Initially, store has NO designations for 000010
    # KRX API returns real-time designation today
    krx_mock.fetch_designations.return_value = [
        {
            "ticker": "000010",
            "type": "관리종목",
            "start_date": "2026-04-06",
            "end_date": None,
        }
    ]

    kis_mock.fetch_balance.return_value = Balance(
        cash=1_000_000.0,
        total_eval_amount=2_000_000.0,
        positions=[
            Position(
                ticker="000010",
                name="위험주",
                qty=100,
                current_price=10000.0,
                eval_amount=1_000_000.0,
            ),
        ],
    )
    kis_mock.fetch_current_price.return_value = 9500.0
    kis_mock.place_order.return_value = OrderResult(
        order_no="LIQ_KRX_01",
        ticker="000010",
        side="SELL",
        qty=100,
        price=9500.0,
        success=True,
    )

    monitor = DailyMonitor(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="mock",
        krx_client=krx_mock,
        order_type="00",  # limit order for morning auction
    )

    liquidated = monitor.check_and_liquidate(as_of_date="2026-04-06")

    # Verify KRX real-time API was called
    krx_mock.fetch_designations.assert_called_once_with(as_of_date="2026-04-06")

    # Verify designation was upserted into store
    db_desigs = store.get_designations(as_of_date="2026-04-06")
    assert not db_desigs.empty
    assert "000010" in db_desigs["ticker"].values

    # Verify liquidation order executed with order_type="00"
    assert len(liquidated) == 1
    kis_mock.place_order.assert_called_once_with(
        ticker="000010",
        side="SELL",
        qty=100,
        price=9500.0,
        order_type="00",
    )





def test_dynamic_weekday_calendar_augmentation_for_live_october_rebalance(store):
    """DB에 과거 시세(예: 10/23까지)만 있어도 10/29(D-1) 및 10/30(월말 리밸런싱일)을 정확히 감지하는지 검증."""
    from quant_ko.live.rebalancer import get_augmented_trading_days

    # DB에 2026-10-23까지만 거래일이 존재하는 상황 가정
    historical_days = [
        "2026-10-21",
        "2026-10-22",
        "2026-10-23",
    ]
    aug_days = get_augmented_trading_days(historical_days, "2026-10-29")
    assert "2026-10-29" in aug_days
    assert "2026-10-30" in aug_days
    # 10월 31일은 토요일이므로 제외되어야 함
    assert "2026-10-31" not in aug_days
    # 10월 9일(한글날) 및 10월 3일(개천절)은 공휴일이므로 제외되어야 함
    assert "2026-10-09" not in aug_days

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=MagicMock(),
        notifier=MagicMock(),
        rebalance_freq="monthly",
    )
    assert rebalancer.is_d_minus_one("2026-10-29", historical_days) is True
    assert rebalancer.is_rebalance_date("2026-10-30", historical_days) is True
    assert rebalancer.is_rebalance_date("2026-10-29", historical_days) is False


def test_rebalancer_october_end_selects_active_stocks_and_uses_plus_5pct_limit_buy(store):
    """10월 말(2026-10-30) 리밸런싱 시 파킹이 아닌 소형주 종목을 편입하고 +5% 지정가(00) 매수 주문을 전송하는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # 2,000,000원 예수금 (주식 2종목 000010, 000020 각 50% 타깃)
    kis_mock.fetch_balance.return_value = Balance(
        cash=2_000_000.0,
        total_eval_amount=2_000_000.0,
        positions=[],
    )
    price_map = {"000010": 10000.0, "000020": 20000.0}
    kis_mock.fetch_current_price.side_effect = lambda t: price_map.get(t, 10000.0)

    placed_calls = []

    def mock_place_order(ticker, side, qty, price, order_type="01"):
        placed_calls.append(
            {
                "ticker": ticker,
                "side": side,
                "qty": qty,
                "price": price,
                "order_type": order_type,
            }
        )
        return OrderResult(
            order_no=f"ORD_{ticker}",
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
        strategy_mode="seasonality",
        buy_buffer_pct=0.05,
    )

    result = rebalancer.execute(
        rebalance_date="2026-10-30",
        pit_date="2026-04-01",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert result["success"] is True
    # 10월 30일은 11~4월 활성 구간 진입일이므로 CD금리 ETF(357870)가 아닌 소형주(000010, 000020)가 매수되어야 함
    bought_tickers = {c["ticker"] for c in placed_calls if c["side"] == "BUY"}
    assert bought_tickers == {"000010", "000020"}

    # 매수 주문이 +5% 호가 단위 지정가("00")로 전송되었는지 검증
    call_10 = next(c for c in placed_calls if c["ticker"] == "000010")
    assert call_10["order_type"] == "00"
    assert call_10["price"] == 10500.0  # 10,000 * 1.05

    call_20 = next(c for c in placed_calls if c["ticker"] == "000020")
    assert call_20["order_type"] == "00"
    assert call_20["price"] == 21000.0  # 20,000 * 1.05

    total_buy_limit_amount = sum(c["qty"] * c["price"] for c in placed_calls if c["side"] == "BUY")
    assert total_buy_limit_amount <= 2_000_000.0


def test_rebalancer_20_stocks_buy_limit_never_exceeds_available_cash_and_sell_is_market():
    """20종목 리밸런싱 시 매도는 시장가(01), 매수는 +5% 호가단위 지정가(00)를 사용하며 지정가 총액이 가용 예수금의 100%를 절대 초과하지 않는지 검증."""
    ds = DataStore(":memory:")
    ds.initialize_schema()

    companies = []
    prices = []
    financials = []
    for i in range(1, 21):
        ticker = f"{i * 10:06d}"
        corp_code = f"c{i:04d}"
        companies.append(
            {
                "ticker": ticker,
                "corp_code": corp_code,
                "name": f"소형주{i}",
                "market": "KOSDAQ",
                "sector": "IT",
            }
        )
        # 다양한 가격대 설정 (KRX 호가단위 테스트 겸용)
        px = 1500 + (i * 1230)
        prices.append(
            {
                "ticker": ticker,
                "date": "2026-10-29",
                "close": px,
                "market_cap": 30_000_000_000 + i * 1_000_000_000,
                "trading_value": 500_000_000,
            }
        )
        financials.append(
            {
                "corp_code": corp_code,
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
            }
        )

    ds.upsert_companies(companies)
    ds.upsert_daily_prices(prices)
    ds.upsert_financials(financials)

    kis_mock = MagicMock(spec=KisClient)
    # 기존 보유 종목 999990 (전량 매도 대상) + 예수금 1,500,000원
    kis_mock.fetch_balance.return_value = Balance(
        cash=1_500_000.0,
        total_eval_amount=2_000_000.0,
        positions=[
            Position(
                ticker="999990",
                name="기존보유주",
                qty=50,
                current_price=10000.0,
                eval_amount=500_000.0,
            )
        ],
    )
    price_map = {p["ticker"]: float(p["close"]) for p in prices}
    price_map["999990"] = 10000.0
    kis_mock.fetch_current_price.side_effect = lambda t: price_map[t]

    placed_calls = []

    def mock_place_order(ticker, side, qty, price, order_type="01"):
        placed_calls.append(
            {
                "ticker": ticker,
                "side": side,
                "qty": qty,
                "price": price,
                "order_type": order_type,
            }
        )
        return OrderResult(
            order_no=f"ORD_{side}_{ticker}",
            ticker=ticker,
            side=side,
            qty=qty,
            price=price,
            success=True,
            message="OK",
        )

    kis_mock.place_order.side_effect = mock_place_order

    rebalancer = LiveRebalancer(
        store=ds,
        kis_client=kis_mock,
        notifier=DiscordNotifier(mock_mode=True),
        env="real",
        strategy_mode="seasonality",
        buy_buffer_pct=0.05,
    )

    result = rebalancer.execute(
        rebalance_date="2026-10-30",
        pit_date="2026-10-29",
        universe_kwargs={"market_cap_quantile": 1.0},
    )
    ds.close()

    assert result["success"] is True
    sell_calls = [c for c in placed_calls if c["side"] == "SELL"]
    buy_calls = [c for c in placed_calls if c["side"] == "BUY"]

    assert len(sell_calls) == 1
    assert sell_calls[0]["ticker"] == "999990"
    assert sell_calls[0]["order_type"] == "01"

    assert len(buy_calls) == 20
    for c in buy_calls:
        assert c["order_type"] == "00"

    # 가용 예수금 = 초기 1,500,000 + 매도 정산금(500,000 * (1 - 0.003)) = 1,998,500원
    expected_available_cash = 1_500_000.0 + 500_000.0 * (1.0 - 0.003)
    total_buy_limit_outlay = sum(c["qty"] * c["price"] for c in buy_calls)
    assert total_buy_limit_outlay <= expected_available_cash



def test_rebalancer_caps_buy_limit_price_at_upper_limit(store):
    """당일 급등주로 인해 현재가 +5%가 상한가(stck_mxpr)를 초과할 경우 상한가로 캡이 적용되는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    kis_mock.fetch_balance.return_value = Balance(
        cash=2_000_000.0,
        total_eval_amount=2_000_000.0,
        positions=[],
    )
    # 000010 현재가 10,000원 (+5%는 10,500원), 그러나 당일 상한가(stck_mxpr)가 10,300원인 상황
    price_map = {"000010": 10000.0, "000020": 20000.0}
    upper_map = {"000010": 10300, "000020": 26000}
    kis_mock.fetch_current_price.side_effect = lambda t: price_map.get(t, 10000.0)
    kis_mock.get_upper_limit = MagicMock(side_effect=lambda t: upper_map.get(t))

    placed_calls = []

    def mock_place_order(ticker, side, qty, price, order_type="01"):
        placed_calls.append(
            {
                "ticker": ticker,
                "side": side,
                "qty": qty,
                "price": price,
                "order_type": order_type,
            }
        )
        return OrderResult(
            order_no=f"ORD_{ticker}",
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
        strategy_mode="seasonality",
        buy_buffer_pct=0.05,
    )

    result = rebalancer.execute(
        rebalance_date="2026-10-30",
        pit_date="2026-04-01",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert result["success"] is True
    call_10 = next(c for c in placed_calls if c["ticker"] == "000010")
    # 10,000 * 1.05 = 10,500원이지만 상한가 10,300원으로 캡이 씌워져야 함
    assert call_10["price"] == 10300.0
    assert call_10["order_type"] == "00"


def test_rebalancer_buy_order_auto_retries_with_minus_one_qty_on_failure(store):
    """마지막 종목 등에서 증거금/수수료 미세 오차로 1차 매수 거부 시 buy_qty - 1로 자동 재시도하여 체결시키는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    kis_mock.fetch_balance.return_value = Balance(
        cash=2_000_000.0,
        total_eval_amount=2_000_000.0,
        positions=[],
    )
    price_map = {"000010": 10000.0, "000020": 20000.0}
    kis_mock.fetch_current_price.side_effect = lambda t: price_map.get(t, 10000.0)
    kis_mock.get_upper_limit = MagicMock(return_value=None)

    attempts_000020 = []

    def mock_place_order(ticker, side, qty, price, order_type="01"):
        if ticker == "000020":
            attempts_000020.append(qty)
            # 1차 시도(원래 수량)는 증거금 부족으로 실패, 2차 시도(qty - 1)는 성공
            if len(attempts_000020) == 1:
                return OrderResult(
                    order_no="",
                    ticker=ticker,
                    side=side,
                    qty=qty,
                    price=price,
                    success=False,
                    message="주문가능금액 초과",
                )
        return OrderResult(
            order_no=f"ORD_{ticker}_{qty}",
            ticker=ticker,
            side=side,
            qty=qty,
            price=price,
            success=True,
            message="정상 주문",
        )

    kis_mock.place_order.side_effect = mock_place_order

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="real",
        strategy_mode="seasonality",
        buy_buffer_pct=0.05,
    )

    result = rebalancer.execute(
        rebalance_date="2026-10-30",
        pit_date="2026-04-01",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert result["success"] is True
    # 000020에 대해 1차 실패 후 1주 감량하여 총 2회 호출되었는지 확인
    assert len(attempts_000020) == 2
    assert attempts_000020[1] == attempts_000020[0] - 1

    order_20 = next(o for o in result["orders"] if o["ticker"] == "000020")
    assert order_20["success"] is True
    assert order_20["qty"] == attempts_000020[1]


def test_rebalancer_discord_message_format_order_received(store):
    """15:20 리밸런싱 주문 시 디스코드 알림이 '주문 접수' 명기 및 익일 자동 보충 안내를 포함하는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    kis_mock.fetch_balance.return_value = Balance(
        cash=1_000_000.0,
        total_eval_amount=1_000_000.0,
        positions=[],
    )
    kis_mock.fetch_current_price.return_value = 10000.0
    kis_mock.get_upper_limit = MagicMock(return_value=None)
    kis_mock.place_order.return_value = OrderResult(
        order_no="ORD123",
        ticker="000010",
        side="BUY",
        qty=10,
        price=10500.0,
        success=True,
        message="정상 접수",
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="real",
        strategy_mode="seasonality",
        buy_buffer_pct=0.05,
    )

    result = rebalancer.execute(
        rebalance_date="2026-10-30",
        pit_date="2026-04-01",
        universe_kwargs={"market_cap_quantile": 1.0},
    )

    assert result["success"] is True
    # Discord 발송 기록 확인
    assert len(notifier.sent_messages) > 0
    embed = notifier.sent_messages[-1]["embeds"][0]
    assert "리밸런싱 완료" in embed["title"]
    assert "15:30 동시호가 중 +5% 초과 급등" in embed["description"]
    assert "다음 거래일 15:20에 남은 예수금 범위 내에서 자동 보충 매수" in embed["description"]

    # 매수 필드 제목 확인
    buy_field = next(f for f in embed["fields"] if "매수 주문 접수" in f["name"])
    assert "15:30 동시호가 체결 예정" in buy_field["name"]


def test_catchup_unfilled_orders_skips_in_parking_season(store):
    """5~10월 파킹 시즌에는 주식 보충 매수를 건너뛰는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)
    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="real",
    )

    res = rebalancer.catchup_unfilled_orders(as_of_date="2026-06-15")
    assert res["success"] is True
    assert "파킹" in res["message"]
    assert res["orders"] == []
    assert kis_mock.place_order.call_count == 0


def test_catchup_unfilled_orders_skips_when_20_stocks_held(store):
    """이미 20종목 이상 보유 중이면 보충 매수가 건너뛰어지는지 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # 20개 포지션 모의
    positions = [
        Position(ticker=f"0000{i:02d}", name=f"종목{i}", qty=10, eval_amount=100000, current_price=10000)
        for i in range(20)
    ]
    kis_mock.fetch_balance.return_value = Balance(
        cash=500_000.0,
        total_eval_amount=2_500_000.0,
        positions=positions,
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="real",
    )

    res = rebalancer.catchup_unfilled_orders(as_of_date="2026-11-02")
    assert res["success"] is True
    assert "보충 매수 대상 큐(PENDING_CATCHUP)가 없습니다." in res["message"]
    assert res["orders"] == []
    assert kis_mock.place_order.call_count == 0


def test_catchup_unfilled_orders_buys_missing_stock_within_cash(store):
    """직전 리밸런싱 미체결 1종목 발생 시 잔여 예수금 내에서 자동 보충 매수 주문 전송 및 알림 검증."""
    notifier = DiscordNotifier(mock_mode=True)
    kis_mock = MagicMock(spec=KisClient)

    # 1. DB에 직전 리밸런싱(2026-10-30) 2개 종목 BUY 주문 등록
    store.insert_order(
        {
            "rebalance_date": "2026-10-30",
            "ticker": "000010",
            "side": "BUY",
            "qty": 50,
            "price": 10000,
            "status": "FILLED",
            "filled_qty": 50,
            "env": "real",
        }
    )
    store.insert_order(
        {
            "rebalance_date": "2026-10-30",
            "ticker": "000020",
            "side": "BUY",
            "qty": 20,
            "price": 20000,
            "status": "PENDING_CATCHUP",
            "filled_qty": 0,
            "env": "real",
        }
    )

    # 2. 실계좌에는 000010만 50주 있고, 000020은 미보유(미체결 취소), 예수금 313,887원 남음
    kis_mock.fetch_balance.return_value = Balance(
        cash=313_887.0,
        total_eval_amount=813_887.0,
        positions=[
            Position(ticker="000010", name="회사A", qty=50, eval_amount=500000, current_price=10000),
        ],
    )
    kis_mock.fetch_current_price.return_value = 20000.0
    kis_mock.get_upper_limit = MagicMock(return_value=None)

    placed_orders = []

    def mock_place_order(ticker, side, qty, price, order_type="01"):
        placed_orders.append({"ticker": ticker, "side": side, "qty": qty, "price": price, "order_type": order_type})
        return OrderResult(
            order_no="CATCHUP_ORD_1",
            ticker=ticker,
            side=side,
            qty=qty,
            price=price,
            success=True,
            message="정상 접수",
        )

    kis_mock.place_order.side_effect = mock_place_order

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=kis_mock,
        notifier=notifier,
        env="real",
        buy_buffer_pct=0.05,
    )

    # 다음 거래일 15:20 보충 매수 실행
    res = rebalancer.catchup_unfilled_orders(as_of_date="2026-11-02", dry_run=False)

    assert res["success"] is True
    assert len(res["orders"]) == 1
    assert res["orders"][0]["ticker"] == "000020"
    assert res["orders"][0]["success"] is True

    # 주문 단가: 20000 * 1.05 = 21000원 (+5% 지정가)
    assert placed_orders[0]["price"] == 21000.0
    assert placed_orders[0]["order_type"] == "00"
    # 수량: 313,887 / (21000 * 1.00015) = 약 14주, 이전 타깃 20주 한도 내
    assert placed_orders[0]["qty"] == 14

    # Discord 알림 확인
    assert len(notifier.sent_messages) > 0
    embed = notifier.sent_messages[-1]["embeds"][0]
    assert "보충 매수" in embed["title"]
    assert "직전 리밸런싱 미체결 1종목" in embed["description"]
