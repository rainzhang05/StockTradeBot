# StockTradeBot

Phase 9 intraday research expansion is implemented. The repository now includes the local-first Python package and FastAPI runtime, SQLite plus Alembic persistence, a React operator dashboard under `frontend/`, free-source daily and intraday market-data backfill, SEC-derived approximate fundamentals, availability-aware daily and intraday feature engineering, deterministic walk-forward validation, event-driven backtesting, a persisted simulation execution stack, IBKR Client Portal paper/live broker boundaries with manual live approvals and autonomous gating, release-grade packaged frontend serving, structured operational logs, and operator-facing intraday research APIs and CLI flows.

## Release Install Flow

```bash
pipx install stocktradebot
stocktradebot init
stocktradebot doctor
stocktradebot
```

The release package now bundles the built frontend so the installed app serves the operator UI without requiring a source checkout.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cd frontend && npm install
cd ..
stocktradebot init
stocktradebot doctor
stocktradebot backfill --symbol AAPL --symbol MSFT --symbol SPY --lookback-days 180 --as-of 2026-04-15
stocktradebot intraday-backfill --frequency 15min --symbol AAPL --symbol MSFT --symbol SPY --lookback-days 40 --as-of 2026-04-15
stocktradebot intraday-dataset --frequency 15min --as-of 2026-04-15
stocktradebot intraday-validate --frequency 15min --as-of 2026-04-15
stocktradebot train --as-of 2026-04-15
stocktradebot backtest
stocktradebot simulate --as-of 2026-04-15
stocktradebot paper
stocktradebot report
stocktradebot status
stocktradebot --no-browser
```

## Local Commands

```bash
make check
make backend-quality
make backend-tests
make frontend-check
make frontend-e2e
make package-check
```

The documentation source of truth lives under [`docs/`](/Users/rainzhang/StockTradeBot/docs/README.md).

The current implementation snapshot is tracked in [`docs/current-state.md`](/Users/rainzhang/StockTradeBot/docs/current-state.md).

Additional operator-facing docs:

- [`docs/operator-guide.md`](/Users/rainzhang/StockTradeBot/docs/operator-guide.md)
- [`docs/troubleshooting.md`](/Users/rainzhang/StockTradeBot/docs/troubleshooting.md)
- [`docs/release-process.md`](/Users/rainzhang/StockTradeBot/docs/release-process.md)
