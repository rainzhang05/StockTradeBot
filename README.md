# Stock Trade Bot

Stock trading bot with a browser-based operator workspace for research, simulation, paper trading, and live operations.

<p align="center">
  <img src="docs/assets/stocktradebot-ui-sample.png" alt="Stock Trade Bot operator workspace sample" width="620">
</p>

Stock Trade Bot packages the repository's documented local-first stock trading workflow into a single `stocktradebot` command. By default it prepares the runtime and opens the operator workspace in the browser, while the full direct command surface remains available for setup, data backfill, intraday research, backtesting, simulation, paper trading, and live runtime tasks.

## Quickstart

Install `pipx` and the package:

```bash
python3 -m pip install --user pipx
pipx ensurepath
pipx install stocktradebot
```

Published releases are shipped to PyPI by [publish-pypi.yml](/Users/rainzhang/StockTradeBot/.github/workflows/publish-pypi.yml). If you are preparing the first release, configure the PyPI Trusted Publisher described in [release-process.md](/Users/rainzhang/StockTradeBot/docs/release-process.md) before expecting `pipx install stocktradebot` to resolve from PyPI.

Open the app from anywhere in your terminal with:

```bash
stocktradebot
```

`stocktradebot` launches the local runtime and opens the operator workspace after the package is installed.

On first launch, `stocktradebot` creates the default application home under `~/.stocktradebot/`.

## Disclaimer
Stock asset trading involves substantial financial risk, including the possible loss of all capital. This software does not guarantee profitability, capital preservation, or suitability for any particular purpose.

Any historical performance information, including backtests, simulations, or paper-trading results, is provided for informational purposes only and does not guarantee future results. Market conditions, liquidity, execution quality, exchange behavior, and other real-world factors may cause live outcomes to differ materially from prior evaluations.

Users should trade only with assets they can afford to lose. Each user is solely responsible for properly configuring, testing, validating, and operating the software, and for any financial outcomes arising from its use. Use of this software is entirely at the user’s own risk.

## Docs

- [Stock Trade Bot Documentation](docs/)
- [Commands](docs/commands.md)

This repository is licensed under the [MIT License](LICENSE).
