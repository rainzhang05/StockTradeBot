# StockTradeBot Engineering Specification

This document defines how the repository should be built, tested, verified, and released.

## 1. Development Principles

Engineering priorities are:

- correctness over speed
- deterministic behavior over convenience
- auditable changes over implicit behavior
- small safe increments over large rewrites

Because this repository is intended for agent-assisted development, unclear or weakly tested code is a defect.

## 2. Tooling Baseline

Backend baseline:

- Python `3.12`
- FastAPI, Typer, SQLAlchemy, Alembic, APScheduler
- pytest for tests
- coverage.py for coverage enforcement
- ruff for linting and formatting
- mypy for static type checking

Frontend baseline:

- React
- TypeScript
- Vite
- Vitest for frontend unit tests

Repository baseline:

- GitHub Actions for CI automation
- local commands that mirror CI intent

## 3. Coding Rules

Python code must:

- use type hints on public functions and non-trivial internals
- keep side effects explicit at service boundaries
- prefer pure functions for calculations and feature logic
- separate domain logic from IO and framework glue
- avoid hidden global state

TypeScript/React code must:

- keep API interactions explicit and typed
- separate presentation components from data-fetching logic
- make unsafe live actions deliberate and difficult to trigger accidentally

All code must:

- include concise comments only where the logic is not self-evident
- keep configuration and thresholds out of hard-coded magic values where practical
- emit structured logs for operationally relevant events

## 4. Testing Taxonomy

Required test layers:

- `unit`
  - formulas, validations, utilities, feature calculations, optimizer constraints, risk rules
- `integration`
  - database interactions, provider adapters, scheduler jobs, API routes, broker adapter behavior
- `e2e`
  - setup flow, mode transitions, paper/live approvals, critical operator workflows
- `data integrity`
  - canonicalization agreement rules, gap repair logic, as-of fundamentals handling, lineage metadata
- `research validation`
  - backtest reproducibility, dataset-to-model linkage, promotion gate calculations

## 5. Coverage Policy

Repository-wide test coverage must remain `>= 80%`.

Rules:

- no change is complete if coverage drops below threshold
- coverage exclusions must be narrow and justified
- critical modules such as risk, execution, canonicalization, and mode transitions should aim above the repository minimum

Documentation-only tasks may report coverage as not applicable if no code changed.

## 6. CI and Workflow Expectations

GitHub workflows must eventually cover:

- backend lint and type-check
- frontend lint and test
- frontend browser end-to-end workflows
- backend unit and integration tests
- coverage threshold enforcement
- build/package verification

Workflow structure rules:

- split GitHub workflows by concern instead of expanding one monolithic workflow file
- keep backend quality, backend tests, frontend checks, and packaging in separate workflow files unless there is a documented reason not to
- keep browser-based frontend E2E in its own focused workflow instead of folding it into the frontend unit/build workflow
- keep PyPI publication in its own dedicated release workflow instead of folding trusted publishing into the package-verification workflow
- when a new subsystem requires CI coverage, add it to the closest focused workflow or create a new focused workflow if it does not fit an existing one

Local developer commands must mirror CI intent closely enough that a contributor can reproduce failures before pushing.

If a new subsystem is added, the necessary workflow coverage for it must be added in the same phase or the next explicitly planned hardening task.

## 7. Secrets and Configuration Safety

Rules:

- never commit secrets
- keep broker and provider credentials out of tracked config files
- use environment variables or local secret stores for sensitive values
- redact secrets from logs and reports
- avoid writing secret-bearing request payloads into audit logs

## 8. Observability Requirements

The system must emit structured operational data for:

- startup and shutdown
- provider fetch jobs
- data-quality incidents
- mode transitions
- freeze events
- order submission and fill lifecycle
- model load and scoring events
- backtests and training runs

Minimum observability outputs:

- human-readable logs
- machine-parseable structured logs
- persisted audit events for material state changes

## 9. Release and Versioning Rules

Release readiness requires:

- passing CI
- coverage threshold satisfied
- relevant docs updated
- `current-state.md` updated
- packaged CLI launch verified

Versioning rules:

- use semantic versioning for the application package
- version datasets, features, labels, and models independently
- never publish a promoted model without linkage to code and dataset versions

## 10. Commit Discipline

Agents and humans must commit in small, coherent slices.

Commit expectations:

- one logical change per commit
- tests and checks should pass for that slice whenever practical
- documentation updates should travel with the implementation they describe
- commit messages should state the behavioral change, not just the files touched

Large batches of unrelated changes are considered process failures in this repository.
