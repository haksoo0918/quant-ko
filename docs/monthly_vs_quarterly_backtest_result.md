# 소형주 성장 가치 퀀트: 월별 vs 분기 리밸런싱 백테스트 비교 리포트 (2019 - 2026.10)

## 전략 설정 및 조건 비교 요약

- 공통 유니버스: 금융주, 지주사, 관리종목, 중국기업, 스팩, 우선주 제외, 흑자기업(분기 & TTM 2중 필터)

- 공통 팩터: 9대 팩터 (낮은 시가총액 + 가치 4개 PER/PSR/POR/PGPR + 성장 4개 순이익/영업익/매출총익/매출액 YoY)

- 공통 파라미터: 초기 자본 1,000만 원, 편도 수수료 0.3% (왕복 0.6%), 종목 수 20개 동일비중


### 종합 성과 비교 요약표

| 전략 구분 | 리밸런싱 주기 | 시총 컷 | 거래대금 조건 | 누적 수익률 | CAGR (연복리) | MDD (최대낙폭) | 샤프지수 | 총 거래비용 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 원안 팩트: 월별 리밸런싱 (시총 20%, 거래대금 제한없음) | 매월 말일 | 하위 20% | 제한없음 | **142.25%** | 12.07% | -48.16% | 0.33 | 4,310,827원 |
| 원안 팩트: 월별 리밸런싱 (시총 20%, 거래대금 2억) | 매월 말일 | 하위 20% | 2억 이상 | **101.32%** | 9.43% | -63.57% | 0.18 | 8,188,462원 |
| 기존 원안: 분기 리밸런싱 (시총 20%, 거래대금 2억) | 분기 (연 4회) | 하위 20% | 2억 이상 | **49.62%** | 5.33% | -58.31% | 0.05 | 1,828,717원 |
| 옵션 B: 분기 리밸런싱 (시총 30%, 거래대금 2억) | 분기 (연 4회) | 하위 30% | 2억 이상 | **88.07%** | 8.48% | -50.07% | 0.13 | 2,172,774원 |

## [원안 팩트: 월별 리밸런싱 (시총 20%, 거래대금 제한없음)] 상세 리포트

# Backtest Performance Report

## 1. Portfolio Overview
| Metric | Portfolio |
|---|---|
| Initial Capital | 10,000,000 KRW |
| Final Equity | 24,224,688 KRW |
| Total Cumulative Return | 142.25% |
| CAGR | 12.07% |
| Maximum Drawdown (MDD) | -48.16% |
| MDD Peak Date | 2022-04-21 |
| MDD Trough Date | 2026-07-29 |
| Annualized Volatility | 25.93% |
| Sharpe Ratio (Rf=3.5%) | 0.33 |
| Win Rate (Rebalance) | 52.13% |
| Win Rate (Yearly) | 62.50% |
| Average Turnover Rate | 30.15% |

## 2. Calendar Year Returns
| Year | Return |
|---|---|
| 2019 | 17.35% |
| 2020 | 65.47% |
| 2021 | 76.68% |
| 2022 | -5.06% |
| 2023 | 3.42% |
| 2024 | -27.43% |
| 2025 | 5.62% |
| 2026 | -6.18% |


### 연도별 상세 수익률
| 연도 | 연간 수익률 |
|:---:|:---:|
| 2019년 | 17.35% |
| 2020년 | 65.47% |
| 2021년 | 76.68% |
| 2022년 | -5.06% |
| 2023년 | 3.42% |
| 2024년 | -27.43% |
| 2025년 | 5.62% |
| 2026년 | -6.18% |

## [원안 팩트: 월별 리밸런싱 (시총 20%, 거래대금 2억)] 상세 리포트

# Backtest Performance Report

## 1. Portfolio Overview
| Metric | Portfolio |
|---|---|
| Initial Capital | 10,000,000 KRW |
| Final Equity | 20,132,497 KRW |
| Total Cumulative Return | 101.32% |
| CAGR | 9.43% |
| Maximum Drawdown (MDD) | -63.57% |
| MDD Peak Date | 2024-05-13 |
| MDD Trough Date | 2026-10-02 |
| Annualized Volatility | 32.67% |
| Sharpe Ratio (Rf=3.5%) | 0.18 |
| Win Rate (Rebalance) | 51.06% |
| Win Rate (Yearly) | 37.50% |
| Average Turnover Rate | 51.39% |

## 2. Calendar Year Returns
| Year | Return |
|---|---|
| 2019 | -6.33% |
| 2020 | 111.17% |
| 2021 | 81.82% |
| 2022 | -4.32% |
| 2023 | 7.78% |
| 2024 | -8.35% |
| 2025 | -11.02% |
| 2026 | -33.43% |


### 연도별 상세 수익률
| 연도 | 연간 수익률 |
|:---:|:---:|
| 2019년 | -6.33% |
| 2020년 | 111.17% |
| 2021년 | 81.82% |
| 2022년 | -4.32% |
| 2023년 | 7.78% |
| 2024년 | -8.35% |
| 2025년 | -11.02% |
| 2026년 | -33.43% |

## [기존 원안: 분기 리밸런싱 (시총 20%, 거래대금 2억)] 상세 리포트

# Backtest Performance Report

## 1. Portfolio Overview
| Metric | Portfolio |
|---|---|
| Initial Capital | 10,000,000 KRW |
| Final Equity | 14,961,906 KRW |
| Total Cumulative Return | 49.62% |
| CAGR | 5.33% |
| Maximum Drawdown (MDD) | -58.31% |
| MDD Peak Date | 2021-07-15 |
| MDD Trough Date | 2026-07-02 |
| Annualized Volatility | 34.32% |
| Sharpe Ratio (Rf=3.5%) | 0.05 |
| Win Rate (Rebalance) | 38.71% |
| Win Rate (Yearly) | 50.00% |
| Average Turnover Rate | 62.68% |

## 2. Calendar Year Returns
| Year | Return |
|---|---|
| 2019 | 0.42% |
| 2020 | 42.53% |
| 2021 | 54.49% |
| 2022 | -14.54% |
| 2023 | -11.09% |
| 2024 | -3.10% |
| 2025 | -12.28% |
| 2026 | 4.78% |


### 연도별 상세 수익률
| 연도 | 연간 수익률 |
|:---:|:---:|
| 2019년 | 0.42% |
| 2020년 | 42.53% |
| 2021년 | 54.49% |
| 2022년 | -14.54% |
| 2023년 | -11.09% |
| 2024년 | -3.10% |
| 2025년 | -12.28% |
| 2026년 | 4.78% |

## [옵션 B: 분기 리밸런싱 (시총 30%, 거래대금 2억)] 상세 리포트

# Backtest Performance Report

## 1. Portfolio Overview
| Metric | Portfolio |
|---|---|
| Initial Capital | 10,000,000 KRW |
| Final Equity | 18,807,349 KRW |
| Total Cumulative Return | 88.07% |
| CAGR | 8.48% |
| Maximum Drawdown (MDD) | -50.07% |
| MDD Peak Date | 2019-04-17 |
| MDD Trough Date | 2020-03-23 |
| Annualized Volatility | 37.36% |
| Sharpe Ratio (Rf=3.5%) | 0.13 |
| Win Rate (Rebalance) | 45.16% |
| Win Rate (Yearly) | 62.50% |
| Average Turnover Rate | 70.99% |

## 2. Calendar Year Returns
| Year | Return |
|---|---|
| 2019 | 1.01% |
| 2020 | 49.52% |
| 2021 | 44.12% |
| 2022 | -15.17% |
| 2023 | -12.20% |
| 2024 | -11.03% |
| 2025 | 3.65% |
| 2026 | 25.79% |


### 연도별 상세 수익률
| 연도 | 연간 수익률 |
|:---:|:---:|
| 2019년 | 1.01% |
| 2020년 | 49.52% |
| 2021년 | 44.12% |
| 2022년 | -15.17% |
| 2023년 | -12.20% |
| 2024년 | -11.03% |
| 2025년 | 3.65% |
| 2026년 | 25.79% |