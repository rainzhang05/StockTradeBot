# StockTradeBot Charter

## Mission

StockTradeBot is a local-first, open-source, production-grade stock trading platform for a single operator. It combines a Python backend, a browser-based React UI, deterministic risk controls, and a disciplined research-to-production workflow so the project can be maintained safely by both humans and AI agents.

The system exists to maximize long-term return while preserving auditability, reproducibility, and operator control.

## Product Commitments

The default user journey is:

```bash
pipx install stocktradebot
stocktradebot
```

Running `stocktradebot` must eventually:

1. initialize required local directories and state
2. start the local backend runtime
3. launch the local web UI in the default browser
4. guide the user through first-run setup

The v1 product is:

- single-user
- local-first
- cash-only
- long-only
- U.S. stocks plus a curated ETF universe
- regular U.S. market hours only
- browser-based with a black-and-white dominant interface

## Trading and Modeling Charter

The production strategy is a multi-layer systematic trading system with:

- cross-sectional ranking as the core alpha output
- technical, cross-sectional, regime, liquidity, and fundamental features
- linear plus boosting model families as the production model stack
- optimizer-based portfolio construction with deterministic constraints
- adaptive execution behavior
- regime-aware exposure control
- event-driven backtesting and promotion gates

The target decision architecture remains multi-timeframe around 15-minute, 1-hour, and daily context. For v1 research and production readiness, daily data is the required baseline. Intraday research expansion is a later phase and must not be assumed complete before it is built and validated.

## Data Charter

The repository is constrained to free market-data and fundamentals sources for v1.

Canonical data policy is conservative:

- no single provider is treated as universally canonical
- raw provider data must be stored with provenance
- canonical bars and fields are accepted only after validation rules pass
- provider disagreements are quarantined rather than silently merged
- unresolved discrepancies are treated as data-quality failures
- repaired values must remain auditable

Point-in-time correctness is mandatory for fundamentals. V1 may use approximate point-in-time fundamentals derived from SEC filing acceptance or availability dates, but future leakage is never allowed.

## Safety Charter

The platform must default to simulation mode and support:

- backtesting
- local simulation
- paper trading
- live-manual trading
- live-autonomous trading

Live-manual is the default live profile. Live-autonomous is supported only after stricter promotion gates are satisfied.

The risk layer always has override authority above alpha, portfolio, and execution intent. The system must auto-freeze on data, broker, model, or execution integrity failures.

Before live eligibility, a model must pass walk-forward validation, benchmark comparison, regime-split review, and at least 30 market days of paper trading.

## Non-Negotiables

The following constraints are mandatory unless they are explicitly revised in `docs/decisions.md`:

- cash-only, no leverage, no shorting
- U.S. stocks plus curated ETFs only
- regular-hours-only v1 execution
- end-of-bar decision engine
- cross-sectional ranking alpha
- technical plus cross-sectional plus fundamental feature architecture
- linear plus boosting ensemble core
- optimizer-based portfolio construction
- adaptive execution
- event-driven backtesting
- simulation as the default runtime mode
- explicit live warnings and user confirmation
- deterministic safety overrides and freeze logic
- IBKR as the execution and live-state boundary
- local-first architecture
- one-command installation and launch target via `pipx`
- repository-wide test coverage of at least 80%
- GitHub workflow parity with local verification

## Documentation Contract

This file is the charter, not the complete implementation spec.

Implementation details live in the rest of the `docs/` tree. Agents must use:

- `current-state.md` for current reality
- `decisions.md` for accepted choices and supersessions
- subsystem specs for concrete behavior and interfaces
- `roadmap.md` for sequencing

All implementation work must keep the repository aligned with this charter.
