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


CD_ETF_TICKER = "357870"  # TIGER CD금리투자KIS(합성) - 1주당 약 53,000원으로 소액 시드 단주 최소화


class LiveRebalancer:
    """Executes rebalancing orders via KIS Open API."""

    def __init__(
        self,
        store: DataStore,
        kis_client: KisClient,
        notifier: DiscordNotifier | None = None,
        env: str = "mock",
        rebalance_freq: str = "quarterly",
        strategy_mode: str = "seasonality",
        cd_etf_ticker: str = CD_ETF_TICKER,
        cost_rate: float = 0.003,
        order_type: str = "01",
    ) -> None:
        self.store = store
        self.kis_client = kis_client
        self.notifier = notifier
        self.env = env
        self.rebalance_freq = rebalance_freq
        self.strategy_mode = strategy_mode
        self.cd_etf_ticker = cd_etf_ticker
        self.cost_rate = cost_rate
        self.order_type = order_type

    def is_rebalance_date(self, date: str, trading_days: list[str]) -> bool:
        """Check if given date matches scheduled rebalancing date."""
        norm = normalize_date(date)
        schedule = get_rebalance_schedule(trading_days, rebalance_freq=self.rebalance_freq)
        reb_dates = {e.rebalance_date for e in schedule}
        return norm in reb_dates

    def execute(
        self,
        rebalance_date: str,
        pit_date: str | None = None,
        universe_kwargs: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute rebalancing.

        1. Inquires current cash balance and held positions from broker.
        2. Filters strategy universe and scores stocks to get target portfolio.
           - In seasonality mode:
             - 5~10월: 100% CD금리 ETF (357870) 안전 파킹
             - 11~4월: 소형주 9대 팩터 20종목 동일비중 (각 5%)
        3. Computes differential orders (sell overweight/unwanted first, buy underweight/new next).
        4. Submits limit orders at current 15:20 auction prices (or simulates if dry_run=True).
        5. Logs orders to SQLite database.
        6. Sends Discord summary notification.
        """
        norm_reb_date = normalize_date(rebalance_date)
        norm_pit_date = normalize_date(pit_date) if pit_date else norm_reb_date

        logger.info(
            "Starting rebalance on %s (PIT date: %s, mode: %s, dry_run: %s)",
            norm_reb_date,
            norm_pit_date,
            self.strategy_mode,
            dry_run,
        )

        # 1. Broker balance & positions
        balance = self.kis_client.fetch_balance()
        current_cash = balance.cash
        held_positions = {p.ticker: p.qty for p in balance.positions if p.qty > 0}

        # 2. Determine target weights based on strategy mode
        from datetime import datetime

        dt = datetime.strptime(norm_reb_date, "%Y-%m-%d")
        is_parking_period = self.strategy_mode == "seasonality" and dt.month in [5, 6, 7, 8, 9, 10]

        target_weights: dict[str, float] = {}
        if is_parking_period:
            # Safe parking: 100% CD rate ETF
            logger.info(
                "Seasonality mode active: 5~10월 파킹 구간이므로 CD금리 ETF(%s) 100%% 배분",
                self.cd_etf_ticker,
            )
            target_weights = {self.cd_etf_ticker: 1.0}
        else:
            # Active equity period (11~4월) or standard mode
            u_kwargs = {"min_trading_value": 0.0}
            if universe_kwargs:
                u_kwargs.update(universe_kwargs)
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

        # 3. Collect current prices (Broker live price -> DataStore DB close fallback)
        all_tickers = set(held_positions.keys()).union(target_weights.keys())
        prices: dict[str, float] = {}
        for ticker in all_tickers:
            price = 0.0
            try:
                price = self.kis_client.fetch_current_price(ticker)
            except Exception:
                pass

            # Fallback to local DataStore daily close if broker fails (e.g. outside trading hours)
            if price <= 0:
                p_df = self.store.get_daily_prices(ticker=ticker)
                if not p_df.empty:
                    price = float(p_df["close"].iloc[-1])

            if price <= 0:
                price = 1.0
            prices[ticker] = price

        # Total portfolio equity
        total_equity = current_cash + sum(
            held_positions.get(t, 0) * prices.get(t, 0.0) for t in held_positions
        )

        # Calculate desired shares (with cost buffer)
        desired_target_shares: dict[str, int] = {}
        for ticker, weight in target_weights.items():
            price = prices.get(ticker, 0.0)
            if price <= 0:
                logger.warning(
                    "종목 %s의 유효 가격이 없어(0원 이하) 매수 대상에서 제외합니다.", ticker
                )
                continue
            cost_per_share = price * (1.0 + self.cost_rate)
            target_val = total_equity * weight
            target_shares = math.floor(target_val / cost_per_share)
            if target_shares > 0:
                desired_target_shares[ticker] = target_shares

        # Identify SELLs and BUYs
        sells: list[tuple[str, int, float]] = []
        buys: list[tuple[str, int, float]] = []

        # Current holdings
        for ticker, held_qty in held_positions.items():
            price = prices.get(ticker, 0.0)
            target_qty = desired_target_shares.get(ticker, 0)
            if target_qty < held_qty and price > 0:
                sells.append((ticker, held_qty - target_qty, price))
            elif target_qty > held_qty and price > 0:
                buys.append((ticker, target_qty - held_qty, price))

        # New target entries not currently held
        for ticker, target_qty in desired_target_shares.items():
            if ticker not in held_positions:
                price = prices.get(ticker, 0.0)
                if price > 0:
                    buys.append((ticker, target_qty, price))

        executed_orders: list[dict[str, Any]] = []
        available_cash = current_cash

        # 4. Execute SELLs first
        for ticker, qty, price in sells:
            try:
                if dry_run:
                    res_success = True
                    order_no = f"DRY_SELL_{ticker}"
                else:
                    res = self.kis_client.place_order(
                        ticker=ticker,
                        side="SELL",
                        qty=qty,
                        price=price,
                        order_type=self.order_type,
                    )
                    res_success = res.success
                    order_no = res.order_no

                order_id = self.store.insert_order(
                    {
                        "rebalance_date": norm_reb_date,
                        "ticker": ticker,
                        "side": "SELL",
                        "qty": qty,
                        "price": price,
                        "status": "DRY_RUN"
                        if dry_run
                        else ("ORDERED" if res_success else "FAILED"),
                        "filled_qty": qty if dry_run else 0,
                        "env": self.env,
                    }
                )
                executed_orders.append(
                    {
                        "id": order_id,
                        "order_no": order_no,
                        "ticker": ticker,
                        "side": "SELL",
                        "qty": qty,
                        "price": price,
                        "success": res_success,
                    }
                )
                net_proceeds = qty * price * (1.0 - self.cost_rate)
                available_cash += net_proceeds
            except Exception as e:
                logger.error("SELL order failed for %s: %s", ticker, e)

        # 5. Execute BUYs next
        for ticker, qty, price in buys:
            if price <= 0:
                continue
            cost_per_share = price * (1.0 + self.cost_rate)
            max_buyable = math.floor(available_cash / cost_per_share) if cost_per_share > 0 else 0
            buy_qty = min(qty, max_buyable)
            if buy_qty <= 0:
                continue

            try:
                if dry_run:
                    res_success = True
                    order_no = f"DRY_BUY_{ticker}"
                else:
                    res = self.kis_client.place_order(
                        ticker=ticker,
                        side="BUY",
                        qty=buy_qty,
                        price=price,
                        order_type=self.order_type,
                    )
                    res_success = res.success
                    order_no = res.order_no

                order_id = self.store.insert_order(
                    {
                        "rebalance_date": norm_reb_date,
                        "ticker": ticker,
                        "side": "BUY",
                        "qty": buy_qty,
                        "price": price,
                        "status": "DRY_RUN"
                        if dry_run
                        else ("ORDERED" if res_success else "FAILED"),
                        "filled_qty": buy_qty if dry_run else 0,
                        "env": self.env,
                    }
                )
                executed_orders.append(
                    {
                        "id": order_id,
                        "order_no": order_no,
                        "ticker": ticker,
                        "side": "BUY",
                        "qty": buy_qty,
                        "price": price,
                        "success": res_success,
                    }
                )
                total_outlay = buy_qty * cost_per_share
                available_cash -= total_outlay
            except Exception as e:
                logger.error("BUY order failed for %s: %s", ticker, e)

        # 6. Discord Notification
        if self.notifier:
            sell_count = sum(1 for o in executed_orders if o["side"] == "SELL")
            buy_count = sum(1 for o in executed_orders if o["side"] == "BUY")
            mode_tag = "[모의 실행 (Dry-Run)]" if dry_run else "[리밸런싱 완료]"
            fields = [
                {"name": "총 주문 수", "value": f"{len(executed_orders)}건", "inline": True},
                {
                    "name": "매도 / 매수",
                    "value": f"매도 {sell_count}건 / 매수 {buy_count}건",
                    "inline": True,
                },
                {
                    "name": "운용 환경",
                    "value": f"{self.env.upper()}{' (DRY-RUN)' if dry_run else ''}",
                    "inline": True,
                },
            ]
            self.notifier.send_embed(
                title=f"📈 {mode_tag} {norm_reb_date}",
                description=f"포트폴리오 총 평가액: {int(total_equity):,}원\n주문 전송이 완료되었습니다.",
                fields=fields,
                color=0x3498DB if dry_run else 0x2ECC71,
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
