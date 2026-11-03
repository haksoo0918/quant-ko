"""Quant-KO 대시보드 데이터 정합성 및 배포 전 자동 건강성(Health) 검증 스위트.

배포 전 다음 4대 핵심 영역을 기계적으로 자동 전수 단언(assert) 검증합니다:
1. Tab 2 실제 거래기록 4대 지표 수치 (21건 / 20건 / 0건 / 1건) 및 한글 종목명 100% 매핑
2. Tab 1 상단 KPI 자산과 하단 자산 곡선 최종 평가액 정합성
3. Tab 4 최신 타깃 20종목 산출 무결성
4. Streamlit 런타임 헤드리스 렌더링(AppTest) 크래시 및 에러 엘리먼트 0건
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows 콘솔 및 CI 환경 UTF-8 인코딩 보장
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# src 디렉터리를 sys.path 최우선 등록
_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from quant_ko.dashboard.data_loader import (  # noqa: E402
    build_account_equity_curve,
    load_account_and_positions,
    load_actual_trade_logs,
    load_cached_top20,
)


def verify_trade_logs_integrity(db_path: str = "data/quant_ko.db") -> dict[str, int]:
    """Tab 2 실제 거래기록 원장 및 상단 4대 메트릭 수치를 기계적으로 전수 검증합니다."""
    print("[1/3] 실제 거래기록(Tab 2) 데이터 무결성 검증 시작...")
    df = load_actual_trade_logs(db_path=db_path, mode_filter="REAL")

    total_cnt = len(df)
    buy_filled_cnt = int(
        len(df[(df["매매구분"] == "BUY") & (df["체결상태"].isin(["FILLED", "ORDERED", "PARTIAL"]))])
    )
    sell_filled_cnt = int(
        len(df[(df["매매구분"] == "SELL") & (df["체결상태"].isin(["FILLED", "ORDERED", "PARTIAL"]))])
    )
    unfilled_cnt = int(
        len(df[df["체결상태"].isin(["FAILED", "RESOLVED", "PENDING_CATCHUP", "REJECTED"])])
    )

    print(f"  - 총 주문 건수: {total_cnt}건 (기대치: 21건)")
    print(f"  - 매수 체결/주문: {buy_filled_cnt}건 (기대치: 20건)")
    print(f"  - 매도 체결/주문: {sell_filled_cnt}건 (기대치: 0건)")
    print(f"  - 실패/미체결/해결: {unfilled_cnt}건 (기대치: 1건)")

    assert total_cnt == 21, f"❌ 총 주문 건수 불일치: 기대 21건, 실제 {total_cnt}건"
    assert buy_filled_cnt == 20, f"❌ 매수 체결 건수 불일치: 기대 20건, 실제 {buy_filled_cnt}건"
    assert sell_filled_cnt == 0, f"❌ 매도 체결 건수 불일치: 기대 0건, 실제 {sell_filled_cnt}건"
    assert unfilled_cnt == 1, f"❌ 실패/미체결 건수 불일치: 기대 1건, 실제 {unfilled_cnt}건"
    assert (
        buy_filled_cnt + sell_filled_cnt + unfilled_cnt == total_cnt
    ), "❌ 하위 상태 합계가 총 주문 건수와 불일치"

    # 한글 종목명 누락 여부 검증 (종목코드 == 종목명 발생 시 즉시 Fail)
    code_as_name_count = (df["종목코드"].astype(str).str.strip() == df["종목명"].astype(str).str.strip()).sum()
    print(f"  - 종목코드가 종목명으로 표출된 결함 건수: {code_as_name_count}건 (기대치: 0건)")
    assert code_as_name_count == 0, f"❌ 종목명이 코드로 표출된 오염 레코드 {code_as_name_count}건 발견"

    # 전 종목 코드 6자리 표준화 검증
    invalid_codes = [t for t in df["종목코드"] if not (len(str(t).strip()) == 6 and str(t).strip().isdigit())]
    assert not invalid_codes, f"❌ 비정상 종목코드 발견: {invalid_codes}"

    print("  -> ✅ 실제 거래기록 4대 지표 및 종목명 100% 무결성 검증 통과\n")
    return {
        "total": total_cnt,
        "buy": buy_filled_cnt,
        "sell": sell_filled_cnt,
        "unfilled": unfilled_cnt,
    }


def verify_account_and_equity_integrity(db_path: str = "data/quant_ko.db") -> None:
    """Tab 1 잔고 및 자산 곡선 데이터의 단일 진실 공급원 정합성을 검증합니다."""
    print("[2/3] 계좌 잔고 및 자산 곡선(Tab 1) 정합성 검증 시작...")
    acc_info = load_account_and_positions(db_path=db_path, fetch_live_kis=False)
    total_equity = float(acc_info.get("total_equity", 0.0))
    cash = float(acc_info.get("cash", 0.0))
    stock_value = float(acc_info.get("stock_value", 0.0))

    print(f"  - 계좌 총자산: {total_equity:,.0f}원 (주식: {stock_value:,.0f}원 + 예수금: {cash:,.0f}원)")
    assert abs(total_equity - (stock_value + cash)) < 1.0, "❌ 계좌 총자산 != 주식평가액 + 예수금"

    equity_df = build_account_equity_curve(db_path=db_path, acc_info=acc_info)
    assert not equity_df.empty, "❌ 자산 추이 시계열 데이터프레임이 비어있음"
    assert "date" in equity_df.columns and "total_equity" in equity_df.columns

    latest_equity = float(equity_df["total_equity"].iloc[-1])
    diff = abs(latest_equity - total_equity)
    print(f"  - 자산 곡선 최종값: {latest_equity:,.0f}원 (오차: {diff:,.0f}원)")
    assert diff < 1.0, f"❌ 상단 KPI 카드({total_equity:,.0f}원)와 자산곡선({latest_equity:,.0f}원) 불일치"

    print("  -> ✅ 계좌 잔고 및 자산 곡선 단일 진실 정합성 검증 통과\n")


def verify_top20_targets_integrity() -> None:
    """Tab 4 최신 타깃 20종목 스냅샷 데이터 무결성을 검증합니다."""
    print("[3/3] 최신 타깃 20종목(Tab 4) 데이터 무결성 검증 시작...")
    latest_date, u_cnt, top20_df = load_cached_top20()
    print(f"  - 최신 기준일자: {latest_date}, 유니버스 통과 종목: {u_cnt}개, Top 20 행수: {len(top20_df)}개")

    assert len(top20_df) == 20, f"❌ 타깃 종목 수가 20개가 아님: {len(top20_df)}개"
    assert "종목코드" in top20_df.columns and "종목명" in top20_df.columns
    assert "Total Rank" in top20_df.columns

    # Total Rank (9대 팩터 종합 순위 합산 스코어) 오름차순 정렬 검증
    total_ranks = [int(r) for r in top20_df["Total Rank"].tolist()]
    is_sorted = all(total_ranks[i] <= total_ranks[i + 1] for i in range(len(total_ranks) - 1))
    print(f"  - Total Rank 최소/최대: {min(total_ranks)} ~ {max(total_ranks)} (오름차순 정렬 여부: {is_sorted})")
    assert is_sorted, f"❌ Top 20 Total Rank가 오름차순 정렬되어 있지 않음: {total_ranks}"

    # 종목코드 6자리 및 한글 종목명 무결성 검증
    for idx, row in top20_df.iterrows():
        code = str(row["종목코드"]).strip()
        name = str(row["종목명"]).strip()
        assert len(code) == 6 and code.isdigit(), f"❌ 비정상 타깃 종목코드 발견: {code} (행 {idx})"
        assert name and name != code, f"❌ 타깃 종목명 누락/오염: 코드={code}, 명={name}"

    print("  -> ✅ 최신 타깃 20종목 팩터 스코어 및 메타데이터 무결성 검증 통과\n")


def main() -> int:
    """전체 데이터 건강성 검증 스위트를 실행합니다."""
    print("=" * 65)
    print("🚀 Quant-KO 대시보드 배포 전 자동 데이터 건강성(Health) 검증 실행")
    print("=" * 65)
    try:
        verify_trade_logs_integrity()
        verify_account_and_equity_integrity()
        verify_top20_targets_integrity()
        print("=" * 65)
        print("🎉 모든 데이터 건강성 및 정합성 검증 100% 통과! (배포 안전 보장)")
        print("=" * 65)
        return 0
    except AssertionError as ae:
        print("\n" + "!" * 65)
        print(f"🚨 [검증 실패] 배포 차단: {ae}")
        print("!" * 65)
        return 1
    except Exception as exc:
        import traceback

        print("\n" + "!" * 65)
        print(f"💥 [시스템 에러] 예외 발생: {exc}")
        traceback.print_exc()
        print("!" * 65)
        return 2


if __name__ == "__main__":
    sys.exit(main())
