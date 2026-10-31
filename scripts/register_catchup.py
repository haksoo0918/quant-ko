"""10/30 리밸런싱 미체결 종목을 조회하여 PENDING_CATCHUP 큐로 자동 등록하는 스크립트."""

import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))
load_dotenv(project_root / ".env")

from quant_ko.broker.kis import KisClient  # noqa: E402
from quant_ko.data.store import DataStore  # noqa: E402


def register_pending_catchup(
    store: DataStore,
    kis_client: KisClient,
    rebalance_date: str = "2026-10-30",
    env: str = "real",
) -> list[str]:
    """실계좌 잔고와 10/30 매수 주문을 대조하여 누락된 종목을 PENDING_CATCHUP으로 등록합니다."""
    # 1. 대상 날짜의 실전 매수 주문 조회
    orders = store.get_orders(rebalance_date=rebalance_date, env=env)
    if orders.empty:
        all_orders = store.get_orders(env=env)
        orders = all_orders[all_orders["side"] == "BUY"]

    if orders.empty:
        print("[!] 10/30 매수 주문 내역을 찾을 수 없습니다.")
        return []

    # 2. 한투 실계좌 잔고 조회
    balance = kis_client.fetch_balance()
    held_tickers = {p.ticker for p in balance.positions if p.qty > 0}
    print(f"[*] 실계좌 보유 종목: {len(held_tickers)}개, 잔여 예수금: {int(balance.cash):,}원")

    # 3. 미보유 종목 식별 및 PENDING_CATCHUP 마킹
    updated_tickers: list[str] = []
    for _, row in orders.iterrows():
        ticker = str(row["ticker"])
        order_id = int(row["id"])
        if ticker not in held_tickers:
            store.update_order_status(order_id, "PENDING_CATCHUP")
            print(f"    >> [미체결 종목 감지] {ticker} (주문 ID: {order_id}) -> PENDING_CATCHUP 등록")
            updated_tickers.append(ticker)

    return updated_tickers


def main() -> None:
    db_path = project_root / "data" / "quant_ko.db"
    store = DataStore(db_path)
    kis = KisClient(is_mock=False)

    print(f"[*] DB 파일: {db_path}")
    updated = register_pending_catchup(store=store, kis_client=kis)

    if updated:
        print(f"\n[성공] 총 {len(updated)}개 종목({', '.join(updated)})이 PENDING_CATCHUP 큐에 등록되었습니다.")
        print("       내일(월요일) 15:20에 잔여 예수금으로 자동 보충 매수됩니다.")
    else:
        print("\n[*] 이미 모든 타깃 종목을 보유 중이거나 미체결 대상이 없습니다.")


if __name__ == "__main__":
    main()
