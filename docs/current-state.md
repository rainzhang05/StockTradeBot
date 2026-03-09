# StockTradeBot Current State

This file describes the repository as it exists now. Update it at the end of every completed task.

## Repository Snapshot

- Date: 2026-03-09
- Branch: `main`
- Repository state: Phase 3 features and approximate fundamentals implemented
- Application code: package, CLI, API, runtime, storage, frontend workspace, market-data pipeline, fundamentals ingestion, and dataset snapshot generation created
- CI/workflows: initial GitHub Actions workflow created and aligned with the local verification loop
- Tests: backend and frontend verification suites created through Phase 3
- Database schema: Phase 3 SQLite schema and Alembic migrations created
- Frontend: React/Vite placeholder app created under `frontend/` and served by the Python runtime when built

## Completed Work

- created the root `AGENTS.md` workflow contract
- created the documentation map in `docs/README.md`
- rewrote `docs/plan.md` into a concise charter
- added architecture, data/modeling, trading, product UI, engineering, roadmap, and decisions specifications
- renamed the repository frontend folder convention from `ui/` to `frontend/`
- added the Python package scaffold, CLI, FastAPI app, runtime/config layers, SQLite bootstrap, and Alembic setup
- added the React/Vite frontend workspace and placeholder HTML fallback
- added local developer commands, backend tests, frontend tests, and the initial CI workflow
- fixed the runtime `ui_url` reporting bug so health output respects CLI host and port overrides
- added typed provider, universe, fundamentals, and model-training configuration to the persisted app config
- added storage tables for backfill runs, provider payloads, normalized observations, canonical bars, incidents, universe snapshots, fundamentals, feature rows, label rows, and dataset snapshots
- added provider adapters for Stooq and Alpha Vantage daily history plus SEC company-facts fundamentals
- added raw payload persistence, canonical daily-bar validation tiers, data-quality incident recording, universe snapshot generation, and duplicate-safe artifact naming
- implemented the `stocktradebot backfill` command and market-data API/status surfaces
- implemented Phase 3 fundamentals ingestion with conservative SEC availability timestamps and stock-only fundamentals backfills
- implemented availability-aware feature engineering, forward-label generation, persisted feature and label version records, and dataset artifact exports
- implemented the `stocktradebot train` dataset-build command plus dataset status and build API endpoints
- added Phase 3 unit and integration tests covering SEC parsing, raw payload collision handling, dataset reproducibility, and CLI/API behavior

## Subsystem Status Matrix

| Subsystem | Status | Notes |
| --- | --- | --- |
| Governance docs | Complete for Phase 0 | Core doc set exists and defines repo operating rules |
| Python package | Complete for Phase 1 | `pyproject.toml`, editable install metadata, and CLI entrypoint exist |
| Backend API | Complete for Phase 3 | FastAPI app exposes health, setup, config, system status, market-data status, and dataset build/status endpoints plus frontend serving |
| Database/storage | Complete for Phase 3 | SQLite bootstrap, Alembic migrations, Phase 3 market-data and dataset tables, and raw payload storage exist |
| Data ingestion | Complete for Phase 3 | Provider adapters, raw payload persistence, canonical daily bars, incidents, universe snapshots, and SEC fundamentals are implemented |
| Features/fundamentals | Complete for Phase 3 | Availability-aware feature generation, labels, dataset lineage, and artifact export are implemented |
| Models/backtesting | Not started | No backtesting or validation framework yet |
| Portfolio/risk/execution | Not started | Trading-system rules documented only |
| IBKR integration | Not started | No broker code yet |
| Frontend/UI | Complete for Phase 1 | React/Vite placeholder exists in `frontend/`; production dashboard not started |
| Tests/coverage | Complete for Phase 3 | Backend pytest coverage is enforced at `>= 80%`; frontend tests run with Vitest |
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
- dataset builds require a prior backfill because the feature pipeline depends on persisted canonical bars and universe snapshots

## Known Gaps

- no backtesting engine, walk-forward validation flow, or benchmark report storage exists yet
- no portfolio construction, risk engine, broker integration, or live-trading controls exist yet
- the frontend is still a placeholder shell rather than the operator dashboard
- the built-in stock candidate seed list is a bootstrap set rather than a full ~300-name universe; wider coverage depends on configuring more candidate symbols
- background scheduling is still limited to the skeleton runtime; backfill and dataset builds are currently CLI/API driven rather than scheduler-driven

## Next Milestone

- start Phase 4 from `docs/roadmap.md`
- implement the backtesting and validation framework, including reproducible reports and artifact linking

## Verification Status

- documentation consistency review: completed manually
- file/path validation for referenced docs: completed for `docs/README.md` links
- backend checks: `.venv/bin/ruff format --check src tests`, `.venv/bin/ruff check src tests alembic/versions/20260309_000003_phase3_features_and_fundamentals.py`, `.venv/bin/mypy src`, and `.venv/bin/pytest` passed locally
- coverage check: passed locally at `84.18%`
- frontend checks: `npm run lint`, `npm run test -- --run`, and `npm run build` passed locally in `frontend/`
- package build: `.venv/bin/python -m build` passed locally
- GitHub workflow parity: local commands cover the same intent as `.github/workflows/ci.yml`
- CLI smoke verification: `.venv/bin/stocktradebot init`, `.venv/bin/stocktradebot doctor`, `.venv/bin/stocktradebot status`, and `.venv/bin/stocktradebot train --as-of 2026-03-09` were checked locally; `train` now fails cleanly with an actionable message when backfill prerequisites are missing

## Last Updated Because

- 2026-03-09: completed the Phase 3 fundamentals, features, dataset lineage, verification, and state cleanup work
