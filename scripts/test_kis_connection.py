"""Safe KIS API connection test script (Read-Only).

Calls OAuth token issuance and account balance inquiry.
Absolutely NO trading or order placement will be performed.
"""

import logging
import os

from dotenv import load_dotenv

from quant_ko.broker.kis import KisClient
from quant_ko.notify.discord import DiscordNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_kis_connection")


def main():
    load_dotenv()

    mode = os.getenv("KIS_MODE", "MOCK").upper()
    logger.info("Testing KIS Connection in mode: %s...", mode)

    # 1. Initialize client using configured env mode
    client = KisClient()
    logger.info("Target URL: %s", client.base_url)
    logger.info("Account: %s-%s", client.account_prefix, client.account_suffix)

    # 2. Test OAuth Token
    try:
        token = client.get_access_token()
        logger.info(" OAuth Token acquired successfully! (Token length: %d)", len(token))
    except Exception as e:
        logger.error(" OAuth Token acquisition FAILED: %s", e)
        return

    # 3. Test Current Price Inquiry (삼성전자 005930)
    try:
        price = client.fetch_current_price("005930")
        logger.info(
            " Current price inquiry success: Samsung Electronics (005930) = %s KRW",
            f"{int(price):,}",
        )
    except Exception as e:
        logger.error(" Current price inquiry FAILED: %s", e)

    # 4. Test Account Balance Inquiry (Read-Only)
    try:
        balance = client.fetch_balance()
        logger.info(" Balance inquiry SUCCESS!")
        print("\n" + "=" * 55)
        print(f" [한국투자증권 계좌 잔고 조회 결과 - {mode} 모드] ")
        print("=" * 55)
        print(f"계좌 번호       : {client.account_prefix}-{client.account_suffix}")
        print(f"주문 가능 예수금: {int(balance.cash):,} 원")
        print(f"총 평가 금액    : {int(balance.total_eval_amount):,} 원")
        print(f"보유 종목 수    : {len(balance.positions)} 개")
        if balance.positions:
            print("\n[보유 종목 리스트]")
            for p in balance.positions:
                print(
                    f"  - {p.name}({p.ticker}): {p.qty}주 (현재가: {int(p.current_price):,}원, 평가액: {int(p.eval_amount):,}원)"
                )
        else:
            print("  (현재 보유 중인 주식이 없습니다)")
        print("=" * 55 + "\n")
    except Exception as e:
        logger.error(" Balance inquiry FAILED: %s", e)

    # 5. Optional Discord Test
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        try:
            notifier = DiscordNotifier(webhook_url=webhook_url)
            notifier.send_embed(
                title=f"🤖 [KIS API 연동 성공] {mode} 모드",
                description="한국투자증권 Open API 토큰 발급 및 잔고 조회가 정상 작동함을 확인했습니다.",
                fields=[
                    {"name": "운용 모드", "value": mode, "inline": True},
                    {"name": "계좌 번호", "value": f"{client.account_prefix}-**", "inline": True},
                ],
                color=0x3498DB,
            )
            logger.info(" Discord test notification sent successfully!")
        except Exception as e:
            logger.warning(" Discord notification failed: %s", e)


if __name__ == "__main__":
    main()
