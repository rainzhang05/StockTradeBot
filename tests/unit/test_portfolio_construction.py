from __future__ import annotations

from stocktradebot.config import AppConfig
from stocktradebot.portfolio import PortfolioCandidate, classify_regime, construct_target_portfolio


def test_classify_regime_handles_expected_buckets() -> None:
    assert classify_regime(regime_return_20d=0.05, regime_vol_20d=0.015) == "risk-on"
    assert classify_regime(regime_return_20d=-0.04, regime_vol_20d=0.02) == "risk-off"
    assert classify_regime(regime_return_20d=0.01, regime_vol_20d=0.022) == "neutral"


def test_construct_target_portfolio_respects_caps_and_turnover() -> None:
    config = AppConfig.default()
    config.portfolio.max_position_weight = 0.10
    config.portfolio.sector_exposure_soft_cap = 0.20
    config.portfolio.turnover_soft_cap = 0.12
    config.portfolio.risk_on_target_positions = 4
    config.portfolio.symbol_sectors = {
        "AAA": "Technology",
        "BBB": "Technology",
        "CCC": "Financials",
        "DDD": "Industrials",
    }
    candidates = [
        PortfolioCandidate(
            symbol="AAA",
            score=0.90,
            price=100.0,
            asset_type="stock",
            realized_vol_20d=0.015,
            dollar_volume_20d=50_000_000.0,
            regime_return_20d=0.05,
            regime_vol_20d=0.015,
        ),
        PortfolioCandidate(
            symbol="BBB",
            score=0.80,
            price=90.0,
            asset_type="stock",
            realized_vol_20d=0.014,
            dollar_volume_20d=45_000_000.0,
            regime_return_20d=0.05,
            regime_vol_20d=0.015,
        ),
        PortfolioCandidate(
            symbol="CCC",
            score=0.70,
            price=80.0,
            asset_type="stock",
            realized_vol_20d=0.013,
            dollar_volume_20d=40_000_000.0,
            regime_return_20d=0.05,
            regime_vol_20d=0.015,
        ),
        PortfolioCandidate(
            symbol="DDD",
            score=0.60,
            price=70.0,
            asset_type="stock",
            realized_vol_20d=0.012,
            dollar_volume_20d=35_000_000.0,
            regime_return_20d=0.05,
            regime_vol_20d=0.015,
        ),
    ]

    result = construct_target_portfolio(
        config,
        candidates=candidates,
        current_weights={"AAA": 0.10},
    )

    assert result.regime == "risk-on"
    assert result.turnover_ratio <= config.portfolio.turnover_soft_cap + 1e-9
    assert result.cash_weight >= 0.0
    assert result.positions
    assert all(
        position.target_weight <= config.portfolio.max_position_weight + 1e-9
        for position in result.positions
    )
    technology_weight = sum(
        position.target_weight for position in result.positions if position.sector == "Technology"
    )
    assert technology_weight <= config.portfolio.sector_exposure_soft_cap + 1e-9
