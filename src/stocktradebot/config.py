from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
CONFIG_FILENAME = "config.json"
DEFAULT_STOOQ_BASE_URL = "https://stooq.com"
DEFAULT_ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co"
DEFAULT_YAHOO_BASE_URL = "https://query1.finance.yahoo.com"
DEFAULT_SEC_COMPANY_FACTS_BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts"
DEFAULT_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_IBKR_GATEWAY_BASE_URL = "https://127.0.0.1:5000/v1/api"
QUALITY_SCOPES = ("research", "promotion")
SUPPORTED_REBALANCE_INTERVAL_DAYS = (1, 3, 5)


def normalize_quality_scope(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in QUALITY_SCOPES:
        supported = ", ".join(QUALITY_SCOPES)
        raise ValueError(f"Unsupported quality scope '{value}'. Expected one of: {supported}.")
    return normalized


def normalize_rebalance_interval_days(value: int) -> int:
    normalized = int(value)
    if normalized not in SUPPORTED_REBALANCE_INTERVAL_DAYS:
        supported = ", ".join(str(item) for item in SUPPORTED_REBALANCE_INTERVAL_DAYS)
        raise ValueError(f"Unsupported rebalance interval '{value}'. Expected one of: {supported}.")
    return normalized


def resolve_app_home(app_home: Path | None = None) -> Path:
    if app_home is not None:
        return app_home.expanduser().resolve()

    env_home = os.getenv("STOCKTRADEBOT_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    return (Path.home() / ".stocktradebot").resolve()


@dataclass(slots=True)
class ValidationThresholds:
    ohlc_relative_tolerance: float = 0.0025
    volume_relative_tolerance: float = 0.05

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> ValidationThresholds:
        defaults = cls()
        if data is None:
            return defaults

        return cls(
            ohlc_relative_tolerance=float(
                data.get("ohlc_relative_tolerance", defaults.ohlc_relative_tolerance)
            ),
            volume_relative_tolerance=float(
                data.get("volume_relative_tolerance", defaults.volume_relative_tolerance)
            ),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "ohlc_relative_tolerance": self.ohlc_relative_tolerance,
            "volume_relative_tolerance": self.volume_relative_tolerance,
        }


@dataclass(slots=True)
class ProviderConfig:
    enabled: bool
    priority: int
    base_url: str
    timeout_seconds: float = 20.0
    api_key_env_var: str | None = None
    rate_limit_per_minute: int | None = None

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any] | None,
        *,
        defaults: ProviderConfig,
    ) -> ProviderConfig:
        if data is None:
            return defaults

        api_key_env_var = data.get("api_key_env_var", defaults.api_key_env_var)
        return cls(
            enabled=bool(data.get("enabled", defaults.enabled)),
            priority=int(data.get("priority", defaults.priority)),
            base_url=str(data.get("base_url", defaults.base_url)),
            timeout_seconds=float(data.get("timeout_seconds", defaults.timeout_seconds)),
            api_key_env_var=None if api_key_env_var is None else str(api_key_env_var),
            rate_limit_per_minute=(
                int(data["rate_limit_per_minute"])
                if data.get("rate_limit_per_minute") is not None
                else defaults.rate_limit_per_minute
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "priority": self.priority,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "api_key_env_var": self.api_key_env_var,
            "rate_limit_per_minute": self.rate_limit_per_minute,
        }


def default_stooq_provider() -> ProviderConfig:
    return ProviderConfig(
        enabled=True,
        priority=1,
        base_url=DEFAULT_STOOQ_BASE_URL,
        timeout_seconds=20.0,
    )


def default_alpha_vantage_provider() -> ProviderConfig:
    return ProviderConfig(
        enabled=False,
        priority=2,
        base_url=DEFAULT_ALPHA_VANTAGE_BASE_URL,
        timeout_seconds=20.0,
        api_key_env_var="ALPHAVANTAGE_API_KEY",
        rate_limit_per_minute=5,
    )


def default_yahoo_provider() -> ProviderConfig:
    return ProviderConfig(
        enabled=True,
        priority=3,
        base_url=DEFAULT_YAHOO_BASE_URL,
        timeout_seconds=20.0,
    )


@dataclass(slots=True)
class DataProvidersConfig:
    primary_provider: str = "stooq"
    secondary_provider: str | None = None
    research_fallback_providers: list[str] = field(default_factory=lambda: ["yahoo"])
    validation: ValidationThresholds = field(default_factory=ValidationThresholds)
    stooq: ProviderConfig = field(default_factory=default_stooq_provider)
    alpha_vantage: ProviderConfig = field(default_factory=default_alpha_vantage_provider)
    yahoo: ProviderConfig = field(default_factory=default_yahoo_provider)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> DataProvidersConfig:
        defaults = cls()
        if data is None:
            return defaults

        secondary_provider = data.get("secondary_provider", defaults.secondary_provider)
        return cls(
            primary_provider=str(data.get("primary_provider", defaults.primary_provider)),
            secondary_provider=None if secondary_provider is None else str(secondary_provider),
            research_fallback_providers=[
                str(provider_name)
                for provider_name in data.get(
                    "research_fallback_providers",
                    defaults.research_fallback_providers,
                )
            ],
            validation=ValidationThresholds.from_dict(data.get("validation")),
            stooq=ProviderConfig.from_dict(data.get("stooq"), defaults=defaults.stooq),
            alpha_vantage=ProviderConfig.from_dict(
                data.get("alpha_vantage"),
                defaults=defaults.alpha_vantage,
            ),
            yahoo=ProviderConfig.from_dict(data.get("yahoo"), defaults=defaults.yahoo),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_provider": self.primary_provider,
            "secondary_provider": self.secondary_provider,
            "research_fallback_providers": self.research_fallback_providers,
            "validation": self.validation.to_dict(),
            "stooq": self.stooq.to_dict(),
            "alpha_vantage": self.alpha_vantage.to_dict(),
            "yahoo": self.yahoo.to_dict(),
        }

    def provider_map(self) -> dict[str, ProviderConfig]:
        return {
            "stooq": self.stooq,
            "alpha_vantage": self.alpha_vantage,
            "yahoo": self.yahoo,
        }


@dataclass(slots=True)
class UniverseConfig:
    max_stocks: int = 300
    min_price: float = 5.0
    min_history_days: int = 20
    liquidity_lookback_days: int = 20
    monthly_refresh_day: int = 1
    stock_candidates: list[str] = field(default_factory=list)
    curated_etfs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> UniverseConfig:
        defaults = cls()
        if data is None:
            return defaults

        return cls(
            max_stocks=int(data.get("max_stocks", defaults.max_stocks)),
            min_price=float(data.get("min_price", defaults.min_price)),
            min_history_days=int(data.get("min_history_days", defaults.min_history_days)),
            liquidity_lookback_days=int(
                data.get("liquidity_lookback_days", defaults.liquidity_lookback_days)
            ),
            monthly_refresh_day=int(data.get("monthly_refresh_day", defaults.monthly_refresh_day)),
            stock_candidates=[str(symbol) for symbol in data.get("stock_candidates", [])],
            curated_etfs=[str(symbol) for symbol in data.get("curated_etfs", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_stocks": self.max_stocks,
            "min_price": self.min_price,
            "min_history_days": self.min_history_days,
            "liquidity_lookback_days": self.liquidity_lookback_days,
            "monthly_refresh_day": self.monthly_refresh_day,
            "stock_candidates": self.stock_candidates,
            "curated_etfs": self.curated_etfs,
        }


@dataclass(slots=True)
class FundamentalsProviderConfig:
    enabled: bool = False
    base_url: str = DEFAULT_SEC_COMPANY_FACTS_BASE_URL
    ticker_mapping_url: str = DEFAULT_SEC_TICKERS_URL
    timeout_seconds: float = 20.0
    user_agent_env_var: str = "SEC_USER_AGENT"
    user_agent: str | None = None
    symbol_to_cik: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> FundamentalsProviderConfig:
        defaults = cls()
        if data is None:
            return defaults

        user_agent = data.get("user_agent", defaults.user_agent)
        symbol_to_cik = {
            str(symbol).upper(): str(cik).zfill(10)
            for symbol, cik in data.get("symbol_to_cik", {}).items()
        }
        return cls(
            enabled=bool(data.get("enabled", defaults.enabled)),
            base_url=str(data.get("base_url", defaults.base_url)),
            ticker_mapping_url=str(data.get("ticker_mapping_url", defaults.ticker_mapping_url)),
            timeout_seconds=float(data.get("timeout_seconds", defaults.timeout_seconds)),
            user_agent_env_var=str(data.get("user_agent_env_var", defaults.user_agent_env_var)),
            user_agent=None if user_agent is None else str(user_agent),
            symbol_to_cik=symbol_to_cik,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "ticker_mapping_url": self.ticker_mapping_url,
            "timeout_seconds": self.timeout_seconds,
            "user_agent_env_var": self.user_agent_env_var,
            "user_agent": self.user_agent,
            "symbol_to_cik": self.symbol_to_cik,
        }

    def resolved_user_agent(self) -> str | None:
        env_user_agent = os.getenv(self.user_agent_env_var)
        if env_user_agent:
            return env_user_agent
        return self.user_agent


@dataclass(slots=True)
class ModelTrainingConfig:
    quality_scope: str = "research"
    feature_set_version: str = "daily-core-v1"
    label_version: str = "forward-return-v1"
    model_family: str = "linear-correlation-v1"
    target_label_name: str = "ranking_label_5d"
    benchmark_symbol: str = "SPY"
    min_feature_history_days: int = 60
    min_label_history_days: int = 10
    dataset_lookback_days: int = 400
    training_window_days: int = 180
    validation_window_days: int = 40
    walk_forward_step_days: int = 20
    min_training_rows: int = 200
    min_validation_folds: int = 2
    target_portfolio_size: int = 10
    rebalance_interval_days: int = 5
    initial_capital: float = 100_000.0
    commission_bps: float = 1.0
    slippage_bps: float = 5.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> ModelTrainingConfig:
        defaults = cls()
        if data is None:
            return defaults

        return cls(
            quality_scope=normalize_quality_scope(
                str(data.get("quality_scope", defaults.quality_scope))
            ),
            feature_set_version=str(data.get("feature_set_version", defaults.feature_set_version)),
            label_version=str(data.get("label_version", defaults.label_version)),
            model_family=str(data.get("model_family", defaults.model_family)),
            target_label_name=str(data.get("target_label_name", defaults.target_label_name)),
            benchmark_symbol=str(data.get("benchmark_symbol", defaults.benchmark_symbol)).upper(),
            min_feature_history_days=int(
                data.get("min_feature_history_days", defaults.min_feature_history_days)
            ),
            min_label_history_days=int(
                data.get("min_label_history_days", defaults.min_label_history_days)
            ),
            dataset_lookback_days=int(
                data.get("dataset_lookback_days", defaults.dataset_lookback_days)
            ),
            training_window_days=int(
                data.get("training_window_days", defaults.training_window_days)
            ),
            validation_window_days=int(
                data.get("validation_window_days", defaults.validation_window_days)
            ),
            walk_forward_step_days=int(
                data.get("walk_forward_step_days", defaults.walk_forward_step_days)
            ),
            min_training_rows=int(data.get("min_training_rows", defaults.min_training_rows)),
            min_validation_folds=int(
                data.get("min_validation_folds", defaults.min_validation_folds)
            ),
            target_portfolio_size=int(
                data.get("target_portfolio_size", defaults.target_portfolio_size)
            ),
            rebalance_interval_days=normalize_rebalance_interval_days(
                int(data.get("rebalance_interval_days", defaults.rebalance_interval_days))
            ),
            initial_capital=float(data.get("initial_capital", defaults.initial_capital)),
            commission_bps=float(data.get("commission_bps", defaults.commission_bps)),
            slippage_bps=float(data.get("slippage_bps", defaults.slippage_bps)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality_scope": self.quality_scope,
            "feature_set_version": self.feature_set_version,
            "label_version": self.label_version,
            "model_family": self.model_family,
            "target_label_name": self.target_label_name,
            "benchmark_symbol": self.benchmark_symbol,
            "min_feature_history_days": self.min_feature_history_days,
            "min_label_history_days": self.min_label_history_days,
            "dataset_lookback_days": self.dataset_lookback_days,
            "training_window_days": self.training_window_days,
            "validation_window_days": self.validation_window_days,
            "walk_forward_step_days": self.walk_forward_step_days,
            "min_training_rows": self.min_training_rows,
            "min_validation_folds": self.min_validation_folds,
            "target_portfolio_size": self.target_portfolio_size,
            "rebalance_interval_days": self.rebalance_interval_days,
            "initial_capital": self.initial_capital,
            "commission_bps": self.commission_bps,
            "slippage_bps": self.slippage_bps,
        }


@dataclass(slots=True)
class IntradayResearchConfig:
    enabled_frequencies: list[str] = field(default_factory=lambda: ["15min", "1h"])
    primary_provider: str = "alpha_vantage"
    secondary_provider: str | None = None
    minimum_session_coverage: float = 0.95
    minimum_verified_ratio: float = 0.95

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> IntradayResearchConfig:
        defaults = cls()
        if data is None:
            return defaults

        secondary_provider = data.get("secondary_provider", defaults.secondary_provider)
        return cls(
            enabled_frequencies=[
                str(value)
                for value in data.get("enabled_frequencies", defaults.enabled_frequencies)
            ],
            primary_provider=str(data.get("primary_provider", defaults.primary_provider)),
            secondary_provider=(None if secondary_provider is None else str(secondary_provider)),
            minimum_session_coverage=float(
                data.get("minimum_session_coverage", defaults.minimum_session_coverage)
            ),
            minimum_verified_ratio=float(
                data.get("minimum_verified_ratio", defaults.minimum_verified_ratio)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled_frequencies": self.enabled_frequencies,
            "primary_provider": self.primary_provider,
            "secondary_provider": self.secondary_provider,
            "minimum_session_coverage": self.minimum_session_coverage,
            "minimum_verified_ratio": self.minimum_verified_ratio,
        }


@dataclass(slots=True)
class PortfolioConfig:
    max_position_weight: float = 0.10
    sector_exposure_soft_cap: float = 0.30
    turnover_soft_cap: float = 0.25
    turnover_penalty: float = 0.20
    minimum_conviction_score: float = 0.0
    risk_on_target_positions: int = 10
    neutral_target_positions: int = 6
    risk_off_target_positions: int = 3
    risk_on_gross_exposure: float = 1.0
    neutral_gross_exposure: float = 0.70
    risk_off_gross_exposure: float = 0.35
    risk_off_defensive_allocation: float = 0.20
    defensive_etf_symbol: str | None = "IEF"
    symbol_sectors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> PortfolioConfig:
        defaults = cls()
        if data is None:
            return defaults

        defensive_etf_symbol = data.get("defensive_etf_symbol", defaults.defensive_etf_symbol)
        normalized_defensive_symbol: str | None
        if defensive_etf_symbol is None:
            normalized_defensive_symbol = None
        else:
            stripped = str(defensive_etf_symbol).strip()
            normalized_defensive_symbol = (
                None if stripped.lower() == "none" or not stripped else stripped.upper()
            )
        symbol_sectors = {
            str(symbol).upper(): str(sector)
            for symbol, sector in data.get("symbol_sectors", {}).items()
        }
        return cls(
            max_position_weight=float(
                data.get("max_position_weight", defaults.max_position_weight)
            ),
            sector_exposure_soft_cap=float(
                data.get("sector_exposure_soft_cap", defaults.sector_exposure_soft_cap)
            ),
            turnover_soft_cap=float(data.get("turnover_soft_cap", defaults.turnover_soft_cap)),
            turnover_penalty=float(data.get("turnover_penalty", defaults.turnover_penalty)),
            minimum_conviction_score=float(
                data.get("minimum_conviction_score", defaults.minimum_conviction_score)
            ),
            risk_on_target_positions=int(
                data.get("risk_on_target_positions", defaults.risk_on_target_positions)
            ),
            neutral_target_positions=int(
                data.get("neutral_target_positions", defaults.neutral_target_positions)
            ),
            risk_off_target_positions=int(
                data.get("risk_off_target_positions", defaults.risk_off_target_positions)
            ),
            risk_on_gross_exposure=float(
                data.get("risk_on_gross_exposure", defaults.risk_on_gross_exposure)
            ),
            neutral_gross_exposure=float(
                data.get("neutral_gross_exposure", defaults.neutral_gross_exposure)
            ),
            risk_off_gross_exposure=float(
                data.get("risk_off_gross_exposure", defaults.risk_off_gross_exposure)
            ),
            risk_off_defensive_allocation=float(
                data.get(
                    "risk_off_defensive_allocation",
                    defaults.risk_off_defensive_allocation,
                )
            ),
            defensive_etf_symbol=normalized_defensive_symbol,
            symbol_sectors=symbol_sectors,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_position_weight": self.max_position_weight,
            "sector_exposure_soft_cap": self.sector_exposure_soft_cap,
            "turnover_soft_cap": self.turnover_soft_cap,
            "turnover_penalty": self.turnover_penalty,
            "minimum_conviction_score": self.minimum_conviction_score,
            "risk_on_target_positions": self.risk_on_target_positions,
            "neutral_target_positions": self.neutral_target_positions,
            "risk_off_target_positions": self.risk_off_target_positions,
            "risk_on_gross_exposure": self.risk_on_gross_exposure,
            "neutral_gross_exposure": self.neutral_gross_exposure,
            "risk_off_gross_exposure": self.risk_off_gross_exposure,
            "risk_off_defensive_allocation": self.risk_off_defensive_allocation,
            "defensive_etf_symbol": self.defensive_etf_symbol,
            "symbol_sectors": self.symbol_sectors,
        }


@dataclass(slots=True)
class RiskConfig:
    daily_loss_cap: float = 0.03
    drawdown_freeze: float = 0.20
    abnormal_slippage_bps: float = 50.0
    abnormal_slippage_spread_multiple: float = 3.0
    freeze_on_open_incidents: bool = True
    kill_switch_enabled: bool = True
    allow_research_models_in_simulation: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> RiskConfig:
        defaults = cls()
        if data is None:
            return defaults

        return cls(
            daily_loss_cap=float(data.get("daily_loss_cap", defaults.daily_loss_cap)),
            drawdown_freeze=float(data.get("drawdown_freeze", defaults.drawdown_freeze)),
            abnormal_slippage_bps=float(
                data.get("abnormal_slippage_bps", defaults.abnormal_slippage_bps)
            ),
            abnormal_slippage_spread_multiple=float(
                data.get(
                    "abnormal_slippage_spread_multiple",
                    defaults.abnormal_slippage_spread_multiple,
                )
            ),
            freeze_on_open_incidents=bool(
                data.get("freeze_on_open_incidents", defaults.freeze_on_open_incidents)
            ),
            kill_switch_enabled=bool(data.get("kill_switch_enabled", defaults.kill_switch_enabled)),
            allow_research_models_in_simulation=bool(
                data.get(
                    "allow_research_models_in_simulation",
                    defaults.allow_research_models_in_simulation,
                )
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_loss_cap": self.daily_loss_cap,
            "drawdown_freeze": self.drawdown_freeze,
            "abnormal_slippage_bps": self.abnormal_slippage_bps,
            "abnormal_slippage_spread_multiple": self.abnormal_slippage_spread_multiple,
            "freeze_on_open_incidents": self.freeze_on_open_incidents,
            "kill_switch_enabled": self.kill_switch_enabled,
            "allow_research_models_in_simulation": self.allow_research_models_in_simulation,
        }


@dataclass(slots=True)
class ExecutionConfig:
    default_mode: str = "simulation"
    live_profile: str = "manual"
    commission_bps: float = 1.0
    base_slippage_bps: float = 5.0
    max_participation_rate: float = 0.05
    stale_data_max_age_days: int = 3
    partial_fill_enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> ExecutionConfig:
        defaults = cls()
        if data is None:
            return defaults

        return cls(
            default_mode=str(data.get("default_mode", defaults.default_mode)),
            live_profile=str(data.get("live_profile", defaults.live_profile)),
            commission_bps=float(data.get("commission_bps", defaults.commission_bps)),
            base_slippage_bps=float(data.get("base_slippage_bps", defaults.base_slippage_bps)),
            max_participation_rate=float(
                data.get("max_participation_rate", defaults.max_participation_rate)
            ),
            stale_data_max_age_days=int(
                data.get("stale_data_max_age_days", defaults.stale_data_max_age_days)
            ),
            partial_fill_enabled=bool(
                data.get("partial_fill_enabled", defaults.partial_fill_enabled)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_mode": self.default_mode,
            "live_profile": self.live_profile,
            "commission_bps": self.commission_bps,
            "base_slippage_bps": self.base_slippage_bps,
            "max_participation_rate": self.max_participation_rate,
            "stale_data_max_age_days": self.stale_data_max_age_days,
            "partial_fill_enabled": self.partial_fill_enabled,
        }


@dataclass(slots=True)
class BrokerGatewayConfig:
    base_url: str = DEFAULT_IBKR_GATEWAY_BASE_URL
    timeout_seconds: float = 15.0
    verify_tls: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> BrokerGatewayConfig:
        defaults = cls()
        if data is None:
            return defaults

        return cls(
            base_url=str(data.get("base_url", defaults.base_url)),
            timeout_seconds=float(data.get("timeout_seconds", defaults.timeout_seconds)),
            verify_tls=bool(data.get("verify_tls", defaults.verify_tls)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "verify_tls": self.verify_tls,
        }


@dataclass(slots=True)
class BrokerConfig:
    enabled: bool = False
    provider: str = "ibkr-client-portal"
    operator_name: str = "local-operator"
    default_exchange: str = "SMART"
    default_currency: str = "USD"
    paper_account_id: str | None = None
    live_account_id: str | None = None
    gateway: BrokerGatewayConfig = field(default_factory=BrokerGatewayConfig)
    live_manual_min_paper_days: int = 30
    live_autonomous_min_safe_days: int = 60
    max_open_incidents_for_autonomous: int = 0
    require_live_autonomous_ack: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> BrokerConfig:
        defaults = cls()
        if data is None:
            return defaults

        paper_account_id = data.get("paper_account_id", defaults.paper_account_id)
        live_account_id = data.get("live_account_id", defaults.live_account_id)
        return cls(
            enabled=bool(data.get("enabled", defaults.enabled)),
            provider=str(data.get("provider", defaults.provider)),
            operator_name=str(data.get("operator_name", defaults.operator_name)),
            default_exchange=str(data.get("default_exchange", defaults.default_exchange)),
            default_currency=str(data.get("default_currency", defaults.default_currency)),
            paper_account_id=(
                None if paper_account_id is None else str(paper_account_id).strip() or None
            ),
            live_account_id=None
            if live_account_id is None
            else str(live_account_id).strip() or None,
            gateway=BrokerGatewayConfig.from_dict(data.get("gateway")),
            live_manual_min_paper_days=int(
                data.get("live_manual_min_paper_days", defaults.live_manual_min_paper_days)
            ),
            live_autonomous_min_safe_days=int(
                data.get(
                    "live_autonomous_min_safe_days",
                    defaults.live_autonomous_min_safe_days,
                )
            ),
            max_open_incidents_for_autonomous=int(
                data.get(
                    "max_open_incidents_for_autonomous",
                    defaults.max_open_incidents_for_autonomous,
                )
            ),
            require_live_autonomous_ack=bool(
                data.get(
                    "require_live_autonomous_ack",
                    defaults.require_live_autonomous_ack,
                )
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "operator_name": self.operator_name,
            "default_exchange": self.default_exchange,
            "default_currency": self.default_currency,
            "paper_account_id": self.paper_account_id,
            "live_account_id": self.live_account_id,
            "gateway": self.gateway.to_dict(),
            "live_manual_min_paper_days": self.live_manual_min_paper_days,
            "live_autonomous_min_safe_days": self.live_autonomous_min_safe_days,
            "max_open_incidents_for_autonomous": self.max_open_incidents_for_autonomous,
            "require_live_autonomous_ack": self.require_live_autonomous_ack,
        }

    def account_id_for_mode(self, mode: str) -> str | None:
        if mode == "paper":
            return self.paper_account_id
        if mode in {"live-manual", "live-autonomous"}:
            return self.live_account_id
        return None


@dataclass(slots=True)
class AppConfig:
    app_home: Path
    config_path: Path
    database_path: Path
    artifacts_dir: Path
    logs_dir: Path
    api_host: str = DEFAULT_HOST
    api_port: int = DEFAULT_PORT
    open_browser_on_launch: bool = True
    timezone: str = "local"
    data_providers: DataProvidersConfig = field(default_factory=DataProvidersConfig)
    fundamentals_provider: FundamentalsProviderConfig = field(
        default_factory=FundamentalsProviderConfig
    )
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    model_training: ModelTrainingConfig = field(default_factory=ModelTrainingConfig)
    intraday_research: IntradayResearchConfig = field(default_factory=IntradayResearchConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)

    @classmethod
    def default(cls, app_home: Path | None = None) -> AppConfig:
        resolved_home = resolve_app_home(app_home)
        return cls(
            app_home=resolved_home,
            config_path=resolved_home / CONFIG_FILENAME,
            database_path=resolved_home / "runtime" / "stocktradebot.sqlite3",
            artifacts_dir=resolved_home / "artifacts",
            logs_dir=resolved_home / "logs",
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], app_home: Path | None = None) -> AppConfig:
        defaults = cls.default(app_home)
        return cls(
            app_home=defaults.app_home,
            config_path=defaults.config_path,
            database_path=Path(data.get("database_path", defaults.database_path)).expanduser(),
            artifacts_dir=Path(data.get("artifacts_dir", defaults.artifacts_dir)).expanduser(),
            logs_dir=Path(data.get("logs_dir", defaults.logs_dir)).expanduser(),
            api_host=str(data.get("api_host", defaults.api_host)),
            api_port=int(data.get("api_port", defaults.api_port)),
            open_browser_on_launch=bool(
                data.get("open_browser_on_launch", defaults.open_browser_on_launch)
            ),
            timezone=str(data.get("timezone", defaults.timezone)),
            data_providers=DataProvidersConfig.from_dict(data.get("data_providers")),
            fundamentals_provider=FundamentalsProviderConfig.from_dict(
                data.get("fundamentals_provider")
            ),
            universe=UniverseConfig.from_dict(data.get("universe")),
            model_training=ModelTrainingConfig.from_dict(data.get("model_training")),
            intraday_research=IntradayResearchConfig.from_dict(data.get("intraday_research")),
            portfolio=PortfolioConfig.from_dict(data.get("portfolio")),
            risk=RiskConfig.from_dict(data.get("risk")),
            execution=ExecutionConfig.from_dict(data.get("execution")),
            broker=BrokerConfig.from_dict(data.get("broker")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": str(self.database_path),
            "artifacts_dir": str(self.artifacts_dir),
            "logs_dir": str(self.logs_dir),
            "api_host": self.api_host,
            "api_port": self.api_port,
            "open_browser_on_launch": self.open_browser_on_launch,
            "timezone": self.timezone,
            "data_providers": self.data_providers.to_dict(),
            "fundamentals_provider": self.fundamentals_provider.to_dict(),
            "universe": self.universe.to_dict(),
            "model_training": self.model_training.to_dict(),
            "intraday_research": self.intraday_research.to_dict(),
            "portfolio": self.portfolio.to_dict(),
            "risk": self.risk.to_dict(),
            "execution": self.execution.to_dict(),
            "broker": self.broker.to_dict(),
        }

    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path}"

    @property
    def raw_payload_dir(self) -> Path:
        return self.artifacts_dir / "raw-provider-payloads"

    @property
    def dataset_artifacts_dir(self) -> Path:
        return self.artifacts_dir / "datasets"

    @property
    def model_artifacts_dir(self) -> Path:
        return self.artifacts_dir / "models"

    @property
    def report_artifacts_dir(self) -> Path:
        return self.artifacts_dir / "reports"

    def ensure_runtime_dirs(self) -> None:
        self.app_home.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.raw_payload_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.model_artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.report_artifacts_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.ensure_runtime_dirs()
        self.config_path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")


def load_config(app_home: Path | None = None) -> AppConfig:
    defaults = AppConfig.default(app_home)
    if not defaults.config_path.exists():
        return defaults

    data = json.loads(defaults.config_path.read_text(encoding="utf-8"))
    return AppConfig.from_dict(data, app_home=defaults.app_home)


def _validate_config_patch_keys(
    base: dict[str, Any],
    patch: dict[str, Any],
    *,
    prefix: str = "",
) -> None:
    for key, value in patch.items():
        if key not in base:
            raise KeyError(f"Unsupported config field: {prefix}{key}")
        base_value = base[key]
        if isinstance(value, dict):
            if not isinstance(base_value, dict):
                raise KeyError(f"Unsupported nested config field: {prefix}{key}")
            _validate_config_patch_keys(base_value, value, prefix=f"{prefix}{key}.")


def _merge_config_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_config_dict(existing, value)
        else:
            merged[key] = value
    return merged


def apply_config_patch(config: AppConfig, patch: dict[str, Any]) -> AppConfig:
    current = config.to_dict()
    _validate_config_patch_keys(current, patch)
    merged = _merge_config_dict(current, patch)
    updated = AppConfig.from_dict(merged, app_home=config.app_home)
    updated.save()
    return updated


def initialize_config(app_home: Path | None = None, *, overwrite: bool = False) -> AppConfig:
    config = AppConfig.default(app_home)
    if config.config_path.exists() and not overwrite:
        return load_config(app_home)

    config.save()
    return config
