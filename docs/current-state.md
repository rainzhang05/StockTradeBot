# StockTradeBot Current State

This file describes the repository as it exists now. Update it at the end of every completed task.

## Repository Snapshot

- Date: 2026-03-09
- Branch: `main`
- Repository state: documentation-first bootstrap
- Application code: not started
- CI/workflows: not started
- Tests: not started
- Database schema: not started
- Frontend: not started

## Completed Work

- created the root `AGENTS.md` workflow contract
- created the documentation map in `docs/README.md`
- rewrote `docs/plan.md` into a concise charter
- added architecture, data/modeling, trading, product UI, engineering, roadmap, and decisions specifications

## Subsystem Status Matrix

| Subsystem | Status | Notes |
| --- | --- | --- |
| Governance docs | Complete for Phase 0 | Core doc set exists and defines repo operating rules |
| Python package | Not started | No `pyproject.toml`, package, or CLI yet |
| Backend API | Not started | FastAPI app not created |
| Database/storage | Not started | SQLite/Alembic design documented only |
| Data ingestion | Not started | Provider adapters and canonicalization not implemented |
| Features/fundamentals | Not started | Specifications exist only |
| Models/backtesting | Not started | No training or validation code yet |
| Portfolio/risk/execution | Not started | Trading-system rules documented only |
| IBKR integration | Not started | No broker code yet |
| Frontend/UI | Not started | React app not created |
| Tests/coverage | Not started | No test harness or coverage tooling yet |
| GitHub Actions | Not started | No workflow files yet |

## Active Constraints

- v1 must remain single-user and local-first
- v1 trading is regular-hours-only
- free-source-only market-data policy is in force
- v1 research and promotion are daily-first
- approximate point-in-time fundamentals are allowed only with conservative availability handling
- live-manual is the default live profile; live-autonomous requires stricter gates
- repository-wide test coverage target is `>= 80%` once code and tests exist

## Known Gaps

- no runnable application exists yet
- no packaging, CLI, API, database, or frontend scaffolding exists
- no verification harness exists yet for coverage or CI parity
- no provider feasibility work has been done yet for the free-source data stack

## Next Milestone

- start Phase 1 from `docs/roadmap.md`
- create the installable Python package, CLI entrypoint, FastAPI skeleton, SQLite bootstrap, and test/CI baseline

## Verification Status

- documentation consistency review: completed manually
- file/path validation for referenced docs: completed for `docs/README.md` links
- code tests: not applicable, no code yet
- coverage check: not applicable, no code or tests yet
- GitHub workflow parity: not applicable, no workflows yet

## Last Updated Because

- 2026-03-09: initialized the repository documentation system and governance baseline for Phase 0
