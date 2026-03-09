# StockTradeBot

Phase 3 is implemented. The repository now includes the local-first Python package and FastAPI runtime skeleton, SQLite plus Alembic persistence, a React frontend workspace under `frontend/`, free-source daily market-data backfill, canonical daily bars with provenance and incident tracking, SEC-derived approximate fundamentals, availability-aware feature engineering, dataset snapshot lineage, and CI/test baselines.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cd frontend && npm install
cd ..
stocktradebot init
stocktradebot doctor
stocktradebot backfill --symbol AAPL --lookback-days 45 --as-of 2026-03-06
stocktradebot train --as-of 2026-03-06
stocktradebot status
stocktradebot --check-only --no-browser
```

## Local Commands

```bash
make check
make frontend-build
```

The documentation source of truth lives under [`docs/`](/Users/rainzhang/StockTradeBot/docs/README.md).
