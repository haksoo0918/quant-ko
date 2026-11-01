"""데이터 수집 파이프라인 및 CLI 실행 모듈.

KRX 포털, FinanceDataReader, OpenDART API로부터 상장 종목, 일별 시세,
재무제표 데이터를 수집하고 정제하여 SQLite DataStore에 적재합니다.
"""

import datetime
import logging
import time
from collections.abc import Sequence
from typing import Any

import pandas as pd

from quant_ko.data.dart import DartClient
from quant_ko.data.krx import (
    KrxClient,
    clean_price_val,
    is_chinese_company,
    is_holding_or_financial,
    is_preferred_stock,
    is_spac,
    normalize_date,
)
from quant_ko.data.store import DataStore

logger = logging.getLogger(__name__)


class DataCollector:
    """KRX 상장종목, 일별 주가 시세, OpenDART 분기 재무제표 수집 오케스트레이터."""

    def __init__(
        self,
        store: DataStore,
        dart_client: DartClient | None = None,
        krx_client: KrxClient | None = None,
        rate_limit_delay: float = 0.0,
    ) -> None:
        self.store = store
        self.dart_client = dart_client
        self.krx_client = krx_client
        self.rate_limit_delay = rate_limit_delay

    def collect_companies(
        self,
        market: str = "ALL",
        include_delisted: bool = True,
    ) -> int:
        """KRX 상장 기업(및 상장폐지 기업)을 수집하고, 제외 대상 플래그 태깅 및 DART corp_code를 매핑하여 DB에 적재합니다."""
        dfs: list[pd.DataFrame] = []

        if self.krx_client is not None:
            active_df = self.krx_client.fetch_ticker_list(market=market)
            if not active_df.empty:
                dfs.append(active_df)
            if include_delisted:
                try:
                    delisted_df = self.krx_client.fetch_delisted_tickers()
                    if not delisted_df.empty:
                        dfs.append(delisted_df)
                except Exception as exc:
                    logger.warning("Failed to fetch delisted tickers: %s", exc)
        else:
            # FinanceDataReader 대체 수집
            try:
                import FinanceDataReader as fdr

                fdr_df = fdr.StockListing("KRX")
                if not fdr_df.empty:
                    renamed = pd.DataFrame()
                    renamed["ticker"] = fdr_df["Code"].astype(str).str.zfill(6)
                    renamed["name"] = fdr_df["Name"]
                    renamed["market"] = fdr_df.get("Market", "KRX")
                    renamed["sector"] = fdr_df.get("Dept", "")
                    dfs.append(renamed)
            except Exception as exc:
                logger.warning("Failed to fetch companies via FinanceDataReader: %s", exc)

        if not dfs:
            return 0

        combined = pd.concat(dfs, ignore_index=True)
        combined = combined.drop_duplicates(subset=["ticker"], keep="last")

        # 필수 컬럼 존재 보장 및 우선주/스팩 여부 산출
        if "is_preferred" not in combined.columns:
            combined["is_preferred"] = combined.apply(
                lambda r: 1 if is_preferred_stock(str(r["ticker"]), str(r.get("name", ""))) else 0,
                axis=1,
            )
        else:
            # 누락되거나 비어있는 경우 재산출
            combined["is_preferred"] = combined.apply(
                lambda r: (
                    1
                    if bool(r["is_preferred"])
                    or is_preferred_stock(str(r["ticker"]), str(r.get("name", "")))
                    else 0
                ),
                axis=1,
            )

        if "is_spac" not in combined.columns:
            combined["is_spac"] = combined.apply(
                lambda r: 1 if is_spac(str(r.get("name", "")), str(r["ticker"])) else 0,
                axis=1,
            )
        else:
            combined["is_spac"] = combined.apply(
                lambda r: (
                    1
                    if bool(r["is_spac"]) or is_spac(str(r.get("name", "")), str(r["ticker"]))
                    else 0
                ),
                axis=1,
            )

        # DartClient가 제공된 경우 OpenDART 8자리 corp_code 매핑
        if self.dart_client is not None:
            try:
                ticker_to_corp = self.dart_client.get_ticker_to_corp_code(only_listed=False)
                if "corp_code" not in combined.columns:
                    combined["corp_code"] = combined["ticker"].map(ticker_to_corp)
                else:
                    combined["corp_code"] = (
                        combined["ticker"].map(ticker_to_corp).fillna(combined["corp_code"])
                    )
            except Exception as exc:
                logger.warning("Failed to map corp_codes via DartClient: %s", exc)

        self.store.upsert_companies(combined)
        return len(combined)

    def collect_financials(
        self,
        corp_codes: list[str],
        start_year: int,
        end_year: int,
        quarters: Sequence[int] = (1, 2, 3, 4),
        fs_types: tuple[str, ...] = ("CFS", "OFS"),
    ) -> int:
        """분기 및 사업보고서 재무제표를 체크포인트 기반으로 수집하고 저장합니다 (기수집 건 건너뛰기 지원)."""
        if self.dart_client is None:
            logger.warning("DartClient not configured; skipping financials collection.")
            return 0

        saved_count = 0
        total_targets = len(corp_codes) * (end_year - start_year + 1) * len(quarters)
        processed = 0

        for corp_code in corp_codes:
            if not corp_code:
                continue
            for year in range(start_year, end_year + 1):
                for qtr in quarters:
                    processed += 1
                    # 이미 저장소에 존재하는지 확인
                    existing = self.store.get_financials(
                        corp_code=corp_code,
                        fiscal_year=year,
                        quarter=qtr,
                    )
                    if not existing.empty:
                        logger.debug(
                            "Skipping already stored financials: corp=%s year=%s q=%s",
                            corp_code,
                            year,
                            qtr,
                        )
                        continue

                    # 연결재무제표(CFS) 우선 시도 후 별도재무제표(OFS) 대체 시도
                    data = None
                    for fs_type in fs_types:
                        try:
                            data = self.dart_client.fetch_and_parse_financials(
                                corp_code=corp_code,
                                fiscal_year=year,
                                quarter=qtr,
                                fs_type=fs_type,
                            )
                        except Exception as exc:
                            logger.warning(
                                "Error fetching financials for corp=%s year=%s q=%s fs=%s: %s",
                                corp_code,
                                year,
                                qtr,
                                fs_type,
                                exc,
                            )
                        if data is not None:
                            break

                    if data is not None:
                        self.store.upsert_financials([data])
                        saved_count += 1
                        logger.info(
                            "Saved financials: corp=%s year=%s q=%s (%d/%d)",
                            corp_code,
                            year,
                            qtr,
                            saved_count,
                            total_targets,
                        )

                    if self.rate_limit_delay > 0:
                        time.sleep(self.rate_limit_delay)

        return saved_count

    def collect_daily_prices(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        price_source_fn: Any = None,
    ) -> int:
        """종목별 일별 주가 시세(종가, 거래대금, 시가총액)를 체크포인트 기반으로 수집하여 저장합니다."""
        norm_start = normalize_date(start_date)
        norm_end = normalize_date(end_date)
        total_saved = 0

        for ticker in tickers:
            ticker_str = str(ticker).strip()
            if not ticker_str:
                continue

            existing = self.store.get_daily_prices(
                ticker=ticker_str,
                start_date=norm_start,
                end_date=norm_end,
            )

            fetch_start = norm_start
            if not existing.empty:
                max_date = existing["date"].max()
                if max_date >= norm_end:
                    logger.debug("Skipping %s: already collected up to %s", ticker_str, max_date)
                    continue
                next_day_dt = pd.Timestamp(max_date) + datetime.timedelta(days=1)
                fetch_start = next_day_dt.strftime("%Y-%m-%d")

            if fetch_start > norm_end:
                continue

            try:
                if price_source_fn is not None:
                    df = price_source_fn(ticker_str, fetch_start, norm_end)
                else:
                    import FinanceDataReader as fdr

                    df = fdr.DataReader(ticker_str, fetch_start, norm_end)
            except Exception as exc:
                logger.warning(
                    "Error fetching prices for %s (%s to %s): %s",
                    ticker_str,
                    fetch_start,
                    norm_end,
                    exc,
                )
                continue

            if df is None or df.empty:
                continue

            records: list[dict[str, Any]] = []
            for dt, row in df.iterrows():
                date_str = pd.to_datetime(dt).strftime("%Y-%m-%d")
                close = clean_price_val(row.get("Close"))
                volume = clean_price_val(row.get("Volume"))
                trading_value = clean_price_val(
                    row.get("Amount", row.get("trading_value", volume * close))
                )
                market_cap = clean_price_val(row.get("MarCap", row.get("market_cap", 0.0)))
                if market_cap <= 0 and close > 0:
                    market_cap = clean_price_val(row.get("MarketCap", 0.0))

                records.append(
                    {
                        "ticker": ticker_str,
                        "date": date_str,
                        "close": close,
                        "market_cap": market_cap,
                        "trading_value": trading_value,
                    }
                )

            if records:
                self.store.upsert_daily_prices(records)
                total_saved += len(records)
                logger.debug("Saved %d price rows for %s", len(records), ticker_str)

            if self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)

        return total_saved

    def collect_benchmark_prices(
        self,
        benchmark_ticker: str = "KQ11",
        start_date: str = "2016-01-01",
        end_date: str | None = None,
        price_source_fn: Any = None,
    ) -> int:
        """벤치마크 지수(기본값: 코스닥 지수 KQ11)의 일별 종가 시세를 수집합니다."""
        if end_date is None:
            end_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        return self.collect_daily_prices(
            tickers=[benchmark_ticker],
            start_date=start_date,
            end_date=end_date,
            price_source_fn=price_source_fn,
        )

    def identify_small_cap_pool(
        self,
        as_of_date: str | None = None,
        quantile: float = 0.20,
    ) -> list[str]:
        """전략 제외 필터를 통과한 보통주 중 시가총액 하위 분위(기본: 하위 20%) 소형주 풀을 추출합니다."""
        companies_df = self.store.get_companies()
        if companies_df.empty:
            return []

        norm_date = normalize_date(as_of_date) if as_of_date else None

        valid_rows: list[dict[str, Any]] = []
        for _, row in companies_df.iterrows():
            ticker = str(row["ticker"]).strip()
            name = str(row.get("name") or "").strip()
            sector = str(row.get("sector") or "").strip()

            # 제외 조건 점검
            if row.get("is_preferred") == 1 or is_preferred_stock(ticker, name):
                continue
            if row.get("is_spac") == 1 or is_spac(name, ticker):
                continue
            if is_chinese_company(name, ticker):
                continue
            if is_holding_or_financial(sector, name):
                continue

            if any(kw in sector for kw in ("관리종목", "환기종목", "외국기업")):
                continue

            market_val = str(row.get("market") or "").strip().upper()
            if market_val == "KONEX":
                continue
            if market_val not in ("KOSPI", "KOSDAQ", "STK", "KSQ"):
                continue

            fiscal_month = row.get("fiscal_month")
            if fiscal_month is not None and fiscal_month != 12:
                continue

            if norm_date:
                delisted_at = row.get("delisted_at")
                if delisted_at and normalize_date(delisted_at) <= norm_date:
                    continue
                listed_at = row.get("listed_at")
                if listed_at and normalize_date(listed_at) > norm_date:
                    continue

            valid_rows.append(row.to_dict())

        if not valid_rows:
            return []

        valid_df = pd.DataFrame(valid_rows)

        # 시가총액 확인을 위한 일별 시세 조회
        price_df = self.store.get_daily_prices(end_date=norm_date)
        if price_df.empty:
            return []

        # 종목별 최신 시가총액 추출
        latest_caps: list[dict[str, Any]] = []
        for ticker, group in price_df.groupby("ticker"):
            sorted_group = group.sort_values("date", ascending=True)
            last_row = sorted_group.iloc[-1]
            latest_caps.append({"ticker": ticker, "market_cap": last_row["market_cap"]})

        cap_df = pd.DataFrame(latest_caps)
        merged = pd.merge(valid_df[["ticker"]], cap_df, on="ticker", how="inner")
        if merged.empty:
            return []

        merged = merged.sort_values("market_cap", ascending=True)
        if quantile < 1.0:
            cutoff = merged["market_cap"].quantile(quantile)
            merged = merged[merged["market_cap"] <= cutoff]

        return merged["ticker"].tolist()

    def run_collection(
        self,
        start_year: int = 2020,
        end_year: int = 2024,
        as_of_date: str | None = None,
        quantile: float = 0.20,
        benchmark_ticker: str = "KQ11",
        price_start_date: str | None = None,
        price_end_date: str | None = None,
        price_source_fn: Any = None,
    ) -> dict[str, Any]:
        """전체 데이터 수집 파이프라인(상장종목 -> 벤치마크 시세 -> 소형주 풀 식별 -> 일별 주가 -> DART 재무제표)을 순차 실행합니다."""
        logger.info(
            "Starting data collection pipeline: years %d-%d, quantile=%.2f",
            start_year,
            end_year,
            quantile,
        )

        # 1. 전체 상장 기업 수집 및 제외 태깅
        companies_count = self.collect_companies()

        # 수집 기간 기본값 설정
        if price_start_date is None:
            price_start_date = f"{start_year}-01-01"
        if price_end_date is None:
            price_end_date = f"{end_year}-12-31"

        # 2. 벤치마크 지수 시세 수집
        benchmark_prices_count = self.collect_benchmark_prices(
            benchmark_ticker=benchmark_ticker,
            start_date=price_start_date,
            end_date=price_end_date,
            price_source_fn=price_source_fn,
        )

        # 3. 시가총액 하위 분위 소형주 타깃 풀 추출
        small_cap_tickers = self.identify_small_cap_pool(
            as_of_date=as_of_date,
            quantile=quantile,
        )
        logger.info("Identified %d small-cap target tickers", len(small_cap_tickers))

        # 4. 타깃 종목 일별 주가 시세 수집
        target_prices_count = self.collect_daily_prices(
            tickers=small_cap_tickers,
            start_date=price_start_date,
            end_date=price_end_date,
            price_source_fn=price_source_fn,
        )

        # 5. 타깃 종목 DART 재무제표 수집
        financials_count = 0
        if small_cap_tickers and self.dart_client is not None:
            comp_df = self.store.get_companies(tickers=small_cap_tickers)
            corp_codes = [
                c for c in comp_df["corp_code"].dropna().unique().tolist() if str(c).strip()
            ]
            financials_count = self.collect_financials(
                corp_codes=corp_codes,
                start_year=start_year,
                end_year=end_year,
            )

        summary = {
            "companies_count": companies_count,
            "small_cap_count": len(small_cap_tickers),
            "small_cap_tickers": small_cap_tickers,
            "benchmark_prices_count": benchmark_prices_count,
            "target_prices_count": target_prices_count,
            "financials_count": financials_count,
        }
        logger.info("Pipeline completed: %s", summary)
        return summary


def main(argv: list[str] | None = None) -> int:
    """데이터 수집 파이프라인 명령줄 인터페이스(CLI) 진입점."""
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Run quant-ko data ingestion pipeline for KRX companies, prices, and DART financials."
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2020,
        help="Start year for financials and price history (default: 2020)",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2024,
        help="End year for financials and price history (default: 2024)",
    )
    parser.add_argument(
        "--quantile",
        type=float,
        default=0.20,
        help="Market cap quantile cutoff for small caps (default: 0.20)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="quant_ko.db",
        help="Path to SQLite database file (default: quant_ko.db)",
    )
    parser.add_argument(
        "--dart-api-key",
        type=str,
        default=None,
        help="OpenDART API Key (or set DART_API_KEY env)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=0.1,
        help="Rate limit delay in seconds between API calls (default: 0.1)",
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default="KQ11",
        help="Benchmark ticker (default: KQ11 for KOSDAQ)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    dart_key = args.dart_api_key or os.getenv("DART_API_KEY")
    dart_client = DartClient(api_key=dart_key) if dart_key else None
    krx_client = KrxClient()

    store = DataStore(db_path=args.db_path)
    store.initialize_schema()

    collector = DataCollector(
        store=store,
        dart_client=dart_client,
        krx_client=krx_client,
        rate_limit_delay=args.rate_limit,
    )

    try:
        summary = collector.run_collection(
            start_year=args.start_year,
            end_year=args.end_year,
            quantile=args.quantile,
            benchmark_ticker=args.benchmark,
        )
        print("Data collection completed successfully!")
        for k, v in summary.items():
            if k == "small_cap_tickers":
                print(f"  {k}: {len(v)} stocks")
            else:
                print(f"  {k}: {v}")
        return 0
    except Exception as exc:
        logger.exception("Data collection failed: %s", exc)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    import sys

    sys.exit(main())
