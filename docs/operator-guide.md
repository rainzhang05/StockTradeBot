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

Complete the `Setup` screen in this order:

1. confirm storage paths for the database, artifacts, and logs
2. set the primary provider and optional secondary corroboration provider
3. enable SEC fundamentals only after configuring a valid user agent
4. review the curated stock and ETF universe inputs
5. save IBKR paper and live account identifiers if broker integration is enabled
6. run the doctor checks until the required prerequisites are green
7. remain in `simulation` mode until backfill, research, and paper validation are complete

## Daily Operator Workflow

Typical daily sequence:

1. open `Dashboard` and confirm current mode, freeze status, broker state, and latest jobs
2. review `Data` for recent incidents and canonicalization health
3. run a backfill when the universe or latest bars are stale
4. run an intraday backfill and intraday validation from the CLI or API when intraday research needs refreshing
5. build a dataset, train, and backtest from `Research` when model refresh is needed
6. run `Simulation` first, then `Paper` when broker connectivity is healthy
7. enter `Live Manual` only after paper safe-day gates and approval requirements are satisfied

## Mode Safety Rules

- `simulation` is the default and safest operating mode
- `paper` requires configured IBKR paper connectivity and passing startup checks
- `live-manual` requires explicit arming and per-order approval
- `live-autonomous` is harder to enter and requires an explicit approval-bypass acknowledgement
- `frozen` blocks new order submission until the freeze is understood and cleared

## Logs and Audit Trail

Current operator-facing diagnostics include:

- `System -> Audit events`: persisted state-changing actions
- `System -> Operational logs`: recent structured runtime events from `logs/events.jsonl`

Use the audit feed to answer what changed. Use the operational logs to answer what happened around a failure.

## Recommended Pre-Live Checklist

Before any live arming:

1. `doctor` passes without blocking checks
2. the latest data incident list is empty for tradable symbols
3. the latest model and dataset versions are visible in the dashboard
4. paper safe-day history satisfies the manual or autonomous gate
5. there is no active freeze
6. the operator has reviewed the latest logs and audit events for unexpected failures