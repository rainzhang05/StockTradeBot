# StockTradeBot Troubleshooting

This guide covers the most common local operator failures for the Phase 8 release-ready flow.

## UI Shows The Placeholder Page

Symptoms:

- the browser loads a static placeholder instead of the operator dashboard

Checks:

1. if running from source, build the frontend with `cd frontend && npm run build`
2. if running from an installed package, rebuild the release artifact because packaged frontend assets should already be bundled
3. confirm `System -> Operational logs` does not show frontend asset lookup failures

## `doctor` Fails On Fundamentals Provider

Symptoms:

- `SEC fundamentals provider requires a configured user agent`

Fix:

1. open `Setup`
2. enable fundamentals only if you have provided a valid user agent string
3. save the config and rerun `stocktradebot doctor`

## `doctor` Fails On Broker Connectivity

Symptoms:

- `broker-connectivity` is blocked
- paper or live status shows gateway connectivity failures

Fix:

1. confirm the IBKR Client Portal Gateway is running locally
2. confirm the gateway URL in `Setup` matches the local gateway
3. confirm both paper and live account ids are set when broker integration is enabled
4. rerun `stocktradebot doctor`

## Backfill Or Research Actions Return `Run backfill first`

Symptoms:

- dataset build, training, backtest, or simulation endpoints fail due to missing universe snapshots

Fix:

1. run a market-data backfill from the `Data` screen or CLI
2. confirm `Data` now shows a latest universe snapshot and a completed backfill
3. retry dataset build or training

## System Remains Frozen

Symptoms:

- mode transitions are blocked while the system is frozen

Checks:

1. inspect the active freeze reason on `Dashboard` or `System`
2. inspect `Data` for unresolved incidents
3. inspect `System -> Operational logs` for the failure that triggered the freeze
4. resolve the underlying data, broker, or model issue before retrying a mode change

## Where To Look First During Any Failure

Use this order:

1. `System -> Operational logs`
2. `System -> Audit events`
3. `Dashboard` freeze and broker status cards
4. `Data` incidents and latest backfill summary
5. CLI `stocktradebot doctor`