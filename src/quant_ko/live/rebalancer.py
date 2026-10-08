"""Live Quarterly Rebalancer."""

import logging
import math
from typing import Any

from quant_ko.backtest.calendar import get_rebalance_schedule
from quant_ko.broker.kis import KisClient
from quant_ko.data.krx import normalize_date
from quant_ko.data.store import DataStore
from quant_ko.notify.discord import DiscordNotifier
from quant_ko.strategy.scoring import score_and_select
from quant_ko.strategy.universe import filter_universe

logger = logging.getLogger(__name__)


class LiveRebalancer:
    """Executes quarterly rebalancing orders via KIS Open API."""

    def __init__(
        self,
        store: DataStore,
        kis_client: KisClient,
        notifier: DiscordNotifier | None = None,
        env: str = "mock",
    ) -> None:
        self.store = store
        self.kis_client = kis_client
        self.notifier = notifier
        self.env = env

    def is_rebalance_date(self, date: str, trading_days: list[str]) -> bool:
        """Check if given date matches scheduled quarterly rebalancing date."""
        norm = normalize_date(date)
        schedule = get_rebalance_schedule(trading_days)
        reb_dates = {e.rebalance_date for e in schedule}
        return norm in reb_dates

    def execute(
        self,
        rebalance_date: str,
        pit_date: str | None = None,
        universe_kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute quarterly rebalancing.

        1. Inquires current cash balance and held positions from broker.
        2. Filters strategy universe and scores stocks to get target 20 equal-weighted portfolio.
        3. Computes differential orders (sell overweight/unwanted first, buy underweight/new next).
        4. Submits limit orders at current 15:20 auction prices.
        5. Logs orders to SQLite database.
        6. Sends Discord summary notification.
        """
        norm_reb_date = normalize_date(rebalance_date)
        norm_pit_date = normalize_date(pit_date) if pit_date else norm_reb_date

        logger.info("Starting rebalance on %s (PIT date: %s)", norm_reb_date, norm_pit_date)

        # 1. Broker balance & positions
        balance = self.kis_client.fetch_balance()
        current_cash = balance.cash
        held_positions = {p.ticker: p.qty for p in balance.positions if p.qty > 0}

        # 2. Strategy selection
        u_kwargs = universe_kwargs or {}
        universe_df = filter_universe(self.store, as_of_date=norm_pit_date, **u_kwargs)
        if universe_df.empty:
            msg = f"Universe is empty on PIT date {norm_pit_date}. Rebalancing aborted."
            logger.warning(msg)
            if self.notifier:
                self.notifier.send_text(f"[리밸런싱 경고] {msg}")
            return {"success": False, "message": msg, "orders": []}

        selected_df = score_and_select(universe_df, top_n=20)
        if selected_df.empty:
            msg = f"No stocks selected on PIT date {norm_pit_date}. Rebalancing aborted."
            logger.warning(msg)
            if self.notifier:
                self.notifier.send_text(f"[리밸런싱 경고] {msg}")
            return {"success": False, "message": msg, "orders": []}

        target_weights = dict(zip(selected_df["ticker"], selected_df["weight"], strict=False))

        # 3. Collect current prices
        all_tickers = set(held_positions.keys()).union(target_weights.keys())
        prices: dict[str, float] = {}
        for ticker in all_tickers:
            try:
                price = self.kis_client.fetch_current_price(ticker)
                if price <= 0:
                    price = 1.0
                prices[ticker] = price
            except Exception as e:
                logger.error("Failed to fetch price for %s: %s", ticker, e)
                prices[ticker] = 1.0

        # Total portfolio equity
        total_equity = current_cash + sum(
            held_positions.get(t, 0) * prices.get(t, 0.0) for t in held_positions
        )

        # Calculate desired shares
        desired_target_shares: dict[str, int] = {}
        for ticker, weight in target_weights.items():
            price = prices.get(ticker, 1.0)
            target_val = total_equity * weight
            target_shares = math.floor(target_val / price)
            if target_shares > 0:
                desired_target_shares[ticker] = target_shares

        # Identify SELLs and BUYs
        sells: list[tuple[str, int, float]] = []
        buys: list[tuple[str, int, float]] = []

        # Current holdings
        for ticker, held_qty in held_positions.items():
            price = prices.get(ticker, 1.0)
            target_qty = desired_target_shares.get(ticker, 0)
            if target_qty < held_qty:
                sells.append((ticker, held_qty - target_qty, price))
            elif target_qty > held_qty:
                buys.append((ticker, target_qty - held_qty, price))

        # New target entries not currently held
        for ticker, target_qty in desired_target_shares.items():
            if ticker not in held_positions:
                price = prices.get(ticker, 1.0)
                buys.append((ticker, target_qty, price))

        executed_orders: list[dict[str, Any]] = []
        available_cash = current_cash

        # 4. Execute SELLs first
        for ticker, qty, price in sells:
            try:
                res = self.kis_client.place_order(ticker=ticker, side="SELL", qty=qty, price=price)
                order_id = self.store.insert_order(
                    {
                        "rebalance_date": norm_reb_date,
                        "ticker": ticker,
                        "side": "SELL",
                        "qty": qty,
                        "price": price,
                        "status": "ORDERED" if res.success else "FAILED",
                        "filled_qty": 0,
                        "env": self.env,
                    }
                )
                executed_orders.append(
                    {
                        "id": order_id,
                        "order_no": res.order_no,
                        "ticker": ticker,
                        "side": "SELL",
                        "qty": qty,
                        "price": price,
                        "success": res.success,
                    }
                )
                available_cash += qty * price
            except Exception as e:
                logger.error("SELL order failed for %s: %s", ticker, e)

        # 5. Execute BUYs next
        for ticker, qty, price in buys:
            # Check cash availability
            max_buyable = math.floor(available_cash / price) if price > 0 else 0
            buy_qty = min(qty, max_buyable)
            if buy_qty <= 0:
                continue

            try:
                res = self.kis_client.place_order(
                    ticker=ticker, side="BUY", qty=buy_qty, price=price
                )
                order_id = self.store.insert_order(
                    {
                        "rebalance_date": norm_reb_date,
                        "ticker": ticker,
                        "side": "BUY",
                        "qty": buy_qty,
                        "price": price,
                        "status": "ORDERED" if res.success else "FAILED",
                        "filled_qty": 0,
                        "env": self.env,
                    }
                )
                executed_orders.append(
                    {
                        "id": order_id,
                        "order_no": res.order_no,
                        "ticker": ticker,
                        "side": "BUY",
                        "qty": buy_qty,
                        "price": price,
                        "success": res.success,
                    }
                )
                available_cash -= buy_qty * price
            except Exception as e:
                logger.error("BUY order failed for %s: %s", ticker, e)

        # 6. Discord Notification
        if self.notifier:
            sell_count = sum(1 for o in executed_orders if o["side"] == "SELL")
            buy_count = sum(1 for o in executed_orders if o["side"] == "BUY")
            fields = [
                {"name": "총 주문 수", "value": f"{len(executed_orders)}건", "inline": True},
                {
                    "name": "매도 / 매수",
                    "value": f"매도 {sell_count}건 / 매수 {buy_count}건",
                    "inline": True,
                },
                {"name": "운용 환경", "value": self.env.upper(), "inline": True},
            ]
            self.notifier.send_embed(
                title=f"📈 [리밸런싱 완료] {norm_reb_date}",
                description=f"포트폴리오 총 평가액: {int(total_equity):,}원\n주문 전송이 완료되었습니다.",
                fields=fields,
                color=0x2ECC71,  # Emerald Green
            )

        return {
            "success": True,
            "rebalance_date": norm_reb_date,
            "total_equity": total_equity,
            "orders": executed_orders,
        }

    def retry_unfilled_orders(self, date: str) -> list[dict[str, Any]]:
        """Track and update unfilled or partially filled orders."""
        norm_date = normalize_date(date)
        db_orders = self.store.get_orders(rebalance_date=norm_date, env=self.env)
        if db_orders.empty:
            return []

        pending_orders = db_orders[db_orders["status"].isin(["UNFILLED", "PARTIAL", "ORDERED"])]
        if pending_orders.empty:
            return []

        broker_orders = self.kis_client.fetch_orders(date=norm_date)
        broker_map = {bo["ticker"]: bo for bo in broker_orders}

        updated_list: list[dict[str, Any]] = []
        for _, row in pending_orders.iterrows():
            order_id = int(row["id"])
            ticker = str(row["ticker"])
            if ticker in broker_map:
                bo = broker_map[ticker]
                new_status = bo.get("status", row["status"])
                filled_qty = bo.get("filled_qty", row["filled_qty"])
                self.store.update_order_status(
                    order_id=order_id,
                    status=new_status,
                    filled_qty=filled_qty,
                )
                updated_list.append(
                    {
                        "id": order_id,
                        "ticker": ticker,
                        "status": new_status,
                        "filled_qty": filled_qty,
                    }
                )

        return updated_list
