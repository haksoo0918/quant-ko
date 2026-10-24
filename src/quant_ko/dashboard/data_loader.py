"""Quant-KO 모니터링 대시보드용 데이터 로더 모듈.

KIS Open API 실시간 잔고 조회 및 오프라인(SQLite DB 기반) 폴백,
일별 실제 계좌 자산 추이 산출, 실제 거래기록 필터링 조회,
9대 팩터 상위 20종목 프리뷰 기능을 순수 함수 형태로 제공합니다.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from quant_ko.broker.kis import KisClient
from quant_ko.data.krx import normalize_date
from quant_ko.data.store import DataStore
from quant_ko.strategy.scoring import score_and_select
from quant_ko.strategy.universe import filter_universe, is_seasonality_parking_period

logger = logging.getLogger(__name__)

CD_ETF_TICKER = "357870"
CD_ETF_NAME = "TIGER CD금리투자KIS(합성)"
EXECUTED_STATUSES = {"FILLED", "PARTIAL", "ORDERED"}


def mask_account_no(cano: str, prdt_cd: str = "01") -> str:
    """계좌번호 앞 4자리만 노출하고 나머지를 마스킹 처리합니다.

    Args:
        cano: 8자리 계좌번호 또는 '12345678-01' 형식의 문자열.
        prdt_cd: 계좌상품코드 (기본값 '01').

    Returns:
        마스킹된 계좌번호 문자열 (예: '5021****-01').
    """
    raw = str(cano or "").strip()
    prdt = str(prdt_cd or "01").strip() or "01"

    if not raw:
        return f"미설정-{prdt}"

    if "-" in raw:
        parts = raw.split("-", 1)
        cano_part = parts[0].strip()
        prdt_part = parts[1].strip() or prdt
    elif len(raw) >= 10:
        cano_part = raw[:8]
        prdt_part = raw[8:10]
    else:
        cano_part = raw
        prdt_part = prdt

    if len(cano_part) >= 4:
        masked_prefix = f"{cano_part[:4]}****"
    elif cano_part:
        masked_prefix = f"{cano_part}****"
    else:
        masked_prefix = "****"

    return f"{masked_prefix}-{prdt_part}"


def _load_company_name_map(store: DataStore) -> dict[str, str]:
    """SQLite companies 테이블에서 종목코드-종목명 매핑 딕셔너리를 생성합니다."""
    name_map: dict[str, str] = {CD_ETF_TICKER: CD_ETF_NAME}
    try:
        comp_df = store.get_companies()
        if not comp_df.empty and "ticker" in comp_df.columns and "name" in comp_df.columns:
            for _, row in comp_df[["ticker", "name"]].iterrows():
                t = str(row["ticker"]).strip()
                n = str(row["name"] or "").strip()
                if t and n:
                    name_map[t] = n
    except Exception as exc:
        logger.warning("종목명 매핑 로드 실패: %s", exc)
    return name_map


def _get_latest_prices_map(store: DataStore, tickers: list[str]) -> dict[str, float]:
    """지정된 종목 리스트의 DB 최신 종가를 조회합니다."""
    prices: dict[str, float] = {}
    if not tickers:
        return prices
    try:
        placeholders = ",".join("?" for _ in tickers)
        query = f"""
            SELECT dp.ticker, dp.close
            FROM daily_prices dp
            INNER JOIN (
                SELECT ticker, MAX(date) AS max_date
                FROM daily_prices
                WHERE ticker IN ({placeholders})
                GROUP BY ticker
            ) latest
            ON dp.ticker = latest.ticker AND dp.date = latest.max_date
        """
        with store.get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=tickers)
        for _, row in df.iterrows():
            prices[str(row["ticker"]).strip()] = float(row["close"] or 0.0)
    except Exception as exc:
        logger.warning("최신 종가 조회 실패: %s", exc)
    return prices


def _effective_order_qty(row: pd.Series | dict[str, Any]) -> int:
    """주문 레코드에서 유효 체결(또는 주문) 수량을 추출합니다."""
    filled = int(row.get("filled_qty") or 0)
    if filled > 0:
        return filled
    return int(row.get("qty") or 0)


def load_account_and_positions(
    db_path: str | Path = "data/quant_ko.db",
    fetch_live_kis: bool = True,
    initial_capital: float = 10_000_000.0,
) -> dict[str, Any]:
    """계좌 요약 정보와 현재 보유 종목 포트폴리오를 로드합니다.

    KIS Open API 실시간 조회를 우선 시도하며, 오프라인이거나 API 키가 없을 경우
    SQLite DB의 체결/접수 주문(`orders`) 및 최신 종가(`daily_prices`)를 기반으로
    보유 포지션과 예수금을 자동 복원합니다.

    Args:
        db_path: SQLite 데이터베이스 파일 경로.
        fetch_live_kis: KIS API 실시간 잔고 조회 시도 여부.
        initial_capital: 오프라인 폴백 시 기준 초기 자본금(원).

    Returns:
        계좌 상태, KPI 지표, 보유 종목 리스트 및 DataFrame을 포함한 딕셔너리.
    """
    load_dotenv()
    kis_mode = os.getenv("KIS_MODE", "MOCK").strip().upper()
    is_mock = kis_mode != "REAL"
    prefix = "KIS_MOCK_" if is_mock else "KIS_REAL_"

    cano = (
        os.getenv(f"{prefix}CANO")
        or os.getenv(f"{prefix}ACCOUNT_NO")
        or os.getenv("KIS_CANO")
        or os.getenv("KIS_ACCOUNT_NO", "")
    )
    prdt_cd = os.getenv(f"{prefix}ACNT_PRDT_CD") or os.getenv("KIS_ACNT_PRDT_CD", "01")
    masked_acc = mask_account_no(cano, prdt_cd)

    today_str = datetime.now().strftime("%Y-%m-%d")
    is_parking_season = is_seasonality_parking_period(today_str)

    store = DataStore(db_path)
    name_map = _load_company_name_map(store)

    orders_df = pd.DataFrame()
    try:
        orders_df = store.get_orders()
    except Exception:
        orders_df = pd.DataFrame()

    total_orders_count = len(orders_df)

    # 1. KIS API 실시간 잔고 조회 시도
    if fetch_live_kis:
        try:
            client = KisClient()
            if client.app_key and client.app_secret and client.account_prefix:
                balance = client.fetch_balance()
                positions_list: list[dict[str, Any]] = []
                stock_value = 0.0
                for pos in balance.positions:
                    if pos.qty <= 0:
                        continue
                    eval_amt = (
                        float(pos.eval_amount)
                        if pos.eval_amount > 0
                        else float(pos.qty * pos.current_price)
                    )
                    stock_value += eval_amt
                    avg_p = float(pos.purchase_price or pos.current_price)
                    ret_pct = ((pos.current_price / avg_p) - 1.0) * 100.0 if avg_p > 0 else 0.0
                    positions_list.append(
                        {
                            "ticker": pos.ticker,
                            "name": pos.name or name_map.get(pos.ticker, pos.ticker),
                            "qty": int(pos.qty),
                            "avg_price": round(avg_p, 0),
                            "current_price": round(float(pos.current_price), 0),
                            "eval_amount": round(eval_amt, 0),
                            "return_pct": round(ret_pct, 2),
                            "weight_pct": 0.0,
                        }
                    )

                cash = float(balance.cash)
                total_equity = (
                    float(balance.total_eval_amount)
                    if balance.total_eval_amount > 0
                    else (cash + stock_value)
                )
                for item in positions_list:
                    item["weight_pct"] = (
                        round((item["eval_amount"] / total_equity) * 100.0, 2)
                        if total_equity > 0
                        else 0.0
                    )

                positions_list.sort(key=lambda x: x["eval_amount"], reverse=True)
                return {
                    "kis_mode": "MOCK" if is_mock else "REAL",
                    "is_mock": is_mock,
                    "account_masked": mask_account_no(client.account_prefix, client.account_suffix),
                    "is_parking_season": is_parking_season,
                    "source": "KIS_LIVE",
                    "cash": round(cash, 0),
                    "stock_value": round(stock_value, 0),
                    "total_equity": round(total_equity, 0),
                    "return_pct": round(((total_equity / initial_capital) - 1.0) * 100.0, 2)
                    if initial_capital > 0
                    else 0.0,
                    "positions_count": len(positions_list),
                    "total_orders_count": total_orders_count,
                    "positions": positions_list,
                    "positions_df": pd.DataFrame(positions_list),
                }
        except Exception as exc:
            logger.info("KIS 실시간 잔고 조회 실패 (SQLite 오프라인 폴백 전환): %s", exc)

    # 2. 오프라인 폴백: SQLite orders + daily_prices 기반 포지션 재구성
    cash = float(initial_capital)
    holdings_qty: dict[str, int] = {}
    holdings_cost: dict[str, float] = {}
    last_order_price: dict[str, float] = {}

    if not orders_df.empty:
        exec_df = orders_df[
            orders_df["status"].astype(str).str.upper().isin(EXECUTED_STATUSES)
        ].copy()
        for _, row in exec_df.iterrows():
            ticker = str(row["ticker"]).strip()
            side = str(row["side"]).strip().upper()
            qty = _effective_order_qty(row)
            price = float(row.get("price") or 0.0)
            if qty <= 0 or price <= 0:
                continue

            last_order_price[ticker] = price
            if side == "BUY":
                prev_qty = holdings_qty.get(ticker, 0)
                prev_cost = holdings_cost.get(ticker, 0.0)
                holdings_qty[ticker] = prev_qty + qty
                holdings_cost[ticker] = prev_cost + (qty * price)
                cash -= qty * price
            elif side == "SELL":
                prev_qty = holdings_qty.get(ticker, 0)
                prev_cost = holdings_cost.get(ticker, 0.0)
                avg_cost = (prev_cost / prev_qty) if prev_qty > 0 else price
                new_qty = max(0, prev_qty - qty)
                holdings_qty[ticker] = new_qty
                holdings_cost[ticker] = new_qty * avg_cost
                cash += qty * price

    active_tickers = [t for t, q in holdings_qty.items() if q > 0]
    latest_prices = _get_latest_prices_map(store, active_tickers)

    positions_list = []
    stock_value = 0.0
    for ticker in active_tickers:
        qty = holdings_qty[ticker]
        avg_price = (
            holdings_cost[ticker] / qty if qty > 0 else last_order_price.get(ticker, 0.0)
        )
        cur_price = latest_prices.get(ticker) or last_order_price.get(ticker, avg_price)
        eval_amt = float(qty * cur_price)
        stock_value += eval_amt
        ret_pct = ((cur_price / avg_price) - 1.0) * 100.0 if avg_price > 0 else 0.0
        positions_list.append(
            {
                "ticker": ticker,
                "name": name_map.get(ticker, ticker),
                "qty": int(qty),
                "avg_price": round(float(avg_price), 0),
                "current_price": round(float(cur_price), 0),
                "eval_amount": round(eval_amt, 0),
                "return_pct": round(ret_pct, 2),
                "weight_pct": 0.0,
            }
        )

    total_equity = cash + stock_value
    for item in positions_list:
        item["weight_pct"] = (
            round((item["eval_amount"] / total_equity) * 100.0, 2)
            if total_equity > 0
            else 0.0
        )

    positions_list.sort(key=lambda x: x["eval_amount"], reverse=True)
    return {
        "kis_mode": "MOCK" if is_mock else "REAL",
        "is_mock": is_mock,
        "account_masked": masked_acc,
        "is_parking_season": is_parking_season,
        "source": "SQLITE_FALLBACK",
        "cash": round(cash, 0),
        "stock_value": round(stock_value, 0),
        "total_equity": round(total_equity, 0),
        "return_pct": round(((total_equity / initial_capital) - 1.0) * 100.0, 2)
        if initial_capital > 0
        else 0.0,
        "positions_count": len(positions_list),
        "total_orders_count": total_orders_count,
        "positions": positions_list,
        "positions_df": pd.DataFrame(positions_list),
    }


def build_account_equity_curve(
    db_path: str | Path = "data/quant_ko.db",
    initial_capital: float = 10_000_000.0,
) -> pd.DataFrame:
    """실제 계좌의 일별 전체 자산 변화 추이(예수금, 주식평가액, 총자산, 수익률)를 계산합니다.

    첫 유효 주문일(`orders`)부터 DB 내 최신 영업일(`daily_prices`)까지
    일별 보유 수량과 종가를 추적하여 자산 추이 시계열 DataFrame을 생성합니다.

    Args:
        db_path: SQLite 데이터베이스 파일 경로.
        initial_capital: 초기 투자 원금(원).

    Returns:
        컬럼 `['date', 'cash', 'stock_value', 'total_equity', 'return_pct']`를 가진 DataFrame.
    """
    columns = ["date", "cash", "stock_value", "total_equity", "return_pct"]
    store = DataStore(db_path)

    try:
        orders_df = store.get_orders()
    except Exception:
        orders_df = pd.DataFrame()

    exec_orders = pd.DataFrame()
    if not orders_df.empty:
        exec_orders = orders_df[
            orders_df["status"].astype(str).str.upper().isin(EXECUTED_STATUSES)
        ].copy()

    if exec_orders.empty:
        try:
            days = store.get_trading_days()
        except Exception:
            days = []
        if not days:
            return pd.DataFrame(columns=columns)
        recent_days = days[-20:]
        return pd.DataFrame(
            [
                {
                    "date": normalize_date(d),
                    "cash": float(initial_capital),
                    "stock_value": 0.0,
                    "total_equity": float(initial_capital),
                    "return_pct": 0.0,
                }
                for d in recent_days
            ],
            columns=columns,
        )

    exec_orders["norm_date"] = exec_orders["rebalance_date"].apply(
        lambda d: normalize_date(str(d))
    )
    first_date = str(exec_orders["norm_date"].min())

    try:
        trading_days = [normalize_date(d) for d in store.get_trading_days(start_date=first_date)]
    except Exception:
        trading_days = []

    order_dates = sorted(exec_orders["norm_date"].unique().tolist())
    all_dates = sorted(set(trading_days).union(order_dates))
    if not all_dates:
        return pd.DataFrame(columns=columns)

    involved_tickers = exec_orders["ticker"].astype(str).str.strip().unique().tolist()
    price_lookup: dict[tuple[str, str], float] = {}
    if involved_tickers:
        try:
            placeholders = ",".join("?" for _ in involved_tickers)
            query = f"""
                SELECT ticker, date, close
                FROM daily_prices
                WHERE ticker IN ({placeholders}) AND date >= ?
                ORDER BY date ASC
            """
            with store.get_connection() as conn:
                p_df = pd.read_sql_query(query, conn, params=[*involved_tickers, first_date])
            for _, r in p_df.iterrows():
                t = str(r["ticker"]).strip()
                d = normalize_date(str(r["date"]))
                c = float(r["close"] or 0.0)
                if c > 0:
                    price_lookup[(d, t)] = c
        except Exception as exc:
            logger.warning("일별 종가 시계열 조회 실패: %s", exc)

    cash = float(initial_capital)
    holdings: dict[str, int] = {}
    last_known_price: dict[str, float] = {}
    records: list[dict[str, Any]] = []

    orders_by_date: dict[str, pd.DataFrame] = {
        str(d): grp for d, grp in exec_orders.groupby("norm_date")
    }

    for cur_date in all_dates:
        if cur_date in orders_by_date:
            for _, row in orders_by_date[cur_date].iterrows():
                ticker = str(row["ticker"]).strip()
                side = str(row["side"]).strip().upper()
                qty = _effective_order_qty(row)
                price = float(row.get("price") or 0.0)
                if qty <= 0 or price <= 0:
                    continue

                last_known_price[ticker] = price
                if side == "BUY":
                    cash -= qty * price
                    holdings[ticker] = holdings.get(ticker, 0) + qty
                elif side == "SELL":
                    cash += qty * price
                    holdings[ticker] = max(0, holdings.get(ticker, 0) - qty)

        for ticker in list(holdings.keys()):
            if (cur_date, ticker) in price_lookup:
                last_known_price[ticker] = price_lookup[(cur_date, ticker)]

        stock_val = sum(
            qty * last_known_price.get(t, 0.0) for t, qty in holdings.items() if qty > 0
        )
        tot_eq = cash + stock_val
        ret_pct = (
            ((tot_eq / initial_capital) - 1.0) * 100.0 if initial_capital > 0 else 0.0
        )

        records.append(
            {
                "date": cur_date,
                "cash": round(cash, 2),
                "stock_value": round(stock_val, 2),
                "total_equity": round(tot_eq, 2),
                "return_pct": round(ret_pct, 2),
            }
        )

    return pd.DataFrame(records, columns=columns)


def load_actual_trade_logs(
    db_path: str | Path = "data/quant_ko.db",
    mode_filter: str = "ALL",
    side_filter: str = "ALL",
    status_filter: str = "ALL",
) -> pd.DataFrame:
    """SQLite `orders` 테이블에서 실제 거래(주문) 기록을 조회하고 필터링합니다.

    Args:
        db_path: SQLite 데이터베이스 파일 경로.
        mode_filter: 운용 환경 필터 ('ALL', 'MOCK', 'REAL').
        side_filter: 매매 구분 필터 ('ALL', 'BUY', 'SELL').
        status_filter: 주문 상태 필터 ('ALL', 'FILLED', 'ORDERED', 'FAILED', 'DRY_RUN').

    Returns:
        한글 컬럼명(`주문일시`, `환경(모의/실전)`, `종목코드`, `종목명`, `매매구분`,
        `주문수량`, `주문단가`, `체결수량`, `상태`)으로 포맷팅된 DataFrame.
    """
    display_cols = [
        "주문일시",
        "환경(모의/실전)",
        "종목코드",
        "종목명",
        "매매구분",
        "주문수량",
        "주문단가",
        "체결수량",
        "상태",
    ]
    store = DataStore(db_path)
    try:
        orders_df = store.get_orders()
    except Exception:
        return pd.DataFrame(columns=display_cols)

    if orders_df.empty:
        return pd.DataFrame(columns=display_cols)

    df = orders_df.copy()
    df["env_norm"] = df["env"].astype(str).str.strip().str.upper()
    df["side_norm"] = df["side"].astype(str).str.strip().str.upper()
    df["status_norm"] = df["status"].astype(str).str.strip().str.upper()

    # 1. 운용 환경 필터
    m_filter = str(mode_filter or "ALL").strip().upper()
    if m_filter in ("MOCK", "모의", "모의투자"):
        df = df[df["env_norm"] == "MOCK"]
    elif m_filter in ("REAL", "실전", "실전투자"):
        df = df[df["env_norm"] == "REAL"]

    # 2. 매매 구분 필터
    s_filter = str(side_filter or "ALL").strip().upper()
    if s_filter in ("BUY", "매수"):
        df = df[df["side_norm"] == "BUY"]
    elif s_filter in ("SELL", "매도"):
        df = df[df["side_norm"] == "SELL"]

    # 3. 체결 상태 필터
    st_filter = str(status_filter or "ALL").strip().upper()
    if st_filter != "ALL":
        df = df[df["status_norm"] == st_filter]

    if df.empty:
        return pd.DataFrame(columns=display_cols)

    name_map = _load_company_name_map(store)
    df = df.sort_values("id", ascending=False).reset_index(drop=True)

    formatted = pd.DataFrame(
        {
            "주문일시": df["rebalance_date"].astype(str),
            "환경(모의/실전)": df["env_norm"].map(
                lambda x: "MOCK (모의)" if x == "MOCK" else ("REAL (실전)" if x == "REAL" else x)
            ),
            "종목코드": df["ticker"].astype(str),
            "종목명": df["ticker"].astype(str).map(lambda t: name_map.get(t, t)),
            "매매구분": df["side_norm"],
            "주문수량": df["qty"].fillna(0).astype(int),
            "주문단가": df["price"].fillna(0.0).astype(float),
            "체결수량": df["filled_qty"].fillna(0).astype(int),
            "상태": df["status_norm"],
        }
    )
    return formatted[display_cols]


def load_top20_preview(
    db_path: str | Path = "data/quant_ko.db",
    top_n: int = 20,
    as_of_date: str | None = None,
) -> tuple[str, int, pd.DataFrame]:
    """최신 거래일 기준 유니버스 통과 종목 수와 9대 팩터 상위 20종목을 산출합니다.

    Args:
        db_path: SQLite 데이터베이스 파일 경로.
        top_n: 선정할 목표 종목 수 (기본값 20).
        as_of_date: 기준 일자 (미지정 시 DB 내 최신 거래일 자동 사용).

    Returns:
        `(latest_date, universe_count, top20_df)` 튜플.
    """
    store = DataStore(db_path)
    try:
        trading_days = store.get_trading_days()
    except Exception:
        trading_days = []

    if not trading_days and not as_of_date:
        return ("-", 0, pd.DataFrame())

    target_date = normalize_date(as_of_date) if as_of_date else normalize_date(trading_days[-1])

    universe_df = filter_universe(
        store=store,
        as_of_date=target_date,
        min_trading_value=0.0,
        market_cap_quantile=0.20,
        max_debt_ratio=None,
        require_quarter_profit=False,
    )
    if universe_df.empty:
        return (target_date, 0, pd.DataFrame())

    universe_count = len(universe_df)
    selected_df = score_and_select(universe_df, top_n=top_n)
    if selected_df.empty:
        return (target_date, universe_count, pd.DataFrame())

    out = selected_df.copy()
    out["순위"] = range(1, len(out) + 1)
    out["종목코드"] = out["ticker"].astype(str)
    out["종목명"] = out["name"].astype(str)
    out["시가총액(억)"] = (out["market_cap"].astype(float) / 1e8).round(1)
    out["PER"] = out["per"].astype(float).round(2)
    out["PSR"] = out["psr"].astype(float).round(2)
    out["POR"] = out["por"].astype(float).round(2)
    out["PGPR"] = out["pgpr"].astype(float).round(2)
    out["부채비율(%)"] = out["debt_ratio"].astype(float).round(1)
    out["Total Rank"] = out["total_rank"].astype(int)

    return (target_date, universe_count, out)


def get_db_status_summary(db_path: str | Path = "data/quant_ko.db") -> dict[str, Any]:
    """대시보드 시스템 상태 탭에 표시할 DB 적재 현황 요약 정보를 반환합니다."""
    store = DataStore(db_path)
    summary: dict[str, Any] = {
        "latest_date": "-",
        "trading_days_count": 0,
        "companies_count": 0,
        "daily_prices_count": 0,
        "financials_count": 0,
        "orders_count": 0,
    }
    try:
        with store.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(date), COUNT(DISTINCT date), COUNT(*) FROM daily_prices")
            row = cur.fetchone()
            if row:
                summary["latest_date"] = str(row[0] or "-")
                summary["trading_days_count"] = int(row[1] or 0)
                summary["daily_prices_count"] = int(row[2] or 0)

            cur.execute("SELECT COUNT(*) FROM companies")
            c_row = cur.fetchone()
            summary["companies_count"] = int(c_row[0] or 0) if c_row else 0

            cur.execute("SELECT COUNT(*) FROM financials")
            f_row = cur.fetchone()
            summary["financials_count"] = int(f_row[0] or 0) if f_row else 0

            cur.execute("SELECT COUNT(*) FROM orders")
            o_row = cur.fetchone()
            summary["orders_count"] = int(o_row[0] or 0) if o_row else 0
    except Exception as exc:
        logger.warning("DB 상태 요약 조회 실패: %s", exc)

    return summary
