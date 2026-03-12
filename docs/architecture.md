# StockTradeBot Architecture Specification

This document defines the concrete system shape that later implementation must follow.

## 1. Target Repository Shape

The intended repository structure is:

```text
.
├── AGENTS.md
├── docs/
├── pyproject.toml
├── src/
│   └── stocktradebot/
│       ├── api/
│       ├── cli/
│       ├── config/
│       ├── data/
│       ├── domain/
│       ├── execution/
│       ├── features/
│       ├── frontend/
│       ├── models/
│       ├── portfolio/
│       ├── risk/
│       ├── runtime/
│       └── storage/
├── frontend/
│   ├── src/
│   ├── public/
│   └── dist/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
└── .github/
    └── workflows/
```

Guiding rules:

- Python code uses a `src/` layout.
- The frontend is developed in `frontend/` and its production build is served by the Python app.
- Migrations live with the Python backend.
- Tests are grouped by scope, not by technology.

## 2. Runtime Topology

V1 is a single-node local system with clean internal boundaries.

Primary runtime components:

- `CLI launcher`: entrypoint for install, setup, jobs, and local runtime control
- `API service`: FastAPI app serving REST endpoints and the built web UI
- `scheduler`: APScheduler-driven recurring job coordinator
- `runtime orchestrator`: manages mode state, background jobs, startup ordering, and shutdown
- `storage layer`: SQLAlchemy access to SQLite plus local artifact storage
- `worker tasks`: background jobs for ingestion, features, training, and reports

Initial deployment shape:

- one local process is acceptable for v1 if the module boundaries remain clean
- background jobs may run in-process initially
- future separation into multiple processes or remote workers must not require rewriting domain contracts

## 3. Service Boundaries

The backend is organized into these service domains:

- `config service`: loads, validates, and persists user/application configuration
- `data service`: fetches raw provider data, validates it, and produces canonical datasets
- `feature service`: computes deterministic feature sets from canonical data
- `model service`: trains, validates, registers, loads, and scores models
- `portfolio service`: converts model output into target holdings under constraints
- `risk service`: applies hard limits, freeze rules, and live-mode gates
- `execution service`: converts approved orders into broker actions and records outcomes
- `mode service`: governs simulation, paper, live-manual, and live-autonomous transitions
- `reporting service`: produces status, audit, and operator reports
- `frontend/api service`: exposes operator-facing APIs and serves the frontend

The frontend must communicate only through documented APIs. It may not call Python service objects directly.

## 4. Stable CLI Contract

The following commands are part of the target stable interface:

- `stocktradebot`
  - starts the local runtime, ensures storage exists, initializes the database if needed, serves the UI, and opens the browser
- `stocktradebot init`
  - initializes application directories, local database, default config, and first-run state
- `stocktradebot doctor`
  - checks environment readiness, config completeness, broker reachability, filesystem permissions, and data/provider health
- `stocktradebot backfill`
  - runs market-data backfill jobs for universe snapshots, prices, corporate actions, and fundamentals
- `stocktradebot intraday-backfill`
  - runs intraday market-data backfill jobs for 15-minute or 1-hour research bars plus quality reporting
- `stocktradebot intraday-dataset`
  - builds an intraday dataset snapshot for a requested research frequency and as-of date
- `stocktradebot intraday-validate`
  - runs intraday walk-forward validation and emits an intraday validation artifact
- `stocktradebot train`
  - runs model training, validation, registry publication, and a persisted walk-forward validation backtest for a specified dataset/feature version and quality scope
- `stocktradebot backtest`
  - runs event-driven backtests through the shared portfolio-construction path and emits reproducible reports for the selected trained model
- `stocktradebot simulate`
  - runs the simulation adapter, persists target portfolios, order intents, fills, and risk results
- `stocktradebot paper`
  - arms or starts paper-trading workflows against IBKR paper endpoints
- `stocktradebot live`
  - arms live trading in either manual or autonomous profile after passing safety checks
- `stocktradebot status`
  - prints runtime state, active mode, last jobs, health, and broker/data status
- `stocktradebot report`
  - produces operator or validation reports from stored state

Subcommands may expand, but these top-level contracts must remain recognizable.

## 5. Stable REST API Groups

API groups and responsibilities:

- `health/setup/config`
  - health status, setup progress, readiness checks, persisted configuration, and environment diagnostics
- `operator workspace`
  - aggregated operator workspace payloads, strategy-profile readiness summaries, and resource-repair actions for the planned strategy modes
- `market-data jobs`
  - universe refreshes, provider jobs, raw ingest status, canonicalization status, and data-quality incidents
- `models/backtests`
  - dataset snapshots, feature versions, training runs, model registry entries, backtest runs, and validation reports
- `portfolio/orders/fills`
  - current positions, target portfolios, open orders, executions, fills, and equity history
- `risk/mode/system`
  - mode state, freeze reasons, kill switch, paper/live gating status, system logs, and scheduler status

API design rules:

- version under `/api/v1`
- use typed request/response schemas
- return audit identifiers for mutating operations
- keep async job progress queryable
- never expose secrets back to the UI

## 6. Config Schema Families

Implementation must support persisted configuration for these families:

- `app/runtime paths`
  - storage root, database path, logs path, artifact path, UI host/port, timezone
- `data providers`
  - enabled providers, rate limits, symbol mapping rules, retry policy, validation thresholds
- `broker`
  - IBKR host/port, client ID, account identifiers, paper/live selection, reconnect policy
- `execution`
  - order profile defaults, freshness thresholds, participation limits, manual approval defaults
- `risk`
  - drawdown caps, daily loss caps, turnover caps, sector caps, freeze thresholds, kill-switch policy
- `model/training`
  - feature set version, label version, training cadence, registry locations, validation thresholds, quality scope, supported model families, and rebalance interval
- `UI preferences`
  - browser launch behavior, refresh intervals, compact/detailed tables, local notifications

Config rules:

- store non-secret configuration on disk in a typed format
- store secrets outside version control and avoid echoing them in logs
- support environment variable overrides for automation
- persist effective config snapshots used for training and backtesting runs

## 7. Persistence Model

Default persisted storage:

- SQLite database for structured application state
- local filesystem for raw provider payloads, dataset snapshots, artifacts, reports, and logs

Core persisted entities:

- app configuration and setup state
- universe snapshots
- raw provider payload metadata
- canonical bars and corporate actions
- fundamentals with availability timestamps
- feature snapshots
- dataset snapshots
- model registry entries
- backtest and validation runs
- mode state and freeze events
- account snapshots, positions, orders, fills, and execution events
- system logs and audit events

Research lineage rules:

- dataset snapshots, model registry entries, validation runs, and backtest runs must persist the effective `quality_scope`
- status and readiness reporting must distinguish `research-capable` from `promotion-blocked` daily data states

Alembic migrations are mandatory from the first database version. Schema changes must be backward migratable or explicitly documented as breaking.

## 8. Mode State Machine

The mode state machine is a stable contract:

- `simulation`
- `paper`
- `live-manual`
- `live-autonomous`
- `frozen`

Allowed transitions:

- `simulation -> paper`
- `paper -> simulation`
- `live-manual -> simulation`
- `paper -> live-manual`
- `live-autonomous -> paper`
- `live-autonomous -> simulation`
- `live-manual -> paper`
- `live-manual -> live-autonomous`
- `live-autonomous -> live-manual`
- any active mode -> `frozen`
- `frozen -> simulation`
- `frozen -> paper`
- `frozen -> live-manual`

Rules:

- entering any live mode requires explicit user action
- entering `live-autonomous` requires stricter promotion and risk gates than `live-manual`
- `frozen` blocks order submission until the freeze is reviewed and cleared
- the current mode and last transition reason must be persisted

## 9. Packaging and Launch Flow

Packaging goals:

- installable via `pipx install stocktradebot`
- CLI entrypoint exposed as `stocktradebot`
- frontend build bundled with the Python package

Launch flow for `stocktradebot`:

1. load effective config
2. ensure runtime directories exist
3. initialize or migrate the SQLite database
4. run startup diagnostics
5. start the API/runtime service
6. start background scheduler tasks that are safe to run
7. open the default browser to the local UI

The application must fail closed: if startup detects unsafe or incomplete state, it should keep the UI available for remediation but avoid enabling paper or live trading.
