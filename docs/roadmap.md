# StockTradeBot Implementation Roadmap

This roadmap defines the order in which the repository should be built. Each phase has objective exit criteria so agents can tell whether the phase is actually complete.

## Phase 0: Governance Baseline

Goal:

- establish the documentation and agent-governance system that every later change must follow

Deliverables:

- `AGENTS.md`
- complete docs map and subsystem specs
- initialized `current-state.md`

Dependencies:

- none

Non-goals:

- application code
- CI implementation

Exit criteria:

- docs set exists and is internally consistent
- current state reflects the real repository
- agent workflow contract is explicit

## Phase 1: Package, CLI, and Runtime Skeleton

Goal:

- create the minimal installable Python package and local runtime skeleton

Deliverables:

- `pyproject.toml`
- `stocktradebot` CLI entrypoint
- FastAPI app skeleton
- runtime config loading
- SQLite bootstrap and Alembic setup
- placeholder UI serving path
- local developer and CI commands

Dependencies:

- Phase 0

Non-goals:

- real market-data ingestion
- real trading logic

Exit criteria:

- `stocktradebot init`, `doctor`, and base launch flow exist
- local app boots and serves a placeholder UI
- tests and CI skeleton exist with coverage enforcement wired in

## Phase 2: Daily Data Ingestion and Storage

Goal:

- build free-source daily market-data ingestion and storage with provenance

Deliverables:

- provider adapter framework
- universe snapshot generation
- raw payload storage
- normalized daily bars and corporate actions
- canonicalization pipeline with incident tracking

Dependencies:

- Phase 1

Non-goals:

- promotable intraday history

Exit criteria:

- dynamic stock universe and curated ETFs can be backfilled
- canonical daily bars are reproducible
- discrepancies are quarantined and auditable

## Phase 3: Features and Approximate Fundamentals

Goal:

- produce verified feature-ready daily datasets with approximate point-in-time fundamentals

Deliverables:

- SEC-derived fundamentals ingestion
- availability-aware as-of joins
- feature engineering pipeline
- feature-set versioning
- label generation
- dataset snapshot metadata

Dependencies:

- Phase 2

Non-goals:

- live trading
- model promotion

Exit criteria:

- one reproducible daily dataset snapshot can be built end-to-end
- feature and label versions are persisted
- approximate point-in-time rules are tested

## Phase 4: Backtesting and Validation Framework

Goal:

- create the research engine that can evaluate models under realistic assumptions

Deliverables:

- event-driven backtester
- benchmark comparison reports
- walk-forward validation flow
- validation report storage
- reproducible artifact linking

Dependencies:

- Phase 3

Non-goals:

- live execution

Exit criteria:

- a documented baseline model can be trained and backtested reproducibly
- reports link code, data, features, labels, and models
- promotion calculations exist even if no model qualifies yet

## Phase 5: Portfolio, Risk, and Execution Core

Goal:

- implement the production decision path from ranked symbols to executable order intents

Deliverables:

- portfolio optimizer
- regime-aware exposure logic
- risk overrides and freeze engine
- execution intent builder
- simulated execution adapter

Dependencies:

- Phase 4

Non-goals:

- IBKR live connectivity

Exit criteria:

- simulation mode can produce auditable order intents and fills
- freeze logic is tested and persisted
- live mode remains disabled by default

## Phase 6: IBKR Paper and Live Integration

Goal:

- connect the decision engine to IBKR paper and live boundaries safely

Deliverables:

- IBKR paper adapter
- IBKR live adapter
- broker state synchronization
- manual approval workflow
- live-autonomous gating logic

Dependencies:

- Phase 5

Non-goals:

- intraday promotable research

Exit criteria:

- paper mode functions end-to-end
- `live-manual` arming path exists
- `live-autonomous` remains blocked unless stricter gates are met

## Phase 7: Operator UI

Goal:

- deliver the full local operator experience

Deliverables:

- setup flow
- dashboard, portfolio, orders, research, data, and system screens
- mode controls and live approval UX
- health and incident displays

Dependencies:

- Phases 1 through 6

Non-goals:

- hosted multi-user features

Exit criteria:

- an operator can install, configure, monitor, and control the system through the UI
- live/manual/autonomous distinctions are clear
- critical workflows are covered by end-to-end tests

## Phase 8: Hardening and Release Readiness

Goal:

- make the repository safe to ship as a production-capable local platform

Deliverables:

- full CI coverage
- packaging verification
- release process
- operator docs and troubleshooting guidance
- stricter observability and reporting

Dependencies:

- Phases 1 through 7

Non-goals:

- new major strategy capabilities

Exit criteria:

- CI passes consistently
- coverage is at least 80%
- `pipx install stocktradebot` and `stocktradebot` are verified
- live-manual can be used safely by an informed operator

## Phase 9: Intraday Research Expansion

Goal:

- extend the daily-first system into promotable 15-minute and 1-hour research

Deliverables:

- free-source intraday feasibility review
- intraday provider adapters and canonicalization rules
- intraday feature versions
- intraday-aware validation reports

Dependencies:

- Phase 8

Non-goals:

- replacing the daily-first baseline

Exit criteria:

- intraday data quality is proven adequate for promotion
- intraday features and labels are reproducible
- documentation is updated to reflect the expanded capability
