# StockTradeBot Master Plan

## 1. Project Overview

StockTradeBot is a local-first, open-source, production-grade stock trading platform with a browser-based local web UI. It is designed for single-user operation initially, with architecture intentionally structured so it can later evolve into a hybrid mode where the UI remains local while the runtime operates remotely.

The system is aimed at long-term return maximization, while still enforcing deterministic safety controls, validation gates, and operational reliability.

The product must install globally with one command and launch from the terminal with:

```bash
pipx install stocktradebot
stocktradebot
```

Running `stocktradebot` must:
1. start the required local services,
2. initialize local state if needed,
3. open the default browser,
4. launch the local web UI,
5. guide the user through first-time setup.

The UI must be minimal, straightforward, and primarily black-and-white.

---

## 2. Core Strategic Architecture

The production strategy architecture is:

- **Multi-layer systematic trading system**
- **ML/statistical models for alpha**
- **Deterministic portfolio, risk, and execution controls**
- **Regime-aware orchestration**
- **Strict validation and promotion gates**

This is not a pure rules bot, pure ML bot, or RL-first system.

### 2.1 Primary Strategy Philosophy

- Objective: **maximize long-term return**
- Upside is prioritized over strict capital preservation
- The system may reduce exposure heavily or go fully to cash in poor conditions
- Trading is **cash-only**
- No borrowing, margin, or leverage
- Market scope: **U.S. stocks + curated ETF list**
- ETFs are fully tradable, but only from an explicit curated universe

### 2.2 Alpha Engine Direction

The core alpha architecture uses:

- **Cross-sectional stock ranking**
- **Technical + cross-sectional market features + fundamental features**
- **Linear + boosting ensemble**
- **Regime behavior based only on market behavior**, not macroeconomic feeds

### 2.3 Trading Style

- Core decision engine: **end-of-bar**
- Timeframe design: **multi-timeframe**, centered on:
  - 15-minute bars
  - 1-hour bars
  - daily context
- Dominant holding profile: **medium swing with intraday-aware entries and exits**
- Trading frequency is not fixed by count; the system trades when the architecture indicates favorable conditions

---

## 3. Tradable Universe

### 3.1 Universe Type

The tradable universe is dynamic and refreshed periodically.

### 3.2 Default Size

- Primary stock universe target: **top 300 liquid U.S. names**
- ETF universe: separate curated ETF list

### 3.3 Exclusions

The system must exclude:

- penny stocks
- ADRs
- recent IPOs
- low-volume names
- leveraged ETFs
- inverse ETFs

### 3.4 Universe Refresh

The dynamic universe must be rebuilt on a scheduled basis using liquidity and quality filters. Historical research must preserve universe membership snapshots to avoid look-ahead contamination.

---

## 4. Data Sources and Data Policy

### 4.1 Broker / Execution / Live State

**Interactive Brokers (IBKR)** is the execution and live-state platform.

IBKR is responsible for:

- order execution
- live account state
- positions
- order state
- fills
- broker-side simulation/paper compatibility where applicable
- market-state checks needed for execution reliability

### 4.2 Historical Training Data

Primary historical data source:
- **Alpha Vantage**

Gap repair source:
- **Yahoo Finance**

### 4.3 Canonical Data Rule

- **Alpha Vantage is canonical**
- **Yahoo Finance is repair-only**
- Yahoo Finance may only fill missing values or missing bars
- Yahoo Finance must not silently override canonical Alpha Vantage values
- Any repaired data points must be flagged and auditable

### 4.4 Historical Depth

- Attempt to build **20 years of history if available**
- Fallback to **max available** history when data depth is limited

### 4.5 Data Retention

Intraday history retention policy:
- keep full history,
- archive older data separately,
- preserve full reproducibility while controlling active storage costs

### 4.6 Corporate Actions

Historical price series must be split- and dividend-adjusted where appropriate for modeling correctness.

### 4.7 Data Layers

The system must keep separate layers for:

1. raw downloaded data
2. normalized canonical data
3. repaired/validated data
4. feature-ready data
5. point-in-time training datasets
6. model-linked dataset snapshots

### 4.8 Point-in-Time Correctness

Fundamental history must be stored and used in **point-in-time** form only. No leakage from future-restated or later-available values is permitted.

---

## 5. Feature System

### 5.1 Required Feature Categories

The feature pipeline must support at minimum:

- price momentum
- mean reversion signals
- volatility features
- volume and liquidity features
- cross-sectional relative strength
- sector relative strength
- market regime indicators
- fundamental ratios

### 5.2 Feature Versioning

Every model must be linked to:

- feature set version
- feature calculation parameters
- training dataset snapshot
- label definition version

This is mandatory for reproducibility and rollback.

### 5.3 Feature Governance

Features must be explicitly defined in documentation and implemented deterministically. Feature changes must be traceable and versioned.

---

## 6. Model Architecture

### 6.1 Production Model Family

The production alpha stack is centered on:

- linear models
- boosting models
- ensemble combination of those families

Neural networks may exist only as experimental research branches unless they later prove superior under the promotion framework.

### 6.2 Alpha Output

The primary model output is a **cross-sectional ranking score** used by portfolio construction.

### 6.3 Regime Layer

Regime behavior must be driven by market behavior only and must support:

- exposure reduction
- switching to a defensive behavior profile
- allowing full cash when conditions are sufficiently poor

### 6.4 Training Cadence

Training policy:
- scheduled retraining: **bi-weekly**
- performance-triggered retraining: **enabled**

### 6.5 Training Runtime Architecture

Training must be separated from the main runtime and designed as:

- a separate worker/job system,
- local-first compatible,
- future remote-compatible.

### 6.6 GitHub Actions Model Training Policy

GitHub Actions may be used for parts of the retraining and model release workflow, but the architecture must not assume GitHub Actions is the only training environment.

Required policy:

- initial released model artifacts may be trained locally and committed/published through a controlled release flow,
- recurring retraining may use GitHub Actions **only if** the workflow is reproducible, secrets are handled correctly, runtime limits are acceptable, and required data snapshots are available,
- the design must also support alternate execution backends for training later,
- model artifacts pushed from CI must be versioned and linked to dataset, feature, and code versions,
- no model may be promoted automatically without passing validation and promotion gates.

This means GitHub Actions is an acceptable **first automation backend**, but the system must be designed so training orchestration is backend-agnostic.

### 6.7 Model Registry

The architecture must support a model registry that stores:

- model version
- training code version
- feature version
- dataset snapshot reference
- validation metrics
- benchmark comparisons
- regime-split results
- paper-trading status
- promotion status
- rollback eligibility

---

## 7. Portfolio Construction

### 7.1 Construction Style

Portfolio construction must be:

- **optimizer-based with constraints**
- not naive equal weighting
- not unconstrained score chasing

### 7.2 Breadth

The live portfolio should target approximately **10–25 positions** depending on signal quality and risk state.

### 7.3 Position Sizing

- hard maximum position size: **10%**
- softer optimizer targets should usually size below the hard cap unless conviction and risk conditions justify otherwise

### 7.4 Exposure

Portfolio exposure must be **dynamic based on regime**. Full capital deployment is allowed when favorable, but the system must support reduced exposure or full cash.

### 7.5 Rebalancing

- rebalancing is **gradual**
- turnover must be explicitly controlled
- unnecessary churn must be penalized

### 7.6 Defensive Capital Allocation

When market conditions are poor, the system may choose among:

- reduced exposure
- full cash
- defensive ETF allocation

Selection must be system-driven under the regime layer and portfolio policy.

### 7.7 Benchmarks

Primary benchmark:
- **SPY buy-and-hold**

The architecture should also allow secondary baseline comparisons such as equal-weight or simple heuristic baselines.

---

## 8. Execution System

### 8.1 Order Routing Philosophy

Execution must use an **adaptive order policy based on spread and liquidity**.

The execution layer must determine whether a market order, limit order, or execution tactic is appropriate under current conditions.

### 8.2 Execution Requirements

The execution engine must handle:

- order submission
- order state tracking
- cancellation and replacement
- partial fills
- stale quote checks
- broker connectivity checks
- pre-trade freshness checks
- slippage-aware decision logic

### 8.3 Execution Freshness

The bot must verify required market state freshness before placing live orders.

### 8.4 Execution Adapter Boundary

Simulation, paper, and live modes must share the same decision path wherever possible, differing primarily at the execution adapter layer.

---

## 9. Simulation, Paper, and Live Modes

### 9.1 Default Safety Mode

The application must default to **simulation mode**.

### 9.2 Mode Types

The architecture must support:

- backtesting mode
- local simulation mode
- paper trading mode
- live trading mode

### 9.3 Live Mode Protection

Switching to live mode must require:

- explicit user warning
- clear risk confirmation
- valid broker/API configuration already present
- user-initiated proceed action from the UI

Live mode must never be silently activated.

### 9.4 Paper Trading Gate

Before model promotion to live eligibility:
- minimum paper trading survival period: **30 market days**

---

## 10. Backtesting and Validation

### 10.1 Backtest Engine Type

Backtesting must be **event-driven**, not merely vectorized.

### 10.2 Required Realism

Backtests and simulations must model:

- IBKR commissions
- slippage
- bid-ask spread
- partial fills
- trading session constraints
- execution delays where applicable

### 10.3 Promotion Gates

Before a model can be promoted for live trading, it must pass:

- walk-forward testing
- paper trading period
- benchmark beating requirement
- regime-split evaluation

### 10.4 Required Evaluations

The evaluation framework must compare strategies against at least the primary benchmark and must include stress testing across different market conditions.

### 10.5 Reproducibility

Every backtest and validation run must be linkable to:

- code version
- dataset version
- feature version
- model version
- parameter set

---

## 11. Risk Management and Safety Controls

### 11.1 Required Hard Controls

The system must include at minimum:

- hard max drawdown protection
- daily loss cap
- kill switch
- dynamic exposure reduction
- risk override authority above alpha output

### 11.2 Automatic Freeze Triggers

The system must auto-freeze trading when any of the following occur:

- broker API disconnect or instability
- stale or invalid data feed
- feature pipeline failure
- missing or invalid model output
- abnormal slippage or execution anomaly

### 11.3 Risk Layer Authority

The risk engine must always be able to override:

- alpha model output
- portfolio intent
- execution intent

### 11.4 Exit Logic

Exits are mostly model- and portfolio-driven rather than fixed stop/take-profit heuristics, but deterministic hard-risk overrides remain mandatory.

---

## 12. Runtime Architecture

### 12.1 Local-First Service Architecture

The local runtime must be structured as distinct services/modules:

- data service
- feature service
- model service
- portfolio service
- execution service
- risk service
- UI/API service

These may run within a local process graph initially, but the interfaces must be clean enough to support later hybrid separation.

### 12.2 API-First Local Design

Even in fully local mode, the frontend must communicate through an API/service boundary rather than directly calling internal runtime logic.

### 12.3 State Persistence

All critical runtime state must be persisted, not kept only in memory.

Required persisted state includes:

- bot mode
- account snapshots
- positions
- open orders
- fills
- portfolio intent
- regime state
- model state references
- system health
- logs and audit events

### 12.4 Storage

Primary local runtime storage:
- **SQLite by default**

Future-compatible option:
- PostgreSQL later if needed

---

## 13. User Interface

### 13.1 UI Philosophy

The UI must be:

- simple
- direct
- low-friction
- black-and-white dominant
- built for clarity over decoration

### 13.2 Required Views / Components

The UI must expose at minimum:

- portfolio equity curve
- current positions
- open orders
- system status
- regime state
- alpha signals summary
- risk status
- logs
- account state
- strategy configuration
- mode management
- backtest access
- setup flow

### 13.3 Setup Flow

The first-run setup wizard must guide the user through:

- local initialization
- broker configuration
- data API configuration
- simulation vs live safety explanation
- storage setup
- basic readiness checks

### 13.4 Mode UX

The UI must clearly distinguish:

- simulation mode
- paper mode
- live mode

Live mode must be visually unmistakable.

---

## 14. Installation and Packaging

### 14.1 Install Goal

The target user flow is:

```bash
pipx install stocktradebot
stocktradebot
```

### 14.2 Launch Behavior

When `stocktradebot` is run, it must:

1. start required local services,
2. ensure storage/runtime directories exist,
3. initialize local database if necessary,
4. perform environment checks,
5. launch or connect the local backend,
6. open the local UI in the default browser.

### 14.3 Open-Source Usability Goal

The project must be easy for technical users to install and run locally without manual multi-step startup.

---

## 15. Testing and Quality Gates

The system must include sufficient testing to support safe modification and agent-driven maintenance.

Minimum governance requirement:

- test coverage must remain **above 80%**
- GitHub workflows must pass before integration is considered complete

Testing should include at least:

- unit tests
- integration tests
- data integrity tests
- execution adapter tests
- backtest validation tests
- safety/risk logic tests

---

## 16. Agent-Driven Repository Expectations

This master plan is not the full documentation hierarchy itself. Instead, it defines what the agent-managed repository must establish.

### 16.1 Docs Folder Expectation

Agents are expected to create and maintain a `docs/` folder containing however many files are necessary to clearly define:

- the complete system plan
- component specifications
- roadmap
- current implementation state
- other supporting specifications needed for correct execution

### 16.2 Current State Tracking

The docs system must include a current-state document that reflects the actual implementation status and not only the intended target design.

### 16.3 AGENTS.md Requirements

`AGENTS.md` must instruct all agents that they are required to:

1. always read the `docs/` folder before making any modification,
2. follow the roadmap and current specifications defined there,
3. update the current-state documentation after finishing implementation or modification,
4. verify at the end that test coverage remains above 80%,
5. verify that all GitHub workflows pass.

### 16.4 Source-of-Truth Behavior

The documentation written under `docs/` must function as the operational source of truth for implementation work.

---

## 17. Development Roadmap Shape

The implementation roadmap should logically proceed through these major phases:

1. repository scaffolding and package launcher
2. local service/runtime skeleton
3. data ingestion and storage layer
4. canonical data validation and gap repair
5. feature pipeline and dataset versioning
6. model training pipeline and registry
7. backtesting and validation framework
8. portfolio, execution, and risk engines
9. simulation and paper trading support
10. live IBKR integration
11. local web UI and setup flow
12. promotion gates, quality gates, and release hardening

The docs created by agents should refine this into concrete milestones and current-state progress tracking.

---

## 18. Non-Negotiable Constraints

The following are non-negotiable for the repository:

- cash-only trading
- U.S. stocks + curated ETF support only
- end-of-bar decision engine
- multi-timeframe alpha centered on 15m + 1h + daily
- cross-sectional ranking alpha
- technical + cross-sectional + fundamental features
- linear + boosting ensemble core
- optimizer-based portfolio construction
- adaptive execution
- event-driven backtesting
- simulation default mode
- explicit live-mode warning and confirmation
- 30 market day paper gate before live eligibility
- deterministic safety overrides
- Alpha Vantage canonical historical source
- Yahoo Finance repair-only source
- IBKR execution/live-state source
- local-first architecture
- simple black-and-white browser UI
- pipx-based one-command installation and CLI launch
- test coverage greater than 80%
- all GitHub workflows passing

---

## 19. Final Intent

This repository is intended to become a serious, agent-maintained, production-grade local trading platform with disciplined architecture, rigorous validation, and user-friendly operation.

The implementation must prioritize:

- correctness,
- reproducibility,
- operational safety,
- maintainability,
- profitability under realistic execution constraints,
- and a clean path from local-first use toward future hybrid operation.

