"""Live Quarterly Rebalancer."""

import logging
import math
import time
from typing import Any, TypedDict

from quant_ko.backtest.calendar import get_rebalance_schedule
from quant_ko.broker.kis import KisClient
from quant_ko.data.krx import normalize_date
from quant_ko.data.store import DataStore
from quant_ko.notify.discord import DiscordNotifier
from quant_ko.strategy.scoring import score_and_select
from quant_ko.strategy.universe import filter_universe, is_seasonality_parking_period

logger = logging.getLogger(__name__)


CD_ETF_TICKER = "357870"  # TIGER CD금리투자KIS(합성) - 1주당 약 53,000원으로 소액 시드 단주 최소화


class ExecutedOrderSummary(TypedDict):
    """Structured summary of an executed (or attempted) order."""

    id: int
    order_no: str
    ticker: str
    name: str
    side: str
    qty: int
    price: float
    amount: float
    success: bool
    message: str


def _format_order_line(order: ExecutedOrderSummary, is_failure: bool = False) -> str:
    """Format an order summary for Discord embed display."""
    if is_failure:
        side_kr = "매수" if order["side"] == "BUY" else "매도"
        return (
            f"• [{side_kr}] {order['name']}({order['ticker']}) "
            f"{order['qty']:,}주 @ {int(order['price']):,}원 - 거절({order.get('message', '알 수 없음')})"
        )
    return (
        f"• {order['name']}({order['ticker']}) "
        f"{order['qty']:,}주 @ {int(order['price']):,}원 ({int(order['amount']):,}원)"
    )


def _chunk_field_lines(
    base_title: str,
    lines: list[str],
    empty_msg: str,
    max_len: int = 1000,
) -> list[dict[str, Any]]:
    """Split lines into field chunks if character length exceeds max_len."""
    if not lines:
        return [{"name": base_title, "value": empty_msg, "inline": False}]

    chunks: list[str] = []
    curr_lines: list[str] = []
    curr_len = 0
    for line in lines:
        line_len = len(line) + 1  # includes newline
        if curr_len + line_len > max_len and curr_lines:
            chunks.append("\n".join(curr_lines))
            curr_lines = [line]
            curr_len = line_len
        else:
            curr_lines.append(line)
            curr_len += line_len

    if curr_lines:
        chunks.append("\n".join(curr_lines))

    if len(chunks) <= 1:
        return [{"name": base_title, "value": chunks[0] if chunks else empty_msg, "inline": False}]

    return [
        {"name": f"{base_title} ({i + 1})", "value": chunk, "inline": False}
        for i, chunk in enumerate(chunks)
    ]


class LiveRebalancer:
    """Executes rebalancing orders via KIS Open API."""

    def __init__(
        self,
        store: DataStore,
        kis_client: KisClient,
        notifier: DiscordNotifier | None = None,
        env: str = "mock",
        rebalance_freq: str = "monthly",
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

    def is_d_minus_one(self, date: str, trading_days: list[str]) -> bool:
        """Check if given date is D-1 (the trading day immediately preceding rebalance date)."""
        norm = normalize_date(date)
        sorted_days = sorted({normalize_date(d) for d in trading_days})
        if norm not in sorted_days:
            return False
        idx = sorted_days.index(norm)
        if idx + 1 >= len(sorted_days):
            return False
        next_day = sorted_days[idx + 1]
        return self.is_rebalance_date(next_day, sorted_days)

    def send_d_minus_one_briefing(
        self,
        as_of_date: str,
        trading_days: list[str] | None = None,
        universe_kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send D-1 advance briefing notification to Discord before scheduled rebalance."""
        from datetime import datetime, timedelta

        norm_date = normalize_date(as_of_date)
        if not trading_days:
            trading_days = self.store.get_trading_days()
        sorted_days = sorted({normalize_date(d) for d in trading_days})

        target_reb_date = norm_date
        if norm_date in sorted_days:
            idx = sorted_days.index(norm_date)
            if idx + 1 < len(sorted_days):
                target_reb_date = sorted_days[idx + 1]
        else:
            dt_tmp = datetime.strptime(norm_date, "%Y-%m-%d")
            target_reb_date = (dt_tmp + timedelta(days=1)).strftime("%Y-%m-%d")

        # 1. Broker balance & positions
        balance = self.kis_client.fetch_balance()
        held_positions = {p.ticker: p for p in balance.positions if p.qty > 0}

        # 2. Strategy target calculation
        is_parking_period = self.strategy_mode == "seasonality" and is_seasonality_parking_period(target_reb_date)

        target_tickers: list[str] = []
        if is_parking_period:
            target_tickers = [self.cd_etf_ticker]
        else:
            try:
                u_kwargs = {"min_trading_value": 0.0}
                if universe_kwargs:
                    u_kwargs.update(universe_kwargs)
                universe_df = filter_universe(self.store, as_of_date=norm_date, **u_kwargs)
                if not universe_df.empty:
                    selected_df = score_and_select(universe_df, top_n=20)
                    if not selected_df.empty:
                        target_tickers = selected_df["ticker"].tolist()
            except Exception as e:
                logger.error("Failed to calculate target scores for D-1 briefing: %s", e)

        # 3. Compare portfolio deltas
        held_set = set(held_positions.keys())
        target_set = set(target_tickers)

        keep_tickers = held_set & target_set
        buy_tickers = target_set - held_set
        sell_tickers = held_set - target_set

        company_map: dict[str, str] = {}
        if self.store is not None:
            try:
                comp_df = self.store.get_companies()
                if not comp_df.empty:
                    company_map = dict(zip(comp_df["ticker"], comp_df["name"], strict=False))
            except Exception:
                pass
        company_map[self.cd_etf_ticker] = "TIGER CD금리투자KIS(합성)"

        # 4. Format Discord embed
        target_lines: list[str] = []
        if is_parking_period:
            target_lines.append(
                f"• {company_map.get(self.cd_etf_ticker, 'CD금리 ETF')}({self.cd_etf_ticker}) 100% 안전 파킹"
            )
        else:
            for rank, t in enumerate(target_tickers, 1):
                name = company_map.get(t, t)
                status_tag = "[유지]" if t in keep_tickers else "[신규]"
                target_lines.append(f"{rank:2d}. {name}({t}) {status_tag} - 목표 5.0%")

        fields: list[dict[str, Any]] = [
            {
                "name": "리밸런싱 예정일",
                "value": f"📅 **{target_reb_date} 15:20** (장마감 시장가)",
                "inline": True,
            },
            {
                "name": "운용 전략 / 환경",
                "value": f"{self.strategy_mode.upper()} / {self.env.upper()}",
                "inline": True,
            },
            {
                "name": "계좌 잔고 요약",
                "value": f"예수금: {int(balance.cash):,}원 | 총 평가액: {int(balance.total_eval_amount):,}원",
                "inline": False,
            },
            {
                "name": "포트폴리오 교체 요약",
                "value": f"🔹 유지 {len(keep_tickers)}개 | 🟢 신규 편입 {len(buy_tickers)}개 | 🔴 전량 매도 {len(sell_tickers)}개",
                "inline": False,
            },
        ]

        target_chunks = _chunk_field_lines(
            f"🎯 예정 타깃 종목 ({len(target_tickers)}개)",
            target_lines,
            "예정 타깃 없음",
            max_len=1000,
        )
        fields.extend(target_chunks)

        if self.notifier:
            self.notifier.send_embed(
                title=f"📢 [D-1 사전 안내] 내일({target_reb_date}) 정기 리밸런싱 예정 브리핑",
                description="내일 15:20 장마감 시장가 리밸런싱이 진행될 예정입니다. 포트폴리오 사전 점검 리포트를 안내합니다.",
                fields=fields,
                color=0x3498DB,  # Nice Blue
            )

        return {
            "success": True,
            "target_date": target_reb_date,
            "target_tickers": target_tickers,
            "keep_count": len(keep_tickers),
            "buy_count": len(buy_tickers),
            "sell_count": len(sell_tickers),
        }


    def get_prior_trading_day(self, date: str, trading_days: list[str] | None = None) -> str:
        """Find the trading day immediately preceding the given date."""
        from datetime import datetime, timedelta

        norm = normalize_date(date)
        if not trading_days:
            trading_days = self.store.get_trading_days()
        sorted_days = sorted({normalize_date(d) for d in trading_days})
        prior_days = [d for d in sorted_days if d < norm]
        if prior_days:
            return prior_days[-1]
        # Fallback to previous calendar day
        return (datetime.strptime(norm, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

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
        norm_pit_date = normalize_date(pit_date) if pit_date else self.get_prior_trading_day(norm_reb_date)

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
        is_parking_period = self.strategy_mode == "seasonality" and is_seasonality_parking_period(norm_reb_date)

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
        # 3. Collect current prices and lookup company names
        all_tickers = set(held_positions.keys()).union(target_weights.keys())
        name_map: dict[str, str] = {}
        if self.store is not None:
            try:
                c_df = self.store.get_companies(list(all_tickers))
                if not c_df.empty:
                    name_map = dict(zip(c_df["ticker"], c_df["name"], strict=False))
            except Exception as e:
                logger.warning("Failed to lookup company names: %s", e)
        if self.cd_etf_ticker not in name_map:
            name_map[self.cd_etf_ticker] = "TIGER CD금리투자KIS(합성)"

        def get_stock_name(t: str) -> str:
            return name_map.get(t) or t

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

        executed_orders: list[ExecutedOrderSummary] = []
        available_cash = current_cash

        # 4. Execute SELLs first
        for ticker, qty, price in sells:
            name = get_stock_name(ticker)
            amount = qty * price
            try:
                if dry_run:
                    res_success = True
                    order_no = f"DRY_SELL_{ticker}"
                    msg = "모의 실행 완료"
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
                    msg = res.message or ("정상 체결" if res.success else "주문 실패")

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
                        "name": name,
                        "side": "SELL",
                        "qty": qty,
                        "price": price,
                        "amount": amount,
                        "success": res_success,
                        "message": msg,
                    }
                )
                if res_success:
                    net_proceeds = qty * price * (1.0 - self.cost_rate)
                    available_cash += net_proceeds
                if not dry_run:
                    time.sleep(0.5)
            except Exception as e:
                logger.error("SELL order failed for %s: %s", ticker, e)
                executed_orders.append(
                    {
                        "id": 0,
                        "order_no": "",
                        "ticker": ticker,
                        "name": name,
                        "side": "SELL",
                        "qty": qty,
                        "price": price,
                        "amount": amount,
                        "success": False,
                        "message": f"시스템 오류 ({type(e).__name__})",
                    }
                )

        # 5. Execute BUYs next
        for ticker, qty, price in buys:
            if price <= 0:
                continue
            name = get_stock_name(ticker)
            cost_per_share = price * (1.0 + self.cost_rate)
            max_buyable = math.floor(available_cash / cost_per_share) if cost_per_share > 0 else 0
            buy_qty = min(qty, max_buyable)
            if buy_qty <= 0:
                if qty > 0:
                    executed_orders.append(
                        {
                            "id": 0,
                            "order_no": "",
                            "ticker": ticker,
                            "name": name,
                            "side": "BUY",
                            "qty": qty,
                            "price": price,
                            "amount": qty * price,
                            "success": False,
                            "message": "예수금 부족으로 주문 스킵",
                        }
                    )
                continue

            amount = buy_qty * price
            try:
                if dry_run:
                    res_success = True
                    order_no = f"DRY_BUY_{ticker}"
                    msg = "모의 실행 완료"
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
                    msg = res.message or ("정상 체결" if res.success else "주문 실패")

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
                        "name": name,
                        "side": "BUY",
                        "qty": buy_qty,
                        "price": price,
                        "amount": amount,
                        "success": res_success,
                        "message": msg,
                    }
                )
                if res_success:
                    total_outlay = buy_qty * cost_per_share
                    available_cash -= total_outlay
                if not dry_run:
                    time.sleep(0.5)
            except Exception as e:
                logger.error("BUY order failed for %s: %s", ticker, e)
                executed_orders.append(
                    {
                        "id": 0,
                        "order_no": "",
                        "ticker": ticker,
                        "name": name,
                        "side": "BUY",
                        "qty": buy_qty,
                        "price": price,
                        "amount": amount,
                        "success": False,
                        "message": f"시스템 오류 ({type(e).__name__})",
                    }
                )

        # 6. Discord Notification
        if self.notifier:
            success_sells = [o for o in executed_orders if o["side"] == "SELL" and o.get("success")]
            success_buys = [o for o in executed_orders if o["side"] == "BUY" and o.get("success")]
            failed_orders = [o for o in executed_orders if not o.get("success")]

            fields: list[dict[str, Any]] = []

            # 1. 🎯 타깃 포트폴리오 (N종목)
            target_lines = [
                f"• {get_stock_name(t)}({t}) {w * 100:.1f}%" for t, w in target_weights.items()
            ]
            fields.extend(
                _chunk_field_lines(
                    f"🎯 타깃 포트폴리오 ({len(target_weights)}종목)",
                    target_lines,
                    "타깃 종목 없음",
                )
            )

            # 2. 🔴 매도 체결 상세 (N건)
            sell_lines = [_format_order_line(o) for o in success_sells]
            fields.extend(
                _chunk_field_lines(
                    f"🔴 매도 체결 상세 ({len(success_sells)}건)",
                    sell_lines,
                    "매도 내역 없음",
                )
            )

            # 3. 🟢 매수 체결 상세 (N건)
            buy_lines = [_format_order_line(o) for o in success_buys]
            fields.extend(
                _chunk_field_lines(
                    f"🟢 매수 체결 상세 ({len(success_buys)}건)",
                    buy_lines,
                    "매수 내역 없음",
                )
            )

            # 4. ⚠️ 주문 실패/거절 (N건) (only if failed_orders exist)
            if failed_orders:
                failed_lines = [_format_order_line(o, is_failure=True) for o in failed_orders]
                fields.extend(
                    _chunk_field_lines(
                        f"⚠️ 주문 실패/거절 ({len(failed_orders)}건)",
                        failed_lines,
                        "실패 내역 없음",
                    )
                )

            # 5. 💰 계좌 요약
            fields.append(
                {
                    "name": "💰 계좌 요약",
                    "value": f"총 평가액: {int(total_equity):,}원 | 예상 잔여 예수금: {int(available_cash):,}원",
                    "inline": False,
                }
            )

            # 6. ⚙️ 운용 환경
            fields.append(
                {
                    "name": "⚙️ 운용 환경",
                    "value": f"{self.env.upper()}{' (DRY-RUN)' if dry_run else ''}",
                    "inline": True,
                }
            )

            mode_tag = "[모의 실행 (Dry-Run)]" if dry_run else "[리밸런싱 완료]"
            embed_color = 0x3498DB if dry_run else (0xE74C3C if failed_orders else 0x2ECC71)

            self.notifier.send_embed(
                title=f"📈 {mode_tag} {norm_reb_date}",
                description=f"포트폴리오 총 평가액: {int(total_equity):,}원\n주문 전송이 완료되었습니다.",
                fields=fields,
                color=embed_color,
            )

        return {
            "success": True,
            "rebalance_date": norm_reb_date,
            "pit_date": norm_pit_date,
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
