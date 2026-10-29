import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    ticker TEXT PRIMARY KEY,
    corp_code TEXT,
    name TEXT,
    market TEXT,
    sector TEXT,
    listed_at TEXT,
    delisted_at TEXT,
    fiscal_month INTEGER DEFAULT 12,
    is_preferred INTEGER DEFAULT 0,
    is_spac INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_companies_corp_code ON companies(corp_code);

CREATE TABLE IF NOT EXISTS daily_prices (
    ticker TEXT,
    date TEXT,
    close REAL,
    market_cap REAL,
    trading_value REAL,
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_prices_date ON daily_prices(date);

CREATE TABLE IF NOT EXISTS financials (
    corp_code TEXT,
    fiscal_year INTEGER,
    quarter INTEGER,
    fs_type TEXT,
    revenue REAL,
    gross_profit REAL,
    op_income REAL,
    net_income_owner REAL,
    total_liabilities REAL,
    total_equity REAL,
    capital_stock REAL,
    rcept_dt TEXT,
    PRIMARY KEY (corp_code, fiscal_year, quarter, fs_type, rcept_dt)
);

CREATE INDEX IF NOT EXISTS idx_financials_lookup ON financials(corp_code, fiscal_year, quarter);
CREATE INDEX IF NOT EXISTS idx_financials_rcept_dt ON financials(rcept_dt);

CREATE TABLE IF NOT EXISTS designations (
    ticker TEXT,
    type TEXT,
    start_date TEXT,
    end_date TEXT,
    PRIMARY KEY (ticker, type, start_date)
);

CREATE INDEX IF NOT EXISTS idx_designations_ticker_date ON designations(ticker, start_date, end_date);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rebalance_date TEXT,
    ticker TEXT,
    side TEXT,
    qty INTEGER,
    price REAL,
    status TEXT,
    filled_qty INTEGER DEFAULT 0,
    env TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_rebalance ON orders(rebalance_date, env);
CREATE INDEX IF NOT EXISTS idx_orders_ticker ON orders(ticker);
"""


class DataStore:
    """Manages SQLite database connections and schemas."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._shared_memory_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._shared_memory_conn = sqlite3.connect(":memory:")

    def close(self) -> None:
        """Close database connection if open."""
        if self._shared_memory_conn is not None:
            try:
                self._shared_memory_conn.close()
            except Exception:
                pass
            self._shared_memory_conn = None

    def __enter__(self) -> "DataStore":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a transactional database connection context."""
        if self._shared_memory_conn is not None:
            yield self._shared_memory_conn
        else:
            conn = sqlite3.connect(self.db_path)
            try:
                yield conn
            finally:
                conn.close()

    def initialize_schema(self) -> None:
        """Create tables and indices if they do not exist."""
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def upsert_companies(self, records: list[dict[str, Any]] | pd.DataFrame) -> None:
        """Insert or replace company metadata."""
        if isinstance(records, pd.DataFrame):
            data = records.to_dict(orient="records")
        else:
            data = records

        if not data:
            return

        sql = """
        INSERT INTO companies (
            ticker, corp_code, name, market, sector, listed_at, delisted_at,
            fiscal_month, is_preferred, is_spac
        ) VALUES (
            :ticker, :corp_code, :name, :market, :sector, :listed_at, :delisted_at,
            COALESCE(:fiscal_month, 12), COALESCE(:is_preferred, 0), COALESCE(:is_spac, 0)
        )
        ON CONFLICT(ticker) DO UPDATE SET
            corp_code = COALESCE(excluded.corp_code, companies.corp_code),
            name = excluded.name,
            market = excluded.market,
            sector = excluded.sector,
            listed_at = excluded.listed_at,
            delisted_at = excluded.delisted_at,
            fiscal_month = excluded.fiscal_month,
            is_preferred = excluded.is_preferred,
            is_spac = excluded.is_spac
        """
        # Ensure default keys exist in all dicts
        normalized = []
        for r in data:
            row = dict(r)
            row.setdefault("corp_code", None)
            row.setdefault("name", "")
            row.setdefault("market", "")
            row.setdefault("sector", "")
            row.setdefault("listed_at", None)
            row.setdefault("delisted_at", None)
            row.setdefault("fiscal_month", 12)
            row.setdefault("is_preferred", 0)
            row.setdefault("is_spac", 0)
            normalized.append(row)

        with self.get_connection() as conn:
            conn.executemany(sql, normalized)
            conn.commit()

    def get_companies(self, tickers: list[str] | None = None) -> pd.DataFrame:
        """Retrieve companies matching ticker filter or all."""
        with self.get_connection() as conn:
            if tickers:
                placeholders = ",".join("?" for _ in tickers)
                query = f"SELECT * FROM companies WHERE ticker IN ({placeholders})"
                return pd.read_sql_query(query, conn, params=tickers)
            return pd.read_sql_query("SELECT * FROM companies", conn)

    def upsert_daily_prices(self, records: list[dict[str, Any]] | pd.DataFrame) -> None:
        """Insert or replace daily stock prices."""
        if isinstance(records, pd.DataFrame):
            data = records.to_dict(orient="records")
        else:
            data = records

        if not data:
            return

        sql = """
        INSERT INTO daily_prices (
            ticker, date, close, market_cap, trading_value
        ) VALUES (
            :ticker, :date, :close, :market_cap, :trading_value
        )
        ON CONFLICT(ticker, date) DO UPDATE SET
            close = excluded.close,
            market_cap = excluded.market_cap,
            trading_value = excluded.trading_value
        """
        with self.get_connection() as conn:
            conn.executemany(sql, data)
            conn.commit()

    def get_daily_prices(
        self,
        ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        """Retrieve daily prices with optional ticker and date range filters."""
        query = "SELECT * FROM daily_prices WHERE 1=1"
        params: list[Any] = []

        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY ticker, date"

        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def get_trading_days(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[str]:
        """Retrieve distinct trading days from daily_prices sorted ascending."""
        query = "SELECT DISTINCT date FROM daily_prices WHERE 1=1"
        params: list[Any] = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date ASC"

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [row[0] for row in cursor.fetchall()]

    def upsert_financials(self, records: list[dict[str, Any]] | pd.DataFrame) -> None:
        """Insert or replace quarterly/annual financial statement metrics."""
        if isinstance(records, pd.DataFrame):
            data = records.to_dict(orient="records")
        else:
            data = records

        if not data:
            return

        sql = """
        INSERT INTO financials (
            corp_code, fiscal_year, quarter, fs_type,
            revenue, gross_profit, op_income, net_income_owner,
            total_liabilities, total_equity, capital_stock, rcept_dt
        ) VALUES (
            :corp_code, :fiscal_year, :quarter, :fs_type,
            :revenue, :gross_profit, :op_income, :net_income_owner,
            :total_liabilities, :total_equity, :capital_stock, :rcept_dt
        )
        ON CONFLICT(corp_code, fiscal_year, quarter, fs_type, rcept_dt) DO UPDATE SET
            revenue = excluded.revenue,
            gross_profit = excluded.gross_profit,
            op_income = excluded.op_income,
            net_income_owner = excluded.net_income_owner,
            total_liabilities = excluded.total_liabilities,
            total_equity = excluded.total_equity,
            capital_stock = excluded.capital_stock
        """
        with self.get_connection() as conn:
            conn.executemany(sql, data)
            conn.commit()

    def get_financials(
        self,
        corp_code: str | None = None,
        fiscal_year: int | None = None,
        quarter: int | None = None,
        fs_type: str | None = None,
        before_rcept_dt: str | None = None,
    ) -> pd.DataFrame:
        """Query financial records with optional filters."""
        query = "SELECT * FROM financials WHERE 1=1"
        params: list[Any] = []

        if corp_code:
            query += " AND corp_code = ?"
            params.append(corp_code)
        if fiscal_year is not None:
            query += " AND fiscal_year = ?"
            params.append(fiscal_year)
        if quarter is not None:
            query += " AND quarter = ?"
            params.append(quarter)
        if fs_type:
            query += " AND fs_type = ?"
            params.append(fs_type)
        if before_rcept_dt:
            query += " AND rcept_dt <= ?"
            params.append(before_rcept_dt)

        query += " ORDER BY corp_code, fiscal_year, quarter, rcept_dt DESC"

        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def upsert_designations(self, records: list[dict[str, Any]] | pd.DataFrame) -> None:
        """Insert or replace special issue designations (관리종목, 투자주의환기종목, 거래정지)."""
        if isinstance(records, pd.DataFrame):
            data = records.to_dict(orient="records")
        else:
            data = records

        if not data:
            return

        sql = """
        INSERT INTO designations (
            ticker, type, start_date, end_date
        ) VALUES (
            :ticker, :type, :start_date, :end_date
        )
        ON CONFLICT(ticker, type, start_date) DO UPDATE SET
            end_date = excluded.end_date
        """
        with self.get_connection() as conn:
            conn.executemany(sql, data)
            conn.commit()

    def get_designations(
        self,
        ticker: str | None = None,
        as_of_date: str | None = None,
    ) -> pd.DataFrame:
        """Query designations with optional ticker and date filters."""
        query = "SELECT * FROM designations WHERE 1=1"
        params: list[Any] = []

        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        if as_of_date:
            query += " AND start_date <= ? AND (end_date IS NULL OR end_date >= ?)"
            params.extend([as_of_date, as_of_date])

        query += " ORDER BY ticker, start_date"

        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def insert_order(self, order: dict[str, Any]) -> int:
        """Insert a rebalance order record and return generated ID."""
        sql = """
        INSERT INTO orders (
            rebalance_date, ticker, side, qty, price, status, filled_qty, env
        ) VALUES (
            :rebalance_date, :ticker, :side, :qty, :price, :status,
            COALESCE(:filled_qty, 0), :env
        )
        """
        record = dict(order)
        record.setdefault("filled_qty", 0)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, record)
            conn.commit()
            return cursor.lastrowid or 0

    def update_order_status(
        self,
        order_id: int,
        status: str,
        filled_qty: int | None = None,
    ) -> None:
        """Update status and optionally filled_qty of an order."""
        if filled_qty is not None:
            sql = "UPDATE orders SET status = ?, filled_qty = ? WHERE id = ?"
            params = (status, filled_qty, order_id)
        else:
            sql = "UPDATE orders SET status = ? WHERE id = ?"
            params = (status, order_id)

        with self.get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    def get_orders(
        self,
        rebalance_date: str | None = None,
        env: str | None = None,
        status: str | None = None,
    ) -> pd.DataFrame:
        """Query orders by rebalance date, environment, and status."""
        query = "SELECT * FROM orders WHERE 1=1"
        params: list[Any] = []

        if rebalance_date:
            query += " AND rebalance_date = ?"
            params.append(rebalance_date)
        if env:
            query += " AND env = ?"
            params.append(env)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY id"

        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)


def apply_oci_db_patch_if_needed(
    store: DataStore,
    patch_path: str | Path | None = None,
    min_latest_date: str = "2026-10-23",
    min_financials_count: int = 25000,
) -> bool:
    """로컬 또는 오라클 서버 DB가 구버전일 경우 oci_db_patch.json.gz 스냅샷을 자동으로 1회 병합합니다.

    DB의 daily_prices 최신 거래일이 min_latest_date 미만이거나 financials 건수가
    min_financials_count 미만일 때만 압축 패치 파일을 읽어 upsert를 수행하며,
    이미 최신 상태인 경우 0.01초 이내에 즉시 False를 반환합니다.
    """
    import gzip
    import json
    import logging

    logger = logging.getLogger(__name__)
    if patch_path is None:
        patch_path = Path(__file__).resolve().parents[3] / "data" / "oci_db_patch.json.gz"
    else:
        patch_path = Path(patch_path)

    if not patch_path.exists():
        return False

    try:
        with store.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(date) FROM daily_prices")
            row_date = cur.fetchone()
            max_date = str(row_date[0] or "") if row_date else ""

            cur.execute("SELECT COUNT(*) FROM financials")
            row_fin = cur.fetchone()
            fin_count = int(row_fin[0] or 0) if row_fin else 0
    except Exception:
        store.initialize_schema()
        max_date = ""
        fin_count = 0

    if max_date >= min_latest_date and fin_count >= min_financials_count:
        return False

    logger.info(
        "Applying DB snapshot patch from %s (current max_date=%s, financials=%d)...",
        patch_path,
        max_date,
        fin_count,
    )
    with gzip.open(patch_path, "rt", encoding="utf-8") as f:
        payload = json.load(f)

    companies = payload.get("companies") or []
    financials = payload.get("financials") or []
    daily_prices = payload.get("daily_prices") or []

    if companies:
        store.upsert_companies(companies)
    if financials:
        store.upsert_financials(financials)
    if daily_prices:
        store.upsert_daily_prices(daily_prices)

    logger.info(
        "DB snapshot patch applied: companies=%d, financials=%d, daily_prices=%d",
        len(companies),
        len(financials),
        len(daily_prices),
    )
    return True
