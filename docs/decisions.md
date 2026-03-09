# StockTradeBot Accepted Decisions

This file records architectural and product decisions that are locked for implementation unless explicitly superseded by a later decision entry.

## Decision Format

Each decision includes:

- `ID`: stable identifier
- `Status`: `accepted` unless superseded later
- `Date`: date the decision was locked
- `Decision`: the chosen path
- `Why`: the reason the project is standardizing on it
- `Impact`: what later implementation must assume

## Accepted Decisions

### ADR-001: Core Application Stack

- Status: accepted
- Date: 2026-03-09
- Decision: use Python 3.12 for the backend with FastAPI, Typer, SQLAlchemy, Alembic, and APScheduler.
- Why: this stack cleanly supports local services, APIs, scheduling, CLI workflows, persistence, and later automation without fragmenting the codebase.
- Impact: backend services, CLI commands, migrations, and scheduled jobs must be designed around this stack. Deviations require a new decision entry.

### ADR-002: Frontend Stack

- Status: accepted
- Date: 2026-03-09
- Decision: use React with TypeScript and Vite for the browser UI, and bundle the built frontend into the Python package.
- Why: this preserves a clean API boundary, keeps the UI maintainable, and still supports the one-command local launch experience.
- Impact: the UI must not bypass backend APIs by reaching directly into Python internals.

### ADR-003: Product Shape

- Status: accepted
- Date: 2026-03-09
- Decision: v1 is single-user and local-first. macOS and Linux are first-class targets. Windows support is deferred.
- Why: this keeps the operational model narrow enough to ship safely while preserving a future path toward hybrid runtime deployment.
- Impact: no hosted multi-user auth or SaaS tenancy should be introduced in v1 documentation or implementation.

### ADR-004: Market Session Scope

- Status: accepted
- Date: 2026-03-09
- Decision: v1 trading and validation support regular U.S. market hours only.
- Why: regular-hours-only execution is safer, easier to test, and less sensitive to poor liquidity and stale data than extended-hours trading.
- Impact: backtests, paper trading, execution logic, and UI language must all assume regular-hours-only behavior in v1.

### ADR-005: Market-Data Sourcing Policy

- Status: accepted
- Date: 2026-03-09
- Decision: v1 must rely on free market-data and fundamentals sources only.
- Why: this is a project constraint from the repository owner and must shape the architecture from the start.
- Impact: the system must not depend on paid vendor entitlements for baseline operation. If a free source proves unusable, a different free source must be integrated rather than switching to a paid plan by default.

### ADR-006: Canonicalization Policy

- Status: accepted
- Date: 2026-03-09
- Decision: canonical market data is produced through conservative multi-source validation instead of trusting one provider absolutely.
- Why: no free provider is reliable enough to be treated as globally authoritative.
- Impact: all raw values need provenance metadata; disagreements must be quarantined; feature-ready and model-ready datasets may only use values that pass validation rules. This supersedes the earlier Alpha Vantage canonical / Yahoo repair-only assumption.

### ADR-007: Research Scope for V1

- Status: accepted
- Date: 2026-03-09
- Decision: v1 research and promotable production models are daily-first. Intraday research expansion is a later roadmap phase.
- Why: broad, high-quality free intraday history is materially harder than daily history and would otherwise block the project.
- Impact: the architecture must keep the intended 15-minute and 1-hour path open, but the first production-capable system must succeed on daily data before intraday promotion work begins.

### ADR-008: Fundamental Data Policy

- Status: accepted
- Date: 2026-03-09
- Decision: v1 includes approximate point-in-time fundamentals using SEC filing acceptance or availability dates rather than waiting for a perfect commercial-grade fundamentals feed.
- Why: the strategy charter requires fundamental features, and SEC data provides a free path if availability is modeled conservatively.
- Impact: fundamental features must be lagged, stamped with availability metadata, and excluded when the as-of view is uncertain.

### ADR-009: Broker Boundary

- Status: accepted
- Date: 2026-03-09
- Decision: Interactive Brokers is the execution, positions, orders, fills, and live account-state boundary.
- Why: one clear broker boundary reduces runtime ambiguity and keeps simulation/paper/live adapters aligned.
- Impact: live and paper execution adapters must target IBKR first. Broker-agnostic abstractions may exist, but IBKR is the required initial implementation.

### ADR-010: Live Trading Profiles

- Status: accepted
- Date: 2026-03-09
- Decision: the system supports `live-manual` and `live-autonomous` profiles, with `live-manual` as the default and `live-autonomous` additionally gated.
- Why: this preserves operator control while still allowing a future fully automated profile.
- Impact: the mode state machine, UI, promotion rules, and verification logic must distinguish the two live profiles explicitly.

### ADR-011: Quality Gates

- Status: accepted
- Date: 2026-03-09
- Decision: repository-wide test coverage must remain at least 80%, and local verification must track the intent of GitHub workflows.
- Why: the repository is meant to be maintained by agents; weak verification would make that unsafe.
- Impact: any future implementation phase must include the missing test and workflow harness needed to enforce this rule.
