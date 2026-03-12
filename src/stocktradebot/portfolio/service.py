from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from stocktradebot.config import AppConfig
from stocktradebot.data.universe import resolve_symbol_sectors


@dataclass(slots=True, frozen=True)
class PortfolioCandidate:
    symbol: str
    score: float
    price: float
    asset_type: str
    realized_vol_20d: float | None
    dollar_volume_20d: float | None
    regime_return_20d: float | None
    regime_vol_20d: float | None


@dataclass(slots=True, frozen=True)
class TargetPortfolioPosition:
    symbol: str
    target_weight: float
    score: float
    sector: str
    asset_type: str
    metadata: dict[str, Any]


@dataclass(slots=True, frozen=True)
class PortfolioConstructionResult:
    regime: str
    target_gross_exposure: float
    cash_weight: float
    turnover_ratio: float
    positions: tuple[TargetPortfolioPosition, ...]
    diagnostics: dict[str, Any]


def classify_regime(
    *,
    regime_return_20d: float | None,
    regime_vol_20d: float | None,
) -> str:
    if regime_return_20d is None or regime_vol_20d is None:
        return "unknown"
    if regime_return_20d <= -0.03 or regime_vol_20d >= 0.03:
        return "risk-off"
    if regime_return_20d >= 0.03 and regime_vol_20d <= 0.02:
        return "risk-on"
    return "neutral"


def _regime_targets(config: AppConfig, regime: str) -> tuple[int, float]:
    if regime == "risk-on":
        return (
            config.portfolio.risk_on_target_positions,
            config.portfolio.risk_on_gross_exposure,
        )
    if regime == "risk-off":
        return (
            config.portfolio.risk_off_target_positions,
            config.portfolio.risk_off_gross_exposure,
        )
    return (
        config.portfolio.neutral_target_positions,
        config.portfolio.neutral_gross_exposure,
    )


def _sector_for_symbol(config: AppConfig, symbol: str) -> str:
    return resolve_symbol_sectors(config).get(symbol, f"UNMAPPED:{symbol}")


def _allocate_with_caps(
    *,
    raw_weights: dict[str, float],
    sectors: dict[str, str],
    target_exposure: float,
    max_position_weight: float,
    sector_cap: float,
) -> dict[str, float]:
    weights = {symbol: 0.0 for symbol in raw_weights}
    sector_allocations: dict[str, float] = defaultdict(float)
    remaining = {
        symbol: raw_weight for symbol, raw_weight in raw_weights.items() if raw_weight > 0.0
    }
    remaining_exposure = target_exposure

    while remaining and remaining_exposure > 1e-9:
        total_raw = sum(remaining.values())
        if total_raw <= 0:
            break

        capped_symbols: list[str] = []
        for symbol, raw_weight in remaining.items():
            proposed = remaining_exposure * raw_weight / total_raw
            sector = sectors[symbol]
            position_room = max_position_weight - weights[symbol]
            sector_room = sector_cap - sector_allocations[sector]
            room = min(position_room, sector_room)
            if room <= 1e-9:
                capped_symbols.append(symbol)
                continue
            if proposed >= room - 1e-9:
                weights[symbol] += room
                sector_allocations[sector] += room
                remaining_exposure -= room
                capped_symbols.append(symbol)

        if capped_symbols:
            for symbol in capped_symbols:
                remaining.pop(symbol, None)
            continue

        for symbol, raw_weight in remaining.items():
            allocation = remaining_exposure * raw_weight / total_raw
            weights[symbol] += allocation
            sector_allocations[sectors[symbol]] += allocation
        remaining_exposure = 0.0

    return {symbol: weight for symbol, weight in weights.items() if weight > 1e-9}


def _apply_turnover_soft_cap(
    *,
    desired_weights: dict[str, float],
    current_weights: dict[str, float],
    turnover_soft_cap: float,
) -> tuple[dict[str, float], float]:
    all_symbols = set(desired_weights) | set(current_weights)
    turnover = (
        sum(
            abs(desired_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0))
            for symbol in all_symbols
        )
        / 2.0
    )
    if turnover <= turnover_soft_cap or turnover <= 1e-9:
        return desired_weights, turnover

    scale = turnover_soft_cap / turnover
    blended: dict[str, float] = {}
    for symbol in all_symbols:
        current_weight = current_weights.get(symbol, 0.0)
        desired_weight = desired_weights.get(symbol, 0.0)
        new_weight = current_weight + (desired_weight - current_weight) * scale
        if new_weight > 1e-9:
            blended[symbol] = new_weight
    blended_turnover = (
        sum(
            abs(blended.get(symbol, 0.0) - current_weights.get(symbol, 0.0))
            for symbol in all_symbols
        )
        / 2.0
    )
    return blended, blended_turnover


def construct_target_portfolio(
    config: AppConfig,
    *,
    candidates: list[PortfolioCandidate],
    current_weights: dict[str, float],
) -> PortfolioConstructionResult:
    if not candidates:
        return PortfolioConstructionResult(
            regime="unknown",
            target_gross_exposure=0.0,
            cash_weight=1.0,
            turnover_ratio=0.0,
            positions=(),
            diagnostics={"reason": "no_candidates"},
        )

    regime = classify_regime(
        regime_return_20d=candidates[0].regime_return_20d,
        regime_vol_20d=candidates[0].regime_vol_20d,
    )
    desired_count, target_exposure = _regime_targets(config, regime)
    scored_candidates = sorted(
        candidates,
        key=lambda candidate: (
            candidate.score
            + current_weights.get(candidate.symbol, 0.0) * config.portfolio.turnover_penalty,
            candidate.symbol,
        ),
        reverse=True,
    )

    selected: list[PortfolioCandidate] = []
    for candidate in scored_candidates:
        is_existing = current_weights.get(candidate.symbol, 0.0) > 0.0
        if candidate.score < config.portfolio.minimum_conviction_score and not is_existing:
            continue
        selected.append(candidate)
        if len(selected) >= desired_count:
            break

    if not selected:
        return PortfolioConstructionResult(
            regime=regime,
            target_gross_exposure=0.0,
            cash_weight=1.0,
            turnover_ratio=0.0,
            positions=(),
            diagnostics={"reason": "no_selected_candidates"},
        )

    defensive_symbol = config.portfolio.defensive_etf_symbol
    defensive_weight = 0.0
    if regime == "risk-off" and defensive_symbol:
        defensive_weight = min(
            config.portfolio.risk_off_defensive_allocation,
            target_exposure,
            config.portfolio.max_position_weight,
        )

    raw_weights = {
        candidate.symbol: max(candidate.score - config.portfolio.minimum_conviction_score, 1e-6)
        for candidate in selected
    }
    sectors = {
        candidate.symbol: _sector_for_symbol(config, candidate.symbol) for candidate in selected
    }
    stock_exposure = max(target_exposure - defensive_weight, 0.0)
    desired_weights = _allocate_with_caps(
        raw_weights=raw_weights,
        sectors=sectors,
        target_exposure=stock_exposure,
        max_position_weight=config.portfolio.max_position_weight,
        sector_cap=config.portfolio.sector_exposure_soft_cap,
    )

    defensive_candidate = next(
        (candidate for candidate in candidates if candidate.symbol == defensive_symbol),
        None,
    )
    if defensive_weight > 0.0 and defensive_candidate is not None and defensive_symbol is not None:
        desired_weights[defensive_symbol] = defensive_weight
        sectors[defensive_symbol] = _sector_for_symbol(config, defensive_symbol)
        if all(candidate.symbol != defensive_symbol for candidate in selected):
            selected.append(defensive_candidate)

    capped_weights, turnover_ratio = _apply_turnover_soft_cap(
        desired_weights=desired_weights,
        current_weights=current_weights,
        turnover_soft_cap=config.portfolio.turnover_soft_cap,
    )
    position_map = {candidate.symbol: candidate for candidate in selected}
    positions = tuple(
        sorted(
            (
                TargetPortfolioPosition(
                    symbol=symbol,
                    target_weight=weight,
                    score=position_map[symbol].score,
                    sector=_sector_for_symbol(config, symbol),
                    asset_type=position_map[symbol].asset_type,
                    metadata={
                        "price": position_map[symbol].price,
                        "realized_vol_20d": position_map[symbol].realized_vol_20d,
                        "dollar_volume_20d": position_map[symbol].dollar_volume_20d,
                    },
                )
                for symbol, weight in capped_weights.items()
                if symbol in position_map
            ),
            key=lambda position: (position.target_weight, position.symbol),
            reverse=True,
        )
    )
    gross_exposure = sum(position.target_weight for position in positions)
    return PortfolioConstructionResult(
        regime=regime,
        target_gross_exposure=gross_exposure,
        cash_weight=max(0.0, 1.0 - gross_exposure),
        turnover_ratio=turnover_ratio,
        positions=positions,
        diagnostics={
            "selected_symbols": [candidate.symbol for candidate in selected],
            "requested_exposure": target_exposure,
            "desired_position_count": desired_count,
        },
    )
