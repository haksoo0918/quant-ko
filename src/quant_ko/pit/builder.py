"""Point-in-Time financial statement snapshot builder."""

from typing import Any

import pandas as pd

from quant_ko.data.store import DataStore


def _normalize_date_str(date_str: str) -> str:
    """Normalize date string to YYYYMMDD format without dashes."""
    return str(date_str).replace("-", "").strip()


INCOME_METRICS = ["revenue", "gross_profit", "op_income", "net_income_owner"]
BS_METRICS = ["total_liabilities", "total_equity", "capital_stock"]


class PITSnapshotBuilder:
    """Extracts Point-in-Time financial metrics without look-ahead bias."""

    def __init__(self, store: DataStore) -> None:
        self.store = store

    def _get_preferred_filings(
        self,
        corp_code: str,
        cutoff_dt: str,
    ) -> dict[tuple[int, int], dict[str, Any]]:
        """Get best filing per (fiscal_year, quarter) up to cutoff_dt.

        Prefers CFS over OFS, and chooses the latest amendment (highest rcept_dt).
        """
        df = self.store.get_financials(corp_code=corp_code, before_rcept_dt=cutoff_dt)
        if df.empty:
            return {}

        df = df[df["rcept_dt"].astype(str).str.replace("-", "") <= cutoff_dt]
        if df.empty:
            return {}

        filings: dict[tuple[int, int], dict[str, Any]] = {}
        for (f_year, qtr), group in df.groupby(["fiscal_year", "quarter"]):
            f_year_int = int(f_year)
            qtr_int = int(qtr)
            cfs = group[group["fs_type"] == "CFS"]
            if not cfs.empty:
                chosen = cfs.sort_values("rcept_dt", ascending=True).iloc[-1]
            else:
                chosen = group.sort_values("rcept_dt", ascending=True).iloc[-1]
            filings[(f_year_int, qtr_int)] = chosen.to_dict()

        return filings

    def _get_discrete_quarter_metrics(
        self,
        filings: dict[tuple[int, int], dict[str, Any]],
        fiscal_year: int,
        quarter: int,
    ) -> dict[str, float | None] | None:
        """Calculate discrete quarterly income metrics for (fiscal_year, quarter).

        For Q1, Q2, Q3: raw filing value.
        For Q4: Annual (Q4 report) - sum(Q1..Q3 discrete).
        """
        key = (fiscal_year, quarter)
        if key not in filings:
            return None

        filing = filings[key]
        discrete: dict[str, float | None] = {}

        if quarter in (1, 2, 3):
            for m in INCOME_METRICS:
                val = filing.get(m)
                discrete[m] = float(val) if val is not None else None
            return discrete

        # quarter == 4: Annual report
        for m in INCOME_METRICS:
            annual_val = filing.get(m)
            if annual_val is None:
                discrete[m] = None
                continue

            # Sum available Q1, Q2, Q3
            prior_sum = 0.0
            found_prior = False
            for q in (1, 2, 3):
                if (fiscal_year, q) in filings:
                    q_val = filings[(fiscal_year, q)].get(m)
                    if q_val is not None:
                        prior_sum += float(q_val)
                        found_prior = True

            if found_prior:
                discrete[m] = float(annual_val) - prior_sum
            else:
                discrete[m] = float(annual_val)

        return discrete

    def get_company_pit_financials(
        self,
        corp_code: str,
        as_of_date: str,
    ) -> dict[str, Any] | None:
        """Extract Point-in-Time financial record for a single company."""
        cutoff_dt = _normalize_date_str(as_of_date)
        filings = self._get_preferred_filings(corp_code, cutoff_dt)
        if not filings:
            return None

        # Determine latest available quarter
        sorted_keys = sorted(filings.keys(), key=lambda x: (x[0], x[1]))
        latest_year, latest_qtr = sorted_keys[-1]
        latest_filing = filings[(latest_year, latest_qtr)]

        # Discrete values for latest quarter
        latest_discrete = self._get_discrete_quarter_metrics(filings, latest_year, latest_qtr)
        if not latest_discrete:
            return None

        result: dict[str, Any] = {
            "corp_code": corp_code,
            "fiscal_year": latest_year,
            "quarter": latest_qtr,
            "rcept_dt": str(latest_filing.get("rcept_dt", "")),
            "fs_type": latest_filing.get("fs_type", ""),
        }

        # Latest quarter income metrics
        for m in INCOME_METRICS:
            val = latest_discrete.get(m)
            result[f"{m}_quarter"] = val
            result[m] = val

        # Calculate TTM (sum of latest 4 discrete quarters)
        # Determine 4 quarters list
        quarters_seq: list[tuple[int, int]] = []
        cur_y, cur_q = latest_year, latest_qtr
        for _ in range(4):
            quarters_seq.append((cur_y, cur_q))
            if cur_q > 1:
                cur_q -= 1
            else:
                cur_y -= 1
                cur_q = 4

        for m in INCOME_METRICS:
            ttm_vals = []
            for y, q in quarters_seq:
                disc = self._get_discrete_quarter_metrics(filings, y, q)
                if disc and disc.get(m) is not None:
                    ttm_vals.append(disc[m])
            if len(ttm_vals) == 4:
                result[f"{m}_ttm"] = sum(v for v in ttm_vals if v is not None)
            elif ttm_vals:
                result[f"{m}_ttm"] = sum(v for v in ttm_vals if v is not None)
            else:
                result[f"{m}_ttm"] = None

        # Calculate YoY (Latest quarter vs same quarter previous year)
        prev_discrete = self._get_discrete_quarter_metrics(filings, latest_year - 1, latest_qtr)

        for m in INCOME_METRICS:
            latest_val = latest_discrete.get(m)
            prev_val = prev_discrete.get(m) if prev_discrete else None

            if latest_val is not None and prev_val is not None:
                is_turnaround = bool(prev_val <= 0 and latest_val > 0)
                if abs(prev_val) > 0:
                    yoy = (latest_val - prev_val) / abs(prev_val)
                elif latest_val > 0:
                    yoy = float("inf")
                elif latest_val == 0:
                    yoy = 0.0
                else:
                    yoy = -1.0
                result[f"{m}_yoy"] = yoy
                result[f"{m}_turnaround"] = is_turnaround
            else:
                result[f"{m}_yoy"] = None
                result[f"{m}_turnaround"] = False

        # Balance sheet metrics (from latest available report)
        for bs in BS_METRICS:
            val = latest_filing.get(bs)
            result[bs] = float(val) if val is not None else None

        # Financial ratios
        total_equity = result.get("total_equity")
        total_liabilities = result.get("total_liabilities")
        capital_stock = result.get("capital_stock")

        if total_equity is not None and total_equity > 0:
            if total_liabilities is not None:
                result["debt_ratio"] = (total_liabilities / total_equity) * 100.0
            else:
                result["debt_ratio"] = 0.0
        elif total_equity is not None and total_equity <= 0:
            result["debt_ratio"] = float("inf")
        else:
            result["debt_ratio"] = None

        if capital_stock is not None and capital_stock > 0:
            if total_equity is not None:
                result["impairment_ratio"] = (
                    (capital_stock - total_equity) / capital_stock
                ) * 100.0
            else:
                result["impairment_ratio"] = 0.0
        else:
            result["impairment_ratio"] = 0.0

        return result

    def build_snapshot(
        self,
        as_of_date: str,
        corp_codes: list[str] | None = None,
    ) -> pd.DataFrame:
        """Build PIT financial snapshot for all companies or specified corp_codes."""
        cutoff_dt = _normalize_date_str(as_of_date)

        if corp_codes is None:
            # Query distinct corp_codes from financials table with rcept_dt <= cutoff_dt
            fin_df = self.store.get_financials(before_rcept_dt=cutoff_dt)
            if fin_df.empty:
                return pd.DataFrame()
            target_codes = fin_df["corp_code"].unique().tolist()
        else:
            target_codes = corp_codes

        rows: list[dict[str, Any]] = []
        for code in target_codes:
            snap = self.get_company_pit_financials(code, as_of_date)
            if snap:
                rows.append(snap)

        if not rows:
            return pd.DataFrame()

        df_snap = pd.DataFrame(rows)

        # Merge ticker from companies table if available
        companies_df = self.store.get_companies()
        if not companies_df.empty and "corp_code" in companies_df.columns:
            code_to_ticker = (
                companies_df.dropna(subset=["corp_code"])
                .drop_duplicates(subset=["corp_code"])
                .set_index("corp_code")["ticker"]
                .to_dict()
            )
            df_snap["ticker"] = df_snap["corp_code"].map(code_to_ticker)

        return df_snap
