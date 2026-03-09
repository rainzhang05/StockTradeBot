# StockTradeBot

Phase 1 is now scaffolded as a local-first Python package with a FastAPI runtime skeleton, SQLite bootstrap plus Alembic migration wiring, a placeholder React frontend under `frontend/`, and CI/test baselines.

## Quick Start

```bash
python3 -m pip install -e ".[dev]"
cd frontend && npm install
cd ..
stocktradebot init
stocktradebot doctor
stocktradebot --check-only --no-browser
```

## Local Commands

```bash
make check
make frontend-build
```

The documentation source of truth lives under [`docs/`](/Users/rainzhang/StockTradeBot/docs/README.md).
