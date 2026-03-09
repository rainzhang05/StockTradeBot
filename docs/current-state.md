# StockTradeBot Current State

This file describes the repository as it exists now. Update it at the end of every completed task.

## Repository Snapshot

- Date: 2026-03-09
- Branch: `main`
- Repository state: Phase 1 scaffold implemented
- Application code: package, CLI, API, runtime, storage, and frontend skeleton created
- CI/workflows: initial GitHub Actions workflow created
- Tests: backend and frontend Phase 1 tests created
- Database schema: initial SQLite schema and Alembic migration created
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

## Subsystem Status Matrix

| Subsystem | Status | Notes |
| --- | --- | --- |
| Governance docs | Complete for Phase 0 | Core doc set exists and defines repo operating rules |
| Python package | Complete for Phase 1 | `pyproject.toml`, editable install metadata, and CLI entrypoint exist |
| Backend API | Complete for Phase 1 | FastAPI app exposes health, setup, config, and status endpoints plus placeholder UI serving |
| Database/storage | Complete for Phase 1 | SQLite bootstrap and Alembic initial migration exist |
| Data ingestion | Not started | Provider adapters and canonicalization not implemented |
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

## Known Gaps

- no market-data ingestion, broker integration, or trading logic exists yet
- the frontend is still a placeholder shell rather than the operator dashboard
- no provider feasibility work has been done yet for the free-source data stack
- Phase 1 does not yet implement real background jobs beyond the skeleton runtime

## Next Milestone

- start Phase 2 from `docs/roadmap.md`
- implement provider adapters, universe snapshots, raw payload storage, and daily canonicalization with incident tracking

## Verification Status

- documentation consistency review: completed manually
- file/path validation for referenced docs: completed for `docs/README.md` links
- backend checks: `ruff format --check`, `ruff check`, `mypy`, and `pytest` passed locally
- coverage check: passed locally at `85.06%`
- frontend checks: `npm run lint`, `npm run test`, and `npm run build` passed locally
- package build: `python -m build` passed locally
- GitHub workflow parity: local commands now cover the same intent as `.github/workflows/ci.yml`

## Last Updated Because

- 2026-03-09: completed Phase 1 scaffolding, verification baseline, and frontend folder naming update
