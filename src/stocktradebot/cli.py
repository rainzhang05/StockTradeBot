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
from stocktradebot.config import DEFAULT_HOST, DEFAULT_PORT, AppConfig, initialize_config
from stocktradebot.data import backfill_market_data
from stocktradebot.execution import (
    approve_live_trading_run,
    arm_live_mode,
    live_status,
    paper_status,
    paper_trade_day,
    prepare_live_trading_day,
    run_live_trading_day,
    simulate_trading_day,
    simulation_status,
)
from stocktradebot.models import backtest_model, model_status, train_model
from stocktradebot.observability import record_operational_event
from stocktradebot.runtime import collect_doctor_checks, prepare_runtime, runtime_status
from stocktradebot.storage import initialize_database, record_audit_event

app = typer.Typer(add_completion=False, help="StockTradeBot command line interface.")


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
ModelVersionOption = Annotated[
    str | None, typer.Option(help="Use a specific trained model version.")
]
RunOption = Annotated[
    bool,
    typer.Option(help="Execute the trading workflow instead of showing status."),
]
ArmOption = Annotated[bool, typer.Option(help="Arm the requested live profile.")]
ProfileOption = Annotated[
    str,
    typer.Option(help="Live profile: manual or autonomous."),
]
ApproveAllOption = Annotated[
    bool,
    typer.Option(help="Approve every pending live-manual order in the selected run."),
]
ApproveSymbolsOption = Annotated[
    list[str] | None,
    typer.Option("--approve-symbol", help="Approve specific live-manual symbols."),
]
RejectSymbolsOption = Annotated[
    list[str] | None,
    typer.Option("--reject-symbol", help="Reject specific live-manual symbols."),
]
RunIdOption = Annotated[
    int | None,
    typer.Option(help="Target a specific prepared live-manual run id."),
]
AckDisableApprovalsOption = Annotated[
    bool,
    typer.Option(
        help=(
            "Required when arming or running live-autonomous because "
            "per-order approval is disabled."
        )
    ),
]


def _log_cli_event(
    config: AppConfig,
    *,
    command: str,
    message: str,
    level: str = "info",
    details: dict[str, object] | None = None,
) -> None:
    record_operational_event(
        config,
        category=f"cli:{command}",
        message=message,
        level=level,
        details=details,
    )


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
    _log_cli_event(
        bootstrap.config,
        command="main",
        message="launch command invoked",
        details={"check_only": check_only, "no_browser": no_browser},
    )
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
    _log_cli_event(
        config, command="init", message="init command completed", details={"force": force}
    )
    typer.echo(f"Initialized StockTradeBot in {config.app_home}")


@app.command()
def doctor(app_home: AppHomeOption = None) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    checks = collect_doctor_checks(config)
    _log_cli_event(
        config,
        command="doctor",
        message="doctor command completed",
        level="info" if all(check.ok for check in checks) else "warning",
        details={"failed_checks": [check.name for check in checks if not check.ok]},
    )
    for check in checks:
        icon = "OK" if check.ok else "FAIL"
        typer.echo(f"{icon:>4} {check.name}: {check.detail}")

    if not all(check.ok for check in checks):
        raise typer.Exit(code=1)


@app.command()
def status(app_home: AppHomeOption = None) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    _log_cli_event(config, command="status", message="status command completed")
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
    _log_cli_event(
        config,
        command="backfill",
        message="market-data backfill completed",
        details={"run_id": summary.run_id, "canonical_count": summary.canonical_count},
    )
    typer.echo(json.dumps(asdict(summary), indent=2, default=str))


@app.command()
def train(
    app_home: AppHomeOption = None,
    as_of: AsOfOption = None,
) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    try:
        summary = train_model(config, as_of_date=_parse_as_of_date(as_of))
    except RuntimeError as exc:
        _log_cli_event(
            config,
            command="train",
            message="training command failed",
            level="error",
            details={"error": str(exc)},
        )
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _log_cli_event(
        config,
        command="train",
        message="training command completed",
        details={"run_id": summary.run_id, "model_version": summary.model_version},
    )
    typer.echo(json.dumps(asdict(summary), indent=2, default=str))


@app.command()
def backtest(
    app_home: AppHomeOption = None,
    model_version: ModelVersionOption = None,
) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    try:
        summary = backtest_model(config, model_version=model_version)
    except RuntimeError as exc:
        _log_cli_event(
            config,
            command="backtest",
            message="backtest command failed",
            level="error",
            details={"error": str(exc)},
        )
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _log_cli_event(
        config,
        command="backtest",
        message="backtest command completed",
        details={"run_id": summary.run_id, "model_version": summary.model_version},
    )
    typer.echo(json.dumps(asdict(summary), indent=2, default=str))


@app.command()
def simulate(
    app_home: AppHomeOption = None,
    as_of: AsOfOption = None,
    model_version: ModelVersionOption = None,
) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    try:
        summary = simulate_trading_day(
            config,
            as_of_date=_parse_as_of_date(as_of),
            model_version=model_version,
        )
    except RuntimeError as exc:
        _log_cli_event(
            config,
            command="simulate",
            message="simulation command failed",
            level="error",
            details={"error": str(exc)},
        )
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _log_cli_event(
        config,
        command="simulate",
        message="simulation command completed",
        details={"run_id": summary.run_id, "mode": summary.mode},
    )
    typer.echo(json.dumps(asdict(summary), indent=2, default=str))


@app.command()
def paper(
    app_home: AppHomeOption = None,
    run: RunOption = False,
    as_of: AsOfOption = None,
    model_version: ModelVersionOption = None,
) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    try:
        if run:
            summary = paper_trade_day(
                config,
                as_of_date=_parse_as_of_date(as_of),
                model_version=model_version,
            )
            _log_cli_event(
                config,
                command="paper",
                message="paper command completed",
                details={"run_id": summary.run_id, "mode": summary.mode},
            )
            typer.echo(json.dumps(asdict(summary), indent=2, default=str))
            return
        _log_cli_event(config, command="paper", message="paper status requested")
        typer.echo(json.dumps(paper_status(config), indent=2, default=str))
    except RuntimeError as exc:
        _log_cli_event(
            config,
            command="paper",
            message="paper command failed",
            level="error",
            details={"error": str(exc)},
        )
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def live(
    app_home: AppHomeOption = None,
    arm: ArmOption = False,
    run: RunOption = False,
    profile: ProfileOption = "manual",
    as_of: AsOfOption = None,
    model_version: ModelVersionOption = None,
    run_id: RunIdOption = None,
    approve_all: ApproveAllOption = False,
    approve_symbol: ApproveSymbolsOption = None,
    reject_symbol: RejectSymbolsOption = None,
    ack_disable_approvals: AckDisableApprovalsOption = False,
) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    try:
        if arm:
            arm_summary = arm_live_mode(
                config,
                profile=profile,
                ack_disable_approvals=ack_disable_approvals,
                source="cli",
                reason="live arm requested from CLI",
            )
            _log_cli_event(
                config,
                command="live",
                message="live arm command completed",
                details={"current_mode": arm_summary.current_mode, "status": arm_summary.status},
            )
            typer.echo(json.dumps(asdict(arm_summary), indent=2, default=str))
            return
        if run:
            if approve_all or approve_symbol or reject_symbol or run_id is not None:
                approval_summary = approve_live_trading_run(
                    config,
                    run_id=run_id,
                    approve_all=approve_all,
                    approve_symbols=approve_symbol,
                    reject_symbols=reject_symbol,
                )
                _log_cli_event(
                    config,
                    command="live",
                    message="live approvals processed",
                    details={"status": approval_summary.status, "run_id": approval_summary.run_id},
                )
                typer.echo(json.dumps(asdict(approval_summary), indent=2, default=str))
                return
            status_snapshot = live_status(config)
            current_mode = None
            if status_snapshot["mode_state"] is not None:
                current_mode = status_snapshot["mode_state"]["current_mode"]
            if current_mode == "live-autonomous":
                run_summary = run_live_trading_day(
                    config,
                    as_of_date=_parse_as_of_date(as_of),
                    model_version=model_version,
                    ack_disable_approvals=ack_disable_approvals,
                )
                _log_cli_event(
                    config,
                    command="live",
                    message="live-autonomous run completed",
                    details={"status": run_summary.status, "run_id": run_summary.run_id},
                )
                typer.echo(json.dumps(asdict(run_summary), indent=2, default=str))
                return
            preparation_summary = prepare_live_trading_day(
                config,
                as_of_date=_parse_as_of_date(as_of),
                model_version=model_version,
            )
            _log_cli_event(
                config,
                command="live",
                message="live-manual preparation completed",
                details={
                    "status": preparation_summary.status,
                    "run_id": preparation_summary.run_id,
                },
            )
            typer.echo(json.dumps(asdict(preparation_summary), indent=2, default=str))
            return
        _log_cli_event(config, command="live", message="live status requested")
        typer.echo(json.dumps(live_status(config), indent=2, default=str))
    except RuntimeError as exc:
        _log_cli_event(
            config,
            command="live",
            message="live command failed",
            level="error",
            details={"error": str(exc)},
        )
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def report(app_home: AppHomeOption = None) -> None:
    config = initialize_config(app_home)
    initialize_database(config)
    _log_cli_event(config, command="report", message="report command completed")
    typer.echo(
        json.dumps(
            {
                "models": model_status(config),
                "simulation": simulation_status(config),
                "paper": paper_status(config),
                "live": live_status(config),
            },
            indent=2,
            default=str,
        )
    )
