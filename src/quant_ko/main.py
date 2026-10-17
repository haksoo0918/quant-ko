"""Main CLI Entrypoint for quant_ko production & mock operations.

Usage:
    # 1. Execute Monthly Rebalance (Live / Mock)
    python -m quant_ko.main --mode rebalance [--dry-run] [--date YYYY-MM-DD] [--env mock|real]

    # 2. Execute Daily Designation Emergency Monitor
    python -m quant_ko.main --mode monitor [--date YYYY-MM-DD] [--env mock|real]

    # 3. Check Account Status & Strategy State
    python -m quant_ko.main --mode status [--env mock|real]
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from quant_ko.broker.kis import KisClient
from quant_ko.data.store import DataStore
from quant_ko.live.monitor import DailyMonitor
from quant_ko.live.rebalancer import LiveRebalancer
from quant_ko.notify.discord import DiscordNotifier

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("quant_ko.main")


def get_current_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def print_status(kis_client: KisClient, env: str, date_str: str) -> None:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    month = dt.month
    is_parking = month in [5, 6, 7, 8, 9, 10]
    season_desc = (
        "5~10월 CD금리 ETF (안전 대피 구간)"
        if is_parking
        else "11~4월 소형주 20종목 (적극 투자 구간)"
    )

    print("\n" + "=" * 60)
    print(f" [quant_ko 운영 현황 리포트 - {env.upper()} 모드] ")
    print("=" * 60)
    print(f"기준 일자        : {date_str} ({dt.strftime('%A')})")
    print(f"전략 상태        : {season_desc}")
    print(f"계좌 번호        : {kis_client.account_prefix}-{kis_client.account_suffix}")

    try:
        balance = kis_client.fetch_balance()
        print(f"주문 가능 예수금 : {int(balance.cash):,} 원")
        print(f"총 평가 금액     : {int(balance.total_eval_amount):,} 원")
        print(f"보유 종목 수     : {len(balance.positions)} 개")
        if balance.positions:
            print("\n[현재 보유 종목]")
            for p in balance.positions:
                print(
                    f"  - {p.name}({p.ticker}): {p.qty}주 | 현재가: {int(p.current_price):,}원 | 평가액: {int(p.eval_amount):,}원"
                )
        else:
            print("  (현재 보유 중인 주식이 없습니다)")
    except Exception as e:
        print(f"계좌 잔고 조회 실패: {e}")

    print("=" * 60 + "\n")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="quant-ko Live / Mock Quantitative Trading CLI")
    parser.add_argument(
        "--mode",
        choices=["rebalance", "monitor", "status", "preview"],
        default="status",
        help="Execution mode: rebalance, monitor, status, or preview (D-1 advance briefing)",
    )
    parser.add_argument(
        "--env",
        choices=["mock", "real"],
        default=os.getenv("KIS_MODE", "MOCK").lower(),
        help="Broker environment: mock or real",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without placing real orders",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date in YYYY-MM-DD format (defaults to today)",
    )
    parser.add_argument(
        "--strategy",
        choices=["seasonality", "standard"],
        default="seasonality",
        help="Strategy mode: seasonality (Strategy 1) or standard",
    )
    parser.add_argument(
        "--order-type",
        choices=["01", "00"],
        default="01",
        help="Order division: '01' (market order / 시장가 15:20 동시호가 100%% 체결, default) or '00' (limit order / 지정가)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force execution even if target date is not a scheduled rebalancing date",
    )
    parser.add_argument(
        "--no-heartbeat",
        action="store_true",
        help="Suppress morning heartbeat Discord notification in monitor mode",
    )

    args = parser.parse_args()
    target_date = args.date or get_current_date()
    is_mock = args.env.lower() == "mock"

    store = DataStore("data/quant_ko.db")
    kis_client = KisClient(is_mock=is_mock)
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    notifier = DiscordNotifier(webhook_url=webhook_url) if webhook_url else None

    logger.info(
        "Running quant-ko in mode: %s, env: %s, date: %s", args.mode, args.env.upper(), target_date
    )

    if args.mode == "status":
        print_status(kis_client=kis_client, env=args.env, date_str=target_date)

    elif args.mode == "monitor":
        monitor = DailyMonitor(
            store=store,
            kis_client=kis_client,
            notifier=notifier,
            env=args.env,
        )
        logger.info("Executing daily designation check for %s...", target_date)
        res = monitor.check_and_liquidate(
            as_of_date=target_date,
            send_heartbeat=not args.no_heartbeat,
        )
        if res:
            logger.warning("Emergency liquidated %d designated stocks!", len(res))
        else:
            logger.info("Designation check complete: All held positions healthy (0 issues).")

    elif args.mode == "preview":
        rebalancer = LiveRebalancer(
            store=store,
            kis_client=kis_client,
            notifier=notifier,
            env=args.env,
            strategy_mode=args.strategy,
        )

        trading_days = store.get_trading_days()
        if not args.force and not rebalancer.is_d_minus_one(target_date, trading_days):
            logger.info(
                "오늘(%s)은 리밸런싱 D-1일이 아닙니다 (매월 마지막 거래일 전 영업일). 작업을 안전하게 종료합니다.",
                target_date,
            )
            sys.exit(0)

        logger.info("Executing D-1 rebalance preview briefing on %s...", target_date)
        res = rebalancer.send_d_minus_one_briefing(as_of_date=target_date, trading_days=trading_days)
        if res.get("success"):
            logger.info(
                "D-1 리밸런싱 사전 브리핑 전송 완료 (리밸런싱 예정일: %s, 예정 타깃: %d개)",
                res.get("target_date"),
                len(res.get("target_tickers", [])),
            )
        else:
            logger.error("D-1 사전 브리핑 실패")
            sys.exit(1)

    elif args.mode == "rebalance":
        rebalancer = LiveRebalancer(
            store=store,
            kis_client=kis_client,
            notifier=notifier,
            env=args.env,
            strategy_mode=args.strategy,
            order_type=args.order_type,
        )

        # 리밸런싱 날짜 게이트 검사 (크론탭 매일 실행 시 불필요한 매매 방지)
        if not args.force:
            trading_days = store.get_trading_days()
            if not rebalancer.is_rebalance_date(target_date, trading_days):
                logger.info(
                    "오늘(%s)은 정기 리밸런싱일이 아닙니다 (매월 마지막 거래일). 작업을 안전하게 종료합니다.",
                    target_date,
                )
                sys.exit(0)

        logger.info("Executing rebalance on %s (Dry-run: %s)...", target_date, args.dry_run)
        res = rebalancer.execute(
            rebalance_date=target_date,
            dry_run=args.dry_run,
        )
        if res.get("success"):
            logger.info(
                "Rebalancing finished successfully! Orders generated: %d",
                len(res.get("orders", [])),
            )
            for o in res.get("orders", []):
                print(
                    f"  [{o['side']}] {o['ticker']}: {o['qty']}주 @ {int(o['price']):,}원 ({o.get('order_no', '')})"
                )
        else:
            logger.error("Rebalancing failed or aborted: %s", res.get("message"))
            sys.exit(1)


if __name__ == "__main__":
    main()
