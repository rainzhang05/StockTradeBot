# StockTradeBot Current State

This file describes the repository as it exists now. Update it at the end of every completed task.

## Repository Snapshot

- Date: 2026-03-09
- Branch: `main`
- Repository state: Phase 5 portfolio, risk, and simulation execution implemented
- Application code: package, CLI, API, runtime, storage, frontend workspace, market-data pipeline, fundamentals ingestion, dataset generation, model training, walk-forward validation, backtesting, portfolio construction, risk freezes, and simulation execution created
- CI/workflows: GitHub Actions are split into focused workflow files for backend quality, backend tests, frontend checks, and package verification
- Tests: backend and frontend verification suites created through Phase 5
- Database schema: Phase 5 SQLite schema and Alembic migrations created
- Frontend: React/Vite placeholder app created under `frontend/` and served by the Python runtime when built

## Completed Work

- created the root `AGENTS.md` workflow contract
- created the documentation map in `docs/README.md`
- rewrote `docs/plan.md` into a concise charter
- added architecture, data/modeling, trading, product UI, engineering, roadmap, and decisions specifications
- renamed the repository frontend folder convention from `ui/` to `frontend/`
- added the Python package scaffold, CLI, FastAPI app, runtime/config layers, SQLite bootstrap, and Alembic setup
- added the React/Vite frontend workspace and placeholder HTML fallback
- added local developer commands, backend tests, frontend tests, and split GitHub workflow coverage by concern
- updated the Makefile to use the repository `.venv` directly and expanded backend-quality checks to include Alembic migration files
- fixed the runtime `ui_url` reporting bug so health output respects CLI host and port overrides
- added typed provider, universe, fundamentals, model-training, portfolio, risk, and execution configuration to the persisted app config
- added storage tables for backfill runs, provider payloads, normalized observations, canonical bars, incidents, universe snapshots, fundamentals, feature rows, label rows, dataset snapshots, model registry entries, validation runs, backtest runs, mode state, freeze events, simulation runs, portfolio snapshots, order intents, and fills
- added provider adapters for Stooq and Alpha Vantage daily history plus SEC company-facts fundamentals
- added raw payload persistence, canonical daily-bar validation tiers, data-quality incident recording, universe snapshot generation, and duplicate-safe artifact naming
- implemented the `stocktradebot backfill` command and market-data API/status surfaces
- implemented Phase 3 fundamentals ingestion with conservative SEC availability timestamps and stock-only fundamentals backfills
- implemented availability-aware feature engineering, forward-label generation, persisted feature and label version records, and dataset artifact exports
- implemented deterministic linear-correlation model fitting, walk-forward validation, candidate-holdout backtests, model artifact persistence, and research status reporting
- implemented the `stocktradebot train`, `stocktradebot backtest`, `stocktradebot simulate`, and `stocktradebot report` Phase 5 flows plus portfolio, risk, order, fill, and simulation API endpoints
- implemented Phase 5 portfolio construction with regime-aware exposure, position caps, sector caps, turnover throttling, defensive allocation support, persistent mode state, risk freeze persistence, simulated order intents, and simulated fills
- added Phase 5 unit and integration tests covering portfolio constraints, risk freezes, full simulation flow, and CLI/API behavior

## Subsystem Status Matrix

| Subsystem | Status | Notes |
| --- | --- | --- |
| Governance docs | Complete for Phase 0 | Core doc set exists and defines repo operating rules |
| Python package | Complete for Phase 1 | `pyproject.toml`, editable install metadata, and CLI entrypoint exist |
| Backend API | Complete for Phase 5 | FastAPI app exposes health, setup, config, market-data, dataset, model, validation, backtest, risk, portfolio, order, fill, and simulation endpoints plus frontend serving |
| Database/storage | Complete for Phase 5 | SQLite bootstrap, Alembic migrations, market-data tables, dataset tables, model registry tables, mode state, freeze state, simulation runs, and raw/artifact storage exist |
| Data ingestion | Complete for Phase 3 | Provider adapters, raw payload persistence, canonical daily bars, incidents, universe snapshots, and SEC fundamentals are implemented |
| Features/fundamentals | Complete for Phase 3 | Availability-aware feature generation, labels, dataset lineage, and artifact export are implemented |
| Models/backtesting | Complete for Phase 4 | Deterministic baseline training, walk-forward validation, event-driven backtests, persisted reports, and model registry entries are implemented |
| Portfolio/risk/execution | Complete for Phase 5 | Regime-aware portfolio construction, risk freeze engine, simulation runs, order intents, fills, and trading status surfaces are implemented |
| IBKR integration | Not started | No broker code yet |
| Frontend/UI | Complete for Phase 1 | React/Vite placeholder exists in `frontend/`; production dashboard not started |
| Tests/coverage | Complete for Phase 5 | Backend pytest coverage is enforced at `>= 80%`; frontend tests run with Vitest |
| GitHub Actions | Complete for Phase 4 | Focused workflows cover backend quality, backend tests, frontend checks, and package build |

## Active Constraints

- v1 must remain single-user and local-first
- v1 trading is regular-hours-only
- free-source-only market-data policy is in force
- v1 research and promotion are daily-first
- approximate point-in-time fundamentals are allowed only with conservative availability handling
- live-manual is the default live profile; live-autonomous requires stricter gates
- repository-wide test coverage target is `>= 80%` once code and tests exist
- verified canonical bars still require a corroborating secondary provider; the default Stooq-only setup yields provisional bars until a secondary source is enabled
- dataset builds require a prior backfill because the feature pipeline depends on persisted canonical bars and universe snapshots
- simulation mode may use research-only models under the current default config, but paper and live remain disabled until later phases
- model promotion remains research-only because paper-trading gate days are still zero and no IBKR execution path exists yet

## Known Gaps

- no IBKR paper or live broker integration exists yet
- no paper-trading loop exists yet, so promotion eligibility is intentionally blocked even when backtests are positive
- the frontend is still a placeholder shell rather than the operator dashboard
- the built-in stock candidate seed list is a bootstrap set rather than a full ~300-name universe; wider coverage depends on configuring more candidate symbols
- background scheduling is still limited to the skeleton runtime; backfill, training, backtests, and simulations are currently CLI/API driven rather than scheduler-driven

## Next Milestone

- start Phase 6 from `docs/roadmap.md`
- connect the decision engine to IBKR paper and live boundaries safely, while keeping live disabled by default

## Verification Status

- documentation consistency review: completed manually
- file/path validation for referenced docs: completed for `docs/README.md` links
- backend checks: `make backend-quality` and `make backend-tests` passed locally
- coverage check: passed locally at `85.15%`
- frontend checks: `npm run lint`, `npm run test -- --run`, and `npm run build` passed locally in `frontend/`
- package build: `make package-check` passed locally
- GitHub workflow parity: `make check` passed locally and maps to the same intent as the split workflow files under `.github/workflows/`
- CLI smoke verification: `stocktradebot init`, `stocktradebot doctor`, `stocktradebot status`, `stocktradebot paper`, `stocktradebot live`, and `stocktradebot simulate --as-of 2026-04-15` were checked locally against a fresh temp app home; `simulate` failed cleanly with `Run backfill first.` when prerequisites were missing

## Last Updated Because

- 2026-03-09: completed the Phase 5 portfolio construction, risk freeze engine, simulation execution stack, and related verification updates
