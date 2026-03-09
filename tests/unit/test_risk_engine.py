from __future__ import annotations

from stocktradebot.config import AppConfig
from stocktradebot.risk import FillRiskInput, evaluate_posttrade_risk, evaluate_pretrade_risk


def test_pretrade_risk_blocks_daily_loss_breach() -> None:
    config = AppConfig.default()

    evaluation = evaluate_pretrade_risk(
        config,
        mode="simulation",
        active_freeze_reason=None,
        start_nav=96_000.0,
        previous_nav=100_000.0,
        high_water_mark=105_000.0,
        open_incident_count=0,
        kill_switch_active=False,
    )

    assert evaluation.allowed is False
    assert evaluation.freeze is not None
    assert evaluation.freeze.freeze_type == "daily-loss"


def test_posttrade_risk_flags_abnormal_slippage() -> None:
    config = AppConfig.default()

    evaluation = evaluate_posttrade_risk(
        config,
        fills=[
            FillRiskInput(
                symbol="AAPL",
                slippage_bps=90.0,
                expected_spread_bps=10.0,
                fill_status="filled",
            )
        ],
    )

    assert evaluation.allowed is False
    assert evaluation.freeze is not None
    assert evaluation.freeze.freeze_type == "execution-slippage"
