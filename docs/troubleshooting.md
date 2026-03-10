# StockTradeBot Troubleshooting

This guide covers the most common local operator failures for the current Phase 9 flow.

## UI Shows The Placeholder Page

Symptoms:

- the browser loads a static placeholder instead of the operator dashboard

Checks:

1. if running from source, build the frontend with `cd frontend && npm run build`
2. if running from an installed package, rebuild or reinstall the release artifact because packaged frontend assets should already be bundled
3. confirm the recent activity feed does not show frontend asset lookup failures

## `stocktradebot` Fails With A Missing `alembic` Path

Symptoms:

- the CLI exits with a traceback ending in `Path doesn't exist: .../alembic`

Fix:

1. reinstall from a fresh current build so the packaged Alembic assets are included
2. rerun `stocktradebot doctor`
3. rerun `stocktradebot --check-only --no-browser` before launching the full runtime

This failure usually means the installed package is stale or missing bundled migration assets, not that your local app data is wrong.

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

- training, backtest, or simulation actions fail due to missing universe snapshots

Fix:

1. run `Refresh data` from `Overview` or use the CLI backfill command
2. confirm the latest activity feed now shows a completed backfill
3. retry training or simulation

## Intraday Validation Returns `Expand the intraday history first`

Symptoms:

- intraday validation cannot build walk-forward folds

Fix:

1. run `stocktradebot intraday-backfill --frequency 15min` or the matching `1h` flow with enough lookback history
2. build an intraday dataset with `stocktradebot intraday-dataset --frequency ...`
3. rerun intraday validation after confirmed verified intraday bars and dataset rows exist

## System Remains Frozen

Symptoms:

- mode transitions are blocked while the system is frozen

Checks:

1. inspect the active freeze reason in `Overview`
2. inspect the recent activity feed for the failure that triggered the freeze
3. inspect the latest data incident summary and broker readiness state
4. resolve the underlying data, broker, or model issue before retrying a mode change

## Where To Look First During Any Failure

Use this order:

1. `Overview`
2. `Activity`
3. `Stocks`
4. CLI `stocktradebot doctor`
