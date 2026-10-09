import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

print("=" * 50)
print(" 1. SQLite DB (data/quant_ko.db) 검증")
print("=" * 50)
db_path = "data/quant_ko.db"
if os.path.exists(db_path):
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"DB 파일 정상 존재: {db_path} ({size_mb:.2f} MB)")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in tables:
        cnt = cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  - [{t}] 테이블: {cnt:,} 행 적재됨")
    
    latest_p = cur.execute("SELECT max(date) FROM daily_prices").fetchone()[0]
    first_p = cur.execute("SELECT min(date) FROM daily_prices").fetchone()[0]
    print(f"  - 일별 시세 기간: {first_p} ~ {latest_p}")
    conn.close()
else:
    print("경고: DB 파일이 존재하지 않습니다.")

print("\n" + "=" * 50)
print(" 2. 벤치마크 및 금리 CSV 검증")
print("=" * 50)
for f in ["data/cd_daily.csv", "data/kq11_daily.csv"]:
    if os.path.exists(f):
        df = pd.read_csv(f)
        print(f"  - {f}: 정상 ({len(df):,} 행, 최신일자: {df.iloc[-1, 0]})")
    else:
        print(f"  - {f}: 파일 없음")

print("\n" + "=" * 50)
print(" 3. .env 키 설정 검증")
print("=" * 50)
mode = os.getenv("KIS_MODE", "미설정")
print(f"운용 모드(KIS_MODE): {mode}")
real_key = os.getenv("KIS_REAL_APP_KEY") or os.getenv("KIS_APP_KEY")
real_cano = os.getenv("KIS_REAL_CANO") or os.getenv("KIS_CANO")
mock_key = os.getenv("KIS_MOCK_APP_KEY")
mock_cano = os.getenv("KIS_MOCK_CANO")
dart_key = os.getenv("OPENDART_API_KEY")
webhook = os.getenv("DISCORD_WEBHOOK_URL")

print(f"실전 API 키: {'정상 등록됨' if real_key else '미등록'} (계좌: {real_cano[:4] + '****' if real_cano else '미입력'})")
print(f"모의 API 키: {'정상 등록됨' if mock_key else '미등록'} (계좌: {mock_cano[:4] + '****' if mock_cano else '미입력'})")
print(f"OpenDART 키: {'정상 등록됨' if dart_key else '미등록'}")
print(f"디스코드 웹훅: {'정상 등록됨' if webhook else '미등록'}")
print("=" * 50)
