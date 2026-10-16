# Quant-KO: Small-Cap Growth & Value Quantitative Auto-Trading System

An automated quantitative investment and live-trading system for the bottom 20% small-cap stocks in KOSPI/KOSDAQ, integrating with Korea Investment & Securities (KIS) Open API.

---

## 📌 Key Highlights

1. **Point-in-Time (PIT) Integrity**
   - Ingests OpenDART financial statements based on actual submission dates (`rcept_dt`).
   - Accounts for delisted companies and designation history to eliminate survivorship bias.
2. **9-Factor Small-Cap Growth & Value Model**
   - **Universe**: KOSPI/KOSDAQ common shares, December fiscal year-end (Excludes financials, holdings, SPACs, preferred, designated, and Chinese-risk stocks).
   - **Market Cap**: Bottom 20% within the filtered pool.
   - **Financial Health & Liquidity**: Debt ratio ≤ 200%, Capital impairment ≤ 0%, 20-day avg trading value ≥ 200M KRW.
   - **Profitability**: Operating income & controlling net income > 0 (both latest quarter and TTM).
   - **Composite Score**: Market Cap (Asc) + 4 Value Factors (PER, PSR, POR, PGPR) + 4 Growth Factors (YoY Net Income, Operating Income, Gross Profit, Revenue).
3. **Quarterly Rebalancing & Risk Management**
   - 4 times a year: 1st trading day of April, last trading day of May, August, November.
   - Closing auction (15:20\~15:30) limit order execution with differential portfolio balancing.
   - Immediate liquidation upon designation as administrative/warning issue.
4. **KIS Open API Execution**
   - Paper trading support before transitioning to live capital.
   - Daily health monitoring and Telegram alerts.

---

## 🏗️ Architecture

```text
src/quant_ko/
  ├── data/        # OpenDART, KRX collectors and SQLite storage
  ├── pit/         # Point-in-Time financial statement snapshot builder
  ├── strategy/    # Universe filters, 9-factor scoring, and portfolio selector
  ├── backtest/    # 2016\~present backtest engine, costs, and performance report
  ├── broker/      # Korea Investment & Securities (KIS) Open API client
  ├── live/        # Rebalancer, daily monitor, and scheduler entry point
  └── notify/      # Telegram notification bot
```

---

## 📖 Documentation
- [PRD (Product Requirements Document)](PRD.md)
- [Task Queue & Milestones](TODO.md)
- [Changelog](CHANGELOG.md)
