# 변경 이력 (Changelog)

이 프로젝트의 모든 주요 변경 사항은 본 문서에 기록됩니다.
본 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/) 원칙 및 [Semantic Versioning](https://semver.org/lang/ko/) 표준을 준수합니다.

## [Unreleased]

### 추가 (Added)
- **데이터 파이프라인 기초 (`src/quant_ko/data/`)**:
  - `store.py`: PRD 5.3 기반 5대 핵심 테이블(`companies`, `daily_prices`, `financials`, `designations`, `orders`) SQLite 데이터베이스 스토리지 및 인덱스 관리 구현.
  - `dart.py`: OpenDART 고유번호 ZIP 압축 파싱, 실제 공시접수일(`rcept_dt`) 기준 연결/별도 7대 재무 계정 추출 파서 구현.
  - `krx.py`: KRX 종목 마스터, 보통주/우선주/스팩/중국계/금융·지주사 판별 필터 태깅, 일별 시가총액·종가·거래대금 수집기 구현.
- **테스트 & 품질 스위트 (`tests/`)**:
  - `test_store.py`, `test_dart.py`, `test_krx.py` 단위 및 통합 테스트 43개 구축 (코드 커버리지 93%, 100% 통과).
- **프로젝트 설정 및 명세**:
  - `PRD.md`: 소형주 성장 가치 퀀트 전략 자동매매 시스템 명세서 작성.
  - `README.md`, `README-en.md`: 시스템 아키텍처 및 9대 팩터 전략 소개 작성.
  - `pyproject.toml`: Ruff 린터 및 Pytest 통합 설정 구성.
