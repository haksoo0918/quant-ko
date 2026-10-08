"""Daily Designation Monitoring Service."""

import logging
from typing import Any

from quant_ko.broker.kis import KisClient
from quant_ko.data.krx import normalize_date
from quant_ko.data.store import DataStore
from quant_ko.notify.discord import DiscordNotifier

logger = logging.getLogger(__name__)

DANGEROUS_DESIGNATION_TYPES = {"관리종목", "투자주의환기종목"}


class DailyMonitor:
    """Monitors held positions for designations and executes immediate liquidations."""

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

    def check_and_liquidate(self, as_of_date: str) -> list[dict[str, Any]]:
        """Check held positions against active designations and liquidate designated stocks.

        If any held stock is designated as '관리종목' or '투자주의환기종목':
        - Immediately places SELL order for all held shares.
        - Proceeds are held in cash.
        - Logs order in SQLite orders table.
        - Sends high-priority Discord alert.
        """
        norm_date = normalize_date(as_of_date)
        balance = self.kis_client.fetch_balance()
        held_positions = {p.ticker: p for p in balance.positions if p.qty > 0}

        if not held_positions:
            return []

        # Query designations active on as_of_date
        designations_df = self.store.get_designations(as_of_date=norm_date)
        if designations_df.empty:
            return []

        # Filter for dangerous designations
        crit_df = designations_df[designations_df["type"].isin(DANGEROUS_DESIGNATION_TYPES)]
        if crit_df.empty:
            return []

        designated_map = dict(zip(crit_df["ticker"], crit_df["type"], strict=False))

        liquidated_orders: list[dict[str, Any]] = []

        for ticker, pos in held_positions.items():
            if ticker in designated_map:
                desig_type = designated_map[ticker]
                price = self.kis_client.fetch_current_price(ticker)
                if price <= 0:
                    price = pos.current_price

                logger.warning(
                    "CRITICAL: Held stock %s (%s) designated as %s. Liquidating %d shares at %s",
                    ticker,
                    pos.name,
                    desig_type,
                    pos.qty,
                    price,
                )

                try:
                    res = self.kis_client.place_order(
                        ticker=ticker,
                        side="SELL",
                        qty=pos.qty,
                        price=price,
                    )
                    order_id = self.store.insert_order(
                        {
                            "rebalance_date": norm_date,
                            "ticker": ticker,
                            "side": "SELL",
                            "qty": pos.qty,
                            "price": price,
                            "status": "ORDERED" if res.success else "FAILED",
                            "filled_qty": 0,
                            "env": self.env,
                        }
                    )

                    liq_info = {
                        "id": order_id,
                        "order_no": res.order_no,
                        "ticker": ticker,
                        "name": pos.name,
                        "designation_type": desig_type,
                        "qty": pos.qty,
                        "price": price,
                        "success": res.success,
                    }
                    liquidated_orders.append(liq_info)

                    if self.notifier:
                        fields = [
                            {
                                "name": "종목코드 / 종목명",
                                "value": f"{ticker} ({pos.name})",
                                "inline": True,
                            },
                            {"name": "지정 사유", "value": desig_type, "inline": True},
                            {
                                "name": "매도 수량 및 단가",
                                "value": f"{pos.qty}주 @ {int(price):,}원",
                                "inline": True,
                            },
                        ]
                        self.notifier.send_embed(
                            title="🚨 [긴급 매도] 관리종목/투자주의환기종목 지정 감지",
                            description=f"보유 종목 {ticker}의 {desig_type} 지정이 감지되어 전량 긴급 매도 주문을 전송했습니다. 매도 대금은 현금으로 보관됩니다.",
                            fields=fields,
                            color=0xE74C3C,  # Bright Red
                        )
                except Exception as e:
                    logger.critical("Failed to liquidate designated stock %s: %s", ticker, e)

        return liquidated_orders
