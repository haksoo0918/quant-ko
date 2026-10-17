"""Daily Designation Monitoring Service."""

import logging
from typing import Any

from quant_ko.broker.kis import KisClient
from quant_ko.data.krx import normalize_date
from quant_ko.data.store import DataStore
from quant_ko.notify.discord import DiscordNotifier

logger = logging.getLogger(__name__)

# 한국거래소(KRX) 공시 명칭과 DB 정규화 명칭 모두 매칭 지원
DANGEROUS_DESIGNATION_TYPES = {"관리", "투자주의환기", "관리종목", "투자주의환기종목"}


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

    def check_and_liquidate(
        self, as_of_date: str, send_heartbeat: bool = True
    ) -> list[dict[str, Any]]:
        """Check held positions against active designations and liquidate designated stocks.

        If any held stock is designated as '관리종목' or '투자주의환기종목':
        - Immediately places SELL order for all held shares.
        - Proceeds are held in cash.
        - Logs order in SQLite orders table.
        - Sends high-priority Discord alert.
        If all positions are healthy and send_heartbeat is True, sends morning ping report.
        """
        norm_date = normalize_date(as_of_date)
        balance = self.kis_client.fetch_balance()
        held_positions = {p.ticker: p for p in balance.positions if p.qty > 0}

        liquidated_orders: list[dict[str, Any]] = []

        if held_positions:
            # Query designations active on as_of_date
            designations_df = self.store.get_designations(as_of_date=norm_date)
            if not designations_df.empty:
                # Filter for dangerous designations
                crit_df = designations_df[designations_df["type"].isin(DANGEROUS_DESIGNATION_TYPES)]
                if not crit_df.empty:
                    designated_map = dict(zip(crit_df["ticker"], crit_df["type"], strict=False))

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

        # 위험 종목이 없고(모두 정상) send_heartbeat가 활성화된 경우 모닝 생존 확인 리포트 전송
        if not liquidated_orders and send_heartbeat and self.notifier:
            self._send_heartbeat(norm_date, balance, held_positions)

        return liquidated_orders

    def _send_heartbeat(
        self,
        as_of_date: str,
        balance: Any,
        held_positions: dict[str, Any],
    ) -> None:
        """Send 08:30 morning heartbeat ping to Discord."""
        pos_count = len(held_positions)
        if pos_count > 0:
            top_positions = list(held_positions.values())[:5]
            pos_preview = ", ".join(f"{p.name}" for p in top_positions)
            if pos_count > 5:
                pos_preview += f" 외 {pos_count - 5}개"
            pos_desc = f"{pos_count}개 ({pos_preview})"
        else:
            pos_desc = "0개 (보유 주식 없음)"

        fields = [
            {"name": "기준 일자", "value": as_of_date, "inline": True},
            {"name": "운용 환경", "value": self.env.upper(), "inline": True},
            {"name": "보유 종목 수", "value": pos_desc, "inline": True},
            {
                "name": "계좌 잔고",
                "value": f"예수금: {int(balance.cash):,}원 | 총 평가액: {int(balance.total_eval_amount):,}원",
                "inline": False,
            },
            {
                "name": "감시 결과",
                "value": "관리종목 / 투자주의환기종목 지정: 0건 (이상 없음)",
                "inline": False,
            },
        ]

        self.notifier.send_embed(
            title="✅ [정상 가동] 08:30 일일 감시 봇 생존 확인",
            description="장 시작 전 일일 관리종목 및 비상 청산 감시가 정상 실행되었습니다. 모든 보유 종목이 안전합니다.",
            fields=fields,
            color=0x2ECC71,  # Green
        )

