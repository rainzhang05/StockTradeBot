# StockTradeBot Trading System Specification

This document defines how signals turn into positions and orders, and how the risk layer constrains the entire process.

## 1. Trading System Flow

The end-to-end production path is:

1. refresh canonical market and fundamentals data
2. compute features for the active universe
3. score the universe with the active model
4. apply regime logic
5. construct a target portfolio with optimizer constraints
6. apply risk overrides and mode-specific rules
7. produce executable intents
8. route intents through simulation, paper, or live execution adapters
9. record orders, fills, slippage, and post-trade diagnostics

The risk engine may block or alter steps 5 through 8 at any time.

## 2. Alpha and Regime Expectations

Alpha behavior:

- output a cross-sectional ranking score per eligible symbol
- support both stock and curated ETF candidates
- remain deterministic for a fixed dataset, feature set, and model artifact

Regime behavior:

- use market-behavior features only
- classify the environment into at least `risk-on`, `neutral`, and `risk-off`
- influence gross exposure, breadth, and defensive allocation choice

Risk-off behavior may choose among:

- reduced exposure
- full cash
- defensive ETF allocation from the curated ETF list

## 3. Portfolio Construction Rules

The portfolio constructor must optimize under constraints rather than equal-weighting or taking the top N scores blindly.

V1 baseline constraints:

- long-only
- cash-only
- hard max position size: `10%`
- target breadth: `10` to `25` positions in normal risk-on conditions
- turnover penalty applied at every rebalance
- sector diversification constraint enabled
- optional defensive ETF allocation in risk-off conditions

V1 baseline policy defaults:

- sector exposure soft cap: `30%`
- rebalance turnover soft cap per decision cycle: `25%` of NAV
- minimum conviction threshold before opening a new position

These numeric defaults belong in config, but the repository should launch with them unless superseded later.

## 4. Execution System Rules

Execution must be adaptive to spread, liquidity, and urgency.

The execution layer must support:

- order submission
- order replacement and cancellation
- partial fills
- stale market-state rejection
- slippage tracking
- broker reconnect handling

Execution policy defaults:

- prefer limit orders when spreads are wide relative to expected edge
- allow marketable orders when urgency is high and liquidity is strong
- reject orders if pre-trade data freshness checks fail
- never submit orders when the system is frozen

The same portfolio and risk decision path must be shared across simulation, paper, and live modes. Only the execution adapter should differ materially.

## 5. Risk Authority

The risk layer overrides alpha, portfolio, and execution.

Mandatory hard controls:

- daily loss cap
- portfolio drawdown cap
- kill switch
- dynamic exposure reduction
- abnormal slippage freeze
- broker and data integrity freeze

V1 baseline defaults:

- daily realized plus marked-to-market loss cap: `3%` of NAV
- strategy high-water-mark drawdown freeze: `20%`
- abnormal slippage incident threshold: `> 50 bps` or `> 3x` expected spread on a fill

Freeze triggers:

- broker disconnect or unstable session
- stale or invalid market data
- missing or invalid model output
- feature pipeline failure
- repeated execution anomalies
- manual operator kill switch

When frozen:

- new order submission is blocked
- open orders may be canceled if the freeze policy requires it
- the operator must see the freeze reason clearly in the UI and API

## 6. Trading Modes

Supported runtime modes:

- `simulation`
- `paper`
- `live-manual`
- `live-autonomous`

Rules:

- default mode at first install is `simulation`
- `paper` requires a configured IBKR paper connection and passing startup checks
- `live-manual` requires explicit arming and per-order operator approval
- `live-autonomous` requires separate arming and no per-order approval, but stricter gates

Mode transitions must be auditable and persisted.

## 7. Live Approval Profiles

### 7.1 Live-Manual

Requirements:

- explicit operator arming
- valid broker connectivity
- current promoted model
- no active freeze
- per-order approval in the UI or CLI before submission

### 7.2 Live-Autonomous

Requirements:

- all `live-manual` requirements
- additional promotion gate completion
- explicit operator acknowledgement that per-order approval is disabled
- no unresolved data-quality incidents affecting tradable symbols

Autonomous mode must be harder to enter than manual mode.

## 8. Validation and Promotion Gates

Before a model becomes eligible for `live-manual`:

- pass walk-forward backtests on the available history
- beat SPY net of estimated trading costs on the most recent out-of-sample segment
- show acceptable regime-split behavior, including survivability in poor markets
- complete at least `30` market days in paper mode without critical safety incidents

Before a model becomes eligible for `live-autonomous`:

- satisfy all `live-manual` gates
- complete at least `60` cumulative market days in paper or live-manual without critical safety incidents
- show stable slippage and execution metrics inside configured limits
- have no open high-severity operational incidents

Promotion decisions must remain explicit and auditable. No model promotes itself automatically.

## 9. Backtesting Requirements

Backtests must be event-driven and include:

- trading-session constraints
- commissions
- spread and slippage assumptions
- partial-fill logic
- decision-to-execution delay assumptions
- turnover and rebalance frictions

Every backtest report must be linkable to code, data, features, labels, and model artifacts.
