# StockTradeBot Documentation Map

This directory is the operating source of truth for the repository. Agents and human contributors are expected to read these files before making changes.

## Reading Order

Read the documents in this order:

1. [`current-state.md`](/Users/rainzhang/StockTradeBot/docs/current-state.md) for what is implemented now
2. [`plan.md`](/Users/rainzhang/StockTradeBot/docs/plan.md) for the project charter and non-negotiables
3. [`decisions.md`](/Users/rainzhang/StockTradeBot/docs/decisions.md) for accepted architecture decisions and superseded assumptions
4. [`roadmap.md`](/Users/rainzhang/StockTradeBot/docs/roadmap.md) for implementation sequencing and phase gates
5. [`architecture.md`](/Users/rainzhang/StockTradeBot/docs/architecture.md) for system structure, interfaces, runtime, and storage
6. [`data-modeling.md`](/Users/rainzhang/StockTradeBot/docs/data-modeling.md) for data ingestion, canonicalization, features, datasets, and lineage
7. [`trading-system.md`](/Users/rainzhang/StockTradeBot/docs/trading-system.md) for signal-to-order behavior, risk authority, and promotion rules
8. [`product-ui.md`](/Users/rainzhang/StockTradeBot/docs/product-ui.md) for operator flows and UI requirements
9. [`engineering.md`](/Users/rainzhang/StockTradeBot/docs/engineering.md) for code quality, testing, CI, security, and release rules
10. [`operator-guide.md`](/Users/rainzhang/StockTradeBot/docs/operator-guide.md) for supported operator workflows and safety usage
11. [`troubleshooting.md`](/Users/rainzhang/StockTradeBot/docs/troubleshooting.md) for common failures and recovery paths
12. [`release-process.md`](/Users/rainzhang/StockTradeBot/docs/release-process.md) for release verification and packaging workflow

Agents must read every file under `docs/` in full before changing the project. The reading order above is the minimum required route through the documentation.

## Precedence Rules

When documentation appears to overlap, interpret it in this order:

1. `current-state.md` describes current reality
2. `decisions.md` records accepted choices and explicit supersessions
3. subsystem specifications define implementation details
4. `plan.md` defines the charter, target shape, and non-negotiables
5. `roadmap.md` defines sequencing and readiness gates

If two files conflict, contributors must stop and resolve the documentation mismatch before continuing implementation.

## Purpose of Each File

- `current-state.md`: auditable implementation snapshot and active next steps
- `plan.md`: concise strategic charter and product constraints
- `decisions.md`: architecture decision record log
- `roadmap.md`: implementation phases with dependencies and exit criteria
- `architecture.md`: repo structure, runtime topology, CLI, API, config, and persistence contracts
- `data-modeling.md`: market data, fundamentals, feature engineering, labels, and reproducibility rules
- `trading-system.md`: alpha-to-execution flow, risk overrides, modes, and promotion gates
- `product-ui.md`: operator-facing UX and setup experience
- `engineering.md`: development workflow, test policy, CI, observability, and release discipline
- `operator-guide.md`: operator-facing install, setup, and daily workflow guidance
- `troubleshooting.md`: common issue diagnosis and recovery guidance
- `release-process.md`: release checklist and packaged runtime smoke expectations

## Documentation Update Rules

Update the docs whenever a change:

- alters an interface, config, or runtime contract
- changes the roadmap or phase status
- changes what is implemented right now
- adds or removes a dependency that matters to development or operations
- changes a safety, validation, or live-trading rule

At the end of every completed task, update `current-state.md` last so it reflects the final repository state.
