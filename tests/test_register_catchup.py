"""Unit test for scripts/register_catchup.py."""

from unittest.mock import MagicMock

from quant_ko.broker.kis import Balance, Position
from quant_ko.data.store import DataStore
from scripts.register_catchup import register_pending_catchup


def test_register_pending_catchup(tmp_path):
    db_path = tmp_path / "test.db"
    store = DataStore(db_path)
    store.initialize_schema()

    # 1. Insert 3 mock orders for 2026-10-30
    store.insert_order({"rebalance_date": "2026-10-30", "ticker": "000010", "side": "BUY", "qty": 10, "price": 1000, "status": "ORDERED", "env": "real"})
    store.insert_order({"rebalance_date": "2026-10-30", "ticker": "000020", "side": "BUY", "qty": 10, "price": 1000, "status": "ORDERED", "env": "real"})
    o3 = store.insert_order({"rebalance_date": "2026-10-30", "ticker": "000030", "side": "BUY", "qty": 10, "price": 1000, "status": "ORDERED", "env": "real"})

    # 2. Mock KIS client returning held positions: only 000010 and 000020 (000030 missing!)
    mock_kis = MagicMock()
    mock_kis.fetch_balance.return_value = Balance(
        cash=300000.0,
        total_eval_amount=500000.0,
        positions=[
            Position(ticker="000010", name="종목1", qty=10, current_price=1000, eval_amount=10000),
            Position(ticker="000020", name="종목2", qty=10, current_price=1000, eval_amount=10000),
        ],
    )

    # 3. Run register_pending_catchup
    updated_tickers = register_pending_catchup(store=store, kis_client=mock_kis)

    assert updated_tickers == ["000030"]

    # 4. Check DB status
    pending = store.get_orders(status="PENDING_CATCHUP", env="real")
    assert len(pending) == 1
    assert pending.iloc[0]["ticker"] == "000030"
    assert pending.iloc[0]["id"] == o3
