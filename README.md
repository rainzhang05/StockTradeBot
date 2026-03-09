# StockTradeBot

Phase 4 is implemented. The repository now includes the local-first Python package and FastAPI runtime, SQLite plus Alembic persistence, a React frontend workspace under `frontend/`, free-source daily market-data backfill, SEC-derived approximate fundamentals, availability-aware feature engineering, a deterministic baseline model trainer, walk-forward validation, event-driven backtesting, persisted research artifacts, and split CI workflows by concern.

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
stocktradebot train --as-of 2026-04-15
stocktradebot backtest
stocktradebot report
stocktradebot status
stocktradebot --check-only --no-browser
```

## Local Commands

```bash
make check
make backend-quality
make backend-tests
make frontend-check
make package-check
```

The documentation source of truth lives under [`docs/`](/Users/rainzhang/StockTradeBot/docs/README.md).
