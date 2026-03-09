# StockTradeBot Product and UI Specification

This document defines the operator experience and the UI behavior the backend must support.

## 1. UX Principles

The UI must be:

- clear before clever
- black-and-white dominant
- information-dense but not visually noisy
- explicit about safety state
- usable by one operator monitoring the system locally

Color should be reserved for alarms, live-mode emphasis, and outcome signals rather than decoration.

## 2. Core Screens

The UI must include these top-level areas:

- `Setup`
  - first-run flow, provider setup, broker configuration, readiness checks
- `Dashboard`
  - current mode, health, freeze status, latest signals, portfolio summary, and recent activity
- `Portfolio`
  - positions, target portfolio, weights, PnL, equity curve, and cash state
- `Orders`
  - order intents, approvals, open orders, fills, cancellations, and execution diagnostics
- `Research`
  - dataset versions, model versions, backtests, validation summaries, and promotion status
- `Data`
  - universe status, provider health, backfill jobs, data-quality incidents, and canonicalization stats
- `System`
  - logs, configuration, scheduler status, secrets readiness, and diagnostics

## 3. First-Run Setup Flow

The first-run wizard must guide the user through:

1. choosing the runtime storage location
2. initializing the local database and artifact directories
3. configuring free data providers
4. configuring IBKR paper connection details
5. explaining simulation, paper, `live-manual`, and `live-autonomous`
6. running readiness checks
7. landing the operator in `simulation` mode

The setup flow must not imply that live trading is ready until all gates are actually satisfied.

## 4. Mode UX

Mode presentation rules:

- show the current mode on every major screen
- make `simulation` and `paper` visibly distinct
- make any live mode visually unmistakable
- show the current arming state and freeze state separately

Live modes must display:

- current profile: `manual` or `autonomous`
- current promoted model
- latest risk check result
- outstanding approvals if applicable

## 5. Manual vs Autonomous Live UX

### 5.1 Live-Manual

The operator must be able to:

- arm the session
- review each proposed order with rationale, size, risk impact, and freshness checks
- approve or reject each order
- disarm the session at any time

### 5.2 Live-Autonomous

The operator must be able to:

- arm or disarm the autonomous session
- see why the model is eligible for autonomous mode
- monitor orders and freezes in real time
- revert immediately to `live-manual`, `paper`, or `simulation`

The UI must not make autonomous mode easier to trigger than manual mode.

## 6. Required Dashboard Elements

The dashboard must expose at minimum:

- active mode and profile
- current freeze status and reason if present
- broker connectivity
- data freshness and provider incident counts
- active model version and dataset version
- portfolio NAV, cash, and day PnL
- top signals and planned rebalances
- recent orders and fills
- most recent completed jobs

## 7. Visual System Rules

Visual direction:

- primary palette: black, white, gray
- accent palette: limited and reserved for alerts or explicit status distinctions
- typography: neutral and highly legible
- layouts: panel-based, compact, and tabular where appropriate

Do not introduce marketing-style visuals, playful gradients, or decorative motion into the operator UI.

## 8. API Dependence

The frontend depends on backend APIs for:

- setup and readiness state
- health and logs
- data ingest and validation jobs
- positions, orders, fills, and portfolio summaries
- model and backtest results
- mode transitions and approvals

The UI must degrade safely if APIs are unavailable. It should surface the issue instead of masking it.
