from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stocktradebot.config import initialize_config
from stocktradebot.execution import (
    approve_live_trading_run,
    arm_live_mode,
    enter_paper_mode,
    enter_simulation_mode,
    paper_trade_day,
    prepare_live_trading_day,
    simulation_status,
)
from stocktradebot.models import train_model
from stocktradebot.storage import CanonicalDailyBar, FreezeEvent, SystemModeState, create_db_engine
from tests.fixtures.phase6_broker import (
    FakeBrokerAdapter,
    mark_latest_model_candidate,
    seed_safe_paper_days,
)
from tests.fixtures.phase_data import seed_phase3_research_data


def _configure_broker(config) -> None:
    config.broker.enabled = True
    config.broker.paper_account_id = "DU1234567"
    config.broker.live_account_id = "U1234567"
    config.broker.live_manual_min_paper_days = 30
    config.broker.live_autonomous_min_safe_days = 60
    config.save()


def _broker_prices(config) -> dict[str, float]:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            latest_trade_date = session.scalar(select(func.max(CanonicalDailyBar.trade_date)))
            if latest_trade_date is None:
                raise RuntimeError("No canonical bars are available for broker pricing.")
            bars = session.scalars(
                select(CanonicalDailyBar).where(
                    CanonicalDailyBar.symbol.in_(("AAPL", "MSFT", "SPY")),
                    CanonicalDailyBar.trade_date == latest_trade_date,
                )
            ).all()
        return {bar.symbol: bar.close for bar in bars}
    finally:
        engine.dispose()


def test_paper_trade_day_executes_end_to_end(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    seed_phase3_research_data(config)
    _configure_broker(config)
    train_model(config, as_of_date=date(2026, 4, 15))
    adapter = FakeBrokerAdapter(
        environment="paper",
        account_id=config.broker.paper_account_id or "DU1234567",
        starting_cash=100_000.0,
        prices=_broker_prices(config),
    )

    summary = paper_trade_day(
        config,
        as_of_date=date(2026, 4, 15),
        adapter=adapter,
    )

    assert summary.mode == "paper"
    assert summary.status == "completed"
    assert summary.order_count > 0
    assert summary.fill_count > 0
    assert (config.app_home / summary.artifact_path).exists()

    snapshot = simulation_status(config)

    assert snapshot["mode_state"]["current_mode"] == "paper"
    assert snapshot["latest_run"]["mode"] == "paper"
    assert snapshot["latest_broker_account_snapshot"]["account_id"] == "DU1234567"
    assert snapshot["latest_broker_orders"]


def test_live_manual_flow_prepares_and_approves_orders(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    seed_phase3_research_data(config)
    _configure_broker(config)
    train_model(config, as_of_date=date(2026, 4, 15))
    mark_latest_model_candidate(config)
    seed_safe_paper_days(config, day_count=30)

    paper_adapter = FakeBrokerAdapter(
        environment="paper",
        account_id=config.broker.paper_account_id or "DU1234567",
        starting_cash=100_000.0,
        prices=_broker_prices(config),
    )
    paper_trade_day(
        config,
        as_of_date=date(2026, 4, 15),
        adapter=paper_adapter,
    )

    live_adapter = FakeBrokerAdapter(
        environment="live",
        account_id=config.broker.live_account_id or "U1234567",
        starting_cash=100_000.0,
        prices=_broker_prices(config),
    )

    arm_summary = arm_live_mode(config, profile="manual", adapter=live_adapter)

    assert arm_summary.armed is True
    assert arm_summary.current_mode == "live-manual"

    preparation = prepare_live_trading_day(
        config,
        as_of_date=date(2026, 4, 15),
        adapter=live_adapter,
    )

    assert preparation.status == "pending-approval"
    assert preparation.run_id is not None
    assert preparation.approvals

    approval = approve_live_trading_run(
        config,
        run_id=preparation.run_id,
        approve_all=True,
        adapter=live_adapter,
    )

    assert approval.status == "completed"
    assert approval.run_id == preparation.run_id

    snapshot = simulation_status(config)

    assert snapshot["mode_state"]["current_mode"] == "live-manual"
    assert snapshot["latest_run"]["mode"] == "live-manual"
    assert snapshot["latest_approvals"]
    assert snapshot["latest_fills"]


def test_live_autonomous_arming_stays_blocked_without_stricter_gates(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    seed_phase3_research_data(config)
    _configure_broker(config)
    train_model(config, as_of_date=date(2026, 4, 15))
    mark_latest_model_candidate(config)
    seed_safe_paper_days(config, day_count=30)

    paper_adapter = FakeBrokerAdapter(
        environment="paper",
        account_id=config.broker.paper_account_id or "DU1234567",
        starting_cash=100_000.0,
        prices=_broker_prices(config),
    )
    paper_trade_day(
        config,
        as_of_date=date(2026, 4, 15),
        adapter=paper_adapter,
    )

    live_adapter = FakeBrokerAdapter(
        environment="live",
        account_id=config.broker.live_account_id or "U1234567",
        starting_cash=100_000.0,
        prices=_broker_prices(config),
    )
    paper_adapter = FakeBrokerAdapter(
        environment="paper",
        account_id=config.broker.paper_account_id or "DU1234567",
        starting_cash=100_000.0,
        prices=_broker_prices(config),
    )
    enter_paper_mode(
        config, source="test", reason="operator entered paper mode", adapter=paper_adapter
    )
    arm_live_mode(config, profile="manual", adapter=live_adapter)

    autonomous = arm_live_mode(
        config,
        profile="autonomous",
        ack_disable_approvals=False,
        adapter=live_adapter,
    )

    assert autonomous.armed is False
    assert autonomous.status == "blocked"
    assert any(
        check["name"] == "autonomous-safe-days" and check["ok"] is False
        for check in autonomous.metadata["checks"]
    )


def test_live_manual_mode_can_return_directly_to_simulation(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    seed_phase3_research_data(config)
    _configure_broker(config)
    train_model(config, as_of_date=date(2026, 4, 15))
    mark_latest_model_candidate(config)
    seed_safe_paper_days(config, day_count=30)

    live_adapter = FakeBrokerAdapter(
        environment="live",
        account_id=config.broker.live_account_id or "U1234567",
        starting_cash=100_000.0,
        prices=_broker_prices(config),
    )
    paper_adapter = FakeBrokerAdapter(
        environment="paper",
        account_id=config.broker.paper_account_id or "DU1234567",
        starting_cash=100_000.0,
        prices=_broker_prices(config),
    )
    enter_paper_mode(
        config,
        source="test",
        reason="operator entered paper mode",
        adapter=paper_adapter,
    )
    arm_live_mode(config, profile="manual", adapter=live_adapter)

    summary = enter_simulation_mode(config, source="test", reason="operator disarmed live mode")

    assert summary.current_mode == "simulation"
    assert summary.status == "entered"
    assert simulation_status(config)["mode_state"]["current_mode"] == "simulation"


def test_active_freeze_blocks_transition_out_of_frozen_mode(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    seed_phase3_research_data(config)
    _configure_broker(config)

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            freeze = FreezeEvent(
                status="active",
                freeze_type="manual",
                source="test",
                reason="operator freeze",
                details_json="{}",
            )
            session.add(freeze)
            session.commit()

            mode_state = session.get(SystemModeState, 1)
            assert mode_state is not None
            mode_state.current_mode = "frozen"
            mode_state.is_frozen = True
            mode_state.active_freeze_event_id = freeze.id
            mode_state.freeze_reason = freeze.reason
            session.commit()
    finally:
        engine.dispose()

    try:
        enter_simulation_mode(config, source="test", reason="attempt recovery")
    except RuntimeError as exc:
        assert "active freeze is cleared" in str(exc)
    else:
        raise AssertionError("enter_simulation_mode should block while an active freeze exists.")
