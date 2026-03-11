# Stock Trade Bot Commands

This guide lists the current `stocktradebot` commands in straightforward language.

## Basic Launch

```bash
stocktradebot
```

Starts the local runtime, prepares the database if needed, serves the browser UI, and opens the operator workspace unless browser launch is disabled.

Useful top-level options:

- `--app-home PATH`: use a different application home instead of `~/.stocktradebot/`
- `--host TEXT`: change the local bind host
- `--port INTEGER`: change the local port
- `--no-browser`: start the runtime without opening the browser automatically
- `--check-only`: run the startup checks and print the UI URL without starting the server

## Command List

### `stocktradebot init`

Creates the application home, config file, runtime folders, and database.

Example:

```bash
stocktradebot init
```

### `stocktradebot doctor`

Runs readiness checks for storage paths, database connectivity, data providers, artifacts, and broker configuration.

Example:

```bash
stocktradebot doctor
```

### `stocktradebot status`

Prints the current runtime snapshot as JSON, including mode, health checks, recent market-data state, model state, and trading state.

Example:

```bash
stocktradebot status
```

### `stocktradebot backfill`

Fetches daily market data and updates the tracked universe.

Common options:

- `--as-of YYYY-MM-DD`
- `--lookback-days INTEGER`
- `--symbol SYMBOL` and repeat it for multiple symbols
- `--primary-provider NAME`
- `--secondary-provider NAME`

Example:

```bash
stocktradebot backfill --symbol AAPL --symbol MSFT --lookback-days 180
```

### `stocktradebot intraday-backfill`

Fetches intraday research data for `15min` or `1h`.

Common options:

- `--frequency 15min|1h`
- `--as-of YYYY-MM-DD`
- `--lookback-days INTEGER`
- `--symbol SYMBOL`

Example:

```bash
stocktradebot intraday-backfill --frequency 15min --symbol AAPL --lookback-days 20
```

### `stocktradebot intraday-dataset`

Builds an intraday dataset snapshot from the stored intraday history.

Common options:

- `--frequency 15min|1h`
- `--as-of YYYY-MM-DD`

Example:

```bash
stocktradebot intraday-dataset --frequency 15min --as-of 2026-03-10
```

### `stocktradebot intraday-validate`

Runs intraday walk-forward validation for the requested research frequency.

Common options:

- `--frequency 15min|1h`
- `--as-of YYYY-MM-DD`

Example:

```bash
stocktradebot intraday-validate --frequency 15min --as-of 2026-03-10
```

### `stocktradebot train`

Trains the current model from the latest available daily dataset.

Common options:

- `--as-of YYYY-MM-DD`

Example:

```bash
stocktradebot train --as-of 2026-03-10
```

### `stocktradebot backtest`

Runs a backtest for the latest model or a specific model version.

Common options:

- `--model-version VERSION`

Example:

```bash
stocktradebot backtest
```

### `stocktradebot simulate`

Runs the trading workflow in simulation mode and records the resulting portfolio, orders, and fills locally.

Common options:

- `--as-of YYYY-MM-DD`
- `--model-version VERSION`

Example:

```bash
stocktradebot simulate --as-of 2026-03-10
```

### `stocktradebot paper`

Shows paper-trading status by default. With `--run`, it executes a paper-trading day against the configured IBKR paper account.

Common options:

- `--run`
- `--as-of YYYY-MM-DD`
- `--model-version VERSION`

Examples:

```bash
stocktradebot paper
stocktradebot paper --run
```

### `stocktradebot live`

Shows live-trading status by default. It also handles live arming, live-manual preparation, live-autonomous runs, and live approval decisions.

Common options:

- `--arm`
- `--run`
- `--profile manual|autonomous`
- `--as-of YYYY-MM-DD`
- `--model-version VERSION`
- `--run-id INTEGER`
- `--approve-all`
- `--approve-symbol SYMBOL`
- `--reject-symbol SYMBOL`
- `--ack-disable-approvals`

Examples:

```bash
stocktradebot live
stocktradebot live --arm --profile manual
stocktradebot live --run
stocktradebot live --run --approve-all
```

### `stocktradebot report`

Prints a combined JSON report containing model, simulation, paper, and live status information.

Example:

```bash
stocktradebot report
```

## How To Learn More

- Use `stocktradebot --help` for the full top-level help output.
- Use `stocktradebot COMMAND --help` for the options of one specific command.
- Use the [operator guide](operator-guide.md) for the recommended daily workflow.
