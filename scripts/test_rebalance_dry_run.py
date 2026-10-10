"""Demonstrate 11월 진입 가상 리밸런싱 Dry-Run (원금 1,000만 원 기준).

실제 KIS 주문 전송 없이,
현재 DB 최신 데이터(2026.10.08)를 기준으로 9대 팩터 20종목 선정 및 수량 계산을 검증합니다.
"""

from unittest.mock import MagicMock

from quant_ko.broker.kis import Balance, KisClient
from quant_ko.data.store import DataStore
from quant_ko.live.rebalancer import LiveRebalancer


def main():
    store = DataStore("data/quant_ko.db")
    mock_kis = KisClient(is_mock=True)

    # 1,000만 원 예수금 가상 설정
    mock_kis.fetch_balance = MagicMock(
        return_value=Balance(cash=10_000_000.0, total_eval_amount=10_000_000.0, positions=[])
    )

    rebalancer = LiveRebalancer(
        store=store,
        kis_client=mock_kis,
        env="mock",
        strategy_mode="standard",  # 주식 20종목 적극 매수 모드
    )

    res = rebalancer.execute(
        rebalance_date="2026-10-31",
        pit_date="2026-10-08",
        dry_run=True,
    )

    print("\n" + "=" * 65)
    print(" [11월 진입 소형주 9대 팩터 20종목 가상 매수 Dry-Run 결과] ")
    print("=" * 65)
    print(f"리밸런싱 일자  : {res['rebalance_date']}")
    print(f"가상 계좌 자산: {int(res['total_equity']):,} 원")
    print(f"총 주문 종목수: {len(res['orders'])} 개 (동일 비중 5%씩)")
    print("-" * 65)

    total_spent = 0
    for idx, o in enumerate(res["orders"], 1):
        c_df = store.get_companies(tickers=[o["ticker"]])
        name = c_df["name"].iloc[0] if not c_df.empty else o["ticker"]
        amt = o["qty"] * o["price"]
        total_spent += amt
        print(
            f" {idx:2d}. {name:<10} ({o['ticker']}) : {o['qty']:3d}주 @ {int(o['price']):,>7}원 = {int(amt):,>8}원"
        )

    print("-" * 65)
    print(
        f"총 매수 투입 금액: {int(total_spent):,} 원 (잔여 현금: {int(res['total_equity'] - total_spent):,} 원)"
    )
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
