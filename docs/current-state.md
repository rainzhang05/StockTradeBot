# StockTradeBot Current State

This file describes the repository as it exists now. Update it at the end of every completed task.

## Repository Snapshot

- Date: 2026-03-10
- Branch: `main`
- Repository state: Phase 9 intraday research expansion implemented with simplified operator UI and hardened packaged CLI bootstrap
- Application code: package, CLI, API, runtime, storage, operator frontend, packaged frontend asset serving, structured operational logging, daily and intraday market-data pipelines, fundamentals ingestion, daily and intraday dataset generation, model training, daily and intraday walk-forward validation, backtesting, portfolio construction, risk freezes, simulation execution, broker integration, paper execution, live-manual approvals, live-autonomous gating, config mutation APIs, mode-control APIs, and operator workspace aggregation created
- CI/workflows: GitHub Actions are split into focused workflow files for backend quality, backend tests, frontend unit/build checks, frontend browser E2E, and package verification
- Tests: backend and frontend verification suites created through Phase 9
- Database schema: Phase 9 SQLite schema and Alembic migrations created
- Frontend: React/Vite operator UI created under `frontend/`, served by the Python runtime when built, and now presented as a simplified four-view operator surface

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
- added broker configuration for the IBKR Client Portal gateway, paper and live account ids, operator identity, and live gate thresholds
- added Phase 6 storage for broker account snapshots, broker position snapshots, broker orders, order approvals, and mode transition audit events
- added an IBKR Client Portal HTTP client plus a broker adapter service layer that can be swapped with fakes in tests
- implemented `stocktradebot paper` status and run flows, broker-state synchronization, and persisted broker order/fill telemetry
- implemented `stocktradebot live` status, arming, live-manual preparation, approval submission, and live-autonomous gate enforcement
- added broker, paper, and live API endpoints plus runtime/doctor broker health reporting
- updated promotion-gate evaluation so paper safe-day history now comes from persisted paper-run outcomes rather than a hard-coded placeholder
- added Phase 6 broker integration tests for paper execution, live-manual approvals, live-autonomous blocking, IBKR client parsing, and CLI/API control surfaces
- resolved the mode-state-machine documentation conflict so live modes can retreat directly to safer modes
- added validated config patch persistence for the operator setup flow
- added Phase 7 API endpoints for operator workspace aggregation, audit-feed retrieval, config updates, system mode transitions, and market-data backfill control
- added simulation retreat support from live-manual and live-autonomous plus a guard that blocks leaving frozen mode while an active freeze still exists
- replaced the frontend placeholder with a full operator UI covering setup, dashboard, portfolio, orders, research, data, and system screens
- added browser-tested manual approval, research, setup, and mode-control workflows in a dedicated frontend E2E lane
- updated the fallback frontend placeholder and README to describe the Phase 7 operator UI
- packaged the built frontend into release artifacts and updated runtime asset discovery so installed builds serve the operator UI instead of the placeholder page
- added structured JSONL operational logging, API exposure for recent logs, and a System-screen operational log feed
- hardened package verification to build the frontend, build the wheel, install it in isolation, and smoke-test the installed runtime UI path
- fixed editable-install metadata generation so backend workflows and fresh source installs no longer require `frontend/dist` to exist before `pip install -e ".[dev]"`
- added operator guide, troubleshooting guidance, and an explicit release process for the local-first shipped workflow
- added intraday frequency specifications, intraday research configuration, and storage metadata for per-frequency backfills, datasets, validations, model training runs, and backtests
- added Alpha Vantage intraday provider support, intraday observation/canonical tables, Phase 9 Alembic migration, and session-level intraday quality reports
- implemented intraday canonicalization, intraday market-data backfill/status flows, and fallback universe-snapshot handling so research can bootstrap from the earliest available universe snapshot when historical snapshot coverage is sparse
- implemented intraday feature generation, label generation, dataset artifact export, walk-forward validation, and API/CLI entrypoints for intraday backfill, dataset builds, and validation runs
- added Phase 9 unit and integration coverage for intraday canonicalization, research flow, API surfaces, CLI surfaces, and typing/lint verification for the new intraday modules
- simplified the frontend into `Overview`, `Stocks`, `Activity`, and `Setup` so the default UI shows only operator-essential information in a black-and-white, smooth-radius presentation aimed at non-technical users
- removed raw JSON-style operational panels from the default operator experience and replaced them with plain-language activity summaries, essential performance cards, and stock-by-stock status actions
- hardened runtime migration lookup so installed packages prefer bundled Alembic assets, fall back to repository assets only when appropriate, and fail with a clear reinstall message when both are missing
- updated package smoke verification so installed builds must pass `stocktradebot status` and `stocktradebot --check-only --no-browser` in addition to the existing `init`, `doctor`, and bundled-frontend checks
- corrected the persisted app-state schema marker written during database bootstrap from `phase6` to `phase9`

## Subsystem Status Matrix

| Subsystem | Status | Notes |
| --- | --- | --- |
| Governance docs | Complete for Phase 0 | Core doc set exists and defines repo operating rules |
| Python package | Complete for Phase 1 | `pyproject.toml`, editable install metadata, and CLI entrypoint exist |
| Backend API | Complete for Phase 9 | FastAPI app exposes health, setup, config, daily and intraday market-data, daily and intraday dataset, daily and intraday validation, backtest, risk, portfolio, order, fill, broker, paper, live, and frontend-serving endpoints |
| Database/storage | Complete for Phase 9 | SQLite bootstrap, Alembic migrations, daily and intraday market-data tables, dataset tables, model registry tables, mode state, freeze state, simulation runs, broker snapshots, broker orders, approvals, transition audit, and raw/artifact storage exist; installed runtimes now prefer packaged Alembic assets during bootstrap |
| Data ingestion | Complete for Phase 9 | Provider adapters, raw payload persistence, canonical daily bars, canonical intraday bars, incidents, universe snapshots, SEC fundamentals, and intraday quality reporting are implemented |
| Features/fundamentals | Complete for Phase 9 | Availability-aware daily and intraday feature generation, labels, dataset lineage, and artifact export are implemented |
| Models/backtesting | Complete for Phase 9 | Deterministic baseline training, daily and intraday walk-forward validation, event-driven backtests, persisted reports, and model registry entries are implemented |
| Portfolio/risk/execution | Complete for Phase 6 | Regime-aware portfolio construction, risk freeze engine, simulation runs, paper execution, live-manual approval workflows, and trading status surfaces are implemented |
| IBKR integration | Complete for Phase 6 | IBKR Client Portal client, paper/live adapters, broker-state sync, manual approvals, and autonomous gating are implemented |
| Frontend/UI | Complete for Phase 9 | The operator experience is now consolidated into `Overview`, `Stocks`, `Activity`, and `Setup`; live approval UX, mode controls, and packaged frontend serving remain implemented while the default surface hides raw backend payloads and unnecessary engineering detail |
| Tests/coverage | Complete for Phase 9 | Backend pytest coverage is enforced at `>= 80%`; frontend tests run with Vitest and browser E2E; package smoke verification now tests installed runtime serving plus installed `status` and `--check-only` command flows; intraday research paths are covered by unit and integration tests |
| GitHub Actions | Complete for Phase 9 | Focused workflows cover backend quality, backend tests, frontend checks, frontend E2E, and package build plus installed-wheel smoke verification for the current intraday-capable codebase, including direct installed-command runtime checks |

## Active Constraints

- v1 must remain single-user and local-first
- v1 trading is regular-hours-only
- free-source-only market-data policy is in force
- v1 production trading and promotion remain daily-first even though intraday research and validation are now supported
- approximate point-in-time fundamentals are allowed only with conservative availability handling
- live-manual is the default live profile; live-autonomous requires stricter gates
- repository-wide test coverage target is `>= 80%` once code and tests exist
- verified canonical bars still require a corroborating secondary provider; the default Stooq-only setup yields provisional bars until a secondary source is enabled
- dataset builds require a prior backfill because the feature pipeline depends on persisted canonical bars and universe snapshots
- intraday research currently depends on free-source intraday coverage quality and can fall back to the earliest available universe snapshot when older historical snapshot coverage is missing
- simulation mode may use research-only models under the current default config
- paper mode requires a configured IBKR paper account and authenticated local gateway access
- live-manual requires explicit arming, a candidate model, no active freeze, enough safe paper days, and operator approval before submission
- live-autonomous remains blocked unless the stricter autonomous gates are satisfied and the operator explicitly acknowledges approval bypass

## Known Gaps

- live-autonomous execution support exists, but a fresh repository will still block it because the stricter safe-day requirements are intentionally unmet
- the IBKR adapter assumes a local authenticated Client Portal Gateway and does not yet manage gateway startup or login orchestration
- the built-in stock candidate seed list is a bootstrap set rather than a full ~300-name universe; wider coverage depends on configuring more candidate symbols
- background scheduling is still limited to the skeleton runtime; backfill, training, backtests, and simulations are currently CLI/API driven rather than scheduler-driven
- the setup UI can update runtime paths inside the current app home, but relocating the app home root itself still depends on the CLI or `STOCKTRADEBOT_HOME`
- a stale `pipx` install built before the packaging fixes will still need a reinstall to pick up the bundled Alembic assets and rebuilt frontend

## Next Milestone

- Phase 9 is implemented; the next roadmap phase is not yet defined in `docs/roadmap.md`
- preserve the daily-first production baseline while deciding whether any post-Phase 9 expansion is warranted

## Verification Status

- documentation consistency review: completed manually
- file/path validation for referenced docs: completed for `docs/README.md` links
- backend checks: `make backend-quality` and `make backend-tests` passed locally
- coverage check: passed locally at `81.49%`
- frontend checks: `npm run lint`, `npm run test -- --run`, and `npm run build` passed locally in `frontend/`
- frontend browser E2E: `make frontend-e2e` passed locally
- package build: `make package-check` passed locally
- repository verification: `make check` passed locally after the Phase 9 intraday implementation
- package smoke verification: local and CI package checks now build the frontend, install the built wheel in isolation, verify `init`, `doctor`, `status`, and `stocktradebot --check-only --no-browser`, and confirm the installed runtime serves the bundled UI
- editable install smoke: passed locally from a fresh source copy with `frontend/dist` removed, using `python -m pip install -e ".[dev]"` under Python 3.14
- GitHub workflow parity: `make check` passed locally and maps to the same intent as the split workflow files under `.github/workflows/`
- backend-served browser smoke: passed locally against a built frontend runtime and confirmed the packaged UI rendered instead of the placeholder page
- Phase 9 integration verification: full pytest suite passed locally, including daily and intraday API flows, intraday dataset and validation paths, paper execution, live-manual preparation and approval, config mutation, mode transitions, and browser-driven operator workflows

## Last Updated Because

- 2026-03-10: simplified the operator UI for non-technical use, hardened packaged CLI bootstrap around bundled Alembic assets, verified the repository with `make check`, and updated the docs to reflect the new runtime and UI behavior
