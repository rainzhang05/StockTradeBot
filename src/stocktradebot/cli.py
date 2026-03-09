from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from stocktradebot.api import create_app
from stocktradebot.config import DEFAULT_HOST, DEFAULT_PORT, initialize_config
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


@app.command()
def backfill() -> None:
    _placeholder("backfill")


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
