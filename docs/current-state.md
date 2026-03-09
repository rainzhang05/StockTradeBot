# StockTradeBot Current State

This file describes the repository as it exists now. Update it at the end of every completed task.

## Repository Snapshot

- Date: 2026-03-09
- Branch: `main`
- Repository state: Phase 4 backtesting and validation implemented
- Application code: package, CLI, API, runtime, storage, frontend workspace, market-data pipeline, fundamentals ingestion, dataset generation, model training, walk-forward validation, and backtesting created
- CI/workflows: GitHub Actions are split into focused workflow files for backend quality, backend tests, frontend checks, and package verification
- Tests: backend and frontend verification suites created through Phase 4
- Database schema: Phase 4 SQLite schema and Alembic migrations created
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
- fixed the runtime `ui_url` reporting bug so health output respects CLI host and port overrides
- added typed provider, universe, fundamentals, model-training, and research-backtest configuration to the persisted app config
- added storage tables for backfill runs, provider payloads, normalized observations, canonical bars, incidents, universe snapshots, fundamentals, feature rows, label rows, dataset snapshots, model registry entries, validation runs, backtest runs, and training runs
- added provider adapters for Stooq and Alpha Vantage daily history plus SEC company-facts fundamentals
- added raw payload persistence, canonical daily-bar validation tiers, data-quality incident recording, universe snapshot generation, and duplicate-safe artifact naming
- implemented the `stocktradebot backfill` command and market-data API/status surfaces
- implemented Phase 3 fundamentals ingestion with conservative SEC availability timestamps and stock-only fundamentals backfills
- implemented availability-aware feature engineering, forward-label generation, persisted feature and label version records, and dataset artifact exports
- implemented deterministic linear-correlation model fitting, walk-forward validation, candidate-holdout backtests, model artifact persistence, and research status reporting
- implemented the `stocktradebot train`, `stocktradebot backtest`, and `stocktradebot report` Phase 4 flows plus model and backtest API endpoints
- added Phase 4 unit and integration tests covering baseline model scoring, full training flow, model status surfaces, and API/CLI behavior

## Subsystem Status Matrix

| Subsystem | Status | Notes |
| --- | --- | --- |
| Governance docs | Complete for Phase 0 | Core doc set exists and defines repo operating rules |
| Python package | Complete for Phase 1 | `pyproject.toml`, editable install metadata, and CLI entrypoint exist |
| Backend API | Complete for Phase 4 | FastAPI app exposes health, setup, config, market-data, dataset, model, validation, and backtest endpoints plus frontend serving |
| Database/storage | Complete for Phase 4 | SQLite bootstrap, Alembic migrations, market-data tables, dataset tables, model registry tables, and raw/artifact storage exist |
| Data ingestion | Complete for Phase 3 | Provider adapters, raw payload persistence, canonical daily bars, incidents, universe snapshots, and SEC fundamentals are implemented |
| Features/fundamentals | Complete for Phase 3 | Availability-aware feature generation, labels, dataset lineage, and artifact export are implemented |
| Models/backtesting | Complete for Phase 4 | Deterministic baseline training, walk-forward validation, event-driven backtests, persisted reports, and model registry entries are implemented |
| Portfolio/risk/execution | Not started | Trading-system rules documented only |
| IBKR integration | Not started | No broker code yet |
| Frontend/UI | Complete for Phase 1 | React/Vite placeholder exists in `frontend/`; production dashboard not started |
| Tests/coverage | Complete for Phase 4 | Backend pytest coverage is enforced at `>= 80%`; frontend tests run with Vitest |
| GitHub Actions | Complete for Phase 4 | Focused workflows now cover backend quality, backend tests, frontend checks, and package build |

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
- Phase 4 model promotion remains research-only because paper-trading gate days are still zero and no execution stack exists yet

## Known Gaps

- no portfolio construction, risk engine, broker integration, or live-trading controls exist yet
- no paper-trading loop exists yet, so promotion eligibility is intentionally blocked even when backtests are positive
- the frontend is still a placeholder shell rather than the operator dashboard
- the built-in stock candidate seed list is a bootstrap set rather than a full ~300-name universe; wider coverage depends on configuring more candidate symbols
- background scheduling is still limited to the skeleton runtime; backfill, training, and backtests are currently CLI/API driven rather than scheduler-driven

## Next Milestone

- start Phase 5 from `docs/roadmap.md`
- implement portfolio construction, regime-aware exposure logic, risk freezes, execution intents, and simulated execution

## Verification Status

- documentation consistency review: completed manually
- file/path validation for referenced docs: completed for `docs/README.md` links
- backend checks: `.venv/bin/ruff format --check src tests`, `.venv/bin/ruff check src tests`, `.venv/bin/mypy src`, and `.venv/bin/pytest` passed locally
- coverage check: passed locally at `85.56%`
- frontend checks: `npm run lint`, `npm run test -- --run`, and `npm run build` passed locally in `frontend/`
- package build: `.venv/bin/python -m build` passed locally
- GitHub workflow parity: local `make backend-quality`, `make backend-tests`, `make frontend-check`, and `make package-check` cover the same intent as the split workflow files under `.github/workflows/`
- CLI smoke verification: `stocktradebot init`, `stocktradebot doctor`, `stocktradebot status`, `stocktradebot train --as-of 2026-03-09`, and `stocktradebot backtest` were checked locally; training and backtesting fail cleanly with actionable messages when prerequisites are missing

## Last Updated Because

- 2026-03-09: completed the Phase 4 model training, walk-forward validation, backtesting, workflow split, and verification updates
