import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quant_ko.dashboard.data_loader import (  # noqa: E402
    get_db_status_summary,
    load_account_and_positions,
    load_actual_trade_logs,
    load_cached_top20,
)

print("=== 1. DB STATUS SUMMARY ===")
summary = get_db_status_summary("data/quant_ko.db")
for k, v in summary.items():
    print(f"  {k}: {v}")

print("\n=== 2. LOAD ACCOUNT AND POSITIONS (fetch_live_kis=False) ===")
acc_offline = load_account_and_positions(db_path="data/quant_ko.db", fetch_live_kis=False)
for k, v in acc_offline.items():
    if k not in ["positions", "positions_df"]:
        print(f"  {k}: {v}")
print(f"  positions count: {len(acc_offline.get('positions', []))}")

print("\n=== 3. LOAD ACTUAL TRADE LOGS ===")
logs_df = load_actual_trade_logs(db_path="data/quant_ko.db")
print(f"  Trade logs rows: {len(logs_df)}")
if not logs_df.empty:
    print(logs_df.head(3))

print("\n=== 4. LOAD CACHED TOP 20 ===")
top_date, top_cnt, top_df = load_cached_top20(db_path="data/quant_ko.db")
print(f"  Top date: {top_date}, Count: {top_cnt}, DataFrame rows: {len(top_df)}")
if not top_df.empty:
    print(top_df.head(3))
