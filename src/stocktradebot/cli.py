from __future__ import annotations

import json
import webbrowser
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from stocktradebot.api import create_app
from stocktradebot.config import DEFAULT_HOST, DEFAULT_PORT, initialize_config
from stocktradebot.data import backfill_market_data
from stocktradebot.runtime import collect_doctor_checks, prepare_runtime, runtime_status
from stocktradebot.storage import initialize_database, record_audit_event

app = typer.Typer(add_completion=False, help="StockTradeBot command line interface.")


def _placeholder(command_name: str) -> None:
    typer.echo(f"{command_name} is reserved for a later roadmap phase and is not implemented yet.")


AppHomeOption = Annotated[Path | None, typer.Option(file_okay=False, dir_okay=True)]
HostOption = Annotated[str, typer.Option()]
PortOption = Annotated[int, typer.Option()]
NoBrowserOption = Annotated[bool, typer.Option()]
CheckOnlyOption = Annotated[bool, typer.Option()]
ForceOption = Annotated[bool, typer.Option(help="Overwrite the config file with defaults.")]
AsOfOption = Annotated[
    str | None,
    typer.Option(help="Backfill as of this date in YYYY-MM-DD format."),
]
LookbackDaysOption = Annotated[int, typer.Option(min=30)]
SymbolsOption = Annotated[
    list[str] | None,
    typer.Option("--symbol", "-s", help="Repeat to backfill specific symbols."),
]
ProviderNameOption = Annotated[str | None, typer.Option()]


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    app_home: AppHomeOption = None,
    host: HostOption = DEFAULT_HOST,
    port: PortOption = DEFAULT_PORT,
    no_browser: NoBrowserOption = False,
    check_only: CheckOnlyOption = False,
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    bootstrap = prepare_runtime(app_home, host=host, port=port)
    for check in bootstrap.checks:
        icon = "OK" if check.ok else "FAIL"
        typer.echo(f"{icon:>4} {check.name}: {check.detail}")

    typer.echo(f"UI: {bootstrap.ui_url}")
    if check_only:
        return

    if bootstrap.config.open_browser_on_launch and not no_browser:
        webbrowser.open(bootstrap.ui_url)

    uvicorn.run(
        create_app(bootstrap.config, runtime_host=host, runtime_port=port),
        host=host,
        port=port,
        log_level="info",
    )


@app.command()
def init(
    app_home: AppHomeOption = None,
    force: ForceOption = False,
) -> None:
    config = initialize_config(app_home, overwrite=force)
    initialize_database(config)
    record_audit_event(config, "cli", "init command completed")
    typer.echo(f"Initialized StockTradeBot in {config.app_home}")


@app.command()
def doctor(app_home: AppHomeOption = None) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    checks = collect_doctor_checks(config)
    for check in checks:
        icon = "OK" if check.ok else "FAIL"
        typer.echo(f"{icon:>4} {check.name}: {check.detail}")

    if not all(check.ok for check in checks):
        raise typer.Exit(code=1)


@app.command()
def status(app_home: AppHomeOption = None) -> None:
    typer.echo(json.dumps(runtime_status(app_home), indent=2))


def _parse_as_of_date(as_of: str | None) -> date | None:
    if as_of is None:
        return None

    try:
        return date.fromisoformat(as_of)
    except ValueError as exc:
        raise typer.BadParameter("Expected YYYY-MM-DD date format.") from exc


@app.command()
def backfill(
    app_home: AppHomeOption = None,
    as_of: AsOfOption = None,
    lookback_days: LookbackDaysOption = 120,
    symbol: SymbolsOption = None,
    primary_provider: ProviderNameOption = None,
    secondary_provider: ProviderNameOption = None,
) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    summary = backfill_market_data(
        config,
        as_of_date=_parse_as_of_date(as_of),
        lookback_days=lookback_days,
        symbols=symbol,
        primary_provider=primary_provider,
        secondary_provider=secondary_provider,
    )
    typer.echo(json.dumps(asdict(summary), indent=2, default=str))


@app.command()
def train() -> None:
    _placeholder("train")


@app.command()
def backtest() -> None:
    _placeholder("backtest")


@app.command()
def paper() -> None:
    _placeholder("paper")


@app.command()
def live() -> None:
    _placeholder("live")


@app.command()
def report() -> None:
    _placeholder("report")
