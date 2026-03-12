# StockTradeBot Operator Guide

This guide describes the supported local operator workflow for the current Phase 9 system.

## Intended Install Flow

Primary release path:

```bash
pipx install stocktradebot
stocktradebot init
stocktradebot doctor
stocktradebot
```

Expected behavior:

- `init` creates the app home, database, runtime directories, and default config
- `doctor` confirms storage, provider, artifact, and broker prerequisites
- `stocktradebot` starts the local runtime and serves the operator UI
- the UI opens in the browser unless `--no-browser` is supplied

## First-Run Setup

Complete the `Setup` view in this order:

1. confirm storage paths for the database, artifacts, and logs
2. set the primary provider and optional secondary corroboration provider
3. enable SEC fundamentals only after configuring a valid user agent
4. review the curated stock and ETF universe inputs
5. save IBKR paper and live account identifiers if broker integration is enabled
6. run the doctor checks until the required prerequisites are green
7. remain in `simulation` mode until backfill, research, and paper validation are complete

Readiness note:

- a Stooq-only runtime may show daily data as `research-capable` but `promotion-blocked`; that means daily research and backtests can run, but candidate promotion and live eligibility still require verified bars
- when you need a multi-year daily research baseline, run `stocktradebot backfill --full-history --historical-snapshots`; that hydrates the provider's full daily range and persists monthly universe snapshots plus the current as-of snapshot

## Daily Operator Workflow

Typical daily sequence:

1. open `Overview` and confirm current mode, readiness, freeze status, backtest return, and latest run profit
2. review the readiness card and recent activity feed for broker or data issues, especially whether daily data is only `research-capable`
3. run `Refresh data` when the universe or latest bars are stale
4. run an intraday backfill and intraday validation from the CLI or API when intraday research needs refreshing
5. use `Train model` and `Run backtest` from `Overview` when model refresh is needed
6. review `Stocks` for symbol-by-symbol status and any pending approvals
7. run `Simulation` first, then `Paper` when broker connectivity is healthy
8. enter `Live Manual` only after paper safe-day gates and approval requirements are satisfied

## Mode Safety Rules

- `simulation` is the default and safest operating mode
- `paper` requires configured IBKR paper connectivity and passing startup checks
- `live-manual` requires explicit arming and per-order approval
- `live-autonomous` is harder to enter and requires an explicit approval-bypass acknowledgement
- `frozen` blocks new order submission until the freeze is understood and cleared

## Activity Feed

Current operator-facing diagnostics are shown in `Activity` and include:

- recent state-changing audit messages
- recent structured runtime events rendered as plain-language entries
- recent orders and fills

Use the activity feed to answer what changed and what happened around a failure without exposing raw JSON payloads by default.

## Recommended Pre-Live Checklist

Before any live arming:

1. `doctor` passes without blocking checks
2. the latest data incident list is empty for tradable symbols
3. the latest model and backtest return are visible in `Overview`
4. paper safe-day history satisfies the manual or autonomous gate
5. there is no active freeze
6. the operator has reviewed the latest activity feed for unexpected failures
