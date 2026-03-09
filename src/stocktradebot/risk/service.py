from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stocktradebot.config import AppConfig


@dataclass(slots=True, frozen=True)
class FillRiskInput:
    symbol: str
    slippage_bps: float
    expected_spread_bps: float
    fill_status: str


@dataclass(slots=True, frozen=True)
class FreezeRecommendation:
    freeze_type: str
    source: str
    reason: str
    details: dict[str, Any]


@dataclass(slots=True, frozen=True)
class RiskEvaluation:
    allowed: bool
    checks: tuple[dict[str, Any], ...]
    freeze: FreezeRecommendation | None = None


def evaluate_pretrade_risk(
    config: AppConfig,
    *,
    mode: str,
    active_freeze_reason: str | None,
    start_nav: float,
    previous_nav: float | None,
    high_water_mark: float | None,
    open_incident_count: int,
    kill_switch_active: bool,
) -> RiskEvaluation:
    checks: list[dict[str, Any]] = []

    if active_freeze_reason is not None:
        checks.append({"name": "active-freeze", "ok": False, "detail": active_freeze_reason})
        return RiskEvaluation(
            allowed=False,
            checks=tuple(checks),
            freeze=FreezeRecommendation(
                freeze_type="existing-freeze",
                source="risk-engine",
                reason=active_freeze_reason,
                details={"mode": mode},
            ),
        )
    checks.append({"name": "active-freeze", "ok": True, "detail": "no active freeze"})

    if config.risk.kill_switch_enabled and kill_switch_active:
        checks.append({"name": "kill-switch", "ok": False, "detail": "manual kill switch active"})
        return RiskEvaluation(
            allowed=False,
            checks=tuple(checks),
            freeze=FreezeRecommendation(
                freeze_type="kill-switch",
                source="risk-engine",
                reason="manual kill switch active",
                details={"mode": mode},
            ),
        )
    checks.append({"name": "kill-switch", "ok": True, "detail": "kill switch clear"})

    if config.risk.freeze_on_open_incidents and open_incident_count > 0:
        checks.append(
            {
                "name": "data-incidents",
                "ok": False,
                "detail": f"{open_incident_count} unresolved data-quality incident(s)",
            }
        )
        return RiskEvaluation(
            allowed=False,
            checks=tuple(checks),
            freeze=FreezeRecommendation(
                freeze_type="data-integrity",
                source="risk-engine",
                reason="unresolved data-quality incidents block trading",
                details={"open_incident_count": open_incident_count},
            ),
        )
    checks.append({"name": "data-incidents", "ok": True, "detail": "no blocking incidents"})

    if previous_nav is not None and previous_nav > 0:
        daily_return = start_nav / previous_nav - 1.0
        daily_loss_ok = daily_return > -config.risk.daily_loss_cap
        checks.append(
            {
                "name": "daily-loss-cap",
                "ok": daily_loss_ok,
                "detail": f"daily return {daily_return:.4f}",
            }
        )
        if not daily_loss_ok:
            return RiskEvaluation(
                allowed=False,
                checks=tuple(checks),
                freeze=FreezeRecommendation(
                    freeze_type="daily-loss",
                    source="risk-engine",
                    reason="daily marked-to-market loss cap breached",
                    details={"daily_return": daily_return, "start_nav": start_nav},
                ),
            )
    else:
        checks.append(
            {
                "name": "daily-loss-cap",
                "ok": True,
                "detail": "no prior NAV available",
            }
        )

    if high_water_mark is not None and high_water_mark > 0:
        drawdown = start_nav / high_water_mark - 1.0
        drawdown_ok = drawdown > -config.risk.drawdown_freeze
        checks.append(
            {
                "name": "drawdown-freeze",
                "ok": drawdown_ok,
                "detail": f"drawdown {drawdown:.4f}",
            }
        )
        if not drawdown_ok:
            return RiskEvaluation(
                allowed=False,
                checks=tuple(checks),
                freeze=FreezeRecommendation(
                    freeze_type="drawdown",
                    source="risk-engine",
                    reason="strategy drawdown freeze breached",
                    details={"drawdown": drawdown, "high_water_mark": high_water_mark},
                ),
            )
    else:
        checks.append(
            {
                "name": "drawdown-freeze",
                "ok": True,
                "detail": "no prior high-water mark available",
            }
        )

    return RiskEvaluation(allowed=True, checks=tuple(checks))


def evaluate_posttrade_risk(
    config: AppConfig,
    *,
    fills: list[FillRiskInput],
) -> RiskEvaluation:
    checks: list[dict[str, Any]] = []
    for fill in fills:
        if fill.fill_status == "unfilled":
            continue
        threshold = max(
            config.risk.abnormal_slippage_bps,
            fill.expected_spread_bps * config.risk.abnormal_slippage_spread_multiple,
        )
        ok = fill.slippage_bps <= threshold
        checks.append(
            {
                "name": f"slippage:{fill.symbol}",
                "ok": ok,
                "detail": (f"slippage {fill.slippage_bps:.2f}bps vs threshold {threshold:.2f}bps"),
            }
        )
        if not ok:
            return RiskEvaluation(
                allowed=False,
                checks=tuple(checks),
                freeze=FreezeRecommendation(
                    freeze_type="execution-slippage",
                    source="execution",
                    reason="abnormal slippage threshold breached",
                    details={
                        "symbol": fill.symbol,
                        "slippage_bps": fill.slippage_bps,
                        "expected_spread_bps": fill.expected_spread_bps,
                        "threshold_bps": threshold,
                    },
                ),
            )
    if not checks:
        checks.append({"name": "slippage", "ok": True, "detail": "no fills recorded"})
    return RiskEvaluation(allowed=True, checks=tuple(checks))
