"""로컬 SQLite DB(data/quant_ko.db)에서 오라클 서버 동기화용 경량 압축 패치(data/oci_db_patch.json.gz)를 추출합니다."""

import gzip
import json
import sqlite3
from pathlib import Path


def export_oci_db_patch(
    db_path: Path | None = None,
    out_path: Path | None = None,
    min_price_date: str = "2026-09-01",
) -> dict[str, int]:
    """companies, financials 전체 및 min_price_date 이후 daily_prices를 gzip JSON으로 내보냅니다."""
    root_dir = Path(__file__).resolve().parents[1]
    if db_path is None:
        db_path = root_dir / "data" / "quant_ko.db"
    if out_path is None:
        out_path = root_dir / "data" / "oci_db_patch.json.gz"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM companies")
        companies = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM financials")
        financials = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT * FROM daily_prices WHERE date >= ? ORDER BY date, ticker",
            (min_price_date,),
        )
        daily_prices = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    payload = {
        "companies": companies,
        "financials": financials,
        "daily_prices": daily_prices,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(
        f"Exported {out_path.name} ({size_mb:.2f} MB): "
        f"companies={len(companies)}, financials={len(financials)}, daily_prices={len(daily_prices)}"
    )
    return {
        "companies": len(companies),
        "financials": len(financials),
        "daily_prices": len(daily_prices),
    }


if __name__ == "__main__":
    export_oci_db_patch()
