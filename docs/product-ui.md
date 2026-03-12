# StockTradeBot Product and UI Specification

This document defines the operator experience and the UI behavior the backend must support.

## 1. UX Principles

The UI must be:

- clear before clever
- black-and-white dominant
- professional, calm, and non-technical in tone
- explicit about safety state
- focused on the few decisions the operator actually needs to make

The product is still a local trading platform, but the presentation should feel closer to a polished consumer-grade control surface than an internal engineering console.

Color should be reserved for alarms, live-mode emphasis, and performance direction rather than decoration.

## 2. Core Screens

The current top-level UI is intentionally consolidated into four areas:

- `Overview`
  - current mode, readiness, freeze status, backtest return, latest run profit, portfolio value, quick actions, and recent activity
- `Stocks`
  - stock-by-stock status, target weights, latest order or fill state, and approval actions when needed
- `Activity`
  - recent performance, orders, fills, and a clean event feed without raw JSON dumps
- `Setup`
  - first-run guidance, provider setup, broker configuration, storage paths, and safety defaults

The backend still exposes richer subsystems such as data, research, portfolio, orders, and system status, but the default UI surface should present them through these simplified views instead of many separate operator screens.

## 3. First-Run Setup Flow

The first-run flow must guide the user through:

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
- keep the mode-change controls easy to find from `Overview`

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

## 6. Required Overview Elements

`Overview` must expose at minimum:

- active mode and profile
- current readiness or attention state
- daily research readiness and promotion readiness when they differ
- current freeze status and reason if present
- latest backtest return
- latest run profit or loss
- portfolio NAV and cash
- pending approval count
- a short readiness summary covering database, market data, fundamentals, and broker state
- quick actions for backfill, training, backtest, simulation, paper, and live preparation
- recent activity in plain language

## 7. Required Stock Status Elements

`Stocks` must expose at minimum:

- symbol
- current score or conviction signal
- target weight
- latest price
- current status such as ready, awaiting approval, submitted, filled, or paused
- latest action time
- approve or reject controls when a pending live-manual approval exists

The stock view must avoid showing raw payloads, internal IDs, or backend response objects by default.

## 8. Visual System Rules

Visual direction:

- primary palette: black, white, gray
- accent palette: limited and reserved for alerts or explicit status distinctions
- typography: neutral and highly legible
- layouts: spacious cards, clear tables, and smooth corner radii
- motion: minimal and purposeful

Do not introduce marketing-style visuals, playful gradients, decorative motion, or raw JSON/debug panels into the operator UI.

## 9. API Dependence

The frontend depends on backend APIs for:

- setup and readiness state
- health and recent activity
- data ingest and validation jobs
- positions, orders, fills, and portfolio summaries
- model and backtest results
- mode transitions and approvals

The UI must degrade safely if APIs are unavailable. It should surface the issue instead of masking it.
