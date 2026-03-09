# StockTradeBot Current State

This file describes the repository as it exists now. Update it at the end of every completed task.

## Repository Snapshot

- Date: 2026-03-09
- Branch: `main`
- Repository state: Phase 2 market-data ingestion and storage implemented
- Application code: package, CLI, API, runtime, storage, frontend skeleton, and Phase 2 data pipeline created
- CI/workflows: initial GitHub Actions workflow created
- Tests: backend and frontend verification suites created through Phase 2
- Database schema: Phase 2 SQLite schema and Alembic migrations created
- Frontend: React/Vite placeholder app created under `frontend/`

## Completed Work

- created the root `AGENTS.md` workflow contract
- created the documentation map in `docs/README.md`
- rewrote `docs/plan.md` into a concise charter
- added architecture, data/modeling, trading, product UI, engineering, roadmap, and decisions specifications
- renamed the repository frontend folder convention from `ui/` to `frontend/`
- added the Python package scaffold, CLI, FastAPI app, runtime/config layers, SQLite bootstrap, and Alembic setup
- added the React/Vite Phase 1 frontend placeholder
- added local developer commands, backend tests, frontend tests, and the initial CI workflow
- fixed the runtime `ui_url` reporting bug so health output respects CLI host and port overrides
- added typed provider and universe configuration to the persisted app config
- added Phase 2 storage tables for backfill runs, provider payloads, normalized observations, canonical bars, incidents, and universe snapshots
- added provider adapters for Stooq and Alpha Vantage daily history
- added raw payload persistence, canonical daily-bar validation tiers, data-quality incident recording, and universe snapshot generation
- implemented the `stocktradebot backfill` command and market-data API/status surfaces
- added Phase 2 unit and integration tests covering canonicalization, universe ranking, backfill reproducibility, and CLI/API behavior

## Subsystem Status Matrix

| Subsystem | Status | Notes |
| --- | --- | --- |
| Governance docs | Complete for Phase 0 | Core doc set exists and defines repo operating rules |
| Python package | Complete for Phase 1 | `pyproject.toml`, editable install metadata, and CLI entrypoint exist |
| Backend API | Complete for Phase 2 | FastAPI app exposes health, setup, config, system status, and market-data status endpoints plus placeholder UI serving |
| Database/storage | Complete for Phase 2 | SQLite bootstrap, Alembic migrations, Phase 2 market-data tables, and raw payload storage exist |
| Data ingestion | Complete for Phase 2 | Provider adapters, raw payload persistence, canonical daily bars, incidents, and universe snapshots are implemented |
| Features/fundamentals | Not started | Specifications exist only |
| Models/backtesting | Not started | No training or validation code yet |
| Portfolio/risk/execution | Not started | Trading-system rules documented only |
| IBKR integration | Not started | No broker code yet |
| Frontend/UI | Complete for Phase 1 | React/Vite placeholder exists in `frontend/`; production dashboard not started |
| Tests/coverage | Complete for Phase 1 | Backend pytest coverage is enforced at `>= 80%`; frontend tests run with Vitest |
| GitHub Actions | Complete for Phase 1 | CI workflow runs backend checks, frontend checks, and package build |

## Active Constraints

- v1 must remain single-user and local-first
- v1 trading is regular-hours-only
- free-source-only market-data policy is in force
- v1 research and promotion are daily-first
- approximate point-in-time fundamentals are allowed only with conservative availability handling
- live-manual is the default live profile; live-autonomous requires stricter gates
- repository-wide test coverage target is `>= 80%` once code and tests exist
- verified canonical bars still require a corroborating secondary provider; the default Stooq-only setup yields provisional bars until a secondary source is enabled

## Known Gaps

- no feature engineering, fundamentals ingestion, broker integration, or trading logic exists yet
- the frontend is still a placeholder shell rather than the operator dashboard
- the built-in stock candidate seed list is a bootstrap set rather than a full ~300-name universe; wider coverage depends on configuring more candidate symbols
- background scheduling is still limited to the skeleton runtime; Phase 2 backfill is currently CLI-driven rather than scheduler-driven

## Next Milestone

- start Phase 3 from `docs/roadmap.md`
- implement SEC-derived approximate fundamentals, feature engineering, label generation, and dataset snapshot lineage

## Verification Status

- documentation consistency review: completed manually
- file/path validation for referenced docs: completed for `docs/README.md` links
- backend checks: `make check` passed locally, including `ruff format --check`, `ruff check`, `mypy`, and `pytest`
- coverage check: passed locally at `84.29%`
- frontend checks: `npm run lint`, `npm run test`, and `npm run build` passed locally
- package build: `python -m build` passed locally
- GitHub workflow parity: local commands now cover the same intent as `.github/workflows/ci.yml`
- CLI smoke verification: `stocktradebot init`, `stocktradebot backfill --symbol AAPL --lookback-days 45 --as-of 2026-03-06`, and `stocktradebot status` passed locally against the default Stooq provider

## Last Updated Because

- 2026-03-09: fixed runtime URL reporting and completed the Phase 2 market-data ingestion, canonicalization, universe snapshot, and verification baseline
